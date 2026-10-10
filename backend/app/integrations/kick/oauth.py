"""Kick OAuth 2.1 with PKCE."""

from __future__ import annotations

from typing import Any, Dict

import httpx

from app.core.config import get_settings
from app.core.pkce import generate_pkce_pair
from app.integrations.kick.constants import resolve_kick_redirect_uri

settings = get_settings()

KICK_OAUTH_BASE = "https://id.kick.com"
KICK_API_BASE = "https://api.kick.com/public/v1"
_app_access_token: str | None = None
_app_access_token_expires_at = 0.0

DEFAULT_SCOPES = (
    "user:read channel:read chat:write events:subscribe"
)


def kick_credentials_valid() -> bool:
    cid = (settings.kick_client_id or "").strip()
    secret = (settings.kick_client_secret or "").strip()
    return bool(cid and secret and cid != secret and len(secret) >= 20)


class KickOAuth:
    async def get_app_access_token(self) -> str:
        global _app_access_token, _app_access_token_expires_at
        import time

        if _app_access_token and time.monotonic() < _app_access_token_expires_at - 60:
            return _app_access_token
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{KICK_OAUTH_BASE}/oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.kick_client_id,
                    "client_secret": settings.kick_client_secret,
                    "scope": "events:subscribe",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()
        token = data.get("access_token")
        if not token:
            raise ValueError("Kick no devolvió un token de aplicación")
        _app_access_token = token
        _app_access_token_expires_at = time.monotonic() + int(data.get("expires_in") or 3600)
        return token

    def build_authorize_payload(self) -> tuple[str, str, str]:
        """Returns (authorization_url, state, code_verifier)."""
        import secrets
        from urllib.parse import urlencode

        verifier, challenge = generate_pkce_pair()
        state = secrets.token_urlsafe(32)
        params = {
            "response_type": "code",
            "client_id": settings.kick_client_id,
            "redirect_uri": resolve_kick_redirect_uri(),
            "scope": DEFAULT_SCOPES,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        url = f"{KICK_OAUTH_BASE}/oauth/authorize?{urlencode(params)}"
        return url, state, verifier

    async def exchange_code(self, code: str, code_verifier: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            payload = {
                "grant_type": "authorization_code",
                "client_id": settings.kick_client_id,
                "client_secret": settings.kick_client_secret,
                "redirect_uri": resolve_kick_redirect_uri(),
                "code": code,
                "code_verifier": code_verifier,
            }
            response = await client.post(
                f"{KICK_OAUTH_BASE}/oauth/token",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if response.status_code >= 400:
                fallback = await client.post(
                    f"{KICK_OAUTH_BASE}/oauth/token",
                    data={k: v for k, v in payload.items() if k != "client_secret"},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                if fallback.status_code < 400:
                    return fallback.json()
                response.raise_for_status()
            return response.json()

    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{KICK_OAUTH_BASE}/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": settings.kick_client_id,
                    "client_secret": settings.kick_client_secret,
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            return response.json()

    async def fetch_user(self, access_token: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{KICK_API_BASE}/users",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            if response.status_code != 200:
                return {}
            data = response.json()
            if isinstance(data, dict) and data.get("data"):
                items = data["data"]
                return items[0] if items else {}
            return data if isinstance(data, dict) else {}

    async def subscribe_chat_events(
        self, access_token: str, broadcaster_user_id: str | None = None
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "events": [{"name": "chat.message.sent", "version": 1}],
            "method": "webhook",
        }
        if broadcaster_user_id:
            payload["broadcaster_user_id"] = int(broadcaster_user_id)
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{KICK_API_BASE}/events/subscriptions",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            return response.json()
