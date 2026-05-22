"""TikTok Live platform adapter."""

from __future__ import annotations

from typing import List

from app.core.logging import get_logger
from app.integrations.tiktok.webcast import fetch_tiktok_room
from app.infrastructure.database.models import Platform, Stream
from app.services.platforms.base import LiveStatus, PlatformAdapter, ViewerSnapshot

logger = get_logger(__name__)


class TikTokPlatformAdapter(PlatformAdapter):
    platform = Platform.TIKTOK

    async def fetch_live_status(self, stream: Stream) -> LiveStatus:
        handle = (stream.settings or {}).get("login") or stream.channel_name
        handle = handle.strip().lstrip("@").lower()
        try:
            room = await fetch_tiktok_room(handle)
        except Exception as exc:
            logger.warning("tiktok_live_status_failed", handle=handle, error=str(exc))
            return LiveStatus(is_live=False)
        if not room:
            return LiveStatus(is_live=False)
        return LiveStatus(
            is_live=room.is_live,
            viewer_count=room.viewer_count,
            title=room.title,
            external_live_id=room.room_id,
        )

    async def fetch_viewers(self, stream: Stream) -> List[ViewerSnapshot]:
        return []
