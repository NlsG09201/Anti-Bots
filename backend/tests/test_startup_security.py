from types import SimpleNamespace

import pytest

from app.core import startup
from app.core.config import Settings


def test_staging_uses_production_security_defaults():
    settings = Settings(app_env="staging", _env_file=None)

    assert settings.is_production is True
    assert settings.cookie_secure is True
    assert settings.cookie_samesite == "none"


def _production_settings(**overrides):
    values = {
        "is_production": True,
        "app_debug": False,
        "app_secret_key": "production-app-secret-that-is-not-default",
        "jwt_secret_key": "production-jwt-secret-that-is-not-default",
        "aes_encryption_key": "production-aes-key-that-is-not-default",
        "app_cors_origins": "https://dashboard.example.com",
        "cors_origins_list": ["https://dashboard.example.com"],
        "cookie_secure": True,
        "database_url": "postgresql+asyncpg://app:password@db.example.com/app",
        "redis_url": "redis://redis.example.com:6379/0",
        "upstash_redis_rest_url": "",
        "upstash_redis_rest_token": "",
        "event_pipeline_enabled": True,
        "event_queue_enabled": True,
        "event_realtime_pubsub_enabled": True,
        "trusted_hosts_list": ["api.example.com"],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_production_settings_accept_explicit_https_origins_and_hosts(monkeypatch):
    monkeypatch.setattr(startup, "get_settings", lambda: _production_settings())

    assert startup.validate_production_settings() == []


def test_production_settings_accept_explicit_render_service_hosts(monkeypatch):
    monkeypatch.setattr(
        startup,
        "get_settings",
        lambda: _production_settings(
            trusted_hosts_list=["anti-bots.onrender.com", "anti-bots-api.onrender.com"]
        ),
    )

    assert startup.validate_production_settings() == []


@pytest.mark.parametrize(
    ("redis_url", "rest_url", "rest_token"),
    [
        ("", "", ""),
        ("", "https://cache.example.com", "configured-token"),
    ],
)
def test_production_requires_native_redis_for_stream_features(
    monkeypatch, redis_url, rest_url, rest_token
):
    monkeypatch.setattr(
        startup,
        "get_settings",
        lambda: _production_settings(
            redis_url=redis_url,
            upstash_redis_rest_url=rest_url,
            upstash_redis_rest_token=rest_token,
        ),
    )

    assert any(
        "REDIS_URL is required in production" in error
        for error in startup.validate_production_settings()
    )


@pytest.mark.parametrize(
    "redis_url",
    [
        "redis://redis.example.com:not-a-port/0",
        "redis://localhost:6379/0",
        "redis://[::1]:6379/0",
        "https://redis.example.com/0",
    ],
)
def test_production_rejects_invalid_or_loopback_redis_urls(monkeypatch, redis_url):
    monkeypatch.setattr(
        startup,
        "get_settings",
        lambda: _production_settings(redis_url=redis_url),
    )

    assert any(
        "REDIS_URL is required in production" in error
        for error in startup.validate_production_settings()
    )


def test_production_can_disable_stream_features_without_redis(monkeypatch):
    monkeypatch.setattr(
        startup,
        "get_settings",
        lambda: _production_settings(
            redis_url="",
            event_pipeline_enabled=False,
            event_queue_enabled=False,
            event_realtime_pubsub_enabled=False,
        ),
    )

    assert startup.validate_production_settings() == []


@pytest.mark.parametrize(
    ("overrides", "expected_error"),
    [
        (
            {"app_cors_origins": "*", "cors_origins_list": ["*"]},
            "APP_CORS_ORIGINS must not allow every origin",
        ),
        (
            {
                "app_cors_origins": "http://dashboard.example.com",
                "cors_origins_list": ["http://dashboard.example.com"],
            },
            "APP_CORS_ORIGINS must use HTTPS",
        ),
        (
            {"trusted_hosts_list": ["*"]},
            "TRUSTED_HOSTS must not allow every host",
        ),
        (
            {"trusted_hosts_list": ["api.example.com", "localhost"]},
            "TRUSTED_HOSTS must not include loopback hosts",
        ),
    ],
)
def test_production_settings_reject_insecure_origins_and_hosts(
    monkeypatch, overrides, expected_error
):
    monkeypatch.setattr(
        startup, "get_settings", lambda: _production_settings(**overrides)
    )

    assert any(
        expected_error in error
        for error in startup.validate_production_settings()
    )
