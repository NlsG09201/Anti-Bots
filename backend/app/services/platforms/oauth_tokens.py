"""Resolve OAuth access tokens from Stream settings (with refresh)."""

from __future__ import annotations

from typing import Optional

from app.core.logging import get_logger
from app.core.security import decrypt_value, encrypt_value
from app.infrastructure.database.models import Platform, Stream

logger = get_logger(__name__)


async def get_stream_access_token(stream: Stream) -> Optional[str]:
    if not stream.oauth_token_encrypted:
        return None
    meta = stream.settings or {}
    access = decrypt_value(stream.oauth_token_encrypted)
    refresh_enc = meta.get("refresh_token_encrypted")
    if not refresh_enc:
        return access

    refresh = decrypt_value(refresh_enc)
    try:
        if stream.platform == Platform.KICK:
            from app.integrations.kick.oauth import KickOAuth

            data = await KickOAuth().refresh_token(refresh)
        elif stream.platform == Platform.YOUTUBE:
            from app.integrations.youtube.oauth import YouTubeOAuth

            data = await YouTubeOAuth().refresh_token(refresh)
        else:
            return access
        new_access = data.get("access_token")
        new_refresh = data.get("refresh_token")
        if new_access:
            stream.oauth_token_encrypted = encrypt_value(new_access)
        if new_refresh:
            meta["refresh_token_encrypted"] = encrypt_value(new_refresh)
            stream.settings = meta
        return new_access or access
    except Exception as exc:
        logger.warning(
            "oauth_refresh_failed",
            platform=stream.platform.value,
            error=str(exc)[:200],
        )
        return access
