"""Tests del pipeline de eventos (sin Redis real)."""

from uuid import uuid4

from app.events.schemas import EventCategory, PipelineEvent, resolve_category
from app.events.schemas import EVENT_TYPE_TO_CATEGORY
from app.events.streams import EventStreamService, STREAM_DEAD_LETTER, STREAM_PRIORITY
import app.events.streams as streams_module
import pytest


def test_event_categories_mapping():
    assert EVENT_TYPE_TO_CATEGORY["viewer_join"] == EventCategory.VIEWER
    assert EVENT_TYPE_TO_CATEGORY["follow"] == EventCategory.FOLLOW
    assert EVENT_TYPE_TO_CATEGORY["chat_message"] == EventCategory.MESSAGE
    assert EVENT_TYPE_TO_CATEGORY["widget_connect"] == EventCategory.CONNECTION


def test_resolve_suspicious_by_pre_risk():
    cat = resolve_category("viewer_join", {"pre_risk_score": 85})
    assert cat == EventCategory.SUSPICIOUS


def test_pipeline_event_roundtrip_fields():
    sid, tid = uuid4(), uuid4()
    event = PipelineEvent.from_ingest(
        stream_id=sid,
        tenant_id=tid,
        event_type="chat_message",
        platform_username="tester",
        metadata={"msg": "hello"},
        source="api",
    )
    fields = event.to_stream_fields()
    restored = PipelineEvent.from_stream_fields(fields)
    assert restored.event_type == "chat_message"
    assert restored.category == EventCategory.MESSAGE
    assert restored.platform_username == "tester"
    assert restored.metadata["msg"] == "hello"


def test_normalize_event_type_mapping():
    from app.events.processor import _normalize_event_type

    assert _normalize_event_type("channel.follow") == "follow"
    assert _normalize_event_type("channel.chat.message") == "chat_message"


@pytest.mark.asyncio
async def test_malformed_stream_entry_is_dead_lettered_before_ack(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.dead_letters = []
            self.acks = []

        async def xgroup_create(self, *args, **kwargs):
            return None

        async def xreadgroup(self, *, streams, **kwargs):
            stream_key = next(iter(streams))
            if stream_key == STREAM_PRIORITY:
                return [(stream_key, [("123-0", {"category": "invalid"})])]
            return []

        async def xadd(self, stream_key, fields, **kwargs):
            self.dead_letters.append((stream_key, fields))

        async def xack(self, stream_key, group, entry_id):
            self.acks.append((stream_key, group, entry_id))

    fake = FakeRedis()
    monkeypatch.setattr(streams_module, "redis_is_configured", lambda: True)

    async def get_fake_redis():
        return fake

    monkeypatch.setattr(streams_module, "get_redis", get_fake_redis)

    events = await EventStreamService().read_batch("test-consumer")

    assert events == []
    assert fake.dead_letters[0][0] == STREAM_DEAD_LETTER
    assert fake.dead_letters[0][1]["source_stream"] == STREAM_PRIORITY
    assert fake.dead_letters[0][1]["source_entry_id"] == "123-0"
    assert fake.dead_letters[0][1]["error_type"] == "ValueError"
    assert fake.acks == [(STREAM_PRIORITY, "ss-processors", "123-0")]
