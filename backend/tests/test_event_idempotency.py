from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.schema import CreateIndex
from sqlalchemy.dialects import postgresql

from app.api.v1.schemas import EventIngest
from app.infrastructure.database.models import StreamEvent
from app.services.ingest.event_ingest import process_stream_event


@pytest.mark.asyncio
async def test_pipeline_replay_returns_stored_result_without_reprocessing():
    event_id = uuid4()
    stored = SimpleNamespace(
        id=event_id,
        risk_score=81.5,
        event_metadata={
            "processing_result": {
                "event_id": str(event_id),
                "risk_score": 81.5,
                "attack_created": True,
                "is_proxy": False,
                "is_vpn": True,
                "is_tor": False,
            }
        },
    )

    class Result:
        def scalar_one_or_none(self):
            return stored

    class Database:
        def get_bind(self):
            from types import SimpleNamespace

            return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

        async def execute(self, _query):
            return Result()

    result = await process_stream_event(
        Database(),
        SimpleNamespace(id=uuid4()),
        uuid4(),
        EventIngest(event_type="chat_message"),
        source="api",
        idempotency_key="message:123-0",
    )

    assert result == {**stored.event_metadata["processing_result"], "duplicate": True}


def test_idempotency_index_is_unique_and_partial_for_legacy_rows():
    index = next(
        item
        for item in StreamEvent.__table__.indexes
        if item.name == "uq_stream_events_stream_idempotency"
    )
    sql = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert index.unique
    assert [column.name for column in index.columns] == [
        "stream_id",
        "idempotency_key",
    ]
    assert "WHERE idempotency_key IS NOT NULL" in sql
