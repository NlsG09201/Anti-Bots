"""Cross-platform viewer sync for enterprise multi-platform streams."""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.database.models import Platform, Stream
from app.services.platforms.registry import get_platform_adapter
from app.services.viewers.session import ViewerSessionService

logger = get_logger(__name__)


class PlatformSyncService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.viewers = ViewerSessionService(db)

    async def sync_viewers(self, stream: Stream) -> Dict[str, Any]:
        adapter = get_platform_adapter(stream.platform)
        kick_subscription_status = None
        live = await adapter.fetch_live_status(stream)
        stream.is_live = live.is_live
        stream.viewer_count = live.viewer_count
        if stream.platform == Platform.KICK:
            meta = dict(stream.settings or {})
            if meta.get("kick_chat_webhook_subscribed"):
                kick_subscription_status = "configured"
            else:
                try:
                    from app.integrations.kick.oauth import KickOAuth
                    from app.services.platforms.oauth_tokens import get_stream_access_token

                    oauth = KickOAuth()
                    token = await get_stream_access_token(stream)
                    app_token = token is None
                    token = token or await oauth.get_app_access_token()
                    await oauth.subscribe_chat_events(
                        token,
                        stream.external_id if app_token else None,
                    )
                    meta["kick_chat_webhook_subscribed"] = True
                    meta["kick_webhook_callback_url"] = get_settings().kick_webhook_callback_url
                    stream.settings = meta
                    kick_subscription_status = "configured"
                except Exception as exc:
                    kick_subscription_status = "failed"
                    logger.warning(
                        "kick_chat_event_subscription_failed",
                        stream_id=str(stream.id),
                        error_type=type(exc).__name__,
                    )
        if stream.platform == Platform.YOUTUBE:
            meta = dict(stream.settings or {})
            if live.external_live_id:
                # YouTube distingue el ID del canal del ID del video en directo.
                meta["live_video_id"] = live.external_live_id
            else:
                meta.pop("live_video_id", None)
            stream.settings = meta

        if live.is_live:
            if stream.platform == Platform.KICK:
                # Kick's supported read path is its authenticated chat/event
                # stream. Its private REST history endpoint is not a stable
                # viewer-list API and an empty response must not erase sessions.
                sync_stats = await self.viewers.count_active(stream.id)
                return {
                    "platform": stream.platform.value,
                    "is_live": live.is_live,
                    "viewer_count": live.viewer_count,
                    "chatters_synced": sync_stats["total"],
                    "source": "kick_live_chat_monitor",
                    "chat_subscription": kick_subscription_status,
                }
            snapshots = await adapter.fetch_viewers(stream)
            chatters = [
                {
                    "username": snap.platform_username or snap.platform_user_id,
                    "user_id": snap.platform_user_id,
                    "source": snap.metadata.get("source", stream.platform.value),
                }
                for snap in snapshots
                if snap.is_in_chat and (snap.platform_username or snap.platform_user_id)
            ]
        else:
            # Un canal confirmado offline no debe conservar participantes activos.
            chatters = []

        sync_stats = await self.viewers.sync_chat_presence(
            stream.id,
            chatters,
            full_resync=True,
            clear_if_empty=not live.is_live,
        )
        synced = sync_stats["total_synced"]

        return {
            "platform": stream.platform.value,
            "is_live": live.is_live,
            "viewer_count": live.viewer_count,
            "chatters_synced": synced,
            "source": stream.platform.value,
            **(
                {"chat_subscription": kick_subscription_status}
                if stream.platform == Platform.KICK
                else {}
            ),
        }
