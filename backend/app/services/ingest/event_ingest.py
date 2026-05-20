"""Procesamiento compartido de eventos (panel autenticado + widget publico)."""

from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import EventIngest
from app.infrastructure.database.models import AttackType, Stream, StreamEvent
from app.services.ai.service import AIService
from app.services.correlation.service import CorrelationService
from app.services.dashboard.metrics import get_tenant_stream_ids
from app.core.config import get_settings
from app.services.detection.engine import BotDetectionEngine, EventBatch
from app.services.detection.realtime_viewbot import get_realtime_viewbot_engine
from app.services.detection.realtime_actions import apply_viewbot_assessment
from app.services.mitigation.enforcement import is_event_blocked
from app.services.mitigation.service import MitigationService
from app.services.realtime.notify import push_dashboard_realtime
from app.services.reputation.service import ReputationService
from app.services.streams.helpers import stream_auto_mitigate, stream_monitor_mode
from app.services.viewers.session import ViewerSessionService

detection_engine = BotDetectionEngine()
ai_service = AIService()
ingest_settings = get_settings()


async def process_stream_event(
    db: AsyncSession,
    stream: Stream,
    tenant_id: UUID,
    event: EventIngest,
    *,
    source: str = "api",
) -> Dict[str, Any]:
    correlation = CorrelationService(db)
    reputation_svc = ReputationService(db)
    mitigation = MitigationService(db)

    blocked = await is_event_blocked(
        mitigation,
        stream.id,
        platform_user_id=event.platform_user_id,
        platform_username=event.platform_username,
        ip_address=event.ip_address,
        fingerprint_hash=event.fingerprint_hash,
    )
    if blocked:
        return {
            "event_id": None,
            "risk_score": 0.0,
            "attack_created": False,
            "blocked": True,
            "ban_type": blocked.get("ban_type"),
        }

    ip_data: Dict[str, Any] = {}
    if event.ip_address:
        ip_data = await reputation_svc.enrich_ip(event.ip_address)

    fp_risk = float(event.metadata.get("fingerprint_risk", 0.0)) if event.fingerprint_hash else 0.0

    ip_result = detection_engine.analyze_ip(ip_data) if ip_data else None
    pattern_score = 0.0
    if event.event_type == "viewer_join":
        vb = detection_engine.analyze_viewbot_pattern(
            EventBatch(
                stream_id=str(stream.id),
                events=[
                    {
                        "ip_address": event.ip_address,
                        "fingerprint_hash": event.fingerprint_hash,
                        "timestamp": event.metadata.get("timestamp"),
                    }
                ],
            )
        )
        if vb.is_threat:
            pattern_score = vb.risk_score

    risk_score = max(
        ip_result.risk_score if ip_result else 0.0,
        fp_risk,
        pattern_score,
    )

    rt_assessment = None
    if ingest_settings.viewbot_realtime_enabled:
        rt_engine = get_realtime_viewbot_engine()
        rt_assessment = await rt_engine.assess_ingest_event(
            stream.id,
            event.event_type,
            ip_data,
            platform_user_id=event.platform_user_id,
            platform_username=event.platform_username,
            ip_address=event.ip_address,
            fingerprint_hash=event.fingerprint_hash,
            fingerprint_risk=fp_risk,
            metadata=dict(event.metadata),
        )
        risk_score = max(risk_score, rt_assessment.risk_score)

    meta = dict(event.metadata)
    meta["ingest_source"] = source

    stream_event = StreamEvent(
        stream_id=stream.id,
        event_type=event.event_type,
        platform_user_id=event.platform_user_id,
        platform_username=event.platform_username,
        ip_address=event.ip_address,
        fingerprint_hash=event.fingerprint_hash,
        asn=ip_data.get("asn") if ip_data else None,
        country_code=ip_data.get("country_code") if ip_data else None,
        is_proxy=ip_data.get("is_proxy", False),
        is_vpn=ip_data.get("is_vpn", False),
        is_tor=ip_data.get("is_tor", False),
        is_datacenter=ip_data.get("is_datacenter", False),
        risk_score=risk_score,
        event_metadata=meta,
        correlation_id=correlation.generate_correlation_id(),
    )
    db.add(stream_event)
    await db.flush()

    # Widget / pulse: solo registro de IP para proxy; no aparecen en lista de chat
    if source != "widget" and event.event_type not in ("viewer_pulse",):
        viewer_svc = ViewerSessionService(db)
        await viewer_svc.upsert_from_event(
            stream.id,
            event.platform_username,
            event.platform_user_id,
            event.ip_address,
            event.fingerprint_hash,
            risk_score,
            event.event_type,
        )

    attack_payload = None
    alert_payload = None

    if rt_assessment and rt_assessment.alert_recommended:
        targets = []
        uid = (event.platform_user_id or "").strip()
        if uid.isdigit():
            targets.append({"type": "user", "value": uid})
        elif event.platform_username:
            targets.append({"type": "user_login", "value": event.platform_username})
        if event.ip_address:
            targets.append({"type": "ip", "value": event.ip_address})
        if event.fingerprint_hash:
            targets.append({"type": "fingerprint", "value": event.fingerprint_hash})
        attack_payload, alert_payload = await apply_viewbot_assessment(
            db,
            stream,
            tenant_id,
            rt_assessment,
            correlation_id=stream_event.correlation_id,
            source_ips=[event.ip_address] if event.ip_address else [],
            fingerprints=[event.fingerprint_hash] if event.fingerprint_hash else [],
            targets=targets or None,
        )

    if attack_payload is None and risk_score >= 50.0:
        attack_type_map = {
            "viewer_join": AttackType.VIEWBOT,
            "viewer_pulse": AttackType.VIEWBOT,
            "follow": AttackType.FOLLOWBOT,
            "chat_message": AttackType.SPAM,
        }
        attack_type = attack_type_map.get(event.event_type, AttackType.COORDINATED)
        evidence: Dict[str, Any] = {
            "event_id": str(stream_event.id),
            "ingest_source": source,
            **(ip_result.evidence if ip_result else {}),
        }
        if ip_data.get("is_proxy"):
            evidence["proxy_detected"] = True
            evidence["proxy_ips"] = [event.ip_address]

        ai_insight = await ai_service.analyze_threat(
            attack_type.value,
            risk_score,
            stream.channel_name,
            evidence,
            monitor_mode=stream_monitor_mode(stream),
        )
        evidence["ai_insight"] = ai_insight

        existing = await correlation.get_active_attack(stream.id, attack_type)
        is_new_attack = existing is None
        if existing:
            attack = existing
        else:
            attack = await correlation.create_attack_record(
                stream_id=stream.id,
                attack_type=attack_type,
                risk_score=risk_score,
                confidence=ip_result.confidence if ip_result else 0.5,
                evidence=evidence,
                source_ips=[event.ip_address] if event.ip_address else [],
                fingerprints=[event.fingerprint_hash] if event.fingerprint_hash else [],
                correlation_id=stream_event.correlation_id,
            )

        alert = None
        if is_new_attack:
            alert = await correlation.create_alert(
                tenant_id=tenant_id,
                attack=attack,
                title=f"Amenaza detectada: {attack_type.value}",
                message=ai_insight.get("summary", f"Risk {risk_score:.1f} en {stream.channel_name}"),
            )

        attack_payload = {
            "id": str(attack.id),
            "attack_type": attack.attack_type.value,
            "severity": attack.severity.value,
            "risk_score": attack.risk_score,
            "stream_id": str(stream.id),
            "channel_name": stream.channel_name,
        }
        if alert:
            alert_payload = {
                "id": str(alert.id),
                "title": alert.title,
                "message": alert.message,
                "severity": alert.severity.value,
                "status": alert.status,
                "created_at": alert.created_at.isoformat(),
            }

        if risk_score >= 70.0 and stream_auto_mitigate(stream):
            targets = []
            uid = (event.platform_user_id or "").strip()
            if uid.isdigit():
                targets.append({"type": "user", "value": uid})
            elif event.platform_username:
                targets.append({"type": "user_login", "value": event.platform_username})
            if event.ip_address:
                targets.append({"type": "ip", "value": event.ip_address})
            if event.fingerprint_hash:
                targets.append({"type": "fingerprint", "value": event.fingerprint_hash})
            if targets:
                await mitigation.progressive_mitigation(
                    stream_id=stream.id,
                    tenant_id=tenant_id,
                    attack_id=attack.id,
                    risk_score=risk_score,
                    threat_type=attack_type.value,
                    targets=targets,
                    evidence=evidence,
                    stream=stream,
                )

    tenant_streams = await get_tenant_stream_ids(db, tenant_id)
    await push_dashboard_realtime(
        db,
        tenant_id,
        tenant_streams,
        alert=alert_payload,
        attack=attack_payload,
    )

    return {
        "event_id": str(stream_event.id),
        "risk_score": risk_score,
        "attack_created": attack_payload is not None,
        "is_proxy": ip_data.get("is_proxy", False),
        "is_vpn": ip_data.get("is_vpn", False),
        "is_tor": ip_data.get("is_tor", False),
        "viewbot_classification": rt_assessment.classification if rt_assessment else "clean",
        "viewbot_signals": rt_assessment.signals if rt_assessment else {},
    }
