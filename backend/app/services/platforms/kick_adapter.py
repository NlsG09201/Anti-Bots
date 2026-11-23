"""Kick platform adapter — public API viewer/chat sync."""

from __future__ import annotations

from typing import List

import httpx

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
        """Read the active-chat roster exposed by Kick's web client when available.

        Kick has no official chatters-list endpoint. This web endpoint is an
        optional best-effort source; verified chat.message.sent webhooks remain
        the supported source and are merged by PlatformSyncService.
        """
        broadcaster_id = str(stream.external_id or "").strip()
        if not broadcaster_id.isdigit():
            return []

        url = f"https://web.kick.com/api/v1/channels/{broadcaster_id}/chat/active-chatters"
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(8.0, connect=4.0),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0 StreamShield/1.0",
                    "Origin": "https://kick.com",
                    "Referer": f"https://kick.com/{stream.channel_name}",
                },
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "kick_active_chatters_unavailable",
                stream_id=str(stream.id),
                error_type=type(exc).__name__,
                status_code=(
                    exc.response.status_code
                    if isinstance(exc, httpx.HTTPStatusError)
                    else None
                ),
            )
            return []

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return []

        viewers: dict[str, ViewerSnapshot] = {}
        for role in ("chatters", "bots", "moderators", "ogs", "vips"):
            users = data.get(role)
            if not isinstance(users, list):
                continue
            for user in users:
                if not isinstance(user, dict):
                    continue
                username = str(user.get("username") or user.get("slug") or "").strip()
                user_id = str(user.get("user_id") or user.get("id") or user.get("slug") or username).strip()
                if not username or not user_id:
                    continue
                key = user_id.casefold()
                viewers[key] = ViewerSnapshot(
                    platform_user_id=user_id,
                    platform_username=username,
                    is_in_chat=True,
                    metadata={"source": "kick_chat", "chat_role": role},
                )
        logger.info(
            "kick_active_chatters_fetched",
            stream_id=str(stream.id),
            count=len(viewers),
        )
        return list(viewers.values())
