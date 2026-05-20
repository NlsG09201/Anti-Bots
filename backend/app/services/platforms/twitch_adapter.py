"""Twitch platform adapter (Helix + optional IRC)."""

from __future__ import annotations

from typing import List

from app.core.security import decrypt_value
from app.infrastructure.database.models import Platform, Stream
from app.integrations.twitch.helix import TwitchHelixClient
from app.services.platforms.base import LiveStatus, PlatformAdapter, ViewerSnapshot


class TwitchPlatformAdapter(PlatformAdapter):
    platform = Platform.TWITCH

    def __init__(self) -> None:
        self._helix = TwitchHelixClient()

    async def supports_oauth(self) -> bool:
        return True

    async def fetch_live_status(self, stream: Stream) -> LiveStatus:
        login = stream.channel_name.lower()
        user = await self._helix.get_user_by_login(login)
        if not user:
            return LiveStatus(is_live=False, viewer_count=0)
        live = await self._helix.get_live_stream(user["id"])
        if not live:
            return LiveStatus(is_live=False, viewer_count=0)
        return LiveStatus(
            is_live=True,
            viewer_count=int(live.get("viewer_count") or 0),
            title=live.get("title"),
            external_live_id=str(live.get("id", "")),
        )

    async def fetch_viewers(self, stream: Stream) -> List[ViewerSnapshot]:
        if not stream.oauth_token_encrypted or not stream.external_id:
            return []
        token = decrypt_value(stream.oauth_token_encrypted)
        names = await self._helix.get_chatters(
            stream.external_id,
            stream.external_id,
            token,
        )
        return [
            ViewerSnapshot(
                platform_user_id=name.lower(),
                platform_username=name,
                is_in_chat=True,
                metadata={"source": "helix_chatters"},
            )
            for name in names
        ]
