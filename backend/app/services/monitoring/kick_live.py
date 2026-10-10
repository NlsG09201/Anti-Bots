"""Monitor Kick live status; chat messages arrive through verified webhooks."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app.core.logging import get_logger
from app.infrastructure.database.models import Platform, Stream
from app.services.monitoring.platform_events import emit_platform_event
from app.services.platform_health.registry import drop_tracker, get_or_create_tracker
from app.services.platforms.registry import get_platform_adapter

logger = get_logger(__name__)


class KickLiveMonitor:
    def __init__(self, stream_id: str, slug: str) -> None:
        self.stream_id = stream_id
        self.slug = slug
        self._health = get_or_create_tracker(stream_id, "kick", slug, slug=slug)
        self._poll_task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._running = False

    async def _poll_viewers(self) -> None:
        from app.infrastructure.database.session import AsyncSessionLocal
        from sqlalchemy import select
        from uuid import UUID

        adapter = get_platform_adapter(Platform.KICK)
        while self._running:
            try:
                import time
                t0 = time.perf_counter()
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(Stream).where(Stream.id == UUID(self.stream_id))
                    )
                    stream = result.scalar_one_or_none()
                    if not stream:
                        self._running = False
                        break
                    live = await adapter.fetch_live_status(stream)
                    
                    # Robust validation before stopping
                    if not live.is_live:
                        from app.services.monitoring.validation_engine import get_stream_validation_engine
                        validator = get_stream_validation_engine()
                        is_still_live, reason = await validator.validate_live_status(self.stream_id)
                        if not is_still_live:
                            await emit_platform_event(
                                db,
                                stream,
                                event_type="stream.offline",
                                metadata={"reason": reason},
                            )
                            self._running = False
                            await db.commit()
                            break
                        else:
                            live.is_live = True
                            logger.info("kick_validation_prevented_offline", stream_id=self.stream_id, reason=reason)

                    # Update Redis heartbeat
                    from app.infrastructure.cache.redis_client import get_redis
                    from app.infrastructure.cache.redis_schema import live_heartbeat_key
                    redis = await get_redis()
                    await redis.set(live_heartbeat_key(self.stream_id), "1", ex=45)

                    prev = stream.viewer_count
                    stream.is_live = live.is_live
                    stream.viewer_count = live.viewer_count

                    meta = dict(stream.settings or {})
                    if live.external_live_id:
                        meta["live_stream_id"] = live.external_live_id
                    history = list(meta.get("viewer_history", []))[-71:]
                    history.append({
                        "t": datetime.now(timezone.utc).isoformat(),
                        "count": live.viewer_count,
                    })
                    meta["viewer_history"] = history
                    meta["last_platform_poll"] = datetime.now(timezone.utc).isoformat()
                    stream.settings = meta
                    
                    import time
                    latency_ms = (time.perf_counter() - t0) * 1000.0
                    
                    # Update Health Monitoring Engine
                    from app.services.monitoring.health_engine import get_health_monitoring_engine
                    health_engine = get_health_monitoring_engine()
                    await health_engine.record_heartbeat(self.stream_id, "kick")
                    await health_engine.record_latency(self.stream_id, latency_ms)

                    self._health.record_poll(
                        viewer_count=live.viewer_count,
                        is_live=live.is_live,
                        latency_ms=latency_ms,
                    )
                    from app.viewer_flow import get_viewer_flow_engine

                    await get_viewer_flow_engine().record_viewer_pulse(
                        tenant_id=str(stream.tenant_id),
                        stream_id=self.stream_id,
                        platform=Platform.KICK,
                        channel_name=stream.channel_name,
                        viewer_count=live.viewer_count,
                        is_live=live.is_live,
                    )
                    if live.is_live and live.viewer_count - prev >= 80:
                        await emit_platform_event(
                            db,
                            stream,
                            event_type="viewer_spike",
                            metadata={
                                "from": prev,
                                "to": live.viewer_count,
                                "jump_percent": round(
                                    ((live.viewer_count - prev) / max(prev, 1)) * 100, 1
                                ),
                            },
                        )

                    if not live.is_live:
                        from app.services.monitoring.validation_engine import get_stream_validation_engine
                        validator = get_stream_validation_engine()
                        is_still_live, reason = await validator.validate_live_status(self.stream_id)
                        if not is_still_live:
                            await emit_platform_event(
                                db,
                                stream,
                                event_type="stream.offline",
                                metadata={"reason": reason},
                            )
                            self._running = False
                        else:
                            live.is_live = True
                            logger.info("kick_validation_prevented_offline", stream_id=self.stream_id, reason=reason)

                    await db.commit()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._health.record_error(str(exc))
                logger.warning("kick_poll_error", slug=self.slug, error=str(exc)[:200])
            await asyncio.sleep(25)

    async def _watchdog(self) -> None:
        """Watchdog to ensure tasks are alive."""
        while self._running:
            if self._poll_task and self._poll_task.done():
                logger.warning("kick_poll_died_restarting", slug=self.slug)
                self._poll_task = asyncio.create_task(self._poll_viewers())

            await asyncio.sleep(60)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_viewers())
        self._watchdog_task = asyncio.create_task(self._watchdog())
        logger.info("kick_monitor_started", slug=self.slug)

    async def stop(self) -> None:
        self._running = False
        drop_tracker(self.stream_id)
        for task in (self._poll_task, self._watchdog_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info("kick_monitor_stopped", slug=self.slug)
