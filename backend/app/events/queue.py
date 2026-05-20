"""
Colas de trabajo estilo BullMQ (Python: arq sobre Redis).

Cada categoría tiene su cola: viewers, follows, messages, connections, suspicious.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.schemas import EventCategory, PipelineEvent
from app.infrastructure.cache.redis_client import redis_is_configured

logger = get_logger(__name__)
settings = get_settings()

# Cola unificada arq (BullMQ-style); categoría va en el payload del job
UNIFIED_QUEUE = "ss:queue:events"

QUEUE_BY_CATEGORY = {
    EventCategory.VIEWER: UNIFIED_QUEUE,
    EventCategory.FOLLOW: UNIFIED_QUEUE,
    EventCategory.MESSAGE: UNIFIED_QUEUE,
    EventCategory.CONNECTION: UNIFIED_QUEUE,
    EventCategory.SUSPICIOUS: UNIFIED_QUEUE,
}


def queue_name_for(category: EventCategory) -> str:
    return UNIFIED_QUEUE


async def enqueue_event_job(
    event: PipelineEvent,
    *,
    stream_entry_id: Optional[str] = None,
) -> Optional[str]:
    """Encola procesamiento en arq (BullMQ-equivalente)."""
    if not settings.event_queue_enabled or not redis_is_configured():
        return None
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        pool = await create_pool(redis_settings)
        job = await pool.enqueue_job(
            "process_pipeline_event_job",
            event.model_dump(mode="json"),
            stream_entry_id=stream_entry_id,
            _queue_name=UNIFIED_QUEUE,
            _job_id=f"{event.category.value}:{event.stream_id}:{event.enqueued_at}",
        )
        await pool.close()
        return job.job_id if job else None
    except Exception as exc:
        logger.warning("event_queue_enqueue_failed", error=str(exc))
        return None


async def get_queue_stats() -> Dict[str, Any]:
    if not redis_is_configured():
        return {"enabled": False}
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        pool = await create_pool(redis_settings)
        stats: Dict[str, Any] = {"enabled": True, "queues": {}}
        for cat, qname in QUEUE_BY_CATEGORY.items():
            stats["queues"][qname] = {"category": cat.value}
        await pool.close()
        return stats
    except Exception as exc:
        return {"enabled": True, "error": str(exc)}
