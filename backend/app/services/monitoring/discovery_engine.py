"""
Live Discovery Engine: Robust multi-platform stream detection and monitoring.
Uses arq (BullMQ-style) for distributed job management and Redis for real-time state.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import get_redis, redis_is_configured
from app.infrastructure.cache.redis_schema import (
    live_discovery_key,
    live_heartbeat_key,
    live_metrics_key,
)
from app.infrastructure.database.models import Platform, Stream
from app.infrastructure.database.session import AsyncSessionLocal
from app.services.platforms.registry import get_platform_adapter

logger = get_logger(__name__)
settings = get_settings()

DISCOVERY_QUEUE = "ss:queue:discovery"


class LiveDiscoveryEngine:
    def __init__(self) -> None:
        self._redis_settings = RedisSettings.from_dsn(settings.redis_url)
        self._pool: Any = None

    async def _get_pool(self):
        if self._pool is None:
            self._pool = await create_pool(self._redis_settings)
        return self._pool

    async def enqueue_discovery_batch(self) -> int:
        """Find streams that need monitoring and enqueue status checks."""
        if not settings.platform_monitor_enabled:
            return 0

        async with AsyncSessionLocal() as db:
            # Select streams for Kick, YouTube, TikTok
            result = await db.execute(
                select(Stream).where(
                    Stream.platform.in_([Platform.KICK, Platform.YOUTUBE, Platform.TIKTOK])
                )
            )
            streams = result.scalars().all()

        pool = await self._get_pool()
        count = 0
        for stream in streams:
            # Enqueue a check job for each stream
            await pool.enqueue_job(
                "check_stream_status_job",
                str(stream.id),
                _queue_name=DISCOVERY_QUEUE,
                _job_id=f"check:{stream.id}:{int(time.time() / 60)}",  # Once per minute
            )
            count += 1
        
        logger.info("discovery_batch_enqueued", count=count)
        return count

    async def check_stream_status(self, stream_id: str) -> Dict[str, Any]:
        """Perform a robust check of a stream's live status."""
        async with AsyncSessionLocal() as db:
            stream = await db.get(Stream, UUID(stream_id))
            if not stream:
                return {"error": "stream_not_found"}

            adapter = get_platform_adapter(stream.platform)
            try:
                live = await adapter.fetch_live_status(stream)
            except Exception as exc:
                logger.warning("discovery_check_failed", stream_id=stream_id, error=str(exc))
                return {"error": str(exc)}

            # Update DB status
            was_live = stream.is_live
            stream.is_live = live.is_live
            stream.viewer_count = live.viewer_count
            if live.external_live_id:
                stream.external_id = live.external_live_id
            
            meta = dict(stream.settings or {})
            meta["last_discovery_check"] = datetime.now(timezone.utc).isoformat()
            meta["last_sync_title"] = live.title
            stream.settings = meta
            
            await db.commit()

            # Update Redis Cache
            redis = await get_redis()
            cache_key = live_discovery_key(stream.platform.value, stream.channel_name)
            await redis.set(
                cache_key,
                json.dumps({
                    "is_live": live.is_live,
                    "viewers": live.viewer_count,
                    "title": live.title,
                    "updated_at": time.time()
                }),
                ex=300
            )

            if live.is_live:
                # If live, ensure monitoring is active
                await self.ensure_monitoring(stream_id)
                
                # IA Validation if requested or if status is ambiguous
                if meta.get("require_ai_validation") or (live.is_live and live.viewer_count == 0):
                    pool = await self._get_pool()
                    await pool.enqueue_job(
                        "validate_stream_ai_job",
                        stream_id,
                        _queue_name=DISCOVERY_QUEUE
                    )

            return {
                "stream_id": stream_id,
                "is_live": live.is_live,
                "viewers": live.viewer_count,
                "was_live": was_live
            }

    async def ensure_monitoring(self, stream_id: str):
        """Ensure a live stream is being actively polled for metrics."""
        pool = await self._get_pool()
        # Enqueue a polling job if not already enqueued for this cycle
        await pool.enqueue_job(
            "poll_stream_metrics_job",
            stream_id,
            _queue_name=DISCOVERY_QUEUE,
            _job_id=f"poll:{stream_id}:{int(time.time() / 15)}", # Every 15s
        )

    async def poll_metrics(self, stream_id: str) -> Dict[str, Any]:
        """Fetch real-time metrics and update engines."""
        async with AsyncSessionLocal() as db:
            stream = await db.get(Stream, UUID(stream_id))
            if not stream or not stream.is_live:
                return {"status": "skipped"}

            adapter = get_platform_adapter(stream.platform)
            try:
                # We can use a faster path here if available, or just fetch_live_status
                live = await adapter.fetch_live_status(stream)
            except Exception as exc:
                logger.warning("metrics_poll_failed", stream_id=stream_id, error=str(exc))
                return {"error": str(exc)}

            # Update metrics in Redis for real-time dashboard
            redis = await get_redis()
            metrics_key = live_metrics_key(stream_id)
            metrics_data = {
                "viewers": live.viewer_count,
                "title": live.title,
                "ts": time.time()
            }
            await redis.set(metrics_key, json.dumps(metrics_data), ex=60)
            
            # Record heartbeat
            await redis.set(live_heartbeat_key(stream_id), "1", ex=45)

            # Update Viewer Flow Engine
            from app.viewer_flow import get_viewer_flow_engine
            await get_viewer_flow_engine().record_viewer_pulse(
                tenant_id=str(stream.tenant_id),
                stream_id=stream_id,
                platform=stream.platform,
                channel_name=stream.channel_name,
                viewer_count=live.viewer_count,
                is_live=live.is_live,
            )

            # Update Live Intel Engine
            from app.live_intel.engine import get_live_intel_engine
            await get_live_intel_engine().sample_stream(stream)

            # Broadcast update via Pub/Sub
            from app.events.realtime import publish_realtime
            await publish_realtime(
                str(stream.tenant_id),
                "stream_metrics_update",
                {
                    "stream_id": stream_id,
                    "platform": stream.platform.value,
                    "viewers": live.viewer_count,
                    "is_live": live.is_live
                }
            )

            # If stream went offline during poll, update DB
            if not live.is_live:
                stream.is_live = False
                await db.commit()
                logger.info("stream_went_offline_during_poll", stream_id=stream_id)

            return metrics_data

    async def sync_viewers_with_discovery(self, stream_id: str) -> Dict[str, Any]:
        """Trigger a fresh discovery poll and sync with Viewer Flow."""
        status = await self.check_stream_status(stream_id)
        if status.get("error"):
            return {"error": status["error"]}
        
        # Also poll metrics immediately to get fresh viewer count
        metrics = await self.poll_metrics(stream_id)
        return {
            "is_live": status.get("is_live", False),
            "viewer_count": metrics.get("viewers", 0),
            "updated_at": metrics.get("ts")
        }

    async def run_health_check(self) -> Dict[str, Any]:
        """Check for stale streams and dead monitors."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Stream).where(
                    Stream.is_live == True,
                    Stream.platform.in_([Platform.KICK, Platform.YOUTUBE, Platform.TIKTOK])
                )
            )
            live_streams = result.scalars().all()

        redis = await get_redis()
        stale_count = 0
        restarted_count = 0
        
        for stream in live_streams:
            sid = str(stream.id)
            hb = await redis.get(live_heartbeat_key(sid))
            if not hb:
                # No heartbeat in 45s -> monitor might be dead or stream ended
                stale_count += 1
                logger.warning("stale_stream_detected", stream_id=sid, channel=stream.channel_name)
                
                # Try one more check
                status = await self.check_stream_status(sid)
                if status.get("is_live"):
                    # Still live but no heartbeat -> restart polling
                    await self.ensure_monitoring(sid)
                    restarted_count += 1

        return {
            "stale_detected": stale_count,
            "restarted": restarted_count
        }


_ENGINE: Optional[LiveDiscoveryEngine] = None


def get_live_discovery_engine() -> LiveDiscoveryEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = LiveDiscoveryEngine()
    return _ENGINE
