import secrets
from datetime import timedelta

from fastapi import Response

from app.core.config import get_settings

settings = get_settings()

REFRESH_COOKIE = "ss_refresh_token"
CSRF_COOKIE = "ss_csrf_token"
SESSION_HINT_COOKIE = "ss_session_hint"
CSRF_HEADER = "X-CSRF-Token"


def set_refresh_cookie(response: Response, token: str, max_age_days: int | None = None) -> None:
    days = max_age_days or settings.jwt_refresh_token_expire_days
    max_age = int(timedelta(days=days).total_seconds())
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        # Path /api so the cookie is sent on all proxied API calls (Vercel → Render).
        path="/api",
    )
    response.set_cookie(
        key=SESSION_HINT_COOKIE,
        value="1",
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE, path="/api")
    response.delete_cookie(key=REFRESH_COOKIE, path="/api/v1/auth")
    response.delete_cookie(key=CSRF_COOKIE, path="/")
    response.delete_cookie(key=SESSION_HINT_COOKIE, path="/")


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=CSRF_COOKIE,
        value=token,
        max_age=86400,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
