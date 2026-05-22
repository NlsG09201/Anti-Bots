"""TikTok Live — room info HTTP + Webcast (TikTokLive async client)."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Awaitable, Callable, Dict, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

TikTokEventHandler = Callable[[str, Dict[str, Any]], Awaitable[None]]


class TikTokRoomInfo:
    def __init__(
        self,
        *,
        unique_id: str,
        room_id: str,
        is_live: bool,
        viewer_count: int = 0,
        title: Optional[str] = None,
    ) -> None:
        self.unique_id = unique_id
        self.room_id = room_id
        self.is_live = is_live
        self.viewer_count = viewer_count
        self.title = title


async def fetch_tiktok_room(unique_id: str) -> Optional[TikTokRoomInfo]:
    """Estado del live room vía API web pública de TikTok."""
    handle = unique_id.strip().lstrip("@").lower()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    params = {"aid": "1988", "uniqueId": handle}
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        try:
            response = await client.get(
                "https://www.tiktok.com/api/live/detail/",
                headers=headers,
                params=params,
            )
            if response.status_code != 200:
                return await _fetch_room_from_page(client, handle, headers)
            payload = response.json()
            data = payload.get("data") or payload
            room = data.get("liveRoom") or data.get("room") or data
            status = int(room.get("status", 0))
            is_live = status == 2 or bool(room.get("liveRoomStats"))
            room_id = str(room.get("id") or room.get("roomId") or "")
            stats = room.get("liveRoomStats") or {}
            viewers = int(stats.get("userCount") or room.get("viewerCount") or 0)
            title = room.get("title")
            if room_id:
                return TikTokRoomInfo(
                    unique_id=handle,
                    room_id=room_id,
                    is_live=is_live,
                    viewer_count=viewers,
                    title=title,
                )
        except Exception as exc:
            logger.warning("tiktok_api_live_detail_failed", handle=handle, error=str(exc)[:200])
        return await _fetch_room_from_page(client, handle, headers)


async def _fetch_room_from_page(
    client: httpx.AsyncClient,
    handle: str,
    headers: Dict[str, str],
) -> Optional[TikTokRoomInfo]:
    try:
        response = await client.get(f"https://www.tiktok.com/@{handle}/live", headers=headers)
        if response.status_code != 200:
            return None
        text = response.text
        room_match = re.search(r'"roomId":"(\d+)"', text)
        live_match = re.search(r'"status":(\d+)', text)
        viewers_match = re.search(r'"userCount":(\d+)', text)
        if not room_match:
            return None
        status = int(live_match.group(1)) if live_match else 0
        return TikTokRoomInfo(
            unique_id=handle,
            room_id=room_match.group(1),
            is_live=status == 2,
            viewer_count=int(viewers_match.group(1)) if viewers_match else 0,
        )
    except Exception as exc:
        logger.warning("tiktok_page_scrape_failed", handle=handle, error=str(exc)[:200])
        return None


class TikTokWebcastMonitor:
    """Monitor de eventos TikTok Live usando TikTokLive (async)."""

    def __init__(self, unique_id: str, *, on_event: TikTokEventHandler) -> None:
        self.unique_id = unique_id.strip().lstrip("@")
        self.on_event = on_event
        self._client = None
        self._running = False

    def _build_client(self):
        from TikTokLive import TikTokLiveClient
        from TikTokLive.events import (
            CommentEvent,
            ConnectEvent,
            DisconnectEvent,
            FollowEvent,
            GiftEvent,
            JoinEvent,
            ShareEvent,
        )

        client = TikTokLiveClient(unique_id=self.unique_id)
        if settings.tiktok_session_id:
            client.webclient.cookies.set("sessionid", settings.tiktok_session_id)

        @client.on(ConnectEvent)
        async def _on_connect(event: ConnectEvent) -> None:
            await self.on_event(
                "connection",
                {
                    "room_id": str(getattr(event, "room_id", "") or ""),
                    "viewer_count": int(getattr(event, "viewer_count", 0) or 0),
                },
            )

        @client.on(DisconnectEvent)
        async def _on_disconnect(_event: DisconnectEvent) -> None:
            await self.on_event("stream.offline", {})

        @client.on(JoinEvent)
        async def _on_join(event: JoinEvent) -> None:
            user = event.user
            await self.on_event(
                "viewer_join",
                {
                    "platform_user_id": str(getattr(user, "id", "") or ""),
                    "platform_username": getattr(user, "unique_id", None)
                    or getattr(user, "nickname", None),
                },
            )

        @client.on(CommentEvent)
        async def _on_comment(event: CommentEvent) -> None:
            user = event.user
            await self.on_event(
                "chat_message",
                {
                    "platform_user_id": str(getattr(user, "id", "") or ""),
                    "platform_username": getattr(user, "unique_id", None)
                    or getattr(user, "nickname", None),
                    "content": getattr(event, "comment", "") or "",
                },
            )

        @client.on(FollowEvent)
        async def _on_follow(event: FollowEvent) -> None:
            user = event.user
            await self.on_event(
                "follow",
                {
                    "platform_user_id": str(getattr(user, "id", "") or ""),
                    "platform_username": getattr(user, "unique_id", None)
                    or getattr(user, "nickname", None),
                },
            )

        @client.on(GiftEvent)
        async def _on_gift(event: GiftEvent) -> None:
            user = event.user
            gift = event.gift
            await self.on_event(
                "gift",
                {
                    "platform_user_id": str(getattr(user, "id", "") or ""),
                    "platform_username": getattr(user, "unique_id", None)
                    or getattr(user, "nickname", None),
                    "gift_name": getattr(gift, "name", None),
                    "gift_count": int(getattr(event, "repeat_count", 1) or 1),
                },
            )

        @client.on(ShareEvent)
        async def _on_share(event: ShareEvent) -> None:
            user = event.user
            await self.on_event(
                "share",
                {
                    "platform_user_id": str(getattr(user, "id", "") or ""),
                    "platform_username": getattr(user, "unique_id", None),
                },
            )

        return client

    async def run(self) -> None:
        self._running = True
        try:
            self._client = self._build_client()
            await self._client.start()
        except ImportError:
            logger.error(
                "tiktok_live_not_installed",
                hint="pip install TikTokLive",
            )
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("tiktok_webcast_stopped", unique_id=self.unique_id, error=str(exc)[:200])
        finally:
            self._running = False

    async def stop(self) -> None:
        self._running = False
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                pass
