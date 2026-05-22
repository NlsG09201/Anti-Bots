"""Ingesta de eventos de monitores Kick / YouTube / TikTok al pipeline SOC."""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import EventIngest
from app.core.logging import get_logger
from app.events.bus import ingest_event
from app.events.realtime import publish_realtime
from app.infrastructure.database.models import Platform, Stream
from app.services.ingest.event_ingest import process_stream_event

logger = get_logger(__name__)

_KICK_EVENT_MAP = {
    "App\\Events\\ChatMessageEvent": "chat_message",
    "ChatMessageEvent": "chat_message",
    "App\\Events\\MessageEvent": "chat_message",
    "App\\Events\\UserFollowedEvent": "follow",
    "UserFollowedEvent": "follow",
    "App\\Events\\StreamerIsLive": "stream.online",
    "App\\Events\\StreamerIsOffline": "stream.offline",
    "App\\Events\\GiftSentEvent": "gift",
}


def normalize_platform_event(
    platform: Platform,
    raw_event: str,
    data: Dict[str, Any],
) -> tuple[str, Optional[str], Optional[str], Dict[str, Any]]:
    meta = dict(data)
    event_type = raw_event
    user_id: Optional[str] = None
    username: Optional[str] = None

    if platform == Platform.KICK:
        event_type = _KICK_EVENT_MAP.get(raw_event, raw_event)
        sender = data.get("sender") or data.get("user") or {}
        if isinstance(sender, dict):
            user_id = str(sender.get("id") or sender.get("user_id") or "") or None
            username = sender.get("username") or sender.get("slug")
        message = data.get("message") or data.get("content")
        if message:
            meta["content"] = message

    elif platform == Platform.YOUTUBE:
        user_id = data.get("platform_user_id")
        username = data.get("platform_username")
        meta.setdefault("content", data.get("content"))

    elif platform == Platform.TIKTOK:
        user_id = data.get("platform_user_id")
        username = data.get("platform_username")
        if raw_event == "gift":
            event_type = "gift"
        elif raw_event in ("connection", "stream.online"):
            event_type = "connection"
        elif raw_event == "stream.offline":
            event_type = "stream.offline"

    return event_type, user_id, username, meta


async def emit_platform_event(
    db: AsyncSession,
    stream: Stream,
    *,
    event_type: str,
    platform_user_id: Optional[str] = None,
    platform_username: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Procesa evento y emite feed SOC en tiempo real."""
    meta = dict(metadata or {})
    meta["platform"] = stream.platform.value
    meta["channel"] = stream.channel_name

    event = EventIngest(
        event_type=event_type,
        platform_user_id=platform_user_id,
        platform_username=platform_username,
        metadata=meta,
    )

    try:
        result = await ingest_event(
            db,
            stream,
            stream.tenant_id,
            event,
            source=f"platform_{stream.platform.value}",
        )
    except Exception as exc:
        logger.warning("platform_ingest_failed", error=str(exc)[:200])
        result = await process_stream_event(
            db,
            stream,
            stream.tenant_id,
            event,
            source=f"platform_{stream.platform.value}",
        )

    await publish_realtime(
        str(stream.tenant_id),
        "live_feed",
        {
            "stream_id": str(stream.id),
            "platform": stream.platform.value,
            "channel_name": stream.channel_name,
            "event_type": event_type,
            "platform_username": platform_username,
            "risk_score": result.get("risk_score", 0),
            "attack_created": result.get("attack_created", False),
            "blocked": result.get("blocked", False),
        },
    )
    return result
