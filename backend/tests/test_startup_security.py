from types import SimpleNamespace

import pytest

from app.core import startup


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
        "trusted_hosts_list": ["api.example.com"],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_production_settings_accept_explicit_https_origins_and_hosts(monkeypatch):
    monkeypatch.setattr(startup, "get_settings", lambda: _production_settings())

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
