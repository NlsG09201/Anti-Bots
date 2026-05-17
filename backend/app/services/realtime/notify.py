from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.websocket.manager import ws_manager
from app.services.dashboard.metrics import compute_dashboard_charts, compute_dashboard_stats


async def push_dashboard_realtime(
    db: AsyncSession,
    tenant_id: UUID,
    stream_ids: Optional[list] = None,
    *,
    alert: Optional[Dict[str, Any]] = None,
    attack: Optional[Dict[str, Any]] = None,
) -> None:
    tid = str(tenant_id)
    stats = await compute_dashboard_stats(db, tenant_id, stream_ids)
    charts = await compute_dashboard_charts(db, stream_ids or [], hours=24)
    payload = {**stats, "charts": charts}

    await ws_manager.broadcast_stats(tid, payload)
    if alert:
        await ws_manager.broadcast_alert(tid, alert)
    if attack:
        await ws_manager.broadcast_attack(tid, attack)
