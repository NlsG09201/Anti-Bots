import hashlib
import hmac

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import RedisCache

logger = get_logger(__name__)
settings = get_settings()


class BruteForceProtection:
    def __init__(self):
        self.cache = RedisCache(prefix="bruteforce")

    def _key(self, identifier: str) -> str:
        fingerprint = hmac.new(
            settings.app_secret_key.encode("utf-8"),
            identifier.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"login:{fingerprint}"

    async def record_failure(self, identifier: str) -> int:
        key = self._key(identifier)
        count = await self.cache.incr(key, ttl=settings.fail2ban_window_seconds)
        if count >= settings.fail2ban_max_attempts:
            logger.warning(
                "bruteforce_lockout",
                identifier_hash=key.removeprefix("login:")[:16],
                attempts=count,
            )
        return count

    async def clear_failures(self, identifier: str) -> None:
        await self.cache.delete(self._key(identifier))

    async def is_locked(self, identifier: str) -> bool:
        key = self._key(identifier)
        val = await self.cache.get(key)
        if val is None:
            return False
        try:
            return int(val) >= settings.fail2ban_max_attempts
        except (TypeError, ValueError):
            return False

    async def check_and_raise(self, identifier: str) -> None:
        if await self.is_locked(identifier):
            raise AuthenticationError(
                f"Too many failed attempts. Try again in {settings.fail2ban_window_seconds // 60} minutes."
            )

