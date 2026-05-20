import secrets
from datetime import datetime, timezone
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from app.core.config import get_settings
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
from app.infrastructure.cache.redis_client import RedisCache
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
from app.services.ingest.event_ingest import process_stream_event
from app.services.monitoring.channel_monitor import ChannelMonitorService
from app.services.streams.helpers import (
    stream_auto_mitigate,
    stream_monitor_mode,
    stream_to_response_dict,
    sync_stream_live_status,
)
from app.services.viewers.session import ViewerSessionService

router = APIRouter(prefix="/streams", tags=["Streams"])
settings = get_settings()
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


@router.post("/{stream_id}/channel-invite")
async def create_channel_invite(
    stream_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Genera enlace para que el streamer conecte OAuth y habilite chatters + ban en Twitch."""
    stream = await _get_stream(db, stream_id, current_user.tenant_id)
    invite = secrets.token_urlsafe(24)
    cache = RedisCache(prefix="oauth")
    login = (stream.settings or {}).get("login", stream.channel_name)
    await cache.set(
        f"invite:{invite}",
        {
            "stream_id": str(stream.id),
            "tenant_id": str(current_user.tenant_id),
            "channel_login": login,
        },
        ttl=7 * 86400,
    )
    frontend = settings.app_frontend_url.rstrip("/")
    return {
        "invite_token": invite,
        "invite_url": f"{frontend}/connect-twitch?invite={invite}",
        "oauth_start_url": f"/api/v1/integrations/twitch/invite/{invite}/start",
        "channel_login": login,
    }


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


@router.post("/{stream_id}/sync/quick")
async def quick_sync_stream(
    stream_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Sincroniza usuarios en chat (Helix rapido) sin escaneo IRC largo."""
    stream = await _get_stream(db, stream_id, current_user.tenant_id)
    if not stream.is_live:
        stream = await sync_stream_live_status(db, stream)
    if not stream.is_live:
        return {"status": "offline", "message": "El canal no esta en vivo"}
    summary = await ChannelMonitorService(db).run_quick_sync(stream, current_user.tenant_id)
    return {"status": "ok", **summary}


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
    counts = await viewer_svc.count_active(stream.id)
    attacks = await db.execute(
        select(Attack).where(
            Attack.stream_id == stream.id,
            Attack.status == "active",
        )
    )
    from app.services.monitoring.proxy_intel import collect_proxy_threats

    proxy_intel = await collect_proxy_threats(db, stream.id)
    silent = max(0, (stream.viewer_count or 0) - counts["total"])
    return {
        "is_live": stream.is_live,
        "viewer_count": stream.viewer_count,
        "last_monitor": meta.get("last_monitor"),
        "last_quick_sync": meta.get("last_quick_sync"),
        "viewer_history": meta.get("viewer_history", [])[-12:],
        "active_viewers_tracked": counts["total"],
        "talking_count": counts["talking"],
        "suspected_bots": counts["suspected"],
        "proxy_ips_detected": len(proxy_intel["proxy_ips"]),
        "silent_viewbots_estimate": silent if silent > 50 else 0,
        "active_attacks": len(attacks.scalars().all()),
        "monitor_mode": stream_monitor_mode(stream),
        "has_broadcaster_oauth": bool(stream.oauth_token_encrypted),
        "note": (
            "Usuarios en chat (Helix/IRC). Viewers totales en Twitch incluyen quien no escribe. "
            "Ataques por proxy se mitigan bloqueando IPs detectadas en eventos."
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
    result = await process_stream_event(
        db,
        stream,
        current_user.tenant_id,
        event,
        source="api",
    )
    return result


@router.post("/{stream_id}/viewers/load-full")
async def load_full_viewer_list(
    stream_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Carga el listado mas completo posible del canal (Helix chatters + IRC).
    Funciona en tu canal y en canales en modo observacion.
    """
    stream = await _get_stream(db, stream_id, current_user.tenant_id)
    if not stream.is_live:
        stream = await sync_stream_live_status(db, stream)
    if not stream.is_live:
        return {
            "status": "offline",
            "message": "El canal no esta en vivo",
            "viewer_count": stream.viewer_count,
        }
    summary = await ChannelMonitorService(db).run_full_viewer_load(
        stream,
        current_user.tenant_id,
    )
    await db.commit()
    return summary


@router.post("/{stream_id}/viewers/screen")
async def screen_viewers_with_ai(
    stream_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Cruza usuarios en chat con base local + IA y actualiza riesgo/descripcion."""
    from app.services.detection.viewer_bot_screening import ViewerBotScreeningService

    stream = await _get_stream(db, stream_id, current_user.tenant_id)
    svc = ViewerSessionService(db)
    sessions = await svc.list_active(stream.id, chat_only=True, limit=500)
    chatters = [
        {"username": s.platform_username}
        for s in sessions
        if s.platform_username
    ]
    stats = await ViewerBotScreeningService().screen_and_update_sessions(
        db, stream.id, stream.channel_name, chatters
    )
    await db.commit()
    return {"status": "ok", **stats}


@router.get("/{stream_id}/viewers", response_model=List[ViewerSessionResponse])
async def list_viewers(
    stream_id: UUID,
    current_user: CurrentUser,
    filter: Literal["all", "talking", "suspected"] = Query(
        "all",
        description="all=todos en chat, talking=hablando, suspected=sospechosos",
    ),
    suspected_only: bool = Query(False, deprecated=True),
    db: AsyncSession = Depends(get_db),
):
    await _get_stream(db, stream_id, current_user.tenant_id)
    svc = ViewerSessionService(db)
    if suspected_only:
        filter = "suspected"
    return await svc.list_active(
        stream_id,
        suspected_only=(filter == "suspected"),
        talking_only=(filter == "talking"),
    )


@router.post("/{stream_id}/viewers/ban-suspected")
async def ban_all_suspected_viewers(
    stream_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    apply_twitch_ban: bool = Query(True),
    duration_hours: Optional[int] = Query(24, ge=1, le=8760),
):
    """
    Bloquea y banea en bloque todos los viewers marcados como sospechosos/bots.
    Requiere escaneo previo (Verificar bots / monitor).
    """
    from app.infrastructure.database.models import AttackType, MitigationAction
    from app.services.correlation.service import CorrelationService
    from app.services.mitigation.service import MitigationService
    from app.services.mitigation.targets import build_targets_from_suspected_sessions

    stream = await _get_stream(db, stream_id, current_user.tenant_id)
    targets = await build_targets_from_suspected_sessions(db, stream.id, limit=50)
    if not targets:
        raise ValidationError(
            "No hay viewers sospechosos. Ejecuta Verificar bots (Insights + IA) o escanea el canal."
        )

    correlation = CorrelationService(db)
    attack = await correlation.get_active_attack(stream.id, AttackType.VIEWBOT)
    if not attack:
        attack = await correlation.create_attack_record(
            stream_id=stream.id,
            attack_type=AttackType.VIEWBOT,
            risk_score=90.0,
            confidence=0.85,
            evidence={"manual_ban_suspected": True, "target_count": len(targets)},
            source_ips=[],
            fingerprints=[],
        )
        await correlation.create_alert(
            tenant_id=current_user.tenant_id,
            attack=attack,
            title=f"Bloqueo masivo de bots en {stream.channel_name}",
            message=f"{len(targets)} objetivos marcados como sospechosos",
        )

    mitigation = MitigationService(db)
    action = MitigationAction.TIMEOUT if stream_monitor_mode(stream) else MitigationAction.BAN
    evidence = {
        "risk_score": 90.0,
        "reason": "StreamShield: bloqueo masivo de viewers sospechosos",
        "apply_twitch_ban": apply_twitch_ban,
    }
    bans = await mitigation.apply_mitigation(
        stream_id=stream.id,
        tenant_id=current_user.tenant_id,
        attack_id=attack.id,
        action=action,
        targets=targets,
        evidence=evidence,
        duration_hours=duration_hours,
        stream=stream if apply_twitch_ban else None,
    )

    await ViewerSessionService(db).deactivate_suspected(stream.id)
    await db.commit()

    twitch_ok = sum(1 for t in evidence.get("twitch_bans", []) if t.get("ok"))

    return {
        "status": "ok",
        "targets": len(targets),
        "bans_created": len(bans),
        "twitch_bans_applied": twitch_ok,
        "attack_id": str(attack.id),
    }


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

    from app.services.mitigation.targets import session_to_user_target

    targets = []
    ut = session_to_user_target(session)
    if ut:
        targets.append(ut)
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
            stream=stream if body.apply_twitch_ban else None,
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
