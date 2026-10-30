"""Kick OAuth 2.1 with PKCE."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

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
    "user:read channel:read chat:write events:subscribe moderation:ban"
)
KICK_WEBHOOK_EVENTS = (
    "chat.message.sent",
    "channel.followed",
    "channel.subscription.new",
    "channel.subscription.renewal",
    "channel.subscription.gifts",
    "livestream.status.updated",
    "livestream.metadata.updated",
    "moderation.banned",
    "channel.reward.redemption.updated",
    "kicks.gifted",
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

    async def reconcile_event_subscriptions(
        self,
        access_token: str,
        broadcaster_user_id: str | None = None,
        *,
        previously_requested: Optional[list[str]] = None,
        requested_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            params = {"broadcaster_user_id": broadcaster_user_id} if broadcaster_user_id else {}
            current_response = await client.get(
                f"{KICK_API_BASE}/events/subscriptions", headers=headers, params=params
            )
            current_response.raise_for_status()
            current_payload = current_response.json()
            current = current_payload.get("data") if isinstance(current_payload, dict) else None
            if not isinstance(current, list):
                raise RuntimeError("Kick returned an invalid subscription listing")
            subscribed = set()
            for item in current if isinstance(current, list) else []:
                if not isinstance(item, dict):
                    continue
                event = item.get("event") or item.get("name") or {}
                name = event.get("name") if isinstance(event, dict) else event
                version = event.get("version", item.get("version", 1)) if isinstance(event, dict) else item.get("version", 1)
                if name and str(version) == "1" and item.get("method", "webhook") == "webhook":
                    subscribed.add(str(name))

            missing = [name for name in KICK_WEBHOOK_EVENTS if name not in subscribed]
            assumed = []
            if previously_requested and requested_at:
                try:
                    requested_time = datetime.fromisoformat(
                        requested_at.replace("Z", "+00:00")
                    )
                    if requested_time.tzinfo is None:
                        requested_time = requested_time.replace(tzinfo=timezone.utc)
                    if (datetime.now(timezone.utc) - requested_time).total_seconds() < 6 * 3600:
                        assumed = sorted(set(missing).intersection(previously_requested))
                        missing = [name for name in missing if name not in assumed]
                except (TypeError, ValueError):
                    pass
            if not missing:
                return {
                    "subscribed": sorted(subscribed),
                    "created": [],
                    "assumed": assumed,
                    "verified_by_api": not assumed,
                }

            payload: Dict[str, Any] = {
                "events": [{"name": name, "version": 1} for name in missing],
                "method": "webhook",
            }
            if broadcaster_user_id:
                payload["broadcaster_user_id"] = int(broadcaster_user_id)
            response = await client.post(
                f"{KICK_API_BASE}/events/subscriptions", headers=headers, json=payload
            )
            response.raise_for_status()
            created_payload = response.json()
            results = created_payload.get("data") if isinstance(created_payload, dict) else None
            if not isinstance(results, list):
                raise RuntimeError("Kick returned an invalid subscription creation response")
            created = sorted(
                {
                    str(item.get("name"))
                    for item in results
                    if isinstance(item, dict)
                    and item.get("name") in missing
                    and str(item.get("version")) == "1"
                    and not item.get("error")
                }
            )
            failed = sorted(set(missing) - set(created))
            return {
                "subscribed": sorted(subscribed),
                "created": created,
                "failed": failed,
                "assumed": assumed,
                "provider_response": created_payload,
                "verified_by_api": False,
            }

    async def subscribe_chat_events(
        self, access_token: str, broadcaster_user_id: str | None = None
    ) -> Dict[str, Any]:
        """Compatibility wrapper; subscriptions now include every supported event."""
        return await self.reconcile_event_subscriptions(access_token, broadcaster_user_id)

    async def unsubscribe_event_subscriptions(
        self, access_token: str, broadcaster_user_id: str
    ) -> int:
        """Remove only this integration's documented webhook event subscriptions."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }
            response = await client.get(
                f"{KICK_API_BASE}/events/subscriptions",
                headers=headers,
                params={"broadcaster_user_id": broadcaster_user_id},
            )
            response.raise_for_status()
            body = response.json()
            subscriptions = body.get("data", []) if isinstance(body, dict) else []
            ids = []
            for item in subscriptions if isinstance(subscriptions, list) else []:
                if (
                    isinstance(item, dict)
                    and item.get("event") in KICK_WEBHOOK_EVENTS
                    and str(item.get("version", "1")) == "1"
                    and item.get("method", "webhook") == "webhook"
                    and item.get("id")
                ):
                    ids.append(str(item["id"]))
            if not ids:
                return 0
            response = await client.delete(
                f"{KICK_API_BASE}/events/subscriptions",
                headers=headers,
                params=[("id", subscription_id) for subscription_id in ids],
            )
            response.raise_for_status()
            return len(ids)
