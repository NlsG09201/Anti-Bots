from uuid import uuid4

import pytest
from sqlalchemy import String, literal_column, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from app.infrastructure.database.models import Platform, Stream, Tenant, User, UserRole
from app.api.v1.widget import _stream_by_ingest_key


@pytest.mark.asyncio
async def test_widget_ingest_lookup_filters_by_json_key_in_database(db_session):
    tenant = Tenant(id=uuid4(), name="Widget lookup", slug=f"widget-lookup-{uuid4().hex[:8]}")
    owner = User(
        id=uuid4(), tenant_id=tenant.id, email=f"widget-{uuid4().hex[:8]}@test.local",
        username="widget-owner", hashed_password="unused", role=UserRole.STREAMER,
    )
    target = Stream(
        id=uuid4(), tenant_id=tenant.id, owner_id=owner.id, platform=Platform.TWITCH,
        external_id="target", channel_name="target", settings={"ingest_key": "target-widget-ingest-key"},
    )
    other = Stream(
        id=uuid4(), tenant_id=tenant.id, owner_id=owner.id, platform=Platform.KICK,
        external_id="other", channel_name="other", settings={"ingest_key": "other-widget-ingest-key"},
    )
    db_session.add_all([tenant, owner, target, other])
    await db_session.flush()

    found = await _stream_by_ingest_key(db_session, "target-widget-ingest-key")

    assert found is not None
    assert found.id == target.id


@pytest.mark.asyncio
async def test_widget_ingest_lookup_rejects_short_keys_without_query(db_session, monkeypatch):
    async def unexpected_query(*_args, **_kwargs):
        raise AssertionError("short widget keys must be rejected before database access")

    monkeypatch.setattr(db_session, "execute", unexpected_query)

    assert await _stream_by_ingest_key(db_session, "too-short") is None


def test_postgres_widget_lookup_expression_matches_partial_index():
    index = next(
        item for item in Stream.__table__.indexes
        if item.name == "ix_streams_widget_ingest_key"
    )
    index_sql = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    query = select(Stream).where(
        Stream.settings.op("->>", return_type=String())(literal_column("'ingest_key'")) == "key"
    )
    query_sql = str(query.compile(dialect=postgresql.dialect()))

    assert "(settings ->> 'ingest_key')" in index_sql
    assert "WHERE settings ? 'ingest_key'" in index_sql
    assert "settings ->> 'ingest_key'" in query_sql


def test_stream_tenant_identity_index_covers_tenant_scoped_lookup():
    index = next(
        item
        for item in Stream.__table__.indexes
        if item.name == "ix_streams_tenant_platform_external"
    )

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "platform",
        "external_id",
    ]
