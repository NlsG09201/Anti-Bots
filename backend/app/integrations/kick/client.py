from typing import Any, Dict, List, Optional
import time

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class KickAPIClient:
    BASE_URL = "https://kick.com/api/v2"
    PUBLIC_API_BASE = "https://api.kick.com/public/v1"

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token
        self.headers = {
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://kick.com/",
        }
        if access_token:
            self.headers["Authorization"] = f"Bearer {access_token}"

    async def get_channel(self, slug: str) -> Dict[str, Any]:
        """Fetch channel data with aggressive retry and bypass cache if possible."""
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            # We add a timestamp to bypass potential CDN caching
            url = f"{self.BASE_URL}/channels/{slug}?_t={int(time.time())}"
            try:
                response = await client.get(url, headers=self.headers)
                if response.status_code == 200:
                    return response.json()
                
                # Fallback to v1 if v2 fails or returns 404/403
                url_v1 = f"https://kick.com/api/v1/channels/{slug}"
                response = await client.get(url_v1, headers=self.headers)
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                logger.debug("kick_get_channel_failed", slug=slug, error=str(exc))
                # Final attempt: try public frontend data if API fails (scraping)
                return await self._scrape_channel_data(slug)

    async def _scrape_channel_data(self, slug: str) -> Dict[str, Any]:
        """Last resort scraping of Kick frontend data."""
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            url = f"https://kick.com/{slug}"
            response = await client.get(url, headers=self.headers)
            if response.status_code != 200:
                raise Exception(f"Failed to scrape Kick channel {slug}")
            
            # Look for window.app data or similar in the HTML
            import re
            match = re.search(r'window\.app\s*=\s*({.*?});', response.text)
            if match:
                try:
                    import json
                    return json.loads(match.group(1))
                except:
                    pass
            raise Exception(f"Could not find app data for Kick channel {slug}")

    async def get_livestream(self, slug: str) -> Optional[Dict[str, Any]]:
        """Determine if a channel is live with fallback logic."""
        channel = await self.get_channel(slug)
        livestream = channel.get("livestream")

        # If livestream is null, sometimes the 'is_live' flag is elsewhere in some versions
        if not livestream:
            if channel.get("is_live") is True:
                return {
                    "id": str(channel.get("id")),
                    "slug": slug,
                    "viewer_count": channel.get("viewers_count", 0),
                    "is_live": True,
                    "title": channel.get("title", "No Title"),
                    "category": "Unknown",
                }
            return None

        return {
            "id": livestream.get("id"),
            "slug": slug,
            "viewer_count": livestream.get("viewer_count", 0),
            "is_live": True,
            "title": livestream.get("session_title"),
            "category": livestream.get("categories", [{}])[0].get("name") if livestream.get("categories") else None,
        }

    async def get_user_livestream(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Read a broadcaster's live status through Kick's supported public API."""
        if not self.access_token:
            raise RuntimeError("Reconnecta Kick para consultar el estado del canal.")
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self.PUBLIC_API_BASE}/users/livestreams",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Accept": "application/json",
                },
                params={"user_id": user_id},
            )
            response.raise_for_status()
            entries = response.json().get("data") or []
            if not entries:
                return None
            live = entries[0]
            return {
                "id": live.get("id"),
                "viewer_count": live.get("viewer_count", 0),
                "title": live.get("title"),
            }

    async def get_broadcaster_id_by_slug(self, slug: str) -> Optional[str]:
        if not self.access_token:
            return None
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self.PUBLIC_API_BASE}/channels",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Accept": "application/json",
                },
                params={"slug": slug.strip().lower().lstrip("@")},
            )
            response.raise_for_status()
            channels = response.json().get("data") or []
            if not channels:
                return None
            user_id = channels[0].get("broadcaster_user_id")
            return str(user_id) if user_id else None

    async def get_chat_messages(self, chatroom_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/messages/{chatroom_id}",
                headers=self.headers,
                params={"limit": limit},
            )
            if response.status_code != 200:
                response.raise_for_status()
            data = response.json()
            return data.get("data", data) if isinstance(data, dict) else data

    def parse_viewer_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "event_type": event_data.get("type", "viewer_join"),
            "platform_user_id": str(event_data.get("user_id", "")),
            "platform_username": event_data.get("username"),
            "metadata": event_data,
        }
