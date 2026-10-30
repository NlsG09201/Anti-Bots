"""
Colas de trabajo estilo BullMQ (Python: arq sobre Redis).

Cada categoría tiene su cola: viewers, follows, messages, connections, suspicious.
"""

from __future__ import annotations

from uuid import uuid4
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
        job_id = f"{event.category.value}:{event.stream_id}:{event.enqueued_at}"
        try:
            job = await pool.enqueue_job(
                "process_pipeline_event_job",
                event.model_dump(mode="json"),
                stream_entry_id=stream_entry_id,
                _queue_name=UNIFIED_QUEUE,
                _job_id=job_id,
            )
            if job:
                return job.job_id

            # arq returns None for both an active job and a retained result.
            # A retained failed result is not an accepted delivery: allow the
            # stream handler to retry inline, and leave the entry pending if
            # that retry fails too.
            from arq.jobs import Job

            duplicate = Job(job_id, pool, _queue_name=UNIFIED_QUEUE)
            result = await duplicate.result_info()
            if result is not None:
                if result.success:
                    return job_id
                logger.warning(
                    "event_queue_duplicate_has_failed_result",
                    error_type=type(result.result).__name__,
                )
                return None

            status = await duplicate.status()
            status_value = getattr(status, "value", status)
            if status_value in {"queued", "deferred", "in_progress"}:
                return job_id

            logger.warning(
                "event_queue_duplicate_not_active",
                status=str(status_value),
            )
            return None
        finally:
            try:
                await pool.close()
            except Exception as exc:
                logger.warning(
                    "event_queue_pool_close_failed",
                    error_type=type(exc).__name__,
                )
    except Exception as exc:
        logger.warning("event_queue_enqueue_failed", error=str(exc))
        return None


async def enqueue_kick_webhook_job(webhook_event_id: str) -> Optional[str]:
    """Queue a durable, already-verified Kick delivery for threat processing."""
    if not settings.event_queue_enabled or not redis_is_configured():
        return None
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        try:
            job = await pool.enqueue_job(
                "process_kick_webhook_event_job",
                webhook_event_id,
                _queue_name=UNIFIED_QUEUE,
                _job_id=f"kick-webhook:{webhook_event_id}:{uuid4().hex}",
            )
        finally:
            await pool.close()
        return job.job_id if job else f"kick-webhook:{webhook_event_id}"
    except Exception as exc:
        logger.warning("kick_webhook_queue_error", error_type=type(exc).__name__)
        return None


async def get_queue_stats() -> Dict[str, Any]:
    configured = redis_is_configured()
    if not settings.event_queue_enabled or not configured:
        return {
            "enabled": False,
            "configured": configured,
            "queues": {},
        }
    pool = None
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        pool = await create_pool(redis_settings)
        queued_count = await pool.zcard(UNIFIED_QUEUE)
        return {
            "enabled": True,
            "configured": True,
            "available": True,
            "queues": {
                UNIFIED_QUEUE: {
                    "queued_count": queued_count,
                    "categories": [category.value for category in QUEUE_BY_CATEGORY],
                }
            },
        }
    except Exception as exc:
        logger.warning("event_queue_stats_failed", error_type=type(exc).__name__)
        return {
            "enabled": True,
            "configured": True,
            "available": False,
            "error_type": type(exc).__name__,
            "queues": {},
        }
    finally:
        if pool is not None:
            try:
                await pool.close()
            except Exception as exc:
                logger.warning(
                    "event_queue_stats_pool_close_failed",
                    error_type=type(exc).__name__,
                )
