import hashlib
import hmac
from typing import Any, Dict, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class TwitchEventSubClient:
    BASE_URL = "https://api.twitch.tv/helix"

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Client-Id": settings.twitch_client_id,
            "Content-Type": "application/json",
        }

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
        """Reuse an enabled matching webhook subscription before creating one."""
        condition = self._subscription_condition(event_type, broadcaster_user_id, chat_user_id)
        cursor = None
        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                params: Dict[str, str] = {"first": "100", "type": event_type}
                if cursor:
                    params["after"] = cursor
                response = await client.get(
                    f"{self.BASE_URL}/eventsub/subscriptions",
                    headers=self.headers,
                    params=params,
                )
                response.raise_for_status()
                result = response.json()
                for subscription in result.get("data", []):
                    transport = subscription.get("transport", {})
                    if (
                        subscription.get("status") == "enabled"
                        and subscription.get("type") == event_type
                        and subscription.get("condition") == condition
                        and transport.get("method") == "webhook"
                        and transport.get("callback") == settings.twitch_eventsub_callback_url
                    ):
                        return {"data": [subscription], "existing": True}
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

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/eventsub/subscriptions",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def delete_subscription(self, subscription_id: str) -> None:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.delete(
                f"{self.BASE_URL}/eventsub/subscriptions",
                headers=self.headers,
                params={"id": subscription_id},
            )
            if response.status_code not in (204, 404):
                response.raise_for_status()

    @staticmethod
    def verify_signature(
        message_id: str,
        timestamp: str,
        body: bytes,
        signature: str,
    ) -> bool:
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
