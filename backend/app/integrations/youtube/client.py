from typing import Any, Dict, List, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class YouTubeLiveClient:
    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token
        self.api_key = settings.youtube_api_key

    def _params(self, extra: Optional[Dict] = None) -> Dict[str, str]:
        params = dict(extra or {})
        if self.api_key:
            params["key"] = self.api_key
        return params

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    async def get_live_broadcasts(self, channel_id: str) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/search",
                headers=self._headers(),
                params=self._params({
                    "part": "snippet",
                    "channelId": channel_id,
                    "eventType": "live",
                    "type": "video",
                }),
            )
            response.raise_for_status()
            items = response.json().get("items", [])
            return [
                {
                    "video_id": item["id"]["videoId"],
                    "title": item["snippet"]["title"],
                    "published_at": item["snippet"]["publishedAt"],
                }
                for item in items
            ]

    async def get_live_chat_messages(
        self,
        live_chat_id: str,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = {"part": "snippet,authorDetails", "liveChatId": live_chat_id, "maxResults": 200}
        if page_token:
            params["pageToken"] = page_token

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/liveChat/messages",
                headers=self._headers(),
                params=self._params(params),
            )
            response.raise_for_status()
            data = response.json()
            messages = []
            for item in data.get("items", []):
                messages.append({
                    "id": item["id"],
                    "platform_user_id": item["authorDetails"]["channelId"],
                    "platform_username": item["authorDetails"]["displayName"],
                    "content": item["snippet"]["displayMessage"],
                    "timestamp": item["snippet"]["publishedAt"],
                    "is_moderator": item["authorDetails"].get("isChatModerator", False),
                    "is_sponsor": item["authorDetails"].get("isChatSponsor", False),
                })
            return {
                "messages": messages,
                "next_page_token": data.get("nextPageToken"),
                "polling_interval_ms": data.get("pollingIntervalMillis", 5000),
            }

    async def get_channel_id_by_handle(self, handle: str) -> Optional[str]:
        """Resolve a handle (@username) to a channelId."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            # First try direct search
            response = await client.get(
                f"{self.BASE_URL}/search",
                headers=self._headers(),
                params=self._params({
                    "part": "snippet",
                    "q": handle,
                    "type": "channel",
                    "maxResults": 1,
                }),
            )
            if response.status_code == 200:
                items = response.json().get("items", [])
                if items:
                    return items[0]["id"]["channelId"]
        return None

    async def search_live_by_channel(self, channel_query: str) -> Optional[Dict[str, Any]]:
        """Find active live video for a channel name or handle with improved accuracy."""
        handle = channel_query if channel_query.startswith("@") else None
        channel_id = None
        
        if handle:
            channel_id = await self.get_channel_id_by_handle(handle)
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Strategy 1: Search by channelId if resolved
            if channel_id:
                response = await client.get(
                    f"{self.BASE_URL}/search",
                    headers=self._headers(),
                    params=self._params({
                        "part": "snippet",
                        "channelId": channel_id,
                        "eventType": "live",
                        "type": "video",
                        "maxResults": 1,
                    }),
                )
                if response.status_code == 200:
                    items = response.json().get("items", [])
                    if items:
                        return await self._format_live_result(items[0])

            # Strategy 2: Generic search with q=query
            response = await client.get(
                f"{self.BASE_URL}/search",
                headers=self._headers(),
                params=self._params({
                    "part": "snippet",
                    "q": channel_query,
                    "eventType": "live",
                    "type": "video",
                    "maxResults": 1,
                }),
            )
            if response.status_code == 200:
                items = response.json().get("items", [])
                if items:
                    return await self._format_live_result(items[0])

        return None

    async def _format_live_result(self, item: Dict[str, Any]) -> Dict[str, Any]:
        video_id = item["id"]["videoId"]
        stats = await self.get_video_statistics(video_id)
        return {
            "id": video_id,
            "snippet": item.get("snippet", {}),
            "statistics": {
                "concurrentViewers": stats.get("concurrent_viewers", 0),
                "viewCount": stats.get("viewer_count", 0),
            },
        }

    async def list_live_chat_messages(
        self, video_id: str, max_results: int = 200
    ) -> List[Dict[str, Any]]:
        stats = await self.get_video_statistics(video_id)
        chat_id = stats.get("active_live_chat_id")
        if not chat_id:
            return []
        result = await self.get_live_chat_messages(chat_id)
        return (result.get("messages") or [])[:max_results]

    async def get_video_statistics(self, video_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/videos",
                headers=self._headers(),
                params=self._params({
                    "part": "liveStreamingDetails,statistics",
                    "id": video_id,
                }),
            )
            response.raise_for_status()
            items = response.json().get("items", [])
            if not items:
                return {}
            item = items[0]
            stats = item.get("statistics", {})
            live = item.get("liveStreamingDetails", {})
            return {
                "viewer_count": int(stats.get("viewCount", 0)),
                "concurrent_viewers": int(live.get("concurrentViewers", 0)),
                "active_live_chat_id": live.get("activeLiveChatId"),
            }
