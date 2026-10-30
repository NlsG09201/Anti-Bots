from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.events.bus as bus_module
import app.services.ingest.event_ingest as ingest_module
from app.api.v1.schemas import EventIngest
from app.events.bus import EventBus


def _inputs():
    stream = SimpleNamespace(id=uuid4())
    tenant_id = uuid4()
    event = EventIngest(event_type="chat_message", metadata={"content": "hello"})
    return SimpleNamespace(), stream, tenant_id, event


@pytest.mark.asyncio
async def test_publish_from_ingest_carries_internal_idempotency_key(monkeypatch):
    captured = []
    key = "a" * 32

    async def publish(_self, pipeline_event):
        captured.append(pipeline_event)
        return {"accepted": True, "stream_entry_id": "123-0"}

    monkeypatch.setattr(EventBus, "publish", publish)
    _, stream, tenant_id, event = _inputs()

    await EventBus().publish_from_ingest(
        stream_id=stream.id,
        tenant_id=tenant_id,
        event=event,
        idempotency_key=key,
    )

    assert captured[0].metadata["_pipeline_event_id"] == key
    assert event.metadata == {"content": "hello"}


@pytest.mark.asyncio
async def test_sync_fallback_does_not_dual_process_after_successful_publish(monkeypatch):
    db, stream, tenant_id, event = _inputs()
    inline_calls = []
    publish_calls = []

    class FakeBus:
        async def publish_from_ingest(self, **kwargs):
            publish_calls.append(kwargs)
            return {"accepted": True, "stream_entry_id": "123-0"}

    async def process_inline(*args, **kwargs):
        inline_calls.append((args, kwargs))
        return {"event_id": "duplicate"}

    monkeypatch.setattr(bus_module.settings, "event_pipeline_enabled", True)
    monkeypatch.setattr(bus_module.settings, "event_pipeline_sync_fallback", True)
    monkeypatch.setattr(bus_module, "redis_is_configured", lambda: True)
    monkeypatch.setattr(bus_module, "get_event_bus", lambda: FakeBus())
    monkeypatch.setattr(ingest_module, "process_stream_event", process_inline)

    result = await bus_module.ingest_event(db, stream, tenant_id, event)

    assert result["queued"] is True
    assert result["stream_entry_id"] == "123-0"
    assert len(publish_calls[0]["idempotency_key"]) == 32
    assert inline_calls == []


@pytest.mark.asyncio
async def test_sync_fallback_processes_inline_only_when_publish_fails(monkeypatch):
    db, stream, tenant_id, event = _inputs()
    publish_calls = []
    inline_calls = []

    class FakeBus:
        async def publish_from_ingest(self, **kwargs):
            publish_calls.append(kwargs)
            raise ConnectionError("redis unavailable")

    async def process_inline(*args, **kwargs):
        inline_calls.append((args, kwargs))
        return {"event_id": "processed-once", "risk_score": 3.0}

    monkeypatch.setattr(bus_module.settings, "event_pipeline_enabled", True)
    monkeypatch.setattr(bus_module.settings, "event_pipeline_sync_fallback", True)
    monkeypatch.setattr(bus_module, "redis_is_configured", lambda: True)
    monkeypatch.setattr(bus_module, "get_event_bus", lambda: FakeBus())
    monkeypatch.setattr(ingest_module, "process_stream_event", process_inline)

    result = await bus_module.ingest_event(db, stream, tenant_id, event)

    assert result == {
        "event_id": "processed-once",
        "risk_score": 3.0,
        "queued": False,
        "sync_fallback": True,
    }
    assert len(publish_calls) == 1
    assert len(inline_calls) == 1
    assert inline_calls[0][1]["idempotency_key"] == publish_calls[0]["idempotency_key"]


@pytest.mark.asyncio
async def test_publish_failure_propagates_when_sync_fallback_disabled(monkeypatch):
    db, stream, tenant_id, event = _inputs()
    inline_calls = []

    class FakeBus:
        async def publish_from_ingest(self, **_kwargs):
            raise ConnectionError("redis unavailable")

    async def process_inline(*args, **kwargs):
        inline_calls.append((args, kwargs))
        return {}

    monkeypatch.setattr(bus_module.settings, "event_pipeline_enabled", True)
    monkeypatch.setattr(bus_module.settings, "event_pipeline_sync_fallback", False)
    monkeypatch.setattr(bus_module, "redis_is_configured", lambda: True)
    monkeypatch.setattr(bus_module, "get_event_bus", lambda: FakeBus())
    monkeypatch.setattr(ingest_module, "process_stream_event", process_inline)

    with pytest.raises(ConnectionError, match="redis unavailable"):
        await bus_module.ingest_event(db, stream, tenant_id, event)

    assert inline_calls == []
