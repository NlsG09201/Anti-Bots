"""Estado del pipeline de eventos en tiempo real."""

from fastapi import APIRouter

from app.api.dependencies import AnalystUser
from app.events.bus import get_event_bus
from app.events.queue import get_queue_stats
from app.events.streams import CONSUMER_GROUP, STREAM_MAIN, STREAM_PRIORITY
from app.core.config import get_settings

router = APIRouter(prefix="/events/pipeline", tags=["Event Pipeline"])
settings = get_settings()


@router.get("/status")
async def pipeline_status(current_user: AnalystUser = None):
    bus = get_event_bus()
    stream_stats = await bus.streams.pending_count()
    queue_stats = await get_queue_stats()
    return {
        "enabled": settings.event_pipeline_enabled,
        "queue_enabled": settings.event_queue_enabled,
        "pubsub_enabled": settings.event_realtime_pubsub_enabled,
        "streams": {
            "main": STREAM_MAIN,
            "priority": STREAM_PRIORITY,
            "consumer_group": CONSUMER_GROUP,
            "max_len": settings.event_stream_max_len,
            "batch_size": settings.event_consumer_batch_size,
            **stream_stats,
        },
        "queues": queue_stats,
        "architecture": {
            "ingress": "Redis Streams (XADD)",
            "processing": "arq worker (BullMQ-equivalent) + inline consumer",
            "realtime": "Redis Pub/Sub → WebSocket /ws/live",
            "categories": ["viewer", "follow", "message", "connection", "suspicious"],
        },
    }
