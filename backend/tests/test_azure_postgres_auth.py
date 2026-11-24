from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.infrastructure.database import azure_postgres


def test_database_auth_mode_keeps_password_as_default_and_accepts_managed_identity():
    assert Settings(_env_file=None).database_auth_mode == "password"
    settings = Settings(_env_file=None, database_auth_mode="managed_identity")
    assert settings.database_auth_mode == "managed_identity"


def test_database_auth_mode_rejects_unknown_values():
    with pytest.raises(ValueError):
        Settings(_env_file=None, database_auth_mode="unsupported")


class FakeCredential:
    def __init__(self):
        self.scopes = []

    def get_token(self, scope):
        self.scopes.append(scope)
        return SimpleNamespace(token=f"access-token-{len(self.scopes)}")


@pytest.mark.asyncio
async def test_managed_identity_connector_uses_fresh_token_and_verified_tls(monkeypatch):
    credential = FakeCredential()
    connect = AsyncMock(side_effect=[object(), object()])
    monkeypatch.setattr(azure_postgres.asyncpg, "connect", connect)
    connector = azure_postgres.create_managed_identity_connector(
        "postgresql+asyncpg://app_identity:ignored-password@db.example/"
        "streamshield?sslmode=verify-full&application_name=streamshield",
        credential,
    )

    first = await connector()
    second = await connector()

    assert first is not second
    assert credential.scopes == [
        azure_postgres.AZURE_POSTGRES_SCOPE,
        azure_postgres.AZURE_POSTGRES_SCOPE,
    ]
    assert connect.await_args_list[0].kwargs == {
        "dsn": "postgresql://app_identity@db.example/streamshield?application_name=streamshield",
        "password": "access-token-1",
        "ssl": True,
    }
    assert connect.await_args_list[1].kwargs["password"] == "access-token-2"


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite+aiosqlite:///:memory:",
        "postgresql+asyncpg:///streamshield",
        "postgresql+asyncpg://identity@db.example/",
    ],
)
def test_managed_identity_connector_rejects_incomplete_or_non_postgres_urls(database_url):
    with pytest.raises(ValueError, match="Managed identity authentication"):
        azure_postgres.create_managed_identity_connector(
            database_url,
            FakeCredential(),
        )
