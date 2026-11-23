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
        # external_id is the broadcaster ID. Older discovery code stored the
        # live-stream ID there, so resolve by the stable channel slug first.
        slug = (stream.settings or {}).get("login") or stream.channel_name
        resolved_id = await client.get_broadcaster_id_by_slug(slug)
        if resolved_id:
            broadcaster_id = resolved_id
            stream.external_id = resolved_id
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
        # Kick's public active-chatters endpoint lists participants currently
        # present in chat. It does not expose viewers who watch silently.
        channel_id = str(stream.external_id or "")
        slug = (stream.settings or {}).get("login") or stream.channel_name
        resolved_id = await (await self._client(stream)).get_broadcaster_id_by_slug(slug)
        if resolved_id:
            channel_id = resolved_id
            stream.external_id = resolved_id
        if not channel_id:
            raise RuntimeError("No se pudo resolver el ID del canal Kick para leer el chat.")

        chatters = await KickAPIClient().get_active_chatters(channel_id)
        return [
            ViewerSnapshot(
                platform_user_id=str(chatter["user_id"]),
                platform_username=str(chatter["username"]),
                is_in_chat=True,
                metadata={"source": "kick_chat", "role": chatter["role"]},
            )
            for chatter in chatters
        ]
