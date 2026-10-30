"""Use cases for adding external channels to a tenant's monitored streams."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.infrastructure.database.models import Platform, Stream
from app.infrastructure.repositories.stream_repository import StreamRepository
from app.integrations.twitch.helix import TwitchHelixClient
from app.services.streams.helpers import sync_stream_live_status

logger = get_logger(__name__)


class StreamWatchService:
    """Resolve a platform channel and persist its tenant-scoped monitor record."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.streams = StreamRepository(session)
        self.settings = get_settings()

    async def watch(
        self,
        platform: Platform,
        login: str,
        tenant_id: UUID,
        owner_id: UUID,
    ) -> Stream:
        if platform == Platform.TWITCH:
            return await self._watch_twitch(login, tenant_id, owner_id)
        return await self._watch_other_platform(platform, login, tenant_id, owner_id)

    async def _watch_other_platform(
        self,
        platform: Platform,
        login: str,
        tenant_id: UUID,
        owner_id: UUID,
    ) -> Stream:
        slug = login.lower()
        stream = await self.streams.get_by_channel_name(tenant_id, platform, slug)
        settings = self._monitor_settings(slug)
        if stream:
            updated = dict(stream.settings or {})
            updated.update(settings)
            stream.settings = updated
            stream.channel_name = login
        else:
            stream = Stream(
                tenant_id=tenant_id,
                owner_id=owner_id,
                platform=platform,
                external_id=slug,
                channel_name=login,
                settings=settings,
            )
            self.session.add(stream)

        await self.session.flush()
        stream = await sync_stream_live_status(self.session, stream)
        if platform == Platform.KICK:
            await self._reconcile_kick_subscriptions(stream)
        return stream

    async def _watch_twitch(self, login: str, tenant_id: UUID, owner_id: UUID) -> Stream:
        helix = TwitchHelixClient()
        if not helix.configured:
            raise ValidationError("Credenciales Twitch no configuradas en el servidor")

        user = await helix.get_user_by_login(login)
        if not user:
            raise NotFoundError("Canal de Twitch")

        broadcaster_id = user["id"]
        canonical_login = user["login"]
        display_name = user.get("display_name", canonical_login)
        stream = await self.streams.get_by_platform_and_external_id(
            tenant_id,
            Platform.TWITCH,
            broadcaster_id,
        )
        settings = self._monitor_settings(canonical_login)
        if stream:
            updated = dict(stream.settings or {})
            updated.update(settings)
            stream.settings = updated
            stream.channel_name = display_name
        else:
            stream = Stream(
                tenant_id=tenant_id,
                owner_id=owner_id,
                platform=Platform.TWITCH,
                external_id=broadcaster_id,
                channel_name=display_name,
                settings=settings,
            )
            self.session.add(stream)

        await self.session.flush()
        return await sync_stream_live_status(self.session, stream)

    @staticmethod
    def _monitor_settings(login: str) -> dict[str, object]:
        return {
            "monitor_mode": True,
            "soc_monitor": True,
            "competitive_intel": True,
            "auto_mitigate": False,
            "login": login,
            "is_owned": False,
            "force_monitor": True,
        }

    async def _reconcile_kick_subscriptions(self, stream: Stream) -> None:
        meta = dict(stream.settings or {})
        meta["kick_mitigation_default_reviewed"] = True
        meta.setdefault("auto_mitigate", False)
        if meta.get("kick_chat_webhook_subscribed") or not stream.external_id.isdigit():
            stream.settings = meta
            return

        now = datetime.now(timezone.utc).isoformat()
        try:
            from app.integrations.kick.oauth import KickOAuth

            oauth = KickOAuth()
            app_token = await oauth.get_app_access_token()
            result = await oauth.reconcile_event_subscriptions(
                app_token,
                stream.external_id,
                previously_requested=meta.get("kick_webhook_subscriptions", []),
                requested_at=meta.get("kick_webhook_subscriptions_requested_at"),
            )
            subscriptions = (
                result.get("subscribed", [])
                + result.get("created", [])
                + result.get("assumed", [])
            )
            if result.get("created"):
                meta["kick_webhook_subscriptions_requested_at"] = now
            meta["kick_webhook_subscriptions"] = subscriptions
            meta["kick_webhook_subscriptions_verified"] = bool(result.get("verified_by_api"))
            meta["kick_chat_webhook_subscribed"] = "chat.message.sent" in subscriptions
            meta["kick_webhook_enabled"] = bool(subscriptions)
            meta["kick_webhook_subscription_error"] = ",".join(result.get("failed", [])) or None
            meta["kick_webhook_callback_url"] = self.settings.kick_webhook_callback_url
        except Exception as exc:
            meta["kick_webhook_subscription_error"] = type(exc).__name__
            logger.warning(
                "kick_watched_channel_subscription_failed",
                stream_id=str(stream.id),
                error_type=type(exc).__name__,
            )
        finally:
            meta["kick_webhook_subscriptions_checked_at"] = now
            stream.settings = meta
            await self.session.flush()
