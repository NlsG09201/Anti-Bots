"""
Middleware de seguridad unificado (defense in depth, OWASP API Top 10).
Orden: DDoS → headers → IP spoof → rate limit → request state.
"""

from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.exceptions import RateLimitError, StreamShieldError, ThreatDetectedError, ValidationError
from app.core.logging import get_logger
from app.infrastructure.security.client_ip import resolve_client_ip
from app.infrastructure.security.headers import validate_request_headers
from app.infrastructure.security.metrics_recorder import get_security_metrics_recorder
from app.infrastructure.security.rate_limiter import AdvancedRateLimiter

logger = get_logger(__name__)
settings = get_settings()

SCANNER_PATHS = (
    "/.env",
    "/.git",
    "/wp-admin",
    "/wp-login",
    "/admin.php",
    "/phpmyadmin",
    "/xmlrpc.php",
    "/actuator",
    "/.aws",
    "/config.json",
    "/server-status",
)


class SecurityGatewayMiddleware(BaseHTTPMiddleware):
    MAX_BODY = 10 * 1024 * 1024
    MAX_QUERY_LEN = 4096

    def __init__(self, app):
        super().__init__(app)
        self._rate_limiter = AdvancedRateLimiter()
        self._metrics = get_security_metrics_recorder()

    async def _record_block(self, reason: str) -> None:
        try:
            await self._metrics.record(reason)
        except Exception:
            pass

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        if any(path.startswith(p) for p in SCANNER_PATHS):
            await self._record_block("scanner_404")
            return Response(status_code=404)

        if len(str(request.url.query)) > self.MAX_QUERY_LEN:
            await self._record_block("query_414")
            return Response(status_code=414, content="URI too long")

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.MAX_BODY:
                    await self._record_block("payload_413")
                    return Response(status_code=413, content="Payload too large")
            except ValueError:
                return Response(status_code=400, content="Invalid Content-Length")

        is_widget = path.startswith("/api/v1/widget")

        header_result = validate_request_headers(request, is_widget=is_widget)
        if not header_result.allowed:
            logger.warning(
                "request_blocked_headers",
                path=path,
                flags=header_result.flags,
            )
            await self._record_block("headers_403")
            return Response(status_code=403, content="Forbidden")

        client_ip, ip_meta = resolve_client_ip(request)
        request.state.client_ip = client_ip
        request.state.ip_meta = ip_meta
        request.state.header_security = header_result.to_dict()

        if ip_meta.get("xff_spoof_risk") and settings.security_block_spoofed_ip:
            logger.warning("ip_spoof_attempt", path=path, meta=ip_meta)
            await self._record_block("spoof_403")
            return Response(status_code=403, content="Forbidden")

        if header_result.automation_detected and settings.security_block_automation:
            await self._record_block("automation_403")
            return Response(status_code=403, content="Automation not allowed")

        try:
            allowed, current, _ = await self._rate_limiter.check(request)
            request.state.rate_limit_remaining = max(
                0, settings.rate_limit_per_minute - current
            )
        except RateLimitError as exc:
            await self._record_block("rate_limit_429")
            return Response(
                status_code=429,
                content=str(exc.message),
                headers={"Retry-After": "60"},
            )

        try:
            response = await call_next(request)
        except (ValidationError, ThreatDetectedError, StreamShieldError) as exc:
            return Response(status_code=exc.status_code, content=exc.message)

        if hasattr(request.state, "rate_limit_remaining"):
            response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_per_minute)
            response.headers["X-RateLimit-Remaining"] = str(
                getattr(request.state, "rate_limit_remaining", 0)
            )
        response.headers["X-Client-IP-Validated"] = "1"
        return response
