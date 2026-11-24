import hashlib
import hmac
import time

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import RedisCache

logger = get_logger(__name__)
settings = get_settings()
_local_failures: dict[str, tuple[int, float]] = {}
_local_pending_clears: set[str] = set()


class BruteForceProtection:
    def __init__(self):
        self.cache = RedisCache(prefix="bruteforce")
        self._local_fallback_until = 0.0

    def _use_local_fallback(self, error: Exception) -> None:
        if self._local_fallback_until <= time.monotonic():
            logger.warning(
                "bruteforce_local_fallback",
                error_type=type(error).__name__,
            )
        self._local_fallback_until = time.monotonic() + 60

    def _local_count(self, key: str) -> int:
        now = time.monotonic()
        count, expires_at = _local_failures.get(key, (0, 0.0))
        if expires_at <= now:
            _local_failures.pop(key, None)
            return 0
        return count

    def _local_record_failure(self, key: str) -> int:
        now = time.monotonic()
        count = self._local_count(key) + 1
        _local_failures[key] = (count, now + settings.fail2ban_window_seconds)
        if len(_local_failures) > 10_000:
            for stale_key in [
                candidate for candidate, (_, expiry) in _local_failures.items()
                if expiry <= now
            ]:
                _local_failures.pop(stale_key, None)
        return count

    def _key(self, identifier: str) -> str:
        fingerprint = hmac.new(
            settings.app_secret_key.encode("utf-8"),
            identifier.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"login:{fingerprint}"

    async def record_failure(self, identifier: str) -> int:
        key = self._key(identifier)
        try:
            if self._local_fallback_until > time.monotonic():
                count = self._local_record_failure(key)
            else:
                count = await self.cache.incr(key, ttl=settings.fail2ban_window_seconds)
        except Exception as exc:
            self._use_local_fallback(exc)
            count = self._local_record_failure(key)
        if count >= settings.fail2ban_max_attempts:
            logger.warning(
                "bruteforce_lockout",
                identifier_hash=key.removeprefix("login:")[:16],
                attempts=count,
            )
        return count

    async def clear_failures(self, identifier: str) -> None:
        key = self._key(identifier)
        _local_failures.pop(key, None)
        if self._local_fallback_until > time.monotonic():
            _local_pending_clears.add(key)
            return
        try:
            await self.cache.delete(key)
            _local_pending_clears.discard(key)
        except Exception as exc:
            self._use_local_fallback(exc)
            _local_pending_clears.add(key)

    async def is_locked(self, identifier: str) -> bool:
        key = self._key(identifier)
        try:
            if self._local_fallback_until > time.monotonic():
                return self._local_count(key) >= settings.fail2ban_max_attempts
            if key in _local_pending_clears:
                await self.cache.delete(key)
                _local_pending_clears.discard(key)
                val = None
            else:
                val = await self.cache.get(key)
            local_count = self._local_count(key)
            for _ in range(local_count):
                await self.cache.incr(key, ttl=settings.fail2ban_window_seconds)
            if local_count:
                val = await self.cache.get(key)
                _local_failures.pop(key, None)
            self._local_fallback_until = 0.0
        except Exception as exc:
            self._use_local_fallback(exc)
            return self._local_count(key) >= settings.fail2ban_max_attempts
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

