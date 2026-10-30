from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

import app.infrastructure.database.init_db as init_db
from app.infrastructure.database.migrations import acquire_schema_startup_lock


@pytest.mark.asyncio
async def test_postgres_schema_startup_lock_uses_transaction_advisory_lock():
    statements = []

    class Connection:
        dialect = SimpleNamespace(name="postgresql")

        async def execute(self, statement):
            statements.append(str(statement))

    await acquire_schema_startup_lock(Connection())

    assert len(statements) == 1
    assert "pg_advisory_xact_lock" in statements[0]
    assert "streamshield_schema_startup" in statements[0]


@pytest.mark.asyncio
async def test_schema_creation_waits_for_startup_lock(monkeypatch):
    operations = []

    async def acquire_lock(_connection):
        operations.append("lock")

    class Connection:
        async def run_sync(self, _callback):
            operations.append("create_all")

    @asynccontextmanager
    async def begin():
        yield Connection()

    class Engine:
        def begin(self):
            return begin()

    monkeypatch.setattr(init_db, "acquire_schema_startup_lock", acquire_lock)

    await init_db.init_database(Engine(), max_attempts=1)

    assert operations == ["lock", "create_all"]


@pytest.mark.asyncio
async def test_non_postgres_schema_startup_lock_is_noop():
    statements = []

    class Connection:
        dialect = SimpleNamespace(name="sqlite")

        async def execute(self, statement):
            statements.append(statement)

    await acquire_schema_startup_lock(Connection())

    assert statements == []
