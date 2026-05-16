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
        return f"login:{identifier}"

    async def record_failure(self, identifier: str) -> int:
        key = self._key(identifier)
        count = await self.cache.incr(key, ttl=settings.fail2ban_window_seconds)
        if count >= settings.fail2ban_max_attempts:
            logger.warning("bruteforce_lockout", identifier=identifier, attempts=count)
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
