"""Suscriptor Redis Pub/Sub → WebSocket (multi-instancia)."""

from __future__ import annotations

import asyncio
import json

from app.api.websocket.manager import ws_manager
from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.realtime import CHANNEL_PREFIX
from app.infrastructure.cache.redis_client import get_redis, redis_is_configured

logger = get_logger(__name__)
settings = get_settings()

_subscriber_task: asyncio.Task | None = None


async def _subscribe_loop() -> None:
    client = await get_redis()
    pubsub = client.pubsub()
    await pubsub.psubscribe(f"{CHANNEL_PREFIX}:*")
    logger.info("realtime_subscriber_started", pattern=f"{CHANNEL_PREFIX}:*")

    async for message in pubsub.listen():
        if message["type"] not in ("pmessage", "message"):
            continue
        try:
            raw = message.get("data")
            if isinstance(raw, bytes):
                raw = raw.decode()
            payload = json.loads(raw)
            channel = message.get("channel") or ""
            if isinstance(channel, bytes):
                channel = channel.decode()
            tenant_id = channel.split(":")[-1] if ":" in channel else ""
            if not tenant_id:
                continue

            msg_type = payload.get("type", "stream_event")
            if msg_type == "stats_update":
                await ws_manager.broadcast_stats(tenant_id, payload.get("data", {}))
            elif msg_type == "attack_detected":
                await ws_manager.broadcast_attack(tenant_id, payload.get("data", {}))
            elif msg_type == "alert":
                await ws_manager.broadcast_alert(tenant_id, payload.get("data", {}))
            else:
                await ws_manager.broadcast_live_event(tenant_id, payload)
        except Exception as exc:
            logger.warning("realtime_subscriber_message_error", error=str(exc))


async def start_realtime_subscriber() -> asyncio.Task | None:
    global _subscriber_task
    if not settings.event_realtime_pubsub_enabled or not redis_is_configured():
        return None
    if _subscriber_task and not _subscriber_task.done():
        return _subscriber_task
    _subscriber_task = asyncio.create_task(_subscribe_loop())
    return _subscriber_task


async def stop_realtime_subscriber() -> None:
    global _subscriber_task
    if _subscriber_task:
        _subscriber_task.cancel()
        try:
            await _subscriber_task
        except asyncio.CancelledError:
            pass
        _subscriber_task = None
