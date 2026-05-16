from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings

settings = get_settings()


class TwitchOAuth:
    AUTH_URL = "https://id.twitch.tv/oauth2/authorize"
    TOKEN_URL = "https://id.twitch.tv/oauth2/token"
    VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"

    SCOPES = [
        "channel:read:subscriptions",
        "moderator:read:followers",
        "channel:read:stream_key",
        "user:read:email",
        "channel:manage:moderators",
        "moderator:manage:banned_users",
    ]

    def get_authorization_url(self, state: str) -> str:
        params = {
            "client_id": settings.twitch_client_id,
            "redirect_uri": settings.twitch_redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.SCOPES),
            "state": state,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": settings.twitch_client_id,
                    "client_secret": settings.twitch_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.twitch_redirect_uri,
                },
            )
            response.raise_for_status()
            return response.json()

    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": settings.twitch_client_id,
                    "client_secret": settings.twitch_client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            response.raise_for_status()
            return response.json()

    async def validate_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.VALIDATE_URL,
                headers={"Authorization": f"OAuth {access_token}"},
            )
            if response.status_code != 200:
                return None
            return response.json()
