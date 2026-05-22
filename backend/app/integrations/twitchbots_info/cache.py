"""Redis cache for TwitchBots.info lookups."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import RedisCache, redis_is_configured

logger = get_logger(__name__)
settings = get_settings()

PREFIX = "tbi"


class TwitchBotsInfoCache:
    def __init__(self) -> None:
        self._redis = RedisCache(prefix=PREFIX)
        self._memory: Dict[str, tuple[str, float]] = {}

    def _mem_get(self, key: str) -> Optional[str]:
        import time

        entry = self._memory.get(key)
        if not entry:
            return None
        value, expires = entry
        if expires and time.monotonic() > expires:
            self._memory.pop(key, None)
            return None
        return value

    def _mem_set(self, key: str, value: str, ttl: int) -> None:
        import time

        self._memory[key] = (value, time.monotonic() + ttl if ttl > 0 else 0.0)

    async def get_bot_hit(self, twitch_id: str) -> Optional[Dict[str, Any]]:
        key = f"hit:{twitch_id}"
        raw = await self._redis.get(key) if redis_is_configured() else self._mem_get(key)
        if not raw:
            return None
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return None

    async def set_bot_hit(self, twitch_id: str, payload: Dict[str, Any]) -> None:
        key = f"hit:{twitch_id}"
        ttl = max(int(settings.twitchbots_info_cache_ttl_hit), 300)
        serialized = json.dumps(payload, default=str)
        if redis_is_configured():
            await self._redis.set(key, serialized, ttl=ttl)
        else:
            self._mem_set(key, serialized, ttl)

    async def is_miss_cached(self, twitch_id: str) -> bool:
        key = f"miss:{twitch_id}"
        if redis_is_configured():
            return (await self._redis.get(key)) is not None
        return self._mem_get(key) is not None

    async def set_miss(self, twitch_id: str) -> None:
        key = f"miss:{twitch_id}"
        ttl = max(int(settings.twitchbots_info_cache_ttl_miss), 60)
        if redis_is_configured():
            await self._redis.set(key, "1", ttl=ttl)
        else:
            self._mem_set(key, "1", ttl)

    async def resolve_username(self, username: str) -> Optional[str]:
        key = f"uid:{username.lower()}"
        raw = await self._redis.get(key) if redis_is_configured() else self._mem_get(key)
        if raw is None:
            return None
        return str(raw).strip() or None

    async def store_username_id(self, username: str, twitch_id: str) -> None:
        key = f"uid:{username.lower()}"
        ttl = max(int(settings.twitchbots_info_username_cache_ttl), 3600)
        if redis_is_configured():
            await self._redis.set(key, twitch_id, ttl=ttl)
        else:
            self._mem_set(key, twitch_id, ttl)

    async def incr_stat(self, tenant_id: str, field: str, amount: int = 1) -> None:
        if not redis_is_configured():
            return
        try:
            await self._redis.incr(f"stats:{tenant_id}:{field}", ttl=86400 * 7)
        except Exception as exc:
            logger.debug("tbi_cache_stat_skip", error=str(exc)[:80])


_cache: Optional[TwitchBotsInfoCache] = None


def get_twitchbots_info_cache() -> TwitchBotsInfoCache:
    global _cache
    if _cache is None:
        _cache = TwitchBotsInfoCache()
    return _cache
