"""Resolve OAuth access tokens from Stream settings (with refresh)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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

    # OAuth providers rotate refresh tokens. Refresh only when the access token
    # is near expiry instead of rotating credentials on every API request.
    expires_at_raw = meta.get("oauth_access_expires_at")
    if expires_at_raw:
        try:
            expires_at = datetime.fromisoformat(str(expires_at_raw).replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at > datetime.now(timezone.utc) + timedelta(minutes=2):
                return access
        except (TypeError, ValueError):
            logger.warning("oauth_expiry_invalid", platform=stream.platform.value)

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
            expires_in = int(data.get("expires_in") or 3600)
            meta["oauth_access_expires_at"] = (
                datetime.now(timezone.utc) + timedelta(seconds=max(expires_in, 60))
            ).isoformat()
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
