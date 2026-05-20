"""
Worker arq (equivalente BullMQ en Python).

Ejecutar: arq app.workers.arq_worker.WorkerSettings
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.processor import process_pipeline_event
from app.events.queue import QUEUE_BY_CATEGORY, queue_name_for
from app.events.schemas import EventCategory, PipelineEvent
from app.events.streams import EventStreamService

logger = get_logger(__name__)
settings = get_settings()


async def process_pipeline_event_job(
    ctx: dict,
    event_payload: Dict[str, Any],
    stream_entry_id: Optional[str] = None,
) -> Dict[str, Any]:
    event = PipelineEvent.model_validate(event_payload)
    result = await process_pipeline_event(event, stream_entry_id=stream_entry_id)
    if stream_entry_id:
        streams = EventStreamService()
        stream_key = streams._stream_for_category(event.category)
        await streams.ack(stream_key, stream_entry_id)
    return result


async def startup(ctx: dict) -> None:
    logger.info("arq_worker_startup", queues=list(QUEUE_BY_CATEGORY.values()))


async def shutdown(ctx: dict) -> None:
    logger.info("arq_worker_shutdown")


async def ai_train_models_job(ctx: dict) -> Dict[str, Any]:
    from app.ai_intel.learning.adaptive import AdaptiveLearner
    from app.ai_intel.training.pipeline import TrainingPipeline

    train_result = await TrainingPipeline().run()
    tune_result = await AdaptiveLearner().tune_from_feedback()
    return {"training": train_result, "adaptive": tune_result}


class WorkerSettings:
    """Configuración arq — una función, múltiples colas vía _queue_name al encolar."""

    functions = [process_pipeline_event_job, ai_train_models_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = get_settings().event_queue_max_jobs
    job_timeout = get_settings().event_queue_job_timeout_seconds
    queue_name = queue_name_for(EventCategory.VIEWER)
