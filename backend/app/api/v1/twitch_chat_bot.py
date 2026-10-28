"""Web configuration API for the Twitch chat moderator bot."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, StreamModeratorUser
from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.infrastructure.cache.redis_client import RedisCache
from app.infrastructure.database.models import Platform, Stream, UserRole
from app.infrastructure.database.session import get_db
from app.integrations.twitch.oauth import TwitchOAuth, twitch_credentials_valid

router = APIRouter(prefix="/twitch/chat-bot", tags=["Twitch Chat Moderator Bot"])


class TwitchChatModerationSettings(BaseModel):
    enabled: bool = False
    observe_only: bool = True
    links_enabled: bool = False
    allowed_domains: list[str] = Field(default_factory=list, max_length=100)
    link_action: Literal["delete", "timeout", "ban"] = "delete"
    repeated_messages_enabled: bool = True
    repeat_limit: int = Field(default=3, ge=2, le=10)
    repeat_window_seconds: int = Field(default=20, ge=5, le=300)
    repeat_action: Literal["timeout", "ban"] = "timeout"
    blocked_words: list[str] = Field(default_factory=list, max_length=100)
    word_action: Literal["delete", "timeout", "ban"] = "timeout"
    timeout_seconds: int = Field(default=600, ge=1, le=1_209_600)

    @field_validator("allowed_domains")
    @classmethod
    def clean_domains(cls, values: list[str]) -> list[str]:
        cleaned = []
        for value in values:
            domain = value.strip().lower().removeprefix("https://").removeprefix("http://")
            domain = domain.split("/", 1)[0]
            if domain.startswith("www."):
                domain = domain[4:]
            if domain and domain not in cleaned:
                cleaned.append(domain)
        return cleaned

    @field_validator("blocked_words")
    @classmethod
    def clean_words(cls, values: list[str]) -> list[str]:
        cleaned = []
        for value in values:
            word = value.strip()[:100]
            if word and word.casefold() not in {item.casefold() for item in cleaned}:
                cleaned.append(word)
        return cleaned


async def _get_manageable_stream(
    stream_id: UUID,
    current_user: StreamModeratorUser,
    db: AsyncSession,
) -> Stream:
    result = await db.execute(
        select(Stream).where(
            Stream.id == stream_id,
            Stream.tenant_id == current_user.tenant_id,
            Stream.platform == Platform.TWITCH,
        )
    )
    stream = result.scalar_one_or_none()
    if not stream:
        raise NotFoundError("Twitch channel")
    if stream.owner_id != current_user.id and current_user.role not in (
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN,
    ):
        raise AuthorizationError("Only the account owner or a tenant administrator can manage the Twitch bot")
    return stream


@router.get("/{stream_id}")
async def get_settings(
    stream_id: UUID,
    current_user: StreamModeratorUser,
    db: AsyncSession = Depends(get_db),
):
    stream = await _get_manageable_stream(stream_id, current_user, db)
    metadata = dict(stream.settings or {})
    saved = metadata.get("twitch_chat_moderation", {})
    config = TwitchChatModerationSettings.model_validate(saved)
    return {
        "stream_id": str(stream.id),
        "channel_name": stream.channel_name,
        "oauth_connected": bool(stream.oauth_token_encrypted),
        "bot_connected": bool(metadata.get("twitch_bot_access_token_encrypted")),
        "bot_login": metadata.get("twitch_bot_login"),
        "bot_user_id": metadata.get("twitch_bot_user_id"),
        "bot_moderator_status": metadata.get("twitch_bot_moderator_status", "not_configured"),
        "eventsub_status": metadata.get("twitch_bot_eventsub_status", "not_configured"),
        **config.model_dump(),
    }


@router.put("/{stream_id}")
async def save_settings(
    stream_id: UUID,
    body: TwitchChatModerationSettings,
    current_user: StreamModeratorUser,
    db: AsyncSession = Depends(get_db),
):
    stream = await _get_manageable_stream(stream_id, current_user, db)
    metadata = dict(stream.settings or {})
    if body.enabled and not metadata.get("twitch_bot_access_token_encrypted"):
        raise ValidationError("Conecta primero la cuenta de bot moderadora de Twitch.")
    metadata["twitch_chat_moderation"] = body.model_dump()
    stream.settings = metadata
    await db.commit()
    return {"saved": True, "stream_id": str(stream.id), **body.model_dump()}


@router.post("/{stream_id}/authorize")
async def authorize_bot(
    stream_id: UUID,
    current_user: StreamModeratorUser,
    db: AsyncSession = Depends(get_db),
):
    stream = await _get_manageable_stream(stream_id, current_user, db)
    if not stream.oauth_token_encrypted:
        raise ValidationError("Conecta primero el canal Twitch propietario en Canales.")
    if not twitch_credentials_valid():
        raise ValidationError("Configura TWITCH_CLIENT_ID y TWITCH_CLIENT_SECRET en el backend.")
    import secrets

    state = secrets.token_urlsafe(32)
    cache = RedisCache(prefix="oauth")
    await cache.set(
        f"state:{state}",
        {
            "flow": "twitch_chat_moderator_bot",
            "user_id": str(current_user.id),
            "tenant_id": str(current_user.tenant_id),
            "stream_id": str(stream.id),
        },
        ttl=900,
    )
    url = TwitchOAuth().get_authorization_url(
        state,
        scopes=TwitchOAuth.CHAT_MODERATOR_SCOPES,
    )
    return {"authorization_url": url}


@router.post("/{stream_id}/setup")
async def setup_bot_in_channel(
    stream_id: UUID,
    current_user: StreamModeratorUser,
    db: AsyncSession = Depends(get_db),
):
    """Grant moderator role using broadcaster OAuth, then enable chat EventSub."""
    stream = await _get_manageable_stream(stream_id, current_user, db)
    metadata = dict(stream.settings or {})
    from app.core.config import get_settings
    from app.services.platforms.oauth_tokens import get_stream_access_token
    from app.services.twitch_chat_moderation import get_twitch_bot_credentials
    from app.integrations.twitch.eventsub import TwitchEventSubClient
    from app.integrations.twitch.moderation import add_channel_moderator_on_twitch

    config = get_settings()
    if not config.twitch_eventsub_callback_url or not config.twitch_webhook_secret:
        raise ValidationError("Configura el callback y el secreto de Twitch EventSub en el backend.")
    bot_token, bot_id, bot_login = await get_twitch_bot_credentials(stream)
    if not bot_token or not bot_id:
        raise ValidationError("Conecta primero la cuenta de bot moderadora de Twitch.")
    broadcaster_token = await get_stream_access_token(stream)
    if not broadcaster_token:
        raise ValidationError("Vuelve a conectar el canal propietario de Twitch.")

    moderator = await add_channel_moderator_on_twitch(
        stream.external_id, bot_id, broadcaster_token
    )
    if not moderator.get("ok"):
        if moderator.get("status") in (401, 403):
            raise ValidationError(
                "Twitch no autorizó gestionar moderadores. Reconecta el canal propietario "
                "en Canales para conceder channel:manage:moderators. "
                f"Detalle de Twitch: {str(moderator.get('detail') or '')[:180]}"
            )
        raise ValidationError(
            "No se pudo añadir la cuenta bot como moderadora. "
            f"Respuesta de Twitch ({moderator.get('status')}): {str(moderator.get('detail') or '')[:180]}"
        )

    metadata = dict(stream.settings or {})
    metadata["twitch_bot_moderator_status"] = "added"
    stream.settings = metadata
    await db.commit()
    try:
        subscription = await TwitchEventSubClient(bot_token).ensure_subscription(
            "channel.chat.message", stream.external_id, chat_user_id=bot_id
        )
    except Exception as exc:
        metadata = dict(stream.settings or {})
        metadata["twitch_bot_eventsub_status"] = "error"
        stream.settings = metadata
        await db.commit()
        raise ValidationError(
            f"@{bot_login} ya quedó como moderador, pero Twitch no activó los eventos del chat. "
            f"Puedes reintentar. Detalle: {str(exc)[:180]}"
        ) from exc

    metadata = dict(stream.settings or {})
    metadata["twitch_bot_eventsub_status"] = "enabled"
    report = dict(metadata.get("eventsub_subscriptions", {}))
    item = subscription.get("data", [{}])[0]
    report["channel.chat.message"] = {
        "status": "enabled",
        "id": item.get("id"),
        "existing": bool(subscription.get("existing")),
    }
    metadata["eventsub_subscriptions"] = report
    stream.settings = metadata
    await db.commit()
    return {
        "moderator_status": "already_moderator" if moderator.get("already_moderator") else "added",
        "eventsub_status": "enabled",
        "bot_login": bot_login,
    }


@router.post("/{stream_id}/subscribe")
async def subscribe_bot_chat_events(
    stream_id: UUID,
    current_user: StreamModeratorUser,
    db: AsyncSession = Depends(get_db),
):
    stream = await _get_manageable_stream(stream_id, current_user, db)
    from app.core.config import get_settings
    from app.services.twitch_chat_moderation import get_twitch_bot_credentials
    from app.integrations.twitch.eventsub import TwitchEventSubClient

    config = get_settings()
    if not config.twitch_eventsub_callback_url or not config.twitch_webhook_secret:
        raise ValidationError("Configura el callback y el secreto de Twitch EventSub en el backend.")
    bot_token, bot_id, _ = await get_twitch_bot_credentials(stream)
    if not bot_token or not bot_id:
        raise ValidationError("Conecta primero la cuenta de bot moderadora de Twitch.")
    try:
        result = await TwitchEventSubClient(bot_token).ensure_subscription(
            "channel.chat.message", stream.external_id, chat_user_id=bot_id
        )
    except Exception as exc:
        metadata = dict(stream.settings or {})
        metadata["twitch_bot_eventsub_status"] = "error"
        stream.settings = metadata
        await db.commit()
        raise ValidationError(
            "Twitch no aceptó la suscripción de chat. Confirma que el bot ya es moderador con "
            f"/mod {metadata.get('twitch_bot_login', 'usuario_bot')} y vuelve a intentarlo. "
            f"Detalle: {str(exc)[:180]}"
        ) from exc
    metadata = dict(stream.settings or {})
    metadata["twitch_bot_eventsub_status"] = "enabled"
    report = dict(metadata.get("eventsub_subscriptions", {}))
    item = result.get("data", [{}])[0]
    report["channel.chat.message"] = {
        "status": "enabled", "id": item.get("id"), "existing": bool(result.get("existing"))
    }
    metadata["eventsub_subscriptions"] = report
    stream.settings = metadata
    await db.commit()
    return {"status": "enabled", "existing": bool(result.get("existing"))}


@router.delete("/{stream_id}/bot")
async def disconnect_bot(
    stream_id: UUID,
    current_user: StreamModeratorUser,
    db: AsyncSession = Depends(get_db),
):
    stream = await _get_manageable_stream(stream_id, current_user, db)
    metadata = dict(stream.settings or {})
    token_encrypted = metadata.get("twitch_bot_access_token_encrypted")
    moderator_removed = False
    bot_user_id = metadata.get("twitch_bot_user_id")
    if bot_user_id and metadata.get("twitch_bot_moderator_status") == "added":
        try:
            from app.services.platforms.oauth_tokens import get_stream_access_token
            from app.integrations.twitch.moderation import remove_channel_moderator_on_twitch

            broadcaster_token = await get_stream_access_token(stream)
            if broadcaster_token:
                result = await remove_channel_moderator_on_twitch(
                    stream.external_id, str(bot_user_id), broadcaster_token
                )
                moderator_removed = bool(result.get("ok"))
        except Exception:
            # Continue local cleanup even if Twitch cannot be reached.
            pass
    metadata = dict(stream.settings or {})
    if token_encrypted:
        try:
            from app.core.config import get_settings
            from app.core.security import decrypt_value
            from app.integrations.twitch.eventsub import TwitchEventSubClient
            import httpx

            token = decrypt_value(token_encrypted)
            subscription_id = (
                (metadata.get("eventsub_subscriptions") or {})
                .get("channel.chat.message", {})
                .get("id")
            )
            if subscription_id:
                await TwitchEventSubClient(token).delete_subscription(str(subscription_id))
            async with httpx.AsyncClient(timeout=8.0) as client:
                await client.post(
                    "https://id.twitch.tv/oauth2/revoke",
                    data={"client_id": get_settings().twitch_client_id, "token": token},
                )
        except Exception:
            # Local disconnection must still complete if Twitch is unreachable.
            pass
    for key in (
        "twitch_bot_access_token_encrypted",
        "twitch_bot_refresh_token_encrypted",
        "twitch_bot_access_expires_at",
        "twitch_bot_user_id",
        "twitch_bot_login",
        "twitch_bot_moderator_status",
        "twitch_bot_eventsub_status",
    ):
        metadata.pop(key, None)
    eventsub_report = dict(metadata.get("eventsub_subscriptions", {}))
    eventsub_report.pop("channel.chat.message", None)
    metadata["eventsub_subscriptions"] = eventsub_report
    config = dict(metadata.get("twitch_chat_moderation", {}))
    config["enabled"] = False
    metadata["twitch_chat_moderation"] = config
    stream.settings = metadata
    await db.commit()
    return {"disconnected": True, "moderator_removed": moderator_removed}
