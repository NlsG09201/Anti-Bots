"""Monitor TikTok Live: Webcast + polling de room stats."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select

from app.core.logging import get_logger
from app.integrations.tiktok.webcast import TikTokWebcastMonitor, fetch_tiktok_room
from app.infrastructure.database.models import Platform, Stream
from app.services.monitoring.platform_events import emit_platform_event, normalize_platform_event
from app.services.platform_health.registry import drop_tracker, get_or_create_tracker

logger = get_logger(__name__)


class TikTokLiveMonitor:
    def __init__(self, stream_id: str, unique_id: str) -> None:
        self.stream_id = stream_id
        self.unique_id = unique_id.strip().lstrip("@").lower()
        self._health = get_or_create_tracker(
            stream_id, "tiktok", self.unique_id, slug=self.unique_id
        )
        self._webcast: Optional[TikTokWebcastMonitor] = None
        self._webcast_task: Optional[asyncio.Task] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._running = False

    async def _on_webcast(self, raw_event: str, data: dict) -> None:
        from app.infrastructure.database.session import AsyncSessionLocal

        event_type, uid, username, meta = normalize_platform_event(
            Platform.TIKTOK, raw_event, data
        )
        self._health.record_event(event_type)
        if event_type == "connection":
            self._health.record_socket(True, "webcast")
        elif event_type == "stream.offline":
            self._health.record_socket(False, "webcast")
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Stream).where(Stream.id == UUID(self.stream_id))
            )
            stream = result.scalar_one_or_none()
            if not stream:
                return
            await emit_platform_event(
                db,
                stream,
                event_type=event_type,
                platform_user_id=uid,
                platform_username=username,
                metadata=meta,
            )
            await db.commit()

    async def _poll_room(self) -> None:
        from app.infrastructure.database.session import AsyncSessionLocal

        while self._running:
            try:
                import time

                t0 = time.perf_counter()
                room = await fetch_tiktok_room(self.unique_id)
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(Stream).where(Stream.id == UUID(self.stream_id))
                    )
                    stream = result.scalar_one_or_none()
                    if not stream:
                        self._running = False
                        break
                    if not room:
                        # Validation before giving up
                        from app.services.monitoring.validation_engine import get_stream_validation_engine
                        validator = get_stream_validation_engine()
                        is_still_live, reason = await validator.validate_live_status(self.stream_id)
                        if not is_still_live:
                            await emit_platform_event(
                                db,
                                stream,
                                event_type="stream.offline",
                                metadata={"reason": "room_missing_and_validation_failed"},
                            )
                            self._running = False
                            await db.commit()
                            break
                        else:
                            await asyncio.sleep(15)
                            continue

                    # Update Redis heartbeat
                    from app.infrastructure.cache.redis_client import get_redis
                    from app.infrastructure.cache.redis_schema import live_heartbeat_key
                    redis = await get_redis()
                    await redis.set(live_heartbeat_key(self.stream_id), "1", ex=45)

                    prev = stream.viewer_count
                    stream.is_live = room.is_live
                    stream.viewer_count = room.viewer_count
                    
                    if room.room_id:
                        stream.external_id = room.room_id
                    meta = dict(stream.settings or {})
                    meta["last_platform_poll"] = datetime.now(timezone.utc).isoformat()
                    stream.settings = meta
                    
                    import time
                    latency_ms = (time.perf_counter() - t0) * 1000.0
                    
                    # Update Health Monitoring Engine
                    from app.services.monitoring.health_engine import get_health_monitoring_engine
                    health_engine = get_health_monitoring_engine()
                    await health_engine.record_heartbeat(self.stream_id, "tiktok")
                    await health_engine.record_latency(self.stream_id, latency_ms)

                    self._health.record_poll(
                        viewer_count=room.viewer_count,
                        is_live=room.is_live,
                        latency_ms=latency_ms,
                    )
                    from app.viewer_flow import get_viewer_flow_engine

                    await get_viewer_flow_engine().record_viewer_pulse(
                        tenant_id=str(stream.tenant_id),
                        stream_id=self.stream_id,
                        platform=Platform.TIKTOK,
                        channel_name=stream.channel_name,
                        viewer_count=room.viewer_count,
                        is_live=room.is_live,
                    )
                    if room.is_live and room.viewer_count - prev >= 50:
                        await emit_platform_event(
                            db,
                            stream,
                            event_type="viewer_spike",
                            metadata={
                                "from": prev,
                                "to": room.viewer_count,
                            },
                        )

                    if not room.is_live:
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
                            room.is_live = True
                            logger.info("tiktok_validation_prevented_offline", stream_id=self.stream_id, reason=reason)

                    await db.commit()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "tiktok_poll_error",
                    unique_id=self.unique_id,
                    error=str(exc)[:200],
                )
            if not self._running:
                break
            await asyncio.sleep(30)

    async def _watchdog(self) -> None:
        """Watchdog for TikTok tasks."""
        while self._running:
            if self._poll_task and self._poll_task.done():
                logger.warning("tiktok_poll_died_restarting", unique_id=self.unique_id)
                self._poll_task = asyncio.create_task(self._poll_room())
            if self._webcast_task and self._webcast_task.done():
                logger.warning("tiktok_webcast_died_restarting", unique_id=self.unique_id)
                self._webcast_task = asyncio.create_task(self._webcast.run())
            await asyncio.sleep(60)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        room = await fetch_tiktok_room(self.unique_id)
        if not room or not room.is_live:
            logger.info("tiktok_not_live", unique_id=self.unique_id)
        self._webcast = TikTokWebcastMonitor(self.unique_id, on_event=self._on_webcast)
        self._webcast_task = asyncio.create_task(self._webcast.run())
        self._poll_task = asyncio.create_task(self._poll_room())
        self._watchdog_task = asyncio.create_task(self._watchdog())

    async def stop(self) -> None:
        self._running = False
        self._health.record_socket(False, "webcast")
        drop_tracker(self.stream_id)
        if self._webcast:
            await self._webcast.stop()
        for task in (self._webcast_task, self._poll_task, self._watchdog_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
