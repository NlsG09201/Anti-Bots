"""Cross-platform viewer sync for enterprise multi-platform streams."""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.database.models import Platform, Stream
from app.services.platforms.base import LiveStatus
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
        live_status_error = None
        try:
            live = await adapter.fetch_live_status(stream)
        except Exception as exc:
            if stream.platform != Platform.KICK:
                raise
            # A transient OAuth/status API failure must not prevent reading the
            # public active-chat roster or erase the last known live status.
            live_status_error = type(exc).__name__
            live = LiveStatus(
                is_live=bool(stream.is_live),
                viewer_count=int(stream.viewer_count or 0),
            )
            logger.warning(
                "kick_live_status_unavailable_using_cached_status",
                stream_id=str(stream.id),
                error_type=live_status_error,
            )
        stream.is_live = live.is_live
        stream.viewer_count = live.viewer_count
        if stream.platform == Platform.KICK:
            meta = dict(stream.settings or {})
            should_subscribe_kick = not (
                meta.get("is_owned") and not stream.oauth_token_encrypted
            )
            if meta.get("kick_chat_webhook_subscribed"):
                kick_subscription_status = "configured"
            elif should_subscribe_kick:
                try:
                    from app.integrations.kick.oauth import KickOAuth
                    from app.services.platforms.oauth_tokens import get_stream_access_token

                    oauth = KickOAuth()
                    token = await get_stream_access_token(stream)
                    app_token = token is None
                    token = token or await oauth.get_app_access_token()
                    subscription_result = await oauth.reconcile_event_subscriptions(
                        token,
                        stream.external_id if app_token else None,
                        previously_requested=meta.get("kick_webhook_subscriptions", []),
                        requested_at=meta.get("kick_webhook_subscriptions_requested_at"),
                    )
                    meta["kick_webhook_subscriptions"] = (
                        subscription_result.get("subscribed", [])
                        + subscription_result.get("created", [])
                        + subscription_result.get("assumed", [])
                    )
                    if subscription_result.get("created"):
                        from datetime import datetime, timezone
                        meta["kick_webhook_subscriptions_requested_at"] = datetime.now(timezone.utc).isoformat()
                    meta["kick_webhook_subscriptions_verified"] = bool(
                        subscription_result.get("verified_by_api")
                    )
                    meta["kick_chat_webhook_subscribed"] = (
                        "chat.message.sent" in meta["kick_webhook_subscriptions"]
                    )
                    meta["kick_webhook_enabled"] = bool(meta["kick_webhook_subscriptions"])
                    meta["kick_webhook_subscription_error"] = (
                        ",".join(subscription_result.get("failed", [])) or None
                    )
                    from datetime import datetime, timezone
                    meta["kick_webhook_subscriptions_checked_at"] = datetime.now(timezone.utc).isoformat()
                    meta["kick_webhook_callback_url"] = get_settings().kick_webhook_callback_url
                    stream.settings = meta
                    kick_subscription_status = (
                        "partial" if subscription_result.get("failed") else "configured"
                    )
                except Exception as exc:
                    kick_subscription_status = "failed"
                    meta["kick_webhook_subscription_error"] = type(exc).__name__
                    from datetime import datetime, timezone
                    meta["kick_webhook_subscriptions_checked_at"] = datetime.now(timezone.utc).isoformat()
                    stream.settings = meta
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

        chat_history_error = None
        kick_roster_complete = False
        if live.is_live or (stream.platform == Platform.KICK and live_status_error):
            try:
                snapshots = await adapter.fetch_viewers(stream)
                if stream.platform == Platform.KICK and not live_status_error:
                    kick_roster_complete = True
            except Exception as exc:
                if stream.platform != Platform.KICK:
                    raise
                snapshots = []
                chat_history_error = type(exc).__name__
                logger.warning(
                    "kick_active_chatters_lookup_failed",
                    stream_id=str(stream.id),
                    error_type=chat_history_error,
                )
            if live_status_error and snapshots:
                live.is_live = True
                stream.is_live = True
                kick_roster_complete = True
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
            # A successful Kick active-chatters response is a complete current
            # roster. Webhook-only fallback is incremental and must retain users.
            full_resync=(
                stream.platform != Platform.KICK
                or kick_roster_complete
                or not live.is_live
            ),
            clear_if_empty=not live.is_live or kick_roster_complete,
        )
        synced = sync_stats["total_synced"]
        if stream.platform == Platform.KICK:
            active_stats = await self.viewers.count_active(stream.id)
            synced = active_stats["total"]

        return {
            "platform": stream.platform.value,
            "is_live": live.is_live,
            "viewer_count": live.viewer_count,
            "chatters_synced": synced,
            "source": (
                "kick_active_chatters"
                if stream.platform == Platform.KICK
                else stream.platform.value
            ),
            **(
                {
                    "chat_subscription": kick_subscription_status,
                }
                if stream.platform == Platform.KICK
                else {}
            ),
            **(
                {"chat_history_error": chat_history_error}
                if chat_history_error
                else {}
            ),
            **(
                {"live_status_error": live_status_error}
                if live_status_error
                else {}
            ),
        }
