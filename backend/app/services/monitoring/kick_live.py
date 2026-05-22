"""Monitor Kick: Pusher chat + polling de viewers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.integrations.kick.client import KickAPIClient
from app.integrations.kick.pusher_ws import KickPusherClient
from app.infrastructure.database.models import Platform, Stream
from app.services.monitoring.platform_events import emit_platform_event, normalize_platform_event
from app.services.platforms.registry import get_platform_adapter

logger = get_logger(__name__)


class KickLiveMonitor:
    def __init__(self, stream_id: str, slug: str, chatroom_id: int) -> None:
        self.stream_id = stream_id
        self.slug = slug
        self.chatroom_id = chatroom_id
        self._pusher: Optional[KickPusherClient] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._pusher_task: Optional[asyncio.Task] = None
        self._running = False

    async def _on_pusher(self, raw_event: str, data: dict) -> None:
        from app.infrastructure.database.session import AsyncSessionLocal
        from sqlalchemy import select

        event_type, uid, username, meta = normalize_platform_event(
            Platform.KICK, raw_event, data
        )
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

    async def _poll_viewers(self) -> None:
        from app.infrastructure.database.session import AsyncSessionLocal
        from sqlalchemy import select
        from uuid import UUID

        client = KickAPIClient()
        adapter = get_platform_adapter(Platform.KICK)
        while self._running:
            try:
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
                    meta = dict(stream.settings or {})
                    history = list(meta.get("viewer_history", []))[-71:]
                    history.append({
                        "t": datetime.now(timezone.utc).isoformat(),
                        "count": live.viewer_count,
                    })
                    meta["viewer_history"] = history
                    meta["last_platform_poll"] = datetime.now(timezone.utc).isoformat()
                    stream.settings = meta
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
                logger.warning("kick_poll_error", slug=self.slug, error=str(exc)[:200])
            await asyncio.sleep(25)

    async def start(self) -> None:
        self._running = True
        self._pusher = KickPusherClient(self.chatroom_id, on_event=self._on_pusher)
        self._pusher_task = asyncio.create_task(self._pusher.run())
        self._poll_task = asyncio.create_task(self._poll_viewers())

    async def stop(self) -> None:
        self._running = False
        if self._pusher:
            await self._pusher.stop()
        for task in (self._pusher_task, self._poll_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


async def resolve_kick_chatroom(slug: str) -> Optional[int]:
    try:
        client = KickAPIClient()
        channel = await client.get_channel(slug.lower())
        if not channel or not isinstance(channel, dict):
            return None
        chatroom = channel.get("chatroom") or {}
        cid = chatroom.get("id")
        return int(cid) if cid else None
    except Exception as exc:
        logger.debug(
            "kick_chatroom_resolve_failed",
            slug=slug,
            error=str(exc)[:120],
        )
        return None
