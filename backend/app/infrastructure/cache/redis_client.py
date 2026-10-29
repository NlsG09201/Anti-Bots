import json
import time
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()
_pool: Optional[redis.Redis] = None
_rest_client: Optional[httpx.AsyncClient] = None
_memory: dict[str, tuple[str, float]] = {}


def redis_is_configured() -> bool:
    """Return whether native Redis TCP is configured (required by arq/pubsub)."""
    url = (settings.redis_url or "").strip()
    if not url or "PEGAR_" in url:
        return False
    if "localhost" in url or "127.0.0.1" in url:
        return False
    if url.startswith("redis://:redis_secure_password"):
        return False
    return True


def redis_rest_is_configured() -> bool:
    url = (settings.upstash_redis_rest_url or "").strip()
    token = (settings.upstash_redis_rest_token or "").strip()
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc and token)


def redis_cache_is_configured() -> bool:
    return redis_is_configured() or redis_rest_is_configured()


async def get_redis() -> redis.Redis:
    global _pool
    if not redis_is_configured():
        raise RuntimeError("Redis TCP URL not configured; Upstash REST cannot provide arq/pubsub connections")
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
    global _pool, _rest_client
    if _pool:
        await _pool.close()
        _pool = None
    if _rest_client:
        await _rest_client.aclose()
        _rest_client = None


async def _upstash_pipeline(
    commands: list[list[Any]], *, transaction: bool = False
) -> list[Any]:
    global _rest_client
    if not redis_rest_is_configured():
        raise RuntimeError("Upstash REST is not configured")
    if _rest_client is None:
        _rest_client = httpx.AsyncClient(timeout=8.0)
    base_url = settings.upstash_redis_rest_url.strip().rstrip("/")
    response = await _rest_client.post(
        f"{base_url}/{'multi-exec' if transaction else 'pipeline'}",
        headers={
            "Authorization": f"Bearer {settings.upstash_redis_rest_token.strip()}",
            "Content-Type": "application/json",
        },
        json=commands,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or len(payload) != len(commands):
        raise RuntimeError("Unexpected Upstash REST pipeline response")
    results = []
    for item in payload:
        if not isinstance(item, dict) or "error" in item:
            detail = item.get("error", "invalid response") if isinstance(item, dict) else "invalid response"
            raise RuntimeError(f"Upstash Redis command failed: {detail}")
        results.append(item.get("result"))
    return results


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
        self._use_memory = not redis_cache_is_configured()
        self._use_rest = not redis_is_configured() and redis_rest_is_configured()

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        full = self._key(key)
        if self._use_memory:
            value = _memory_get(full)
        elif self._use_rest:
            value = (await _upstash_pipeline([["GET", full]]))[0]
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
        if self._use_rest:
            command = ["SET", full, serialized]
            if ttl > 0:
                command.extend(["EX", ttl])
            await _upstash_pipeline([command])
            return
        client = await get_redis()
        await client.setex(full, ttl, serialized)

    async def delete(self, key: str) -> None:
        full = self._key(key)
        if self._use_memory:
            _memory.pop(full, None)
            return
        if self._use_rest:
            await _upstash_pipeline([["DEL", full]])
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
        if self._use_rest:
            results = await _upstash_pipeline(
                [["INCR", full], ["EXPIRE", full, ttl]], transaction=True
            )
            return int(results[0])
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
            if self._use_rest:
                return bool((await _upstash_pipeline([["EXISTS", full]]))[0])
            client = await get_redis()
            return bool(await client.exists(full))
        except Exception:
            return False

    async def blacklist_token(self, jti: str, ttl: int) -> None:
        full = self._key(f"blacklist:{jti}")
        if self._use_memory:
            _memory_set(full, "1", ttl)
            return
        if self._use_rest:
            await _upstash_pipeline([["SET", full, "1", "EX", ttl]])
            return
        client = await get_redis()
        await client.setex(full, ttl, "1")

    async def check_rate_limit(self, identifier: str, limit: int, window: int) -> tuple[bool, int]:
        try:
            current = await self.incr(f"ratelimit:{identifier}", ttl=window)
            return current <= limit, current
        except Exception:
            return True, 0
