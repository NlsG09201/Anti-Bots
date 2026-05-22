"""SOC API — métricas multi-plataforma y feed en vivo."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AnalystUser
from app.infrastructure.database.session import get_db
from app.services.dashboard.metrics import compute_dashboard_stats, get_tenant_stream_ids
from app.services.dashboard.soc_metrics import compute_soc_overview, recent_live_feed
from app.services.monitoring.orchestrator import get_platform_monitor_orchestrator
from app.services.realtime.notify import push_dashboard_realtime

router = APIRouter(prefix="/soc", tags=["SOC"])


@router.get("/overview")
async def soc_overview(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
):
    stream_ids = await get_tenant_stream_ids(db, current_user.tenant_id)
    stats = await compute_dashboard_stats(db, current_user.tenant_id, stream_ids)
    overview = await compute_soc_overview(db, current_user.tenant_id, stream_ids)
    return {"stats": stats, "soc": overview}


@router.get("/feed")
async def soc_live_feed(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    stream_ids = await get_tenant_stream_ids(db, current_user.tenant_id)
    return {"events": await recent_live_feed(db, stream_ids, limit=limit)}


@router.post("/refresh")
async def soc_push_refresh(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
):
    stream_ids = await get_tenant_stream_ids(db, current_user.tenant_id)
    await push_dashboard_realtime(db, current_user.tenant_id, stream_ids)
    overview = await compute_soc_overview(db, current_user.tenant_id, stream_ids)
    return {"ok": True, "soc": overview}


@router.get("/monitors/status")
async def platform_monitors_status(_user: AnalystUser):
    from app.core.config import get_settings

    orch = get_platform_monitor_orchestrator()
    return {
        "enabled": get_settings().platform_monitor_enabled,
        "running": orch._running,
        "active_monitors": list(orch._monitors.keys()),
        "count": len(orch._monitors),
        "max_streams": get_settings().platform_monitor_max_streams,
    }
