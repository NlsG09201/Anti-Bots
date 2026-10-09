"""YouTube Live adapter — Data API live chat + viewer stats."""

from __future__ import annotations

from typing import List

from app.infrastructure.database.models import Platform, Stream
from app.integrations.youtube.client import YouTubeLiveClient
from app.services.platforms.base import LiveStatus, PlatformAdapter, ViewerSnapshot
from app.services.platforms.oauth_tokens import get_stream_access_token


class YouTubePlatformAdapter(PlatformAdapter):
    platform = Platform.YOUTUBE

    async def supports_oauth(self) -> bool:
        return True

    async def _client(self, stream: Stream) -> YouTubeLiveClient:
        token = await get_stream_access_token(stream)
        return YouTubeLiveClient(access_token=token)

    async def fetch_live_status(self, stream: Stream) -> LiveStatus:
        client = await self._client(stream)
        channel = (stream.settings or {}).get("login") or stream.channel_name
        live = await client.search_live_by_channel(channel)

        if not live and stream.oauth_token_encrypted and stream.external_id:
            broadcasts = await client.get_live_broadcasts(stream.external_id)
            if broadcasts:
                video_id = broadcasts[0]["video_id"]
                stats = await client.get_video_statistics(video_id)
                return LiveStatus(
                    is_live=True,
                    viewer_count=int(stats.get("concurrent_viewers") or 0),
                    title=broadcasts[0].get("title"),
                    external_live_id=video_id,
                )

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
        client = await self._client(stream)
        video_id = (stream.settings or {}).get("live_video_id")
        if not video_id and len(stream.external_id or "") == 11:
            video_id = stream.external_id
        if not video_id:
            channel = (stream.settings or {}).get("login") or stream.channel_name
            live = await client.search_live_by_channel(channel)
            video_id = live.get("id") if live else None
        if not video_id:
            return []

        messages = await client.list_live_chat_messages(video_id, max_results=200)

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
