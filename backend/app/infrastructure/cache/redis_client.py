import json
from typing import Any, Optional

import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()
_pool: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
    return _pool


async def close_redis() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


class RedisCache:
    def __init__(self, prefix: str = "ss"):
        self.prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        client = await get_redis()
        value = await client.get(self._key(key))
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        client = await get_redis()
        serialized = json.dumps(value) if not isinstance(value, str) else value
        await client.setex(self._key(key), ttl, serialized)

    async def delete(self, key: str) -> None:
        client = await get_redis()
        await client.delete(self._key(key))

    async def incr(self, key: str, ttl: int = 60) -> int:
        client = await get_redis()
        full_key = self._key(key)
        pipe = client.pipeline()
        pipe.incr(full_key)
        pipe.expire(full_key, ttl)
        results = await pipe.execute()
        return results[0]

    async def is_blacklisted(self, jti: str) -> bool:
        try:
            client = await get_redis()
            return bool(await client.exists(self._key(f"blacklist:{jti}")))
        except Exception:
            return False

    async def blacklist_token(self, jti: str, ttl: int) -> None:
        client = await get_redis()
        await client.setex(self._key(f"blacklist:{jti}"), ttl, "1")

    async def check_rate_limit(self, identifier: str, limit: int, window: int) -> tuple[bool, int]:
        client = await get_redis()
        key = self._key(f"ratelimit:{identifier}")
        current = await client.incr(key)
        if current == 1:
            await client.expire(key, window)
        return current <= limit, current
