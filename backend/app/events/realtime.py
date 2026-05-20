"""Fan-out en tiempo real vía Redis Pub/Sub → WebSockets."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.events.schemas import EventCategory, PipelineEvent
from app.infrastructure.cache.redis_client import get_redis, redis_is_configured

logger = get_logger(__name__)

CHANNEL_PREFIX = "ss:realtime:tenant"


def tenant_channel(tenant_id: str) -> str:
    return f"{CHANNEL_PREFIX}:{tenant_id}"


async def publish_realtime(
    tenant_id: str,
    message_type: str,
    data: Dict[str, Any],
    *,
    category: Optional[EventCategory] = None,
) -> None:
    if not redis_is_configured():
        return
    payload = {
        "type": message_type,
        "data": data,
        "category": category.value if category else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        client = await get_redis()
        await client.publish(tenant_channel(tenant_id), json.dumps(payload, separators=(",", ":")))
    except Exception as exc:
        logger.warning("realtime_publish_failed", error=str(exc))


async def publish_event_processed(
    event: PipelineEvent,
    result: Dict[str, Any],
) -> None:
    await publish_realtime(
        event.tenant_id,
        "stream_event",
        {
            "stream_id": event.stream_id,
            "event_type": event.event_type,
            "category": event.category.value,
            "risk_score": result.get("risk_score", 0),
            "attack_created": result.get("attack_created", False),
            "is_proxy": result.get("is_proxy", False),
            "blocked": result.get("blocked", False),
        },
        category=event.category,
    )


async def publish_suspicious_signal(event: PipelineEvent, reason: str, score: float) -> None:
    await publish_realtime(
        event.tenant_id,
        "suspicious_event",
        {
            "stream_id": event.stream_id,
            "event_type": event.event_type,
            "reason": reason,
            "risk_score": score,
            "ip_address": event.ip_address,
            "username": event.platform_username,
        },
        category=EventCategory.SUSPICIOUS,
    )
