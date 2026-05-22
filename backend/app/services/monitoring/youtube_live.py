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
                    prev = stream.viewer_count
                    stream.is_live = live.is_live
                    stream.viewer_count = live.viewer_count
                    if live.external_live_id:
                        stream.external_id = live.external_live_id
                        self.video_id = live.external_live_id

                    if not live.is_live:
                        await emit_platform_event(
                            db,
                            stream,
                            event_type="stream.offline",
                            metadata={},
                        )
                        self._running = False
                        await db.commit()
                        break

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
                    self._health.record_poll(
                        viewer_count=stream.viewer_count,
                        is_live=stream.is_live,
                        latency_ms=latency_ms,
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

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        self._health.record_socket(False, "poll")
        drop_tracker(self.stream_id)
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
