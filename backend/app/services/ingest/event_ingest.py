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
from app.core.logging import get_logger
from app.services.detection.anomaly_intelligence import AnomalyIntelligenceService
from app.services.detection.engine import BotDetectionEngine, EventBatch
from app.services.detection.realtime_viewbot import get_realtime_viewbot_engine
from app.services.detection.realtime_actions import apply_viewbot_assessment
from app.services.security.network_policy import NetworkPolicyEngine
from app.services.mitigation.enforcement import is_event_blocked
from app.services.mitigation.service import MitigationService
from app.services.realtime.notify import push_dashboard_realtime
from app.services.reputation.service import ReputationService
from app.services.streams.helpers import stream_auto_mitigate, stream_monitor_mode
from app.services.viewers.session import ViewerSessionService

detection_engine = BotDetectionEngine()
ai_service = AIService()
network_policy = NetworkPolicyEngine()
anomaly_svc = AnomalyIntelligenceService()
ingest_settings = get_settings()
logger = get_logger(__name__)


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

    if ingest_settings.live_intel_enabled:
        try:
            from app.live_intel import get_live_intel_engine

            await get_live_intel_engine().record_platform_event(
                str(stream.id),
                event.event_type,
                username=event.platform_username,
            )
        except Exception:
            pass

    tbi_result = None
    if ingest_settings.twitchbots_info_enabled:
        try:
            from app.services.twitchbots.verification_service import (
                get_twitchbots_verification_service,
            )

            tbi_result = await get_twitchbots_verification_service().verify_ingest_user(
                tenant_id=str(tenant_id),
                stream_id=str(stream.id),
                event_type=event.event_type,
                username=event.platform_username,
                platform_user_id=event.platform_user_id,
            )
        except Exception as exc:
            logger.warning("twitchbots_ingest_verify_failed", error=str(exc)[:120])

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

    fp_flags = event.metadata.get("automation_flags") or event.metadata.get("checks") or []
    if isinstance(fp_flags, dict):
        fp_flags = list(fp_flags.keys())
    policy = network_policy.evaluate(
        ip_intel=ip_data,
        fingerprint_flags=fp_flags if isinstance(fp_flags, list) else [],
        automation_detected=bool(event.metadata.get("automation_detected")),
    )
    if not policy.allowed:
        return {
            "event_id": None,
            "risk_score": policy.risk_score,
            "attack_created": False,
            "blocked": True,
            "ban_type": "network_policy",
            "policy": policy.to_dict(),
        }

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
        policy.risk_score,
    )
    if tbi_result and tbi_result.is_known_bot:
        risk_score = max(risk_score, float(tbi_result.reputation.suspicious_score))

    if event.event_type == "viewer_join":
        anomaly = await anomaly_svc.assess_window(
            str(stream.id),
            joins_per_minute=float(event.metadata.get("joins_per_minute", 1)),
            unique_ip_ratio=float(event.metadata.get("unique_ip_ratio", 1.0)),
            proxy_ratio=1.0 if ip_data.get("is_proxy") else 0.0,
            fingerprint_collision_ratio=float(
                event.metadata.get("fingerprint_collision_ratio", 0)
            ),
            chat_participation_ratio=float(
                event.metadata.get("chat_participation_ratio", 0.5)
            ),
        )
        if anomaly.is_anomaly:
            risk_score = max(risk_score, anomaly.anomaly_score)
            meta_anomaly = anomaly.to_dict()
        else:
            meta_anomaly = None
    else:
        meta_anomaly = None

    ai_assessment = None
    if ingest_settings.ai_intel_enabled:
        try:
            from app.ai_intel.orchestrator import get_ai_orchestrator

            ai_meta = dict(event.metadata)
            if tbi_result and tbi_result.is_known_bot:
                ai_meta["known_public_bot"] = True
                ai_meta["twitchbots_info"] = tbi_result.to_verdict_dict().get(
                    "twitchbots_info", {}
                )
            ai_assessment = await get_ai_orchestrator().assess_event(
                db,
                stream_id=stream.id,
                tenant_id=tenant_id,
                event_type=event.event_type,
                metadata=ai_meta,
                ip_intel=ip_data,
                fingerprint_risk=fp_risk,
                platform_user_id=event.platform_user_id,
                ip_address=event.ip_address,
                fingerprint_hash=event.fingerprint_hash,
            )
            risk_score = max(risk_score, ai_assessment.risk_score)
        except Exception as exc:
            logger.warning("ai_intel_assess_failed", error=str(exc))

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
    meta["network_policy"] = policy.to_dict()
    if tbi_result:
        meta["twitchbots_info"] = tbi_result.to_verdict_dict().get("twitchbots_info", {})
        meta["known_public_bot"] = tbi_result.is_known_bot
    if meta_anomaly:
        meta["anomaly"] = meta_anomaly
    if ai_assessment:
        meta["ai_intel"] = ai_assessment.to_dict()

    ti_assessment = None
    if ingest_settings.threat_intel_engine_enabled:
        try:
            from app.threat_intel_engine import get_threat_intel_engine

            ti_meta = dict(meta)
            if event.platform_username:
                ti_meta.setdefault("username", event.platform_username)
            if event.platform_user_id:
                ti_meta.setdefault("user_id", event.platform_user_id)
            if event.ip_address:
                ti_meta.setdefault("ip_address", event.ip_address)
            if event.fingerprint_hash:
                ti_meta.setdefault("fingerprint_hash", event.fingerprint_hash)
            if ip_data:
                ti_meta.setdefault("network_reputation", ip_data)
            ti_assessment = await get_threat_intel_engine().process_event(
                db,
                tenant_id=tenant_id,
                stream_id=stream.id,
                platform=stream.platform.value,
                event_type=event.event_type,
                metadata=ti_meta,
                skip_ai=True,
            )
            if ti_assessment:
                meta["threat_intel"] = ti_assessment.to_dict()
        except Exception as exc:
            logger.warning("threat_intel_engine_failed", error=str(exc))

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
            "viewer_spike": AttackType.VIEWBOT,
            "follow": AttackType.FOLLOWBOT,
            "chat_message": AttackType.SPAM,
            "gift": AttackType.FAKE_ENGAGEMENT,
            "raid": AttackType.CHAT_RAID,
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
        "threat_intel": ti_assessment.to_dict() if ti_assessment else None,
    }
