"""Kick live chat vía Pusher WebSocket (canal chatrooms.{id}.v2)."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable, Dict, Optional  # noqa: F401 used by callbacks

import websockets
from websockets.exceptions import ConnectionClosed

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

EventHandler = Callable[[str, Dict[str, Any]], Awaitable[None]]


class KickPusherClient:
    def __init__(
        self,
        chatroom_id: int,
        *,
        on_event: EventHandler,
        on_connected: Optional[Callable[[], Awaitable[None]]] = None,
        on_reconnect: Optional[Callable[[], Awaitable[None]]] = None,
        app_key: Optional[str] = None,
        cluster: Optional[str] = None,
    ) -> None:
        self.chatroom_id = chatroom_id
        self.on_event = on_event
        self.on_connected = on_connected
        self.on_reconnect = on_reconnect
        self.app_key = app_key or settings.kick_pusher_app_key
        self.cluster = cluster or settings.kick_pusher_cluster
        self._channel = f"chatrooms.{chatroom_id}.v2"
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False

    def _ws_url(self) -> str:
        return (
            f"wss://ws-{self.cluster}.pusher.com/app/{self.app_key}"
            "?protocol=7&client=streamshield&version=1.0"
        )

    async def _subscribe(self) -> None:
        if not self._ws:
            return
        payload = json.dumps({"channel": self._channel})
        await self._ws.send(
            json.dumps({"event": "pusher:subscribe", "data": payload})
        )

    async def _handle_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        event = msg.get("event") or ""
        if event in ("pusher:connection_established", "pusher_internal:subscription_succeeded"):
            return
        data_raw = msg.get("data")
        if isinstance(data_raw, str):
            try:
                data = json.loads(data_raw)
            except json.JSONDecodeError:
                data = {"raw": data_raw}
        elif isinstance(data_raw, dict):
            data = data_raw
        else:
            data = {}
        await self.on_event(event, data)

    async def run(self) -> None:
        self._running = True
        backoff = 2.0
        max_backoff = float(settings.platform_monitor_reconnect_max_seconds)
        while self._running:
            try:
                async with websockets.connect(
                    self._ws_url(),
                    ping_interval=25,
                    ping_timeout=20,
                    close_timeout=5,
                    max_size=2**20,
                ) as ws:
                    self._ws = ws
                    backoff = 2.0
                    await self._subscribe()
                    if self.on_connected:
                        await self.on_connected()
                    async for message in ws:
                        if not self._running:
                            break
                        await self._handle_message(message)
            except ConnectionClosed:
                logger.info("kick_pusher_closed", chatroom_id=self.chatroom_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "kick_pusher_error",
                    chatroom_id=self.chatroom_id,
                    error=str(exc)[:200],
                )
            finally:
                self._ws = None
            if not self._running:
                break
            if self.on_reconnect:
                await self.on_reconnect()
            await asyncio.sleep(min(backoff, max_backoff))
            backoff = min(backoff * 1.5, max_backoff)

    async def stop(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()
