"""Kick platform adapter — public API viewer/chat sync."""

from __future__ import annotations

from typing import List

from app.infrastructure.database.models import Platform, Stream
from app.integrations.kick.client import KickAPIClient
from app.services.platforms.base import LiveStatus, PlatformAdapter, ViewerSnapshot
from app.services.platforms.oauth_tokens import get_stream_access_token


class KickPlatformAdapter(PlatformAdapter):
    platform = Platform.KICK

    async def supports_oauth(self) -> bool:
        return True

    async def _client(self, stream: Stream) -> KickAPIClient:
        token = await get_stream_access_token(stream)
        if not token:
            from app.integrations.kick.oauth import KickOAuth

            token = await KickOAuth().get_app_access_token()
        return KickAPIClient(access_token=token)

    async def fetch_live_status(self, stream: Stream) -> LiveStatus:
        client = await self._client(stream)
        broadcaster_id = str(stream.external_id or "")
        if not broadcaster_id.isdigit():
            broadcaster_id = await client.get_broadcaster_id_by_slug(
                (stream.settings or {}).get("login") or stream.channel_name
            ) or ""
            if broadcaster_id:
                stream.external_id = broadcaster_id
        if not broadcaster_id.isdigit() and client.access_token:
            # Older monitor builds overwrote external_id with the livestream
            # UUID. Recover the broadcaster ID from the connected Kick account.
            from app.integrations.kick.oauth import KickOAuth

            profile = await KickOAuth().fetch_user(client.access_token)
            broadcaster_id = str(profile.get("id") or profile.get("user_id") or "")
            if broadcaster_id.isdigit():
                stream.external_id = broadcaster_id
        if not broadcaster_id.isdigit():
            raise RuntimeError("No se pudo resolver el ID del canal Kick; vuelve a conectarlo.")
        live = await client.get_user_livestream(broadcaster_id)
        if not live:
            return LiveStatus(is_live=False)
        return LiveStatus(
            is_live=True,
            viewer_count=int(live.get("viewer_count") or 0),
            title=live.get("title"),
            external_live_id=str(live.get("id", "")),
        )

    async def fetch_viewers(self, stream: Stream) -> List[ViewerSnapshot]:
        # Kick's documented Events API sends chat messages, not a complete
        # participant roster. Verified chat webhooks populate active sessions.
        return []
