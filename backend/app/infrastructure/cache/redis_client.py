import ipaddress
import json
import time
import fnmatch
from typing import Any, Iterator, Optional
from urllib.parse import urlparse

import httpx
import redis.asyncio as redis
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
    TimeoutError as RedisTimeoutError,
)

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()
_pool: Optional[redis.Redis] = None
_rest_client: Optional[httpx.AsyncClient] = None
_memory: dict[str, tuple[str, float]] = {}
_upstash_quota_exhausted = False


def report_redis_error(error: Exception) -> bool:
    """Open a process-local circuit after a Redis quota or connectivity failure."""
    global _upstash_quota_exhausted
    detail = str(error).lower()
    quota_exhausted = "max requests limit exceeded" in detail
    connection_failed = isinstance(
        error, (TimeoutError, RedisConnectionError, RedisTimeoutError)
    ) or any(
        marker in detail
        for marker in (
            "timeout connecting to server",
            "connection refused",
            "connection reset",
            "name or service not known",
            "temporary failure in name resolution",
        )
    )
    if not (quota_exhausted or connection_failed):
        return False
    if not _upstash_quota_exhausted:
        logger.error(
            "redis_unavailable_local_fallback_enabled",
            error_type=type(error).__name__,
            failure="quota_exhausted" if quota_exhausted else "connection_unavailable",
        )
    _upstash_quota_exhausted = True
    return True


def redis_quota_is_exhausted() -> bool:
    return _upstash_quota_exhausted


def redis_tcp_url_is_configured(url: Optional[str]) -> bool:
    """Validate a native Redis TCP URL without connecting to the service."""
    url = (url or "").strip()
    if not url or "PEGAR_" in url.upper():
        return False
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme not in {"redis", "rediss"} or not hostname:
        return False
    if port is not None and not 1 <= port <= 65535:
        return False
    try:
        is_localhost = hostname.lower().rstrip(".") == "localhost"
        if is_localhost or ipaddress.ip_address(hostname).is_loopback:
            return False
    except ValueError:
        pass
    if parsed.password == "redis_secure_password":
        return False
    return True


def redis_is_configured() -> bool:
    """Return whether native Redis TCP is configured (required by arq/pubsub)."""
    return not _upstash_quota_exhausted and redis_tcp_url_is_configured(settings.redis_url)


def redis_rest_is_configured() -> bool:
    url = (settings.upstash_redis_rest_url or "").strip()
    token = (settings.upstash_redis_rest_token or "").strip()
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc and token)


def redis_cache_is_configured() -> bool:
    return not _upstash_quota_exhausted and (
        redis_tcp_url_is_configured(settings.redis_url) or redis_rest_is_configured()
    )


async def get_redis() -> redis.Redis:
    global _pool
    if _upstash_quota_exhausted:
        raise RuntimeError("Upstash request quota exhausted; Redis circuit is open")
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


def _memory_scan(full_match: str) -> Iterator[str]:
    now = time.monotonic()
    for key, (_, expires) in list(_memory.items()):
        if expires and now > expires:
            _memory.pop(key, None)
        elif fnmatch.fnmatchcase(key, full_match):
            yield key


class RedisCache:
    def __init__(self, prefix: str = "ss"):
        self.prefix = prefix
        self._use_memory = _upstash_quota_exhausted or not redis_cache_is_configured()
        self._use_rest = (
            not self._use_memory
            and not redis_tcp_url_is_configured(settings.redis_url)
            and redis_rest_is_configured()
        )

    def _sync_quota_fallback(self, error: Exception) -> bool:
        if not report_redis_error(error):
            return False
        self._use_memory = True
        self._use_rest = False
        return True

    def _activate_open_circuit(self) -> None:
        if _upstash_quota_exhausted:
            self._use_memory = True
            self._use_rest = False

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        self._activate_open_circuit()
        full = self._key(key)
        if self._use_memory:
            value = _memory_get(full)
        elif self._use_rest:
            try:
                value = (await _upstash_pipeline([["GET", full]]))[0]
            except Exception as exc:
                if not self._sync_quota_fallback(exc):
                    raise
                value = _memory_get(full)
        else:
            try:
                client = await get_redis()
                value = await client.get(full)
            except Exception as exc:
                if not self._sync_quota_fallback(exc):
                    raise
                value = _memory_get(full)
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        self._activate_open_circuit()
        serialized = json.dumps(value) if not isinstance(value, str) else value
        full = self._key(key)
        if self._use_memory:
            _memory_set(full, serialized, ttl)
            return
        if self._use_rest:
            command = ["SET", full, serialized]
            if ttl > 0:
                command.extend(["EX", ttl])
            try:
                await _upstash_pipeline([command])
            except Exception as exc:
                if not self._sync_quota_fallback(exc):
                    raise
                _memory_set(full, serialized, ttl)
            return
        try:
            client = await get_redis()
            await client.setex(full, ttl, serialized)
        except Exception as exc:
            if not self._sync_quota_fallback(exc):
                raise
            _memory_set(full, serialized, ttl)

    async def set_if_absent(self, key: str, value: Any, ttl: int = 60) -> bool:
        """Atomically create a key only when it does not exist, with expiry."""
        self._activate_open_circuit()
        serialized = json.dumps(value) if not isinstance(value, str) else value
        full = self._key(key)
        if self._use_memory:
            if _memory_get(full) is not None:
                return False
            _memory_set(full, serialized, ttl)
            return True
        if self._use_rest:
            try:
                result = (await _upstash_pipeline([[
                    "SET", full, serialized, "NX", "EX", ttl,
                ]]))[0]
            except Exception as exc:
                if not self._sync_quota_fallback(exc):
                    raise
                if _memory_get(full) is not None:
                    return False
                _memory_set(full, serialized, ttl)
                return True
            return result == "OK"
        try:
            client = await get_redis()
            return bool(await client.set(full, serialized, ex=ttl, nx=True))
        except Exception as exc:
            if not self._sync_quota_fallback(exc):
                raise
            if _memory_get(full) is not None:
                return False
            _memory_set(full, serialized, ttl)
            return True

    async def delete(self, key: str) -> None:
        self._activate_open_circuit()
        full = self._key(key)
        if self._use_memory:
            _memory.pop(full, None)
            return
        if self._use_rest:
            try:
                await _upstash_pipeline([["DEL", full]])
            except Exception as exc:
                if not self._sync_quota_fallback(exc):
                    raise
                _memory.pop(full, None)
            return
        try:
            client = await get_redis()
            await client.delete(full)
        except Exception as exc:
            if not self._sync_quota_fallback(exc):
                raise
            _memory.pop(full, None)

    async def scan_iter(self, match: str, count: int = 50):
        """Iterate matching cache keys over native Redis, REST, or local memory."""
        self._activate_open_circuit()
        full_match = self._key(match)
        if self._use_memory:
            for key in _memory_scan(full_match):
                yield key
            return
        try:
            keys: list[str] = []
            if self._use_rest:
                cursor = "0"
                while True:
                    response = (await _upstash_pipeline([
                        ["SCAN", cursor, "MATCH", full_match, "COUNT", count]
                    ]))[0]
                    if not isinstance(response, (list, tuple)) or len(response) != 2:
                        raise RuntimeError("Unexpected Redis SCAN response")
                    cursor = str(response[0])
                    keys.extend(str(key) for key in (response[1] or []))
                    if cursor == "0":
                        break
            else:
                client = await get_redis()
                async for key in client.scan_iter(match=full_match, count=count):
                    keys.append(str(key))
        except Exception as exc:
            if not self._sync_quota_fallback(exc):
                raise
            for key in _memory_scan(full_match):
                yield key
            return
        for key in keys:
            yield key

    async def incr(self, key: str, ttl: int = 60) -> int:
        self._activate_open_circuit()
        full = self._key(key)
        if self._use_memory:
            raw = _memory_get(full)
            current = int(raw) + 1 if raw and raw.isdigit() else 1
            _memory_set(full, str(current), ttl)
            return current
        if self._use_rest:
            try:
                results = await _upstash_pipeline(
                    [["INCR", full], ["EXPIRE", full, ttl]], transaction=True
                )
            except Exception as exc:
                if not self._sync_quota_fallback(exc):
                    raise
                raw = _memory_get(full)
                current = int(raw) + 1 if raw and raw.isdigit() else 1
                _memory_set(full, str(current), ttl)
                return current
            return int(results[0])
        try:
            client = await get_redis()
            pipe = client.pipeline()
            pipe.incr(full)
            pipe.expire(full, ttl)
            results = await pipe.execute()
            return results[0]
        except Exception as exc:
            if not self._sync_quota_fallback(exc):
                raise
            raw = _memory_get(full)
            current = int(raw) + 1 if raw and raw.isdigit() else 1
            _memory_set(full, str(current), ttl)
            return current

    async def is_blacklisted(self, jti: str) -> bool:
        self._activate_open_circuit()
        full = self._key(f"blacklist:{jti}")
        if self._use_memory:
            return _memory_get(full) is not None
        if self._use_rest:
            try:
                return bool((await _upstash_pipeline([["EXISTS", full]]))[0])
            except Exception as exc:
                if not self._sync_quota_fallback(exc):
                    raise
                return _memory_get(full) is not None
        try:
            client = await get_redis()
            return bool(await client.exists(full))
        except Exception as exc:
            if not self._sync_quota_fallback(exc):
                raise
            return _memory_get(full) is not None

    async def blacklist_token(self, jti: str, ttl: int) -> None:
        self._activate_open_circuit()
        full = self._key(f"blacklist:{jti}")
        if self._use_memory:
            _memory_set(full, "1", ttl)
            return
        if self._use_rest:
            try:
                await _upstash_pipeline([["SET", full, "1", "EX", ttl]])
            except Exception as exc:
                if not self._sync_quota_fallback(exc):
                    raise
                _memory_set(full, "1", ttl)
            return
        try:
            client = await get_redis()
            await client.setex(full, ttl, "1")
        except Exception as exc:
            if not self._sync_quota_fallback(exc):
                raise
            _memory_set(full, "1", ttl)

    async def check_rate_limit(self, identifier: str, limit: int, window: int) -> tuple[bool, int]:
        current = await self.incr(f"ratelimit:{identifier}", ttl=window)
        return current <= limit, current
