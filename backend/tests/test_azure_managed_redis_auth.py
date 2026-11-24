from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.config import Settings
from app.infrastructure.cache import redis_client
from redis_entraid import cred_provider, identity_provider


def test_redis_auth_mode_keeps_password_auth_as_default():
    assert Settings(_env_file=None).redis_auth_mode == "password"
    assert (
        Settings(_env_file=None, redis_auth_mode="managed_identity").redis_auth_mode
        == "managed_identity"
    )


def test_redis_auth_mode_rejects_unknown_values():
    with pytest.raises(ValueError):
        Settings(_env_file=None, redis_auth_mode="unsupported")


@pytest.mark.parametrize(
    "url",
    [
        "redis://cache.example.com:10000",
        "rediss://user:password@cache.example.com:10000",
        "rediss://localhost:10000",
        "rediss://cache.example.com:not-a-port",
    ],
)
def test_managed_identity_requires_tls_external_host_and_no_url_credentials(url):
    assert not redis_client.redis_tcp_url_is_configured(url, require_tls=True)


def test_managed_identity_accepts_tls_url_without_embedded_credentials():
    assert redis_client.redis_tcp_url_is_configured(
        "rediss://cache.example.com:10000/0",
        require_tls=True,
    )


@pytest.mark.parametrize(
    ("client_id", "identity_type", "id_type", "id_value"),
    [
        ("", identity_provider.ManagedIdentityType.SYSTEM_ASSIGNED, None, ""),
        (
            "user-assigned-client-id",
            identity_provider.ManagedIdentityType.USER_ASSIGNED,
            identity_provider.ManagedIdentityIdType.CLIENT_ID,
            "user-assigned-client-id",
        ),
    ],
)
def test_managed_identity_provider_uses_configured_identity(
    monkeypatch, client_id, identity_type, id_type, id_value
):
    settings = SimpleNamespace(redis_managed_identity_client_id=client_id)
    factory = Mock(return_value=object())
    monkeypatch.setattr(redis_client, "settings", settings)
    monkeypatch.setattr(cred_provider, "create_from_managed_identity", factory)

    provider = redis_client._create_redis_credential_provider()

    assert provider is factory.return_value
    factory.assert_called_once_with(
        identity_type=identity_type,
        resource="https://redis.azure.com/",
        **(
            {"id_type": id_type, "id_value": id_value}
            if id_type is not None
            else {}
        ),
    )


@pytest.mark.asyncio
async def test_password_auth_remains_compatible_without_credential_provider(monkeypatch):
    pool = object()
    settings = SimpleNamespace(
        redis_auth_mode="password",
        redis_url="rediss://:existing-password@cache.example.com:10000/0",
    )
    from_url = Mock(return_value=pool)
    monkeypatch.setattr(redis_client, "settings", settings)
    monkeypatch.setattr(redis_client, "_pool", None)
    monkeypatch.setattr(redis_client.redis, "from_url", from_url)

    try:
        assert await redis_client.get_redis() is pool
        assert from_url.call_args.kwargs == {
            "encoding": "utf-8",
            "decode_responses": True,
            "max_connections": 50,
        }
    finally:
        monkeypatch.setattr(redis_client, "_pool", None)


@pytest.mark.asyncio
async def test_managed_identity_client_uses_refreshing_provider_and_tls_url(monkeypatch):
    provider = object()
    pool = object()
    settings = SimpleNamespace(
        redis_auth_mode="managed_identity",
        redis_managed_identity_client_id="",
        redis_url="rediss://cache.example.com:10000/0",
    )
    from_url = Mock(return_value=pool)
    monkeypatch.setattr(redis_client, "settings", settings)
    monkeypatch.setattr(redis_client, "_pool", None)
    monkeypatch.setattr(redis_client, "_create_redis_credential_provider", Mock(return_value=provider))
    monkeypatch.setattr(redis_client.redis, "from_url", from_url)

    try:
        assert await redis_client.get_redis() is pool
        from_url.assert_called_once_with(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
            credential_provider=provider,
        )
    finally:
        monkeypatch.setattr(redis_client, "_pool", None)


@pytest.mark.asyncio
async def test_managed_identity_rejects_non_tls_url_before_creating_client(monkeypatch):
    settings = SimpleNamespace(
        redis_auth_mode="managed_identity",
        redis_managed_identity_client_id="",
        redis_url="redis://cache.example.com:6379/0",
    )
    from_url = Mock()
    monkeypatch.setattr(redis_client, "settings", settings)
    monkeypatch.setattr(redis_client, "_pool", None)
    monkeypatch.setattr(redis_client.redis, "from_url", from_url)

    with pytest.raises(RuntimeError, match="requires a rediss:// URL"):
        await redis_client.get_redis()

    from_url.assert_not_called()
