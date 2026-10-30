"""Protección anti-replay (nonce + ventana temporal). OWASP: replay attack prevention."""

import hashlib
import hmac
import time
from typing import Optional

from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.infrastructure.cache.redis_client import RedisCache

settings = get_settings()


class ReplayProtection:
    def __init__(self, cache: Optional[RedisCache] = None):
        self._cache = cache or RedisCache(prefix="replay")

    async def validate_request(
        self,
        *,
        scope: str,
        nonce: Optional[str],
        timestamp_ms: Optional[int],
        signature: Optional[str] = None,
        body: bytes = b"",
        secret: Optional[str] = None,
    ) -> None:
        if not settings.security_replay_protection_enabled and not settings.security_widget_hmac_enabled:
            return

        if not nonce or timestamp_ms is None:
            raise ValidationError("Missing X-SS-Nonce or X-SS-Timestamp")

        now_ms = int(time.time() * 1000)
        skew_ms = settings.security_replay_max_skew_seconds * 1000
        if abs(now_ms - int(timestamp_ms)) > skew_ms:
            raise ValidationError("Request timestamp outside allowed window")

        if settings.security_widget_hmac_enabled:
            if not secret or not signature:
                raise ValidationError("Missing X-SS-Signature")
            expected = hmac.new(
                secret.encode("utf-8"),
                f"{timestamp_ms}.{nonce}.".encode("utf-8") + body,
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, signature.strip()):
                raise ValidationError("Invalid request signature")

        # A timestamp accepted at the future-skew boundary remains valid for
        # almost twice the configured skew window. Retain its nonce beyond that.
        ttl = max(
            settings.security_replay_nonce_ttl_seconds,
            2 * settings.security_replay_max_skew_seconds + 1,
        )
        claimed = await self._cache.set_if_absent(f"{scope}:{nonce}", "1", ttl=ttl)
        if not claimed:
            raise ValidationError("Replay detected: nonce already used")
