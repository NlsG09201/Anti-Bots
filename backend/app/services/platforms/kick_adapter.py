"""Kick platform adapter — public API viewer/chat sync."""

from __future__ import annotations

from typing import List

from app.core.logging import get_logger
from app.infrastructure.database.models import Platform, Stream
from app.integrations.kick.client import KickAPIClient
from app.services.platforms.base import LiveStatus, PlatformAdapter, ViewerSnapshot
from app.services.platforms.oauth_tokens import get_stream_access_token

logger = get_logger(__name__)


class KickPlatformAdapter(PlatformAdapter):
    platform = Platform.KICK

    async def supports_oauth(self) -> bool:
        return True

    async def _client(self, stream: Stream) -> KickAPIClient:
        token = await get_stream_access_token(stream)
        return KickAPIClient(access_token=token)

    async def fetch_live_status(self, stream: Stream) -> LiveStatus:
        slug = (stream.settings or {}).get("login") or stream.channel_name.lower()
        client = await self._client(stream)
        try:
            live = await client.get_livestream(slug)
        except Exception as exc:
            logger.warning("kick_live_status_failed", slug=slug, error=str(exc))
            return LiveStatus(is_live=False)
        if not live:
            return LiveStatus(is_live=False)
        return LiveStatus(
            is_live=True,
            viewer_count=int(live.get("viewer_count") or 0),
            title=live.get("title"),
            external_live_id=str(live.get("id", "")),
        )

    async def fetch_viewers(self, stream: Stream) -> List[ViewerSnapshot]:
        slug = (stream.settings or {}).get("login") or stream.channel_name.lower()
        client = await self._client(stream)
        try:
            channel = await client.get_channel(slug)
        except Exception as exc:
            logger.warning("kick_channel_failed", slug=slug, error=str(exc))
            return []

        chatroom_id = channel.get("chatroom", {}).get("id")
        if not chatroom_id:
            return []

        messages = await client.get_chat_messages(int(chatroom_id), limit=100)
        seen: set[str] = set()
        viewers: List[ViewerSnapshot] = []
        for msg in messages:
            user = msg.get("sender") or msg.get("user") or {}
            uid = str(user.get("id") or user.get("username") or "")
            username = user.get("username") or user.get("slug")
            if not uid or uid in seen:
                continue
            seen.add(uid)
            viewers.append(
                ViewerSnapshot(
                    platform_user_id=uid,
                    platform_username=username,
                    is_in_chat=True,
                    metadata={"source": "kick_chat"},
                )
            )
        return viewers
