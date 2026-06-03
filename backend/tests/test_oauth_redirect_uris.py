from app.core.config import invalidate_settings_cache
from app.integrations.kick.constants import (
    PRODUCTION_CALLBACK_URL as KICK_PRODUCTION_CALLBACK_URL,
    resolve_kick_redirect_uri,
)
from app.integrations.youtube.constants import (
    PRODUCTION_CALLBACK_URL as YOUTUBE_PRODUCTION_CALLBACK_URL,
    resolve_youtube_redirect_uri,
)


def test_kick_legacy_frontend_callback_is_normalized(monkeypatch):
    monkeypatch.setenv(
        "KICK_REDIRECT_URI",
        "https://anti-bots.vercel.app/auth/kick/callback",
    )
    invalidate_settings_cache()

    assert (
        resolve_kick_redirect_uri()
        == "https://anti-bots.vercel.app/api/v1/integrations/kick/callback"
    )

    invalidate_settings_cache()


def test_youtube_legacy_frontend_callback_is_normalized(monkeypatch):
    monkeypatch.setenv(
        "YOUTUBE_REDIRECT_URI",
        "https://anti-bots.vercel.app/auth/youtube/callback",
    )
    invalidate_settings_cache()

    assert (
        resolve_youtube_redirect_uri()
        == "https://anti-bots.vercel.app/api/v1/integrations/youtube/callback"
    )

    invalidate_settings_cache()


def test_render_does_not_use_local_redirects(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("KICK_REDIRECT_URI", "http://localhost:3000/auth/kick/callback")
    monkeypatch.setenv(
        "YOUTUBE_REDIRECT_URI",
        "http://localhost:3000/auth/youtube/callback",
    )
    invalidate_settings_cache()

    assert resolve_kick_redirect_uri() == KICK_PRODUCTION_CALLBACK_URL
    assert resolve_youtube_redirect_uri() == YOUTUBE_PRODUCTION_CALLBACK_URL

    invalidate_settings_cache()


def test_render_does_not_use_inactive_render_alias(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv(
        "KICK_REDIRECT_URI",
        "https://anti-bots-api.onrender.com/api/v1/integrations/kick/callback",
    )
    monkeypatch.setenv(
        "YOUTUBE_REDIRECT_URI",
        "https://anti-bots-api.onrender.com/api/v1/integrations/youtube/callback",
    )
    invalidate_settings_cache()

    assert resolve_kick_redirect_uri() == KICK_PRODUCTION_CALLBACK_URL
    assert resolve_youtube_redirect_uri() == YOUTUBE_PRODUCTION_CALLBACK_URL

    invalidate_settings_cache()


def test_render_does_not_use_vercel_proxy_callback(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv(
        "KICK_REDIRECT_URI",
        "https://anti-bots.vercel.app/auth/kick/callback",
    )
    monkeypatch.setenv(
        "YOUTUBE_REDIRECT_URI",
        "https://anti-bots.vercel.app/auth/youtube/callback",
    )
    invalidate_settings_cache()

    assert resolve_kick_redirect_uri() == KICK_PRODUCTION_CALLBACK_URL
    assert resolve_youtube_redirect_uri() == YOUTUBE_PRODUCTION_CALLBACK_URL

    invalidate_settings_cache()
