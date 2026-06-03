import os
from urllib.parse import urlparse

from app.core.config import get_settings

PRODUCTION_CALLBACK_URL = (
    "https://anti-bots.onrender.com/api/v1/integrations/youtube/callback"
)
LEGACY_FRONTEND_CALLBACK_PATH = "/auth/youtube/callback"
BACKEND_CALLBACK_PATH = "/api/v1/integrations/youtube/callback"
INVALID_PRODUCTION_HOSTS = {
    "anti-bots-api.onrender.com",
    "anti-bots.vercel.app",
    "anti-bots-vhbo.vercel.app",
}

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def resolve_youtube_redirect_uri() -> str:
    settings = get_settings()
    uri = (settings.youtube_redirect_uri or "").strip().rstrip("/")
    if uri.endswith(LEGACY_FRONTEND_CALLBACK_PATH):
        uri = uri[: -len(LEGACY_FRONTEND_CALLBACK_PATH)] + BACKEND_CALLBACK_PATH
    if os.getenv("RENDER") or settings.is_production:
        host = urlparse(uri).hostname if uri else ""
        if (
            not uri
            or "localhost" in uri
            or "127.0.0.1" in uri
            or host in INVALID_PRODUCTION_HOSTS
        ):
            return PRODUCTION_CALLBACK_URL
    if not uri:
        return PRODUCTION_CALLBACK_URL
    return uri
