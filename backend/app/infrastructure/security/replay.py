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
        if not settings.security_replay_protection_enabled:
            return

        if not nonce or timestamp_ms is None:
            if settings.security_replay_strict:
                raise ValidationError("Missing X-SS-Nonce or X-SS-Timestamp")
            return

        now_ms = int(time.time() * 1000)
        skew_ms = settings.security_replay_max_skew_seconds * 1000
        if abs(now_ms - int(timestamp_ms)) > skew_ms:
            raise ValidationError("Request timestamp outside allowed window")

        nonce_key = f"{scope}:{nonce}"
        existing = await self._cache.get(nonce_key)
        if existing:
            raise ValidationError("Replay detected: nonce already used")

        if secret and signature and settings.security_widget_hmac_enabled:
            expected = hmac.new(
                secret.encode("utf-8"),
                f"{timestamp_ms}.{nonce}.".encode("utf-8") + body,
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, signature.strip()):
                raise ValidationError("Invalid request signature")

        ttl = settings.security_replay_nonce_ttl_seconds
        await self._cache.set(nonce_key, "1", ttl=ttl)
