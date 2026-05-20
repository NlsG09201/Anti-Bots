"""YouTube Live adapter — Data API live chat + viewer stats."""

from __future__ import annotations

from typing import List

from app.core.logging import get_logger
from app.infrastructure.database.models import Platform, Stream
from app.integrations.youtube.client import YouTubeLiveClient
from app.services.platforms.base import LiveStatus, PlatformAdapter, ViewerSnapshot

logger = get_logger(__name__)


class YouTubePlatformAdapter(PlatformAdapter):
    platform = Platform.YOUTUBE

    async def fetch_live_status(self, stream: Stream) -> LiveStatus:
        client = YouTubeLiveClient()
        try:
            live = await client.search_live_by_channel(stream.channel_name)
        except Exception as exc:
            logger.warning("youtube_live_failed", channel=stream.channel_name, error=str(exc))
            return LiveStatus(is_live=False)
        if not live:
            return LiveStatus(is_live=False)
        stats = live.get("statistics") or {}
        return LiveStatus(
            is_live=True,
            viewer_count=int(stats.get("concurrentViewers") or stats.get("viewCount") or 0),
            title=live.get("snippet", {}).get("title"),
            external_live_id=live.get("id"),
        )

    async def fetch_viewers(self, stream: Stream) -> List[ViewerSnapshot]:
        client = YouTubeLiveClient()
        video_id = stream.external_id
        if not video_id:
            try:
                live = await client.search_live_by_channel(stream.channel_name)
                video_id = live.get("id") if live else None
            except Exception:
                return []
        if not video_id:
            return []

        try:
            messages = await client.list_live_chat_messages(video_id, max_results=200)
        except Exception as exc:
            logger.warning("youtube_chat_failed", video_id=video_id, error=str(exc))
            return []

        seen: set[str] = set()
        viewers: List[ViewerSnapshot] = []
        for item in messages:
            uid = item.get("platform_user_id") or item.get("id")
            username = item.get("platform_username")
            if not uid or uid in seen:
                continue
            seen.add(uid)
            viewers.append(
                ViewerSnapshot(
                    platform_user_id=str(uid),
                    platform_username=username,
                    is_in_chat=True,
                    metadata={"source": "youtube_live_chat"},
                )
            )
        return viewers
