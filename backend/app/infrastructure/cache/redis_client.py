import json
import time
from typing import Any, Optional

import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()
_pool: Optional[redis.Redis] = None
_memory: dict[str, tuple[str, float]] = {}


def redis_is_configured() -> bool:
    url = (settings.redis_url or "").strip()
    if not url or "PEGAR_" in url:
        return False
    if "localhost" in url or "127.0.0.1" in url:
        return False
    if url.startswith("redis://:redis_secure_password"):
        return False
    return True


async def get_redis() -> redis.Redis:
    global _pool
    if not redis_is_configured():
        raise RuntimeError("Redis not configured")
    if _pool is None:
        _pool = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
    return _pool


async def optional_get_redis() -> Optional[redis.Redis]:
    """Redis client when configured; None otherwise (never raises)."""
    if not redis_is_configured():
        return None
    try:
        return await get_redis()
    except Exception:
        return None


async def close_redis() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def _memory_get(full_key: str) -> Optional[str]:
    entry = _memory.get(full_key)
    if not entry:
        return None
    value, expires = entry
    if expires and time.monotonic() > expires:
        _memory.pop(full_key, None)
        return None
    return value


def _memory_set(full_key: str, value: str, ttl: int) -> None:
    expires = time.monotonic() + ttl if ttl > 0 else 0.0
    _memory[full_key] = (value, expires)


class RedisCache:
    def __init__(self, prefix: str = "ss"):
        self.prefix = prefix
        self._use_memory = not redis_is_configured()

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        full = self._key(key)
        if self._use_memory:
            value = _memory_get(full)
        else:
            client = await get_redis()
            value = await client.get(full)
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        serialized = json.dumps(value) if not isinstance(value, str) else value
        full = self._key(key)
        if self._use_memory:
            _memory_set(full, serialized, ttl)
            return
        client = await get_redis()
        await client.setex(full, ttl, serialized)

    async def delete(self, key: str) -> None:
        full = self._key(key)
        if self._use_memory:
            _memory.pop(full, None)
            return
        client = await get_redis()
        await client.delete(full)

    async def incr(self, key: str, ttl: int = 60) -> int:
        full = self._key(key)
        if self._use_memory:
            raw = _memory_get(full)
            current = int(raw) + 1 if raw and raw.isdigit() else 1
            _memory_set(full, str(current), ttl)
            return current
        client = await get_redis()
        pipe = client.pipeline()
        pipe.incr(full)
        pipe.expire(full, ttl)
        results = await pipe.execute()
        return results[0]

    async def is_blacklisted(self, jti: str) -> bool:
        try:
            full = self._key(f"blacklist:{jti}")
            if self._use_memory:
                return _memory_get(full) is not None
            client = await get_redis()
            return bool(await client.exists(full))
        except Exception:
            return False

    async def blacklist_token(self, jti: str, ttl: int) -> None:
        full = self._key(f"blacklist:{jti}")
        if self._use_memory:
            _memory_set(full, "1", ttl)
            return
        client = await get_redis()
        await client.setex(full, ttl, "1")

    async def check_rate_limit(self, identifier: str, limit: int, window: int) -> tuple[bool, int]:
        try:
            current = await self.incr(f"ratelimit:{identifier}", ttl=window)
            return current <= limit, current
        except Exception:
            return True, 0
