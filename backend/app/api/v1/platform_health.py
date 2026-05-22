"""SOC API — platform monitor health (Kick / YouTube / TikTok)."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.api.dependencies import AnalystUser
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.monitoring.orchestrator import get_platform_monitor_orchestrator
from app.services.platform_health.engine import get_platform_health_engine
from app.services.platform_health.registry import all_trackers
from app.services.platform_health.store import PlatformHealthStore

logger = get_logger(__name__)
router = APIRouter(prefix="/platform-health", tags=["Platform Monitor Health"])


@router.get("/overview")
async def platform_health_overview(_user: AnalystUser) -> Dict[str, Any]:
    cfg = get_settings()
    if not cfg.platform_health_enabled:
        return {"enabled": False, "message": "PLATFORM_HEALTH_ENABLED=false"}
    engine = get_platform_health_engine()
    overview = await engine.build_overview()
    return {"enabled": True, **overview.model_dump()}


@router.get("/streams")
async def platform_health_streams(_user: AnalystUser) -> Dict[str, Any]:
    cfg = get_settings()
    streams = await PlatformHealthStore().load_all_stream_health()
    live_trackers = [t.to_snapshot() for t in all_trackers().values()]
    return {
        "enabled": cfg.platform_health_enabled,
        "streams": [s.model_dump() for s in streams],
        "live_trackers": [s.model_dump() for s in live_trackers],
        "count": len(streams),
    }


@router.get("/integrations")
async def platform_health_integrations(_user: AnalystUser) -> Dict[str, Any]:
    from app.services.platform_health.probes import run_all_integration_probes

    cfg = get_settings()
    if not cfg.platform_health_enabled:
        return {"enabled": False, "integrations": []}
    probes = await run_all_integration_probes()
    system, _ = await PlatformHealthStore().load_global()
    return {
        "enabled": True,
        "integrations": [p.model_dump() for p in probes],
        "system": system.model_dump(),
    }


@router.post("/audit")
async def platform_health_audit(_user: AnalystUser) -> Dict[str, Any]:
    cfg = get_settings()
    if not cfg.platform_health_enabled:
        return {"enabled": False, "status": "disabled"}
    overview = await get_platform_health_engine().audit_once()
    return {"enabled": True, "status": "ok", **overview.model_dump()}


@router.get("/monitors/status")
async def platform_health_monitors_status(_user: AnalystUser) -> Dict[str, Any]:
    """Detailed monitor status (extends SOC /soc/monitors/status)."""
    cfg = get_settings()
    orch = get_platform_monitor_orchestrator()
    store = PlatformHealthStore()
    worker_alive, worker_ts = await store.worker_is_alive(
        cfg.platform_health_worker_heartbeat_ttl
    )
    redis_ok, redis_ms = await store.probe_redis_latency()
    streams = await store.load_all_stream_health()
    return {
        "enabled": cfg.platform_monitor_enabled,
        "health_enabled": cfg.platform_health_enabled,
        "orchestrator_running": orch._running,
        "active_monitors": list(orch._monitors.keys()),
        "count": len(orch._monitors),
        "max_streams": cfg.platform_monitor_max_streams,
        "worker_alive": worker_alive,
        "worker_last_seen": worker_ts,
        "redis_ok": redis_ok,
        "redis_latency_ms": redis_ms,
        "run_in_api": cfg.platform_monitor_run_in_api,
        "worker_mode": cfg.platform_monitor_worker_mode_resolved,
        "streams_health": [s.model_dump() for s in streams],
    }
