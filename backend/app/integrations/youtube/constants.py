import os

from app.core.config import get_settings

PRODUCTION_CALLBACK_URL = (
    "https://anti-bots.onrender.com/api/v1/integrations/youtube/callback"
)

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def resolve_youtube_redirect_uri() -> str:
    settings = get_settings()
    uri = (settings.youtube_redirect_uri or "").strip().rstrip("/")
    if os.getenv("RENDER") or settings.is_production:
        if not uri or "localhost" in uri or "127.0.0.1" in uri:
            return PRODUCTION_CALLBACK_URL
    if not uri:
        return PRODUCTION_CALLBACK_URL
    return uri
