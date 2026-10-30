"""Tests del pipeline de eventos (sin Redis real)."""

from uuid import uuid4

from app.events.schemas import EventCategory, PipelineEvent, resolve_category
from app.events.schemas import EVENT_TYPE_TO_CATEGORY
from app.events.streams import (
    CONSUMER_GROUP,
    EventStreamService,
    STREAM_DEAD_LETTER,
    STREAM_MAIN,
    STREAM_PRIORITY,
)
import app.events.streams as streams_module
import app.events.processor as processor_module
import pytest
from types import SimpleNamespace


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
async def test_pipeline_rejects_event_for_stream_owned_by_another_tenant(monkeypatch):
    stream_id = uuid4()
    owner_tenant_id = uuid4()
    event = PipelineEvent.from_ingest(
        stream_id=stream_id,
        tenant_id=uuid4(),
        event_type="chat_message",
        metadata={"content": "must not be processed"},
    )
    stream = SimpleNamespace(id=stream_id, tenant_id=owner_tenant_id)
    processed = False

    class FakeResult:
        def scalar_one_or_none(self):
            return stream

    class FakeDatabase:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def execute(self, _query):
            return FakeResult()

    monkeypatch.setattr(processor_module, "AsyncSessionLocal", FakeDatabase)

    async def should_not_process(*_args, **_kwargs):
        nonlocal processed
        processed = True

    monkeypatch.setattr(processor_module, "process_stream_event", should_not_process)

    result = await processor_module.process_pipeline_event(event)

    assert result == {"processed": False, "error": "tenant_mismatch"}
    assert not processed


@pytest.mark.asyncio
async def test_malformed_stream_entry_is_dead_lettered_before_ack(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.dead_letters = []
            self.acks = []

        async def xgroup_create(self, *args, **kwargs):
            return None

        async def xautoclaim(self, *args, **kwargs):
            return ("0-0", [], [])

        async def xreadgroup(self, *, streams, **kwargs):
            stream_key = next(iter(streams))
            if stream_key == STREAM_PRIORITY:
                return [
                    (
                        stream_key,
                        [
                            (
                                "123-0",
                                {
                                    "stream_id": "stream",
                                    "tenant_id": "tenant",
                                    "event_type": "suspicious",
                                    "category": "invalid",
                                },
                            )
                        ],
                    )
                ]
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


@pytest.mark.asyncio
async def test_terminal_rejection_is_persisted_to_dead_letter_before_ack(monkeypatch):
    operations = []
    service = EventStreamService()
    event = PipelineEvent.from_ingest(
        stream_id=uuid4(), tenant_id=uuid4(), event_type="viewer_join"
    )

    async def dead_letter(**kwargs):
        operations.append(("dead_letter", kwargs))

    async def ack(stream_key, entry_id):
        operations.append(("ack", stream_key, entry_id))

    monkeypatch.setattr(service, "dead_letter", dead_letter)
    monkeypatch.setattr(service, "ack", ack)

    handled = await service.dead_letter_rejected_result(
        stream_key=STREAM_MAIN,
        entry_id="123-0",
        event=event,
        result={"processed": False, "error": "tenant_mismatch"},
    )

    assert handled is True
    assert operations[0][0] == "dead_letter"
    assert operations[0][1]["error_type"] == "pipeline_tenant_mismatch"
    assert operations[0][1]["fields"] == event.to_stream_fields()
    assert operations[1] == ("ack", STREAM_MAIN, "123-0")


@pytest.mark.asyncio
async def test_successful_processor_result_is_not_dead_lettered(monkeypatch):
    service = EventStreamService()

    async def unexpected_call(**_kwargs):
        raise AssertionError("successful pipeline results must remain on the success path")

    monkeypatch.setattr(service, "dead_letter", unexpected_call)
    handled = await service.dead_letter_rejected_result(
        stream_key=STREAM_MAIN,
        entry_id="123-0",
        event=PipelineEvent.from_ingest(
            stream_id=uuid4(), tenant_id=uuid4(), event_type="viewer_join"
        ),
        result={"processed": True},
    )

    assert handled is False


@pytest.mark.asyncio
async def test_stale_pending_stream_entry_is_reclaimed(monkeypatch):
    event = PipelineEvent.from_ingest(
        stream_id=uuid4(),
        tenant_id=uuid4(),
        event_type="chat_message",
        metadata={"content": "hello"},
    )

    class FakeRedis:
        def __init__(self):
            self.claim_calls = []

        async def xgroup_create(self, *args, **kwargs):
            return None

        async def xautoclaim(self, *args, **kwargs):
            self.claim_calls.append((args, kwargs))
            stream_key = args[0]
            if stream_key == STREAM_PRIORITY:
                return ("0-0", [("456-0", event.to_stream_fields())], [])
            return ("0-0", [], [])

        async def xreadgroup(self, **kwargs):
            return []

    fake = FakeRedis()
    monkeypatch.setattr(streams_module, "redis_is_configured", lambda: True)

    async def get_fake_redis():
        return fake

    monkeypatch.setattr(streams_module, "get_redis", get_fake_redis)
    service = EventStreamService()

    events = await service.read_batch("replacement-consumer")

    assert len(events) == 1
    assert events[0][0:2] == (STREAM_PRIORITY, "456-0")
    assert events[0][2].metadata == {"content": "hello"}
    assert fake.claim_calls[0][1]["min_idle_time"] >= (
        streams_module.settings.event_queue_job_timeout_seconds * 1000 + 30_000
    )


@pytest.mark.asyncio
async def test_pending_count_reports_backlog_per_stream(monkeypatch):
    class FakeRedis:
        async def xinfo_stream(self, stream_key):
            return {"length": 30 if stream_key == STREAM_MAIN else 5, "groups": 1}

        async def xinfo_groups(self, stream_key):
            pending = 7 if stream_key == STREAM_MAIN else 2
            return [
                {"name": CONSUMER_GROUP, "pending": pending, "consumers": 3}
            ]

        async def xlen(self, stream_key):
            assert stream_key == STREAM_DEAD_LETTER
            return 4

    monkeypatch.setattr(streams_module, "redis_is_configured", lambda: True)

    async def get_fake_redis():
        return FakeRedis()

    monkeypatch.setattr(streams_module, "get_redis", get_fake_redis)
    stats = await EventStreamService().pending_count()

    assert stats[STREAM_MAIN] == {
        "available": True,
        "length": 30,
        "groups": 1,
        "pending": 7,
        "consumers": 3,
    }
    assert stats[STREAM_PRIORITY]["pending"] == 2
    assert stats["dead_letter"] == {
        "available": True,
        "length": 4,
        "max_len": streams_module.settings.event_stream_max_len,
    }


@pytest.mark.asyncio
async def test_pending_count_does_not_report_failed_query_as_zero(monkeypatch):
    class FakeRedis:
        async def xinfo_stream(self, stream_key):
            return {"length": 12, "groups": 1}

        async def xinfo_groups(self, stream_key):
            raise RuntimeError("temporarily unavailable")

        async def xlen(self, stream_key):
            raise ConnectionError("temporarily unavailable")

    monkeypatch.setattr(streams_module, "redis_is_configured", lambda: True)

    async def get_fake_redis():
        return FakeRedis()

    monkeypatch.setattr(streams_module, "get_redis", get_fake_redis)
    stats = await EventStreamService().pending_count()

    assert stats[STREAM_MAIN]["length"] == 12
    assert stats[STREAM_MAIN]["pending"] is None
    assert stats[STREAM_MAIN]["pending_error_type"] == "RuntimeError"
    assert stats["dead_letter"] == {
        "available": False,
        "error_type": "ConnectionError",
        "max_len": streams_module.settings.event_stream_max_len,
    }
