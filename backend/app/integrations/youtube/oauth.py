"""YouTube / Google OAuth for Live Data API."""

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.integrations.youtube.constants import YOUTUBE_SCOPES, resolve_youtube_redirect_uri

settings = get_settings()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def youtube_credentials_valid() -> bool:
    cid = (settings.youtube_client_id or "").strip()
    secret = (settings.youtube_client_secret or "").strip()
    return bool(cid and secret and cid != secret)


class YouTubeOAuth:
    def get_authorization_url(self, state: str) -> str:
        params = {
            "client_id": settings.youtube_client_id,
            "redirect_uri": resolve_youtube_redirect_uri(),
            "response_type": "code",
            "scope": " ".join(YOUTUBE_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.youtube_client_id,
                    "client_secret": settings.youtube_client_secret,
                    "redirect_uri": resolve_youtube_redirect_uri(),
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            return response.json()

    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.youtube_client_id,
                    "client_secret": settings.youtube_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            return response.json()
