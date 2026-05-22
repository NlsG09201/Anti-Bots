"""
Worker arq (equivalente BullMQ en Python).

Ejecutar: arq app.workers.arq_worker.WorkerSettings
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

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
    # Schedule discovery batch every minute
    from arq import create_pool
    from arq.connections import RedisSettings
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    pool = await create_pool(redis_settings)
    await pool.enqueue_job("discovery_batch_job", _queue_name=UNIFIED_QUEUE, _job_id="discovery_init_batch")
    await pool.enqueue_job("reconnect_monitors_job", _queue_name=UNIFIED_QUEUE, _job_id="reconnect_init")
    await pool.close()


async def shutdown(ctx: dict) -> None:
    logger.info("arq_worker_shutdown")


async def ai_train_models_job(ctx: dict) -> Dict[str, Any]:
    from app.ai_intel.learning.adaptive import AdaptiveLearner
    from app.ai_intel.training.pipeline import TrainingPipeline

    train_result = await TrainingPipeline().run()
    tune_result = await AdaptiveLearner().tune_from_feedback()
    return {"training": train_result, "adaptive": tune_result}


async def twitchbots_verify_batch_job(
    ctx: dict,
    tenant_id: str,
    users: List[Dict[str, Any]],
    *,
    stream_id: Optional[str] = None,
) -> Dict[str, Any]:
    from uuid import UUID

    from app.infrastructure.database.session import AsyncSessionLocal
    from app.services.twitchbots.verification_service import (
        get_twitchbots_verification_service,
    )

    svc = get_twitchbots_verification_service()
    results = await svc.verify_batch(tenant_id, users, stream_id=stream_id)
    applied = 0
    if stream_id:
        try:
            async with AsyncSessionLocal() as db:
                applied = await svc.apply_to_sessions(db, UUID(stream_id), results)
                await db.commit()
        except Exception as exc:
            logger.warning("twitchbots_apply_sessions_failed", error=str(exc)[:150])
    known = sum(1 for r in results.values() if r.is_known_bot)
    return {
        "verified": len(results),
        "known_bots": known,
        "sessions_updated": applied,
    }


async def platform_health_audit_job(ctx: dict) -> Dict[str, Any]:
    from app.services.platform_health.engine import get_platform_health_engine

    overview = await get_platform_health_engine().audit_once()
    return {
        "streams": len(overview.streams),
        "summary": overview.summary,
        "worker_alive": overview.system.worker_alive,
    }


async def weka_j48_train_job(
    ctx: dict,
    tenant_id: Optional[str] = None,
    source: str = "mixed",
    include_twitch_insights: bool = True,
) -> Dict[str, Any]:
    from uuid import UUID

    from app.infrastructure.database.session import AsyncSessionLocal
    from app.ml.weka_j48.service import get_weka_j48_service

    if not tenant_id:
        return {"ok": False, "error": "tenant_id_required"}
    async with AsyncSessionLocal() as db:
        result = await get_weka_j48_service().train_for_tenant(
            db,
            UUID(tenant_id),
            source=source,  # type: ignore[arg-type]
            include_twitch_insights=include_twitch_insights,
        )
        await db.commit()
    return result


async def discovery_batch_job(ctx: dict) -> Dict[str, Any]:
    from app.services.monitoring.discovery_engine import get_live_discovery_engine

    count = await get_live_discovery_engine().enqueue_discovery_batch()
    
    # Reschedule in 60 seconds
    from arq import create_pool
    from arq.connections import RedisSettings
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    pool = await create_pool(redis_settings)
    await pool.enqueue_job(
        "discovery_batch_job",
        _queue_name=UNIFIED_QUEUE,
        _defer_by=60,
        _job_id=f"discovery_batch_{int(time.time() / 60) + 1}"
    )
    # Also trigger a health check
    await pool.enqueue_job("health_check_job", _queue_name=UNIFIED_QUEUE)
    await pool.close()
    
    return {"enqueued": count}


async def check_stream_status_job(ctx: dict, stream_id: str) -> Dict[str, Any]:
    from app.services.monitoring.discovery_engine import get_live_discovery_engine

    return await get_live_discovery_engine().check_stream_status(stream_id)


async def poll_stream_metrics_job(ctx: dict, stream_id: str) -> Dict[str, Any]:
    from app.services.monitoring.discovery_engine import get_live_discovery_engine

    result = await get_live_discovery_engine().poll_metrics(stream_id)
    
    # If still live, reschedule in 15 seconds
    if result.get("viewers") is not None:
        from arq import create_pool
        from arq.connections import RedisSettings
        redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
        pool = await create_pool(redis_settings)
        await pool.enqueue_job(
            "poll_stream_metrics_job",
            stream_id,
            _queue_name=UNIFIED_QUEUE,
            _defer_by=15
        )
        await pool.close()
    
    return result


async def validate_stream_ai_job(ctx: dict, stream_id: str) -> Dict[str, Any]:
    from app.ai_intel.orchestrator import get_ai_orchestrator
    from app.infrastructure.database.session import AsyncSessionLocal
    from app.infrastructure.database.models import Stream
    from uuid import UUID

    async with AsyncSessionLocal() as db:
        stream = await db.get(Stream, UUID(stream_id))
        if not stream:
            return {"error": "stream_not_found"}

        ai = get_ai_orchestrator()
        # Simple AI validation logic: check if metrics are frozen or suspicious
        is_valid = True
        reason = "metrics_look_normal"

        # Example check: if viewers > 0 but no chat activity (simplified)
        if stream.viewer_count > 100 and not stream.is_live:
            is_valid = False
            reason = "high_viewers_but_offline_status"

        return {"stream_id": stream_id, "is_valid": is_valid, "reason": reason}


async def health_check_job(ctx: dict) -> Dict[str, Any]:
    from app.services.monitoring.discovery_engine import get_live_discovery_engine

    return await get_live_discovery_engine().run_health_check()


async def reconnect_monitors_job(ctx: dict) -> Dict[str, Any]:
    """Checks for stale monitors and restarts them."""
    from app.services.monitoring.orchestrator import get_platform_monitor_orchestrator
    from app.infrastructure.cache.redis_client import get_redis
    from app.infrastructure.cache.redis_schema import live_heartbeat_key
    from app.infrastructure.database.session import AsyncSessionLocal
    from app.infrastructure.database.models import Stream
    from sqlalchemy import select
    from uuid import UUID
    import time
    
    orch = get_platform_monitor_orchestrator()
    redis = await get_redis()
    
    reconnected = 0
    
    async with AsyncSessionLocal() as db:
        # Get all streams that should be monitored
        result = await db.execute(
            select(Stream).where(
                Stream.is_live == True,
                Stream.platform.in_(["kick", "youtube", "tiktok"])
            )
        )
        streams = result.scalars().all()
        
        for stream in streams:
            sid = str(stream.id)
            hb = await redis.get(live_heartbeat_key(sid))
            
            # If no heartbeat in 90 seconds but DB says live, restart monitor
            if not hb or (time.time() - float(hb)) > 90:
                logger.warning("monitor_stale_restarting", stream_id=sid, channel=stream.channel_name)
                await orch._start_monitor(stream)
                reconnected += 1
    
    # Reschedule in 30 seconds
    from arq import create_pool
    from arq.connections import RedisSettings
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    pool = await create_pool(redis_settings)
    await pool.enqueue_job(
        "reconnect_monitors_job",
        _queue_name=UNIFIED_QUEUE,
        _defer_by=30,
        _job_id=f"reconnect_batch_{int(time.time() / 30) + 1}"
    )
    await pool.close()
    
    return {"reconnected": reconnected}


class WorkerSettings:
    """Configuración arq — una función, múltiples colas vía _queue_name al encolar."""

    functions = [
        process_pipeline_event_job,
        ai_train_models_job,
        weka_j48_train_job,
        twitchbots_verify_batch_job,
        platform_health_audit_job,
        check_stream_status_job,
        poll_stream_metrics_job,
        validate_stream_ai_job,
        discovery_batch_job,
        health_check_job,
        reconnect_monitors_job,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = get_settings().event_queue_max_jobs
    job_timeout = get_settings().event_queue_job_timeout_seconds
    queue_name = queue_name_for(EventCategory.VIEWER)
