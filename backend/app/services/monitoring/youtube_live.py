"""Monitor YouTube Live: polling de live chat y estadísticas."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select

from app.core.logging import get_logger
from app.integrations.youtube.client import YouTubeLiveClient
from app.infrastructure.database.models import Platform, Stream
from app.services.monitoring.platform_events import emit_platform_event, normalize_platform_event
from app.services.platform_health.registry import drop_tracker, get_or_create_tracker
from app.services.platforms.registry import get_platform_adapter

logger = get_logger(__name__)


class YouTubeLiveMonitor:
    def __init__(self, stream_id: str, channel_query: str, video_id: Optional[str] = None) -> None:
        self.stream_id = stream_id
        self.channel_query = channel_query
        self.video_id = video_id
        self._health = get_or_create_tracker(
            stream_id, "youtube", channel_query, slug=channel_query
        )
        self._health.record_socket(True, "poll")
        self._task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._running = False
        self._page_token: Optional[str] = None
        self._chat_id: Optional[str] = None
        self._seen_message_ids: set[str] = set()

    async def _loop(self) -> None:
        from app.infrastructure.database.session import AsyncSessionLocal

        client = YouTubeLiveClient()
        adapter = get_platform_adapter(Platform.YOUTUBE)
        poll_ms = 5000

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
                            # Validation says we are still live (or retry pending)
                            live.is_live = True
                            logger.info("youtube_validation_prevented_offline", stream_id=self.stream_id, reason=reason)

                    # Update Redis heartbeat
                    from app.infrastructure.cache.redis_client import get_redis
                    from app.infrastructure.cache.redis_schema import live_heartbeat_key
                    redis = await get_redis()
                    await redis.set(live_heartbeat_key(self.stream_id), "1", ex=45)

                    prev = stream.viewer_count
                    stream.is_live = live.is_live
                    stream.viewer_count = live.viewer_count
                    if live.external_live_id:
                        stream.external_id = live.external_live_id
                        self.video_id = live.external_live_id

                    if live.viewer_count - prev >= 100:
                        await emit_platform_event(
                            db,
                            stream,
                            event_type="viewer_spike",
                            metadata={
                                "from": prev,
                                "to": live.viewer_count,
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
                            logger.info("youtube_validation_prevented_offline", stream_id=self.stream_id, reason=reason)

                    video_id = self.video_id or stream.external_id
                    if video_id:
                        stats = await client.get_video_statistics(video_id)
                        chat_id = stats.get("active_live_chat_id")
                        if chat_id:
                            self._chat_id = chat_id
                            chat = await client.get_live_chat_messages(
                                chat_id,
                                page_token=self._page_token,
                            )
                            poll_ms = int(chat.get("polling_interval_ms") or 5000)
                            self._page_token = chat.get("next_page_token")
                            for msg in chat.get("messages") or []:
                                mid = msg.get("id")
                                if mid and mid in self._seen_message_ids:
                                    continue
                                if mid:
                                    self._seen_message_ids.add(mid)
                                    if len(self._seen_message_ids) > 5000:
                                        self._seen_message_ids.clear()
                                et, uid, username, meta = normalize_platform_event(
                                    Platform.YOUTUBE,
                                    "chat_message",
                                    msg,
                                )
                                await emit_platform_event(
                                    db,
                                    stream,
                                    event_type=et,
                                    platform_user_id=uid,
                                    platform_username=username,
                                    metadata=meta,
                                )
                                self._health.record_event(et)

                    meta = dict(stream.settings or {})
                    meta["last_platform_poll"] = datetime.now(timezone.utc).isoformat()
                    stream.settings = meta
                    latency_ms = (time.perf_counter() - t0) * 1000.0
                    
                    # Update Health Monitoring Engine
                    from app.services.monitoring.health_engine import get_health_monitoring_engine
                    health_engine = get_health_monitoring_engine()
                    await health_engine.record_heartbeat(self.stream_id, "youtube")
                    await health_engine.record_latency(self.stream_id, latency_ms)

                    self._health.record_poll(
                        viewer_count=stream.viewer_count,
                        is_live=stream.is_live,
                        latency_ms=latency_ms,
                    )
                    from app.viewer_flow import get_viewer_flow_engine

                    await get_viewer_flow_engine().record_viewer_pulse(
                        tenant_id=str(stream.tenant_id),
                        stream_id=self.stream_id,
                        platform=Platform.YOUTUBE,
                        channel_name=stream.channel_name,
                        viewer_count=stream.viewer_count,
                        is_live=stream.is_live,
                    )
                    await db.commit()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._health.record_error(str(exc))
                logger.warning(
                    "youtube_monitor_error",
                    channel=self.channel_query,
                    error=str(exc)[:200],
                )
            await asyncio.sleep(max(poll_ms / 1000.0, 3.0))

    async def _watchdog(self) -> None:
        """Watchdog for YouTube tasks."""
        while self._running:
            if self._task and self._task.done():
                logger.warning("youtube_task_died_restarting", channel=self.channel_query)
                self._task = asyncio.create_task(self._loop())
            await asyncio.sleep(60)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        self._watchdog_task = asyncio.create_task(self._watchdog())
        logger.info("youtube_monitor_started", channel=self.channel_query)

    async def stop(self) -> None:
        self._running = False
        self._health.record_socket(False, "poll")
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
        drop_tracker(self.stream_id)
        logger.info("youtube_monitor_stopped", channel=self.channel_query)
