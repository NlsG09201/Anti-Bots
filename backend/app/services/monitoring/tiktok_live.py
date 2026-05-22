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
                        await asyncio.sleep(30)
                        continue
                    prev = stream.viewer_count
                    stream.is_live = room.is_live
                    stream.viewer_count = room.viewer_count
                    if room.room_id:
                        stream.external_id = room.room_id
                    meta = dict(stream.settings or {})
                    meta["last_platform_poll"] = datetime.now(timezone.utc).isoformat()
                    stream.settings = meta
                    latency_ms = (time.perf_counter() - t0) * 1000.0
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
                        await emit_platform_event(
                            db,
                            stream,
                            event_type="stream.offline",
                            metadata={},
                        )
                        self._running = False
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

    async def start(self) -> None:
        self._running = True
        room = await fetch_tiktok_room(self.unique_id)
        if not room or not room.is_live:
            logger.info("tiktok_not_live", unique_id=self.unique_id)
        self._webcast = TikTokWebcastMonitor(self.unique_id, on_event=self._on_webcast)
        self._webcast_task = asyncio.create_task(self._webcast.run())
        self._poll_task = asyncio.create_task(self._poll_room())

    async def stop(self) -> None:
        self._running = False
        self._health.record_socket(False, "webcast")
        drop_tracker(self.stream_id)
        if self._webcast:
            await self._webcast.stop()
        for task in (self._webcast_task, self._poll_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
