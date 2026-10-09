from typing import Any, Dict, List, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.integrations.twitch.oauth import twitch_credentials_valid

logger = get_logger(__name__)
settings = get_settings()


class TwitchHelixClient:
    """Helix con App Access Token (client credentials) para canales públicos."""

    TOKEN_URL = "https://id.twitch.tv/oauth2/token"
    API_BASE = "https://api.twitch.tv/helix"

    def __init__(self) -> None:
        self._app_token: Optional[str] = None

    @property
    def configured(self) -> bool:
        return twitch_credentials_valid()

    async def _get_app_token(self) -> str:
        if self._app_token:
            return self._app_token
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                self.TOKEN_URL,
                params={
                    "client_id": settings.twitch_client_id,
                    "client_secret": settings.twitch_client_secret,
                    "grant_type": "client_credentials",
                },
            )
            response.raise_for_status()
            self._app_token = response.json()["access_token"]
            return self._app_token

    def _headers(self, token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Client-Id": settings.twitch_client_id,
        }

    async def get_user_by_login(self, login: str) -> Optional[Dict[str, Any]]:
        if not self.configured:
            return None
        login = login.strip().lower().lstrip("@")
        token = await self._get_app_token()
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self.API_BASE}/users",
                params={"login": login},
                headers=self._headers(token),
            )
            if response.status_code != 200:
                return None
            users = response.json().get("data", [])
            return users[0] if users else None

    async def get_live_stream(self, user_id: str) -> Optional[Dict[str, Any]]:
        if not self.configured:
            return None
        token = await self._get_app_token()
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self.API_BASE}/streams",
                params={"user_id": user_id},
                headers=self._headers(token),
            )
            if response.status_code != 200:
                return None
            streams = response.json().get("data", [])
            return streams[0] if streams else None

    async def get_channel_status(self, user_id: str) -> Dict[str, Any]:
        live = await self.get_live_stream(user_id)
        if not live:
            return {"is_live": False, "viewer_count": 0, "title": None}
        return {
            "is_live": True,
            "viewer_count": live.get("viewer_count", 0),
            "title": live.get("title"),
            "game_name": live.get("game_name"),
        }

    async def get_chatters(
        self,
        broadcaster_id: str,
        moderator_id: str,
        user_access_token: str,
    ) -> List[Dict[str, Any]]:
        """Usuarios actualmente en el chat (requiere OAuth del broadcaster/mod)."""
        all_chatters: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        async with httpx.AsyncClient(timeout=20.0) as client:
            while True:
                params: Dict[str, Any] = {
                    "broadcaster_id": broadcaster_id,
                    "moderator_id": moderator_id,
                    "first": 1000,
                }
                if cursor:
                    params["after"] = cursor
                response = await client.get(
                    f"{self.API_BASE}/chat/chatters",
                    params=params,
                    headers=self._headers(user_access_token),
                )
                if response.status_code != 200:
                    response.raise_for_status()
                payload = response.json()
                all_chatters.extend(payload.get("data", []))
                cursor = payload.get("pagination", {}).get("cursor")
                if not cursor:
                    break
        return all_chatters
