"""Rate limiting avanzado por IP, ruta, burst y endpoint sensible."""

from typing import Dict, Optional, Tuple

from fastapi import Request

from app.core.config import get_settings
from app.core.exceptions import RateLimitError
from app.infrastructure.cache.redis_client import RedisCache
from app.infrastructure.security.client_ip import resolve_client_ip

settings = get_settings()

# (requests, window_seconds)
ROUTE_LIMITS: Dict[str, Tuple[int, int]] = {
    "/api/v1/auth/login": (8, 60),
    "/api/v1/auth/register": (4, 3600),
    "/api/v1/auth/refresh": (30, 60),
    "/api/v1/auth/mfa": (10, 60),
    "/api/v1/detection/fingerprint": (40, 60),
    "/api/v1/detection/analyze-ip": (20, 60),
    "/api/v1/widget/ping": (180, 60),
}


class AdvancedRateLimiter:
    def __init__(self, cache: Optional[RedisCache] = None):
        self._cache = cache or RedisCache(prefix="rl")

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

        # Bucket global por IP (anti-DDoS distribuido)
        global_key = f"ip:{client_ip}:global"
        global_limit = settings.security_global_ip_limit_per_minute
        allowed_g, count_g = await self._cache.check_rate_limit(
            global_key, global_limit, 60
        )
        if not allowed_g:
            raise RateLimitError(
                f"Global rate limit exceeded for IP ({count_g}/{global_limit} per minute)"
            )

        # Burst corto (picos de 10s)
        burst_key = f"ip:{client_ip}:burst"
        burst_limit = settings.rate_limit_burst
        allowed_b, count_b = await self._cache.check_rate_limit(
            burst_key, burst_limit, 10
        )
        if not allowed_b:
            raise RateLimitError(f"Burst limit exceeded ({count_b}/{burst_limit} per 10s)")

        # Por ruta
        route_key = f"ip:{client_ip}:route:{path}"
        allowed_r, count_r = await self._cache.check_rate_limit(
            route_key, route_limit, window
        )
        if not allowed_r:
            raise RateLimitError(
                f"Rate limit exceeded for {path} ({count_r}/{route_limit})"
            )

        return True, count_r, route_key
