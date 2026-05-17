from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import Stream
from app.integrations.twitch.helix import TwitchHelixClient


def stream_monitor_mode(stream: Stream) -> bool:
    return bool((stream.settings or {}).get("monitor_mode"))


def stream_auto_mitigate(stream: Stream) -> bool:
    settings = stream.settings or {}
    if stream_monitor_mode(stream):
        return bool(settings.get("auto_mitigate", False))
    return bool(settings.get("auto_mitigate", True))


def stream_to_response_dict(stream: Stream) -> Dict[str, Any]:
    monitor = stream_monitor_mode(stream)
    owned = bool(stream.oauth_token_encrypted) and not monitor
    return {
        "id": stream.id,
        "platform": stream.platform,
        "external_id": stream.external_id,
        "channel_name": stream.channel_name,
        "is_live": stream.is_live,
        "viewer_count": stream.viewer_count,
        "created_at": stream.created_at,
        "monitor_mode": monitor,
        "is_owned": owned,
        "login": (stream.settings or {}).get("login"),
    }


async def sync_stream_live_status(db: AsyncSession, stream: Stream) -> Stream:
    if stream.platform.value != "twitch":
        return stream
    client = TwitchHelixClient()
    if not client.configured:
        return stream
    status = await client.get_channel_status(stream.external_id)
    prev_count = stream.viewer_count
    stream.is_live = status["is_live"]
    stream.viewer_count = status["viewer_count"]
    meta = dict(stream.settings or {})
    meta["last_sync_title"] = status.get("title")
    meta["last_game"] = status.get("game_name")
    if status["is_live"] and status["viewer_count"] - prev_count >= 500:
        meta["viewer_spike"] = {
            "from": prev_count,
            "to": status["viewer_count"],
        }
    stream.settings = meta
    await db.flush()
    return stream
