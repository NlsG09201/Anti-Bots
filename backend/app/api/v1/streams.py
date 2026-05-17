from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.api.v1.schemas import (
    BlockViewerRequest,
    DashboardCharts,
    DashboardStats,
    EventIngest,
    StreamCreate,
    StreamResponse,
    StreamWatchRequest,
    ViewerSessionResponse,
)
from app.core.exceptions import NotFoundError, ValidationError
from app.infrastructure.database.models import (
    Attack,
    AttackType,
    Platform,
    Stream,
    StreamEvent,
    ViewerSession,
)
from app.infrastructure.database.session import get_db
from app.integrations.twitch.helix import TwitchHelixClient
from app.services.ai.service import AIService
from app.services.correlation.service import CorrelationService
from app.services.dashboard.metrics import (
    compute_dashboard_charts,
    compute_dashboard_stats,
    get_tenant_stream_ids,
)
from app.services.detection.engine import BotDetectionEngine, EventBatch
from app.services.mitigation.service import MitigationService
from app.services.realtime.notify import push_dashboard_realtime
from app.services.reputation.service import ReputationService
from app.services.monitoring.channel_monitor import ChannelMonitorService
from app.services.streams.helpers import (
    stream_auto_mitigate,
    stream_monitor_mode,
    stream_to_response_dict,
    sync_stream_live_status,
)
from app.services.viewers.session import ViewerSessionService

router = APIRouter(prefix="/streams", tags=["Streams"])
detection_engine = BotDetectionEngine()
ai_service = AIService()


def _as_stream_response(stream: Stream) -> StreamResponse:
    data = stream_to_response_dict(stream)
    return StreamResponse(**data)


@router.post("", response_model=StreamResponse)
async def create_stream(
    data: StreamCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    stream = Stream(
        tenant_id=current_user.tenant_id,
        owner_id=current_user.id,
        platform=data.platform,
        external_id=data.external_id,
        channel_name=data.channel_name,
        settings={"login": data.channel_name.lower(), "is_owned": False, "monitor_mode": True},
    )
    db.add(stream)
    await db.flush()
    return _as_stream_response(stream)


@router.post("/watch", response_model=StreamResponse)
async def watch_channel(
    data: StreamWatchRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Monitoreo de otro canal (solo lectura en Twitch; ideal para pruebas reales)."""
    if data.platform != Platform.TWITCH:
        raise ValidationError("Solo Twitch está soportado para monitoreo externo")

    helix = TwitchHelixClient()
    if not helix.configured:
        raise ValidationError("Credenciales Twitch no configuradas en el servidor")

    user = await helix.get_user_by_login(data.login)
    if not user:
        raise NotFoundError("Canal de Twitch")

    broadcaster_id = user["id"]
    login = user["login"]
    display_name = user.get("display_name", login)

    result = await db.execute(
        select(Stream).where(
            Stream.tenant_id == current_user.tenant_id,
            Stream.platform == Platform.TWITCH,
            Stream.external_id == broadcaster_id,
        )
    )
    stream = result.scalar_one_or_none()
    if stream:
        meta = dict(stream.settings or {})
        meta.update({
            "monitor_mode": True,
            "auto_mitigate": False,
            "login": login,
            "is_owned": False,
        })
        stream.settings = meta
        stream.channel_name = display_name
    else:
        stream = Stream(
            tenant_id=current_user.tenant_id,
            owner_id=current_user.id,
            platform=Platform.TWITCH,
            external_id=broadcaster_id,
            channel_name=display_name,
            settings={
                "monitor_mode": True,
                "auto_mitigate": False,
                "login": login,
                "is_owned": False,
            },
        )
        db.add(stream)

    await db.flush()
    stream = await sync_stream_live_status(db, stream)
    return _as_stream_response(stream)


@router.delete("/watch/{stream_id}")
async def unwatch_channel(
    stream_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    stream = await _get_stream(db, stream_id, current_user.tenant_id)
    if not stream_monitor_mode(stream):
        raise ValidationError("Solo se puede quitar monitoreo de canales en modo observación")
    if stream.oauth_token_encrypted:
        meta = dict(stream.settings or {})
        meta["monitor_mode"] = False
        meta["is_owned"] = True
        stream.settings = meta
        await db.flush()
        return {"status": "converted_to_owned"}
    await db.delete(stream)
    await db.flush()
    return {"status": "removed"}


@router.post("/{stream_id}/sync", response_model=StreamResponse)
async def sync_stream(
    stream_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    deep: bool = Query(False, description="Escaneo IRC/chatters + deteccion (~30s)"),
):
    stream = await _get_stream(db, stream_id, current_user.tenant_id)
    if deep and stream.is_live:
        await ChannelMonitorService(db).run_cycle(stream, current_user.tenant_id)
    else:
        stream = await sync_stream_live_status(db, stream)
        tenant_streams = await get_tenant_stream_ids(db, current_user.tenant_id)
        await push_dashboard_realtime(db, current_user.tenant_id, tenant_streams)
    await db.refresh(stream)
    return _as_stream_response(stream)


@router.post("/{stream_id}/monitor")
async def run_channel_monitor(
    stream_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Escaneo en vivo: chat IRC o Helix chatters + deteccion de ataque."""
    stream = await _get_stream(db, stream_id, current_user.tenant_id)
    if not stream.is_live:
        stream = await sync_stream_live_status(db, stream)
    if not stream.is_live:
        return {"status": "offline", "message": "El canal no esta en vivo"}
    summary = await ChannelMonitorService(db).run_cycle(stream, current_user.tenant_id)
    return {"status": "ok", **summary}


@router.get("/{stream_id}/monitor/status")
async def monitor_status(
    stream_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    stream = await _get_stream(db, stream_id, current_user.tenant_id)
    meta = stream.settings or {}
    viewer_svc = ViewerSessionService(db)
    suspected = await viewer_svc.list_active(stream.id, suspected_only=True)
    active = await viewer_svc.list_active(stream.id, suspected_only=False, limit=500)
    attacks = await db.execute(
        select(Attack).where(
            Attack.stream_id == stream.id,
            Attack.status == "active",
        )
    )
    return {
        "is_live": stream.is_live,
        "viewer_count": stream.viewer_count,
        "last_monitor": meta.get("last_monitor"),
        "viewer_history": meta.get("viewer_history", [])[-12:],
        "active_viewers_tracked": len(active),
        "suspected_bots": len(suspected),
        "active_attacks": len(attacks.scalars().all()),
        "monitor_mode": stream_monitor_mode(stream),
        "note": (
            "Lista usuarios en chat (IRC/Helix). Los viewbots silenciosos se detectan por picos de viewers."
        ),
    }


@router.get("", response_model=List[StreamResponse])
async def list_streams(
    current_user: CurrentUser,
    sync: bool = Query(False, description="Actualizar estado live desde Twitch"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Stream).where(Stream.tenant_id == current_user.tenant_id)
    )
    streams = list(result.scalars().all())
    if sync:
        for stream in streams:
            if stream_monitor_mode(stream) or stream.platform == Platform.TWITCH:
                await sync_stream_live_status(db, stream)
    return [_as_stream_response(s) for s in streams]


@router.get("/{stream_id}", response_model=StreamResponse)
async def get_stream(
    stream_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    stream = await _get_stream(db, stream_id, current_user.tenant_id)
    return _as_stream_response(stream)


@router.post("/{stream_id}/events")
async def ingest_event(
    stream_id: UUID,
    event: EventIngest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    stream = await _get_stream(db, stream_id, current_user.tenant_id)
    correlation = CorrelationService(db)
    reputation_svc = ReputationService(db)

    ip_data = {}
    if event.ip_address:
        ip_data = await reputation_svc.enrich_ip(event.ip_address)

    fp_risk = 0.0
    if event.fingerprint_hash:
        fp_risk = event.metadata.get("fingerprint_risk", 0.0)

    ip_result = detection_engine.analyze_ip(ip_data) if ip_data else None
    pattern_score = 0.0
    if event.event_type == "viewer_join":
        vb = detection_engine.analyze_viewbot_pattern(
            EventBatch(
                stream_id=str(stream.id),
                events=[{
                    "ip_address": event.ip_address,
                    "fingerprint_hash": event.fingerprint_hash,
                    "timestamp": event.metadata.get("timestamp"),
                }],
            )
        )
        if vb.is_threat:
            pattern_score = vb.risk_score
    risk_score = max(
        ip_result.risk_score if ip_result else 0.0,
        fp_risk,
        pattern_score,
    )

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
        event_metadata=event.metadata,
        correlation_id=correlation.generate_correlation_id(),
    )
    db.add(stream_event)
    await db.flush()

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

    if risk_score >= 50.0:
        attack_type_map = {
            "viewer_join": AttackType.VIEWBOT,
            "follow": AttackType.FOLLOWBOT,
            "chat_message": AttackType.SPAM,
        }
        attack_type = attack_type_map.get(event.event_type, AttackType.COORDINATED)
        evidence = {"event_id": str(stream_event.id), **(ip_result.evidence if ip_result else {})}

        ai_insight = await ai_service.analyze_threat(
            attack_type.value,
            risk_score,
            stream.channel_name,
            evidence,
            monitor_mode=stream_monitor_mode(stream),
        )
        evidence["ai_insight"] = ai_insight

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
        alert = await correlation.create_alert(
            tenant_id=current_user.tenant_id,
            attack=attack,
            title=f"Threat detected: {attack_type.value}",
            message=ai_insight.get("summary", f"Risk {risk_score:.1f} on {stream.channel_name}"),
        )

        attack_payload = {
            "id": str(attack.id),
            "attack_type": attack.attack_type.value,
            "severity": attack.severity.value,
            "risk_score": attack.risk_score,
            "stream_id": str(stream.id),
            "channel_name": stream.channel_name,
            "ai_insight": ai_insight,
        }
        alert_payload = {
            "id": str(alert.id),
            "title": alert.title,
            "message": alert.message,
            "severity": alert.severity.value,
            "status": alert.status,
            "created_at": alert.created_at.isoformat(),
        }

        if risk_score >= 70.0 and stream_auto_mitigate(stream):
            mitigation = MitigationService(db)
            targets = []
            if event.platform_user_id:
                targets.append({"type": "user", "value": event.platform_user_id})
            if event.ip_address:
                targets.append({"type": "ip", "value": event.ip_address})
            if event.fingerprint_hash:
                targets.append({"type": "fingerprint", "value": event.fingerprint_hash})
            await mitigation.progressive_mitigation(
                stream_id=stream.id,
                tenant_id=current_user.tenant_id,
                attack_id=attack.id,
                risk_score=risk_score,
                threat_type=attack_type.value,
                targets=targets,
                evidence=attack.evidence,
            )

    tenant_streams = await get_tenant_stream_ids(db, current_user.tenant_id)
    await push_dashboard_realtime(
        db,
        current_user.tenant_id,
        tenant_streams,
        alert=alert_payload,
        attack=attack_payload,
    )

    return {
        "event_id": str(stream_event.id),
        "risk_score": risk_score,
        "attack_created": attack_payload is not None,
        "ai_insight": attack_payload.get("ai_insight") if attack_payload else None,
    }


@router.get("/{stream_id}/viewers", response_model=List[ViewerSessionResponse])
async def list_viewers(
    stream_id: UUID,
    current_user: CurrentUser,
    suspected_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    await _get_stream(db, stream_id, current_user.tenant_id)
    svc = ViewerSessionService(db)
    return await svc.list_active(stream_id, suspected_only=suspected_only)


@router.post("/{stream_id}/viewers/{viewer_id}/block")
async def block_viewer(
    stream_id: UUID,
    viewer_id: UUID,
    body: BlockViewerRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    from app.core.security import decrypt_value
    from app.integrations.twitch.moderation import ban_user_on_twitch
    from app.infrastructure.database.models import MitigationAction

    stream = await _get_stream(db, stream_id, current_user.tenant_id)
    result = await db.execute(
        select(ViewerSession).where(
            ViewerSession.id == viewer_id,
            ViewerSession.stream_id == stream.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise NotFoundError("Viewer session")

    user_target = session.platform_user_id or session.platform_username or ""
    targets = [{"type": "user", "value": user_target}]
    if session.ip_address and session.ip_address != "twitch:chat":
        targets.append({"type": "ip", "value": session.ip_address})

    mitigation = MitigationService(db)
    attack_result = await db.execute(
        select(Attack).where(
            Attack.stream_id == stream.id,
            Attack.status == "active",
        ).order_by(Attack.created_at.desc()).limit(1)
    )
    attack = attack_result.scalar_one_or_none()
    attack_id = attack.id if attack else None

    if attack_id:
        await mitigation.apply_mitigation(
            stream_id=stream.id,
            tenant_id=current_user.tenant_id,
            attack_id=attack_id,
            action=MitigationAction.TIMEOUT if stream_monitor_mode(stream) else MitigationAction.BAN,
            targets=targets,
            evidence={
                "blocked_viewer": session.platform_username,
                "risk_score": session.risk_score,
                "reason": body.reason,
            },
            duration_hours=body.duration_hours,
        )
        if attack:
            attack.status = "mitigated"
    else:
        from app.infrastructure.database.models import Ban
        for t in targets:
            db.add(Ban(
                stream_id=stream.id,
                tenant_id=current_user.tenant_id,
                target_type=t["type"],
                target_value=t["value"],
                reason=body.reason,
                ban_type="timeout" if stream_monitor_mode(stream) else "ban",
                is_automated=False,
                created_by=current_user.id,
            ))

    twitch_result = None
    can_twitch = (
        body.apply_twitch_ban
        and stream.oauth_token_encrypted
        and not stream_monitor_mode(stream)
        and session.platform_user_id
        and session.platform_user_id.isdigit()
    )
    if can_twitch:
        token = decrypt_value(stream.oauth_token_encrypted)
        twitch_result = await ban_user_on_twitch(
            stream.external_id,
            token,
            session.platform_user_id,
            reason=body.reason,
            duration_seconds=(body.duration_hours or 24) * 3600,
        )

    session.is_active = False
    session.left_at = datetime.now(timezone.utc)
    await db.flush()

    tenant_streams = await get_tenant_stream_ids(db, current_user.tenant_id)
    await push_dashboard_realtime(db, current_user.tenant_id, tenant_streams)

    return {
        "blocked": True,
        "username": session.platform_username,
        "twitch_ban": twitch_result,
        "local_only": stream_monitor_mode(stream) or not can_twitch,
        "message": (
            "Bloqueo registrado en StreamShield."
            + (
                " En canal ajeno no se puede banear en Twitch sin permisos del broadcaster."
                if stream_monitor_mode(stream)
                else ""
            )
        ),
    }


@router.get("/dashboard/stats", response_model=DashboardStats)
async def dashboard_stats(
    current_user: CurrentUser,
    stream_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stream_ids = await get_tenant_stream_ids(db, current_user.tenant_id)
    if stream_id:
        await _get_stream(db, stream_id, current_user.tenant_id)
        stream_ids = [stream_id]
    stats = await compute_dashboard_stats(db, current_user.tenant_id, stream_ids)
    return DashboardStats(**stats)


@router.get("/dashboard/charts", response_model=DashboardCharts)
async def dashboard_charts(
    current_user: CurrentUser,
    stream_id: Optional[UUID] = Query(None),
    hours: int = Query(24, ge=1, le=72),
    db: AsyncSession = Depends(get_db),
):
    stream_ids = await get_tenant_stream_ids(db, current_user.tenant_id)
    if stream_id:
        await _get_stream(db, stream_id, current_user.tenant_id)
        stream_ids = [stream_id]
    charts = await compute_dashboard_charts(db, stream_ids, hours=hours)
    return DashboardCharts(**charts)


async def _get_stream(db: AsyncSession, stream_id: UUID, tenant_id: UUID) -> Stream:
    result = await db.execute(
        select(Stream).where(Stream.id == stream_id, Stream.tenant_id == tenant_id)
    )
    stream = result.scalar_one_or_none()
    if not stream:
        raise NotFoundError("Stream")
    return stream
