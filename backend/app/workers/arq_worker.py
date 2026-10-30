"""
Worker arq (equivalente BullMQ en Python).

Ejecutar: arq app.workers.arq_worker.WorkerSettings
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import case, select, update

from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.processor import process_pipeline_event
from app.events.queue import QUEUE_BY_CATEGORY, queue_name_for
from app.events.schemas import EventCategory, PipelineEvent
from app.events.streams import EventStreamService
from app.infrastructure.database.models import AuditLog, KickWebhookEvent, Platform, Stream

logger = get_logger(__name__)
settings = get_settings()
KICK_WEBHOOK_MAX_PROCESSING_ATTEMPTS = 10


async def process_pipeline_event_job(
    ctx: dict,
    event_payload: Dict[str, Any],
    stream_entry_id: Optional[str] = None,
) -> Dict[str, Any]:
    event = PipelineEvent.model_validate(event_payload)
    try:
        result = await process_pipeline_event(event, stream_entry_id=stream_entry_id)
    except Exception as exc:
        job_try = int(ctx.get("job_try", 1))
        if stream_entry_id and job_try >= settings.event_queue_max_tries:
            streams = EventStreamService()
            stream_key = streams._stream_for_category(event.category)
            await streams.dead_letter(
                stream_key=stream_key,
                entry_id=stream_entry_id,
                fields=event.to_stream_fields(),
                error_type=type(exc).__name__,
            )
            await streams.ack(stream_key, stream_entry_id)
            logger.error(
                "pipeline_event_dead_lettered_after_retries",
                entry_id=stream_entry_id,
                error_type=type(exc).__name__,
                attempts=job_try,
            )
        raise
    if stream_entry_id:
        streams = EventStreamService()
        stream_key = streams._stream_for_category(event.category)
        if await streams.dead_letter_rejected_result(
            stream_key=stream_key,
            entry_id=stream_entry_id,
            event=event,
            result=result,
        ):
            logger.warning(
                "pipeline_event_rejected_and_dead_lettered",
                entry_id=stream_entry_id,
                reason=result.get("error"),
            )
            return {**result, "dead_lettered": True}
        await streams.ack(stream_key, stream_entry_id)
    return result


def _normalize_kick_webhook(row: KickWebhookEvent) -> tuple[str, Optional[str], Optional[str], Dict[str, Any]]:
    payload = row.raw_payload
    actor: Dict[str, Any] = {}
    event_type = row.event_type
    normalized = "kick_event"
    if event_type == "chat.message.sent":
        actor = payload.get("sender") or {}
        normalized = "chat_message"
    elif event_type == "channel.followed":
        actor = payload.get("follower") or {}
        normalized = "follow"
    elif event_type in ("channel.subscription.new", "channel.subscription.renewal"):
        actor = payload.get("subscriber") or {}
        normalized = "subscription"
    elif event_type == "channel.subscription.gifts":
        actor = payload.get("gifter") or {}
        normalized = "gift"
    elif event_type == "kicks.gifted":
        actor = payload.get("sender") or {}
        normalized = "gift"
    elif event_type == "channel.reward.redemption.updated":
        actor = payload.get("redeemer") or {}
        normalized = "reward_redemption"
    elif event_type == "moderation.banned":
        actor = payload.get("banned_user") or {}
        normalized = "moderation_banned"
    elif event_type == "livestream.status.updated":
        normalized = "stream_online" if payload.get("is_live") else "stream_offline"
    elif event_type == "livestream.metadata.updated":
        normalized = "stream_metadata_updated"

    metadata = dict(payload)
    if event_type == "chat.message.sent":
        metadata["content"] = payload.get("content", "")
    metadata.update(
        {
            "kick_event_id": row.message_id,
            "kick_event_type": event_type,
            "kick_event_version": row.event_version,
            "timestamp": row.message_timestamp.isoformat(),
        }
    )
    return normalized, str(actor.get("user_id") or "") or None, actor.get("username"), metadata


async def process_kick_webhook_event_job(ctx: dict, webhook_event_id: str) -> Dict[str, Any]:
    """Run verified Kick events through the standard threat pipeline transactionally."""
    from app.api.v1.schemas import EventIngest
    from app.infrastructure.database.session import AsyncSessionLocal
    from app.services.ingest.event_ingest import process_stream_event

    webhook_uuid = UUID(webhook_event_id)
    try:
        async with AsyncSessionLocal() as db:
            row = await db.scalar(
                select(KickWebhookEvent)
                .where(KickWebhookEvent.id == webhook_uuid)
                .with_for_update()
            )
            if not row or row.processing_status in ("processed", "ignored", "expired", "failed"):
                return {"status": row.processing_status if row else "missing"}
            row.processing_status = "processing"
            stream = await db.scalar(select(Stream).where(Stream.id == row.stream_id)) if row.stream_id else None
            if not stream:
                row.processing_status = "ignored"
                row.processed_at = datetime.now(timezone.utc)
                await db.commit()
                return {"status": "ignored"}

            normalized, user_id, username, metadata = _normalize_kick_webhook(row)
            if row.event_type == "livestream.status.updated":
                stream.is_live = bool(row.raw_payload.get("is_live"))
            elif row.event_type == "livestream.metadata.updated":
                channel_metadata = row.raw_payload.get("metadata") or {}
                stream_settings = dict(stream.settings or {})
                stream_settings["kick_live_metadata"] = channel_metadata
                if channel_metadata.get("title"):
                    stream_settings["live_title"] = channel_metadata["title"]
                stream.settings = stream_settings
            source = "platform_kick" if row.event_type == "chat.message.sent" else "kick_webhook"
            await process_stream_event(
                db,
                stream,
                stream.tenant_id,
                EventIngest(
                    event_type=normalized,
                    platform_user_id=user_id,
                    platform_username=username,
                    metadata=metadata,
                ),
                source=source,
            )
            row.processing_status = "processed"
            row.processed_at = datetime.now(timezone.utc)
            row.last_error = None
            db.add(
                AuditLog(
                    tenant_id=stream.tenant_id,
                    action="kick.webhook.processed",
                    resource_type="kick_webhook_event",
                    resource_id=row.message_id,
                    details={"event_type": row.event_type, "stream_id": str(stream.id)},
                )
            )
            await db.commit()
            return {"status": "processed", "event_type": row.event_type}
    except Exception as exc:
        async with AsyncSessionLocal() as db:
            row = await db.scalar(
                select(KickWebhookEvent).where(KickWebhookEvent.id == webhook_uuid)
            )
            if row and row.processing_status != "processed":
                row.processing_attempts += 1
                row.processing_status = (
                    "failed"
                    if row.processing_attempts >= KICK_WEBHOOK_MAX_PROCESSING_ATTEMPTS
                    else "pending"
                )
                row.last_error = type(exc).__name__
                await db.commit()
        logger.exception(
            "kick_webhook_processing_failed",
            event_id=webhook_event_id,
            error_type=type(exc).__name__,
        )
        raise


async def recover_kick_webhook_events_job(ctx: dict) -> Dict[str, int]:
    """Requeue durable pending deliveries after worker or Redis interruptions."""
    from app.events.queue import enqueue_kick_webhook_job
    from app.infrastructure.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.scalars(
                    select(KickWebhookEvent)
                    .where(KickWebhookEvent.processing_status == "pending")
                    .where(
                        KickWebhookEvent.processing_attempts
                        < KICK_WEBHOOK_MAX_PROCESSING_ATTEMPTS
                    )
                    .order_by(KickWebhookEvent.received_at)
                    .limit(200)
                )
            ).all()
        )
        event_ids = [str(row.id) for row in rows]
    enqueued = 0
    for event_id in event_ids:
        if await enqueue_kick_webhook_job(event_id):
            enqueued += 1
    return {"pending": len(event_ids), "enqueued": enqueued}


async def reconcile_kick_subscriptions_job(ctx: dict) -> Dict[str, int]:
    """Repair missing documented Kick subscriptions and persist health state."""
    from app.integrations.kick.oauth import KickOAuth
    from app.infrastructure.database.session import AsyncSessionLocal
    from app.services.platforms.oauth_tokens import get_stream_access_token

    async with AsyncSessionLocal() as db:
        streams = list(
            (
                await db.scalars(
                    select(Stream).where(Stream.platform == Platform.KICK)
                )
            ).all()
        )
        checked = failed = 0
        for stream in streams:
            stream_meta = stream.settings or {}
            configured = bool(
                stream_meta.get(
                    "kick_webhook_enabled",
                    stream_meta.get("kick_chat_webhook_subscribed", False),
                )
            )
            if not configured or (
                stream_meta.get("is_owned") and not stream.oauth_token_encrypted
            ):
                continue
            if not str(stream.external_id).isdigit():
                continue
            try:
                token = await get_stream_access_token(stream)
                app_token = token is None
                oauth = KickOAuth()
                token = token or await oauth.get_app_access_token()
                result = await oauth.reconcile_event_subscriptions(
                    token,
                    str(stream.external_id) if app_token else None,
                    previously_requested=(stream.settings or {}).get("kick_webhook_subscriptions", []),
                    requested_at=(stream.settings or {}).get("kick_webhook_subscriptions_requested_at"),
                )
                meta = dict(stream.settings or {})
                meta["kick_webhook_callback_url"] = get_settings().kick_webhook_callback_url
                meta["kick_webhook_subscriptions_checked_at"] = datetime.now(timezone.utc).isoformat()
                meta["kick_webhook_subscriptions"] = (
                    result.get("subscribed", [])
                    + result.get("created", [])
                    + result.get("assumed", [])
                )
                if result.get("created"):
                    meta["kick_webhook_subscriptions_requested_at"] = datetime.now(timezone.utc).isoformat()
                meta["kick_webhook_subscriptions_verified"] = bool(result.get("verified_by_api"))
                meta["kick_webhook_subscription_error"] = (
                    ",".join(result.get("failed", [])) or None
                )
                meta["kick_chat_webhook_subscribed"] = "chat.message.sent" in meta["kick_webhook_subscriptions"]
                meta["kick_webhook_enabled"] = bool(meta["kick_webhook_subscriptions"])
                stream.settings = meta
                checked += 1
                if result.get("failed"):
                    failed += 1
                    logger.warning(
                        "kick_subscription_reconcile_partial",
                        stream_id=str(stream.id),
                        failed_events=result["failed"],
                    )
            except Exception as exc:
                meta = dict(stream.settings or {})
                meta["kick_webhook_subscriptions_checked_at"] = datetime.now(timezone.utc).isoformat()
                meta["kick_webhook_subscription_error"] = type(exc).__name__
                stream.settings = meta
                failed += 1
                logger.warning(
                    "kick_subscription_reconcile_failed",
                    stream_id=str(stream.id),
                    error_type=type(exc).__name__,
                )
        await db.commit()
    return {"checked": checked, "failed": failed}


async def purge_kick_webhook_payloads_job(ctx: dict) -> Dict[str, int]:
    """Purge raw provider payloads at Kick's documented 24-hour cache limit."""
    from datetime import timedelta
    from app.infrastructure.database.session import AsyncSessionLocal

    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=get_settings().kick_webhook_payload_retention_hours
    )
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(KickWebhookEvent)
            .where(
                KickWebhookEvent.received_at < cutoff,
                KickWebhookEvent.raw_payload != {},
            )
            .values(
                raw_payload={},
                processing_status=case(
                    (KickWebhookEvent.processing_status.in_(("pending", "processing")), "expired"),
                    else_=KickWebhookEvent.processing_status,
                ),
                last_error=case(
                    (KickWebhookEvent.processing_status.in_(("pending", "processing")), "raw_payload_retention_expired"),
                    else_=KickWebhookEvent.last_error,
                ),
            )
        )
        await db.commit()
        return {"purged_payloads": result.rowcount or 0}


async def startup(ctx: dict) -> None:
    logger.info("arq_worker_startup", queues=list(QUEUE_BY_CATEGORY.values()))
    cfg = get_settings()
    if cfg.live_intel_enabled and cfg.platform_monitor_worker_mode_resolved:
        from app.live_intel import get_live_intel_engine

        engine = get_live_intel_engine()
        ctx["live_intel_engine"] = engine
        try:
            await engine.start()
            logger.info("live_intel_sampler_in_worker")
        except Exception as exc:
            logger.exception("live_intel_worker_start_failed", error=str(exc)[:180])
    # Schedule discovery batch every minute
    from arq import create_pool
    from arq.connections import RedisSettings
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    pool = await create_pool(redis_settings)
    await pool.enqueue_job("discovery_batch_job", _queue_name=UNIFIED_QUEUE, _job_id="discovery_init_batch")
    await pool.enqueue_job("reconnect_monitors_job", _queue_name=UNIFIED_QUEUE, _job_id="reconnect_init")
    await pool.close()


async def shutdown(ctx: dict) -> None:
    engine = ctx.get("live_intel_engine")
    if engine:
        await engine.stop()
    from app.services.ai.openai_engine import close_openai_client

    await close_openai_client()
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
        process_kick_webhook_event_job,
        recover_kick_webhook_events_job,
        reconcile_kick_subscriptions_job,
        purge_kick_webhook_payloads_job,
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
    cron_jobs = [
        cron(recover_kick_webhook_events_job, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(reconcile_kick_subscriptions_job, minute={7, 37}),
        cron(purge_kick_webhook_payloads_job, minute=20),
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = get_settings().event_queue_max_jobs
    job_timeout = get_settings().event_queue_job_timeout_seconds
    max_tries = get_settings().event_queue_max_tries
    queue_name = queue_name_for(EventCategory.VIEWER)
