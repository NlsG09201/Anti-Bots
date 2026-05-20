import secrets

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.cookies import CSRF_COOKIE, CSRF_HEADER
from app.core.config import get_settings

settings = get_settings()

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_EXEMPT_PATHS = {
    "/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/v1/webhooks",
    "/api/v1/integrations/twitch/callback",
    "/api/v1/widget",
    # Refresh is protected by HttpOnly refresh cookie + rotation; exempt avoids
    # parallel 401 retries failing CSRF when the header cookie is stale.
    "/api/v1/auth/refresh",
}


class CSRFMiddleware(BaseHTTPMiddleware):
    """Validates CSRF token for cookie-authenticated state-changing requests."""

    async def dispatch(self, request: Request, call_next):
        if not settings.is_production:
            return await call_next(request)

        path = request.url.path
        if request.method in SAFE_METHODS:
            return await call_next(request)
        if any(path.startswith(p) for p in CSRF_EXEMPT_PATHS):
            return await call_next(request)

        from app.core.cookies import REFRESH_COOKIE
        if REFRESH_COOKIE not in request.cookies:
            return await call_next(request)

        cookie_token = request.cookies.get(CSRF_COOKIE)
        header_token = request.headers.get(CSRF_HEADER)
        if not cookie_token or not header_token or cookie_token != header_token:
            return Response(status_code=403, content="CSRF validation failed")

        return await call_next(request)


