import hashlib
import hmac
import time
from typing import Any, Dict, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()
_app_access_token: Optional[str] = None
_app_access_token_expires_at = 0.0


class TwitchEventSubClient:
    BASE_URL = "https://api.twitch.tv/helix"

    def __init__(self, access_token: str):
        # Kept in the constructor for call-site compatibility. Webhook
        # EventSub endpoints require an app access token, not this user token.
        self.access_token = access_token

    @staticmethod
    async def _get_app_access_token() -> str:
        global _app_access_token, _app_access_token_expires_at
        if _app_access_token and time.monotonic() < _app_access_token_expires_at:
            return _app_access_token
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://id.twitch.tv/oauth2/token",
                data={
                    "client_id": settings.twitch_client_id,
                    "client_secret": settings.twitch_client_secret,
                    "grant_type": "client_credentials",
                },
            )
            if response.is_error:
                raise RuntimeError(
                    f"Twitch app token HTTP {response.status_code}: {response.text[:400]}"
                )
            token_data = response.json()
        token = token_data.get("access_token")
        if not token:
            raise RuntimeError("Twitch did not return an app access token")
        _app_access_token = str(token)
        expires_in = max(int(token_data.get("expires_in") or 3600), 60)
        _app_access_token_expires_at = time.monotonic() + expires_in - 60
        return _app_access_token

    @staticmethod
    def _headers(access_token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Client-Id": settings.twitch_client_id,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _raise_for_twitch(response: httpx.Response) -> None:
        if response.is_error:
            raise httpx.HTTPStatusError(
                f"Twitch EventSub HTTP {response.status_code}: {response.text[:500]}",
                request=response.request,
                response=response,
            )

    @staticmethod
    def _subscription_condition(
        event_type: str,
        broadcaster_user_id: str,
        chat_user_id: Optional[str] = None,
    ) -> Dict[str, str]:
        conditions = {
            "channel.follow": {
                "broadcaster_user_id": broadcaster_user_id,
                "moderator_user_id": broadcaster_user_id,
            },
            "channel.subscribe": {"broadcaster_user_id": broadcaster_user_id},
            "stream.online": {"broadcaster_user_id": broadcaster_user_id},
            "stream.offline": {"broadcaster_user_id": broadcaster_user_id},
            "channel.chat.message": {
                "broadcaster_user_id": broadcaster_user_id,
                "user_id": chat_user_id or broadcaster_user_id,
            },
        }
        return conditions.get(event_type, {"broadcaster_user_id": broadcaster_user_id})

    async def ensure_subscription(
        self,
        event_type: str,
        broadcaster_user_id: str,
        chat_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reuse an active matching webhook subscription before creating one."""
        condition = self._subscription_condition(event_type, broadcaster_user_id, chat_user_id)
        cursor = None
        app_token = await self._get_app_access_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                params: Dict[str, str] = {"first": "100", "type": event_type}
                if cursor:
                    params["after"] = cursor
                response = await client.get(
                    f"{self.BASE_URL}/eventsub/subscriptions",
                    headers=self._headers(app_token),
                    params=params,
                )
                self._raise_for_twitch(response)
                result = response.json()
                for subscription in result.get("data", []):
                    transport = subscription.get("transport", {})
                    if (
                        subscription.get("type") == event_type
                        and subscription.get("condition") == condition
                        and transport.get("method") == "webhook"
                        and transport.get("callback") == settings.twitch_eventsub_callback_url
                    ):
                        if subscription.get("status") in (
                            "enabled",
                            "webhook_callback_verification_pending",
                        ):
                            return {"data": [subscription], "existing": True}
                        subscription_id = subscription.get("id")
                        if subscription_id:
                            delete_response = await client.delete(
                                f"{self.BASE_URL}/eventsub/subscriptions",
                                headers=self._headers(app_token),
                                params={"id": str(subscription_id)},
                            )
                            if delete_response.status_code not in (204, 404):
                                self._raise_for_twitch(delete_response)
                        return await self.create_subscription(
                            event_type,
                            broadcaster_user_id,
                            chat_user_id=chat_user_id,
                        )
                cursor = result.get("pagination", {}).get("cursor")
                if not cursor:
                    break
        return await self.create_subscription(event_type, broadcaster_user_id, chat_user_id=chat_user_id)

    async def create_subscription(
        self,
        event_type: str,
        broadcaster_user_id: str,
        session_id: Optional[str] = None,
        chat_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        version_map = {
            "channel.follow": "2",
            "channel.subscribe": "1",
            "stream.online": "1",
            "stream.offline": "1",
            "channel.chat.message": "1",
        }

        payload = {
            "type": event_type,
            "version": version_map.get(event_type, "1"),
            "condition": self._subscription_condition(event_type, broadcaster_user_id, chat_user_id),
            "transport": {
                "method": "webhook",
                "callback": settings.twitch_eventsub_callback_url,
                "secret": settings.twitch_webhook_secret,
            },
        }

        app_token = await self._get_app_access_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/eventsub/subscriptions",
                headers=self._headers(app_token),
                json=payload,
            )
            self._raise_for_twitch(response)
            return response.json()

    async def delete_subscription(self, subscription_id: str) -> None:
        app_token = await self._get_app_access_token()
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.delete(
                f"{self.BASE_URL}/eventsub/subscriptions",
                headers=self._headers(app_token),
                params={"id": subscription_id},
            )
            if response.status_code not in (204, 404):
                self._raise_for_twitch(response)

    @staticmethod
    def verify_signature(
        message_id: str,
        timestamp: str,
        body: bytes,
        signature: str,
    ) -> bool:
        if not settings.twitch_webhook_secret:
            return False
        message = message_id.encode() + timestamp.encode() + body
        expected = hmac.new(
            settings.twitch_webhook_secret.encode(),
            message,
            hashlib.sha256,
        ).hexdigest()
        expected_sig = f"sha256={expected}"
        return hmac.compare_digest(expected_sig, signature)

    @staticmethod
    def parse_event(headers: Dict[str, str], body: Dict[str, Any]) -> Dict[str, Any]:
        subscription_type = headers.get("twitch-eventsub-subscription-type", "")
        event = body.get("event", {})
        return {
            "type": subscription_type,
            "event": event,
            "broadcaster_id": event.get("broadcaster_user_id"),
            "user_id": event.get("user_id") or event.get("chatter_user_id"),
            "username": (
                event.get("user_name")
                or event.get("user_login")
                or event.get("chatter_user_name")
                or event.get("chatter_user_login")
            ),
            "timestamp": headers.get("twitch-eventsub-message-timestamp"),
            "chat_user_id": (body.get("subscription", {}).get("condition") or {}).get("user_id"),
        }
