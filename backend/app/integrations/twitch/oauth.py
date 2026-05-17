import os
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.integrations.twitch.constants import PRODUCTION_CALLBACK_URL

settings = get_settings()

_BAD_REDIRECT_MARKERS = (
    "vhbo",
    "anti-bots-api",
    "/login",
    "localhost",
    "127.0.0.1",
    "vercel.app/login",
)


def resolve_twitch_redirect_uri() -> str:
    """URI que debe estar registrada en Twitch Developer Console."""
    uri = (settings.twitch_redirect_uri or "").strip().rstrip("/")
    if os.getenv("RENDER") or settings.is_production:
        if not uri or any(m in uri for m in _BAD_REDIRECT_MARKERS):
            return PRODUCTION_CALLBACK_URL
    if not uri:
        return PRODUCTION_CALLBACK_URL
    return uri


def twitch_credentials_valid() -> bool:
    cid = (settings.twitch_client_id or "").strip()
    secret = (settings.twitch_client_secret or "").strip()
    if not cid or not secret:
        return False
    if cid == secret:
        return False
    if len(secret) < 20:
        return False
    return True


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
            "redirect_uri": resolve_twitch_redirect_uri(),
            "response_type": "code",
            "scope": " ".join(self.SCOPES),
            "state": state,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        redirect_uri = resolve_twitch_redirect_uri()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": settings.twitch_client_id,
                    "client_secret": settings.twitch_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
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
