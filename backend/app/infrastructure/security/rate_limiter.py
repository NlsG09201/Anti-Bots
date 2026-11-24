"""Rate limiting avanzado por IP, ruta, burst y endpoint sensible."""

import time
from typing import Dict, Optional, Tuple

from fastapi import Request

from app.core.config import get_settings
from app.core.exceptions import RateLimitError
from app.infrastructure.cache.redis_client import RedisCache
from app.infrastructure.security.client_ip import resolve_client_ip

settings = get_settings()

# (requests, window_seconds)
ROUTE_LIMITS: Dict[str, Tuple[int, int]] = {
    "/api/v1/webhooks/kick": (1200, 60),
    "/api/v1/webhooks/twitch": (1200, 60),
    "/api/v1/integrations/kick/webhook": (1200, 60),
    "/api/v1/auth/login": (8, 60),
    "/api/v1/auth/register": (4, 3600),
    "/api/v1/auth/refresh": (60, 60),
    "/api/v1/auth/csrf": (120, 60),
    "/api/v1/auth/me": (120, 60),
    "/api/v1/auth/mfa": (10, 60),
    "/api/v1/detection/fingerprint": (40, 60),
    "/api/v1/detection/analyze-ip": (20, 60),
    "/api/v1/widget/ping": (180, 60),
}


class AdvancedRateLimiter:
    def __init__(self, cache: Optional[RedisCache] = None):
        self._cache = cache or RedisCache(prefix="rl")
        self._local_buckets: Dict[str, Tuple[int, float]] = {}

    def _check_local_bucket(self, key: str, limit: int, window: int) -> Tuple[bool, int]:
        now = time.monotonic()
        count, expires_at = self._local_buckets.get(key, (0, 0.0))
        if expires_at <= now:
            count, expires_at = 0, now + window
        count += 1
        self._local_buckets[key] = (count, expires_at)
        if len(self._local_buckets) > 10_000:
            self._local_buckets = {
                bucket: value
                for bucket, value in self._local_buckets.items()
                if value[1] > now
            }
        return count <= limit, count

    def check_local(self, request: Request) -> Tuple[bool, int, str]:
        """Emergency per-process limits for auth while the shared store is down."""
        path = request.url.path
        client_ip, _ = resolve_client_ip(request)
        route_limit, window = self._match_route_limit(path)
        auth_header = request.headers.get("authorization", "")
        has_bearer = auth_header.lower().startswith("bearer ")

        global_limit = settings.security_global_ip_limit_per_minute
        if has_bearer:
            global_limit = max(global_limit, 600)
        allowed, count = self._check_local_bucket(
            f"ip:{client_ip}:global", global_limit, 60
        )
        if not allowed:
            raise RateLimitError(
                f"Global rate limit exceeded for IP ({count}/{global_limit} per minute)"
            )

        if not has_bearer:
            allowed, count = self._check_local_bucket(
                f"ip:{client_ip}:burst", settings.rate_limit_burst, 10
            )
            if not allowed:
                raise RateLimitError(
                    f"Burst limit exceeded ({count}/{settings.rate_limit_burst} per 10s)"
                )

        route_key = f"ip:{client_ip}:route:{path}"
        allowed, count = self._check_local_bucket(route_key, route_limit, window)
        if not allowed:
            raise RateLimitError(
                f"Rate limit exceeded for {path} ({count}/{route_limit})"
            )
        return True, count, route_key

    def _match_route_limit(self, path: str) -> Tuple[int, int]:
        for prefix, limits in ROUTE_LIMITS.items():
            if path.startswith(prefix):
                return limits
        return settings.rate_limit_per_minute, 60

    async def check(self, request: Request) -> Tuple[bool, int, str]:
        """
        Comprueba límites globales por IP, burst y ruta.
        Returns (allowed, current_count, bucket_key).
        """
        if not settings.security_rate_limit_enabled:
            return True, 0, ""

        path = request.url.path
        if path in ("/health", "/metrics", "/docs", "/openapi.json", "/redoc"):
            return True, 0, ""

        client_ip, _ = resolve_client_ip(request)
        route_limit, window = self._match_route_limit(path)
        is_platform_webhook = path in {
            "/api/v1/webhooks/kick",
            "/api/v1/webhooks/twitch",
            "/api/v1/integrations/kick/webhook",
        }
        auth_header = request.headers.get("authorization", "")
        has_bearer = auth_header.lower().startswith("bearer ")

        # Bucket global por IP (anti-DDoS distribuido)
        global_key = f"ip:{client_ip}:global"
        global_limit = settings.security_global_ip_limit_per_minute
        if is_platform_webhook:
            # Platform deliveries can burst (and share proxy IPs); signed
            # webhook handlers provide endpoint-level authenticity checks.
            global_limit = max(global_limit, 1200)
        if has_bearer:
            global_limit = max(global_limit, 600)
        allowed_g, count_g = await self._cache.check_rate_limit(
            global_key, global_limit, 60
        )
        if not allowed_g:
            raise RateLimitError(
                f"Global rate limit exceeded for IP ({count_g}/{global_limit} per minute)"
            )

        # Burst corto (picos de 10s) — no aplicar a sesiones Bearer (dashboard SPA)
        if not has_bearer and not is_platform_webhook:
            burst_key = f"ip:{client_ip}:burst"
            burst_limit = settings.rate_limit_burst
            allowed_b, count_b = await self._cache.check_rate_limit(
                burst_key, burst_limit, 10
            )
            if not allowed_b:
                raise RateLimitError(f"Burst limit exceeded ({count_b}/{burst_limit} per 10s)")

        # Por ruta (agrupa sub-recursos para no contar cada UUID por separado en el burst de ruta)
        route_path = path
        if path.startswith("/api/v1/streams/") and path.count("/") >= 4:
            parts = path.split("/")
            if len(parts) >= 5:
                route_path = "/".join(parts[:5])
        route_key = f"ip:{client_ip}:route:{route_path}"
        allowed_r, count_r = await self._cache.check_rate_limit(
            route_key, route_limit, window
        )
        if not allowed_r:
            raise RateLimitError(
                f"Rate limit exceeded for {path} ({count_r}/{route_limit})"
            )

        return True, count_r, route_key
