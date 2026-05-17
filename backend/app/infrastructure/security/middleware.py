import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.exceptions import RateLimitError
from app.infrastructure.cache.redis_client import RedisCache

settings = get_settings()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        csp = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self' wss: https:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers["Content-Security-Policy"] = csp
        return response


class DistributedRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, cache: RedisCache = None):
        super().__init__(app)
        self.cache = cache or RedisCache(prefix="ratelimit")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in ("/health", "/metrics", "/docs", "/openapi.json"):
            return await call_next(request)
        if request.url.path.startswith("/api/v1/widget"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        identifier = f"{client_ip}:{request.url.path}"

        try:
            allowed, current = await self.cache.check_rate_limit(
                identifier,
                settings.rate_limit_per_minute,
                60,
            )
        except Exception:
            allowed, current = True, 0

        if not allowed:
            raise RateLimitError(f"Rate limit exceeded: {current}/{settings.rate_limit_per_minute}")

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(max(0, settings.rate_limit_per_minute - current))
        return response


class AntiDDoSMiddleware(BaseHTTPMiddleware):
    MAX_BODY_SIZE = 10 * 1024 * 1024
    BLOCKED_PATHS = {"/.env", "/wp-admin", "/admin.php", "/.git"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if any(request.url.path.startswith(p) for p in self.BLOCKED_PATHS):
            return Response(status_code=404)

        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.MAX_BODY_SIZE:
            return Response(status_code=413, content="Payload too large")

        user_agent = request.headers.get("user-agent", "")
        if not user_agent and request.url.path.startswith("/api"):
            return Response(status_code=403, content="Forbidden")

        return await call_next(request)


class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        response.headers["X-Response-Time"] = f"{duration:.4f}s"
        return response
