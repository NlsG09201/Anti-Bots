from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.database.models import Platform
from app.infrastructure.repositories.stream_repository import StreamRepository


class FakeSession:
    def __init__(self, dialect_name):
        self.dialect_name = dialect_name
        self.execute = AsyncMock()

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name=self.dialect_name))


@pytest.mark.asyncio
async def test_postgres_identity_lock_is_tenant_platform_and_external_id_scoped():
    session = FakeSession("postgresql")
    tenant_id = uuid4()

    await StreamRepository(session).lock_identity(
        tenant_id, Platform.TWITCH, "broadcaster-123"
    )

    statement, params = session.execute.await_args.args
    assert "pg_advisory_xact_lock(hashtextextended(:lock_key, 0))" in str(statement)
    assert params["lock_key"] == f"stream:{tenant_id}:twitch:broadcaster-123"


@pytest.mark.asyncio
async def test_non_postgres_identity_lock_is_a_noop():
    session = FakeSession("sqlite")

    await StreamRepository(session).lock_identity(
        uuid4(), Platform.KICK, "channel-slug"
    )

    session.execute.assert_not_awaited()
