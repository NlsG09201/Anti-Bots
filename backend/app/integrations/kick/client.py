from typing import Any, Dict, List, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class KickAPIClient:
    BASE_URL = "https://kick.com/api/v2"

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token
        self.headers = {"Accept": "application/json"}
        if access_token:
            self.headers["Authorization"] = f"Bearer {access_token}"

    async def get_channel(self, slug: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/channels/{slug}",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def get_livestream(self, slug: str) -> Optional[Dict[str, Any]]:
        channel = await self.get_channel(slug)
        livestream = channel.get("livestream")
        if not livestream:
            return None
        return {
            "id": livestream.get("id"),
            "slug": slug,
            "viewer_count": livestream.get("viewer_count", 0),
            "is_live": True,
            "title": livestream.get("session_title"),
            "category": livestream.get("categories", [{}])[0].get("name") if livestream.get("categories") else None,
        }

    async def get_chat_messages(self, chatroom_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/messages/{chatroom_id}",
                headers=self.headers,
                params={"limit": limit},
            )
            if response.status_code != 200:
                return []
            data = response.json()
            return data.get("data", data) if isinstance(data, dict) else data

    def parse_viewer_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "event_type": event_data.get("type", "viewer_join"),
            "platform_user_id": str(event_data.get("user_id", "")),
            "platform_username": event_data.get("username"),
            "metadata": event_data,
        }
