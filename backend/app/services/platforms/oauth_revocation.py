"""Best-effort revocation of platform OAuth grants before local unlinking."""

from __future__ import annotations

from typing import Iterable

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import decrypt_value
from app.infrastructure.database.models import Platform, Stream

logger = get_logger(__name__)


async def revoke_provider_grant(
    platform: Platform,
    access_token: str | None,
    refresh_token: str | None,
) -> bool:
    """Revoke provider credentials where supported; never expose token values in logs."""
    candidates: Iterable[tuple[str, str, dict[str, str], dict[str, str]]] = ()
    settings = get_settings()

    if platform == Platform.TWITCH and access_token:
        candidates = ((
            "twitch",
            "https://id.twitch.tv/oauth2/revoke",
            {"client_id": settings.twitch_client_id, "token": access_token},
            {},
        ),)
    elif platform == Platform.KICK:
        candidates = tuple(
            ("kick", "https://id.kick.com/oauth/revoke", {}, {
                "token": token,
                "token_hint_type": token_type,
            })
            for token, token_type in (
                (refresh_token, "refresh_token"),
                (access_token, "access_token"),
            )
            if token
        )
    elif platform == Platform.YOUTUBE:
        token = refresh_token or access_token
        if token:
            candidates = ((
                "youtube",
                "https://oauth2.googleapis.com/revoke",
                {"token": token},
                {},
            ),)

    if not candidates:
        return False

    any_revoked = False
    async with httpx.AsyncClient(timeout=8.0) as client:
        for provider, url, form, params in candidates:
            try:
                response = await client.post(
                    url,
                    data=form,
                    params=params,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                if response.is_success:
                    any_revoked = True
                else:
                    logger.warning(
                        "oauth_provider_revocation_failed",
                        platform=provider,
                        status_code=response.status_code,
                    )
            except httpx.HTTPError as exc:
                logger.warning(
                    "oauth_provider_revocation_failed",
                    platform=provider,
                    error_type=type(exc).__name__,
                )
    return any_revoked


async def disconnect_stream_account(stream: Stream) -> dict[str, object]:
    """Revoke provider credentials if possible and always remove them locally."""
    metadata = dict(stream.settings or {})
    access_token = None
    refresh_token = None
    try:
        if stream.oauth_token_encrypted:
            access_token = decrypt_value(stream.oauth_token_encrypted)
    except Exception as exc:
        logger.warning(
            "oauth_access_token_decryption_failed",
            platform=stream.platform.value,
            error_type=type(exc).__name__,
        )
    try:
        refresh_token_encrypted = metadata.get("refresh_token_encrypted")
        if refresh_token_encrypted:
            refresh_token = decrypt_value(refresh_token_encrypted)
    except Exception as exc:
        logger.warning(
            "oauth_refresh_token_decryption_failed",
            platform=stream.platform.value,
            error_type=type(exc).__name__,
        )

    provider_revoked = await revoke_provider_grant(
        stream.platform,
        access_token,
        refresh_token,
    )

    stream.oauth_token_encrypted = None
    for key in ("refresh_token_encrypted", "oauth_access_expires_at"):
        metadata.pop(key, None)
    if stream.platform == Platform.TWITCH:
        metadata.pop("eventsub_subscriptions", None)
    if stream.platform == Platform.KICK:
        metadata.pop("kick_chat_webhook_subscribed", None)
        metadata.pop("kick_webhook_callback_url", None)
    stream.settings = metadata

    return {"disconnected": True, "provider_revoked": provider_revoked}
