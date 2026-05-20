from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.api.websocket.manager import ws_manager
from app.events.realtime import publish_realtime
from app.services.dashboard.metrics import compute_dashboard_charts, compute_dashboard_stats

_notify_settings = get_settings()


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

    if _notify_settings.event_realtime_pubsub_enabled:
        await publish_realtime(tid, "stats_update", payload)
        if alert:
            await publish_realtime(tid, "alert", alert)
        if attack:
            await publish_realtime(tid, "attack_detected", attack)
    else:
        await ws_manager.broadcast_stats(tid, payload)
        if alert:
            await ws_manager.broadcast_alert(tid, alert)
        if attack:
            await ws_manager.broadcast_attack(tid, attack)
