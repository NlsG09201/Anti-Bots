from uuid import uuid4

import pytest

import app.events.bus as bus_module
from app.events.schemas import PipelineEvent


def _event():
    return PipelineEvent.from_ingest(
        stream_id=uuid4(),
        tenant_id=uuid4(),
        event_type="chat_message",
        metadata={"content": "delivery retry"},
    )


@pytest.mark.asyncio
async def test_failed_arq_result_falls_back_inline_then_acks(monkeypatch):
    acknowledgements = []
    inline_calls = []

    class FakeStreams:
        async def dead_letter_rejected_result(self, **_kwargs):
            return False

        async def ack(self, stream_key, entry_id):
            acknowledgements.append((stream_key, entry_id))

    async def enqueue_failed_result(*_args, **_kwargs):
        return None

    async def process_inline(event, *, stream_entry_id):
        inline_calls.append((event, stream_entry_id))
        return {"processed": True}

    monkeypatch.setattr(bus_module.settings, "event_queue_enabled", True)
    monkeypatch.setattr(bus_module, "enqueue_event_job", enqueue_failed_result)
    monkeypatch.setattr(bus_module, "process_pipeline_event", process_inline)
    monkeypatch.setattr(
        bus_module,
        "get_event_bus",
        lambda: type("Bus", (), {"streams": FakeStreams()})(),
    )

    event = _event()
    await bus_module.handle_stream_message("ss:events:main", "123-0", event)

    assert inline_calls == [(event, "123-0")]
    assert acknowledgements == [("ss:events:main", "123-0")]


@pytest.mark.asyncio
async def test_inline_retry_failure_leaves_stream_entry_unacked(monkeypatch):
    acknowledgements = []

    class FakeStreams:
        async def dead_letter_rejected_result(self, **_kwargs):
            return False

        async def ack(self, stream_key, entry_id):
            acknowledgements.append((stream_key, entry_id))

    async def enqueue_failed_result(*_args, **_kwargs):
        return None

    async def process_inline(*_args, **_kwargs):
        raise RuntimeError("transient processing failure")

    monkeypatch.setattr(bus_module.settings, "event_queue_enabled", True)
    monkeypatch.setattr(bus_module, "enqueue_event_job", enqueue_failed_result)
    monkeypatch.setattr(bus_module, "process_pipeline_event", process_inline)
    monkeypatch.setattr(
        bus_module,
        "get_event_bus",
        lambda: type("Bus", (), {"streams": FakeStreams()})(),
    )

    await bus_module.handle_stream_message("ss:events:main", "123-0", _event())

    assert acknowledgements == []


@pytest.mark.asyncio
async def test_terminal_processor_rejection_is_dead_lettered_before_ack(monkeypatch):
    operations = []

    class FakeStreams:
        async def dead_letter_rejected_result(self, **kwargs):
            operations.append(("dead_letter", kwargs["result"]))
            operations.append(("ack", kwargs["stream_key"], kwargs["entry_id"]))
            return True

        async def ack(self, stream_key, entry_id):
            operations.append(("ack", stream_key, entry_id))

    async def enqueue_failed_result(*_args, **_kwargs):
        return None

    async def process_rejected(*_args, **_kwargs):
        return {"processed": False, "error": "tenant_mismatch"}

    monkeypatch.setattr(bus_module.settings, "event_queue_enabled", False)
    monkeypatch.setattr(bus_module, "process_pipeline_event", process_rejected)
    monkeypatch.setattr(
        bus_module,
        "get_event_bus",
        lambda: type("Bus", (), {"streams": FakeStreams()})(),
    )

    await bus_module.handle_stream_message("ss:events:main", "123-0", _event())

    assert operations == [
        ("dead_letter", {"processed": False, "error": "tenant_mismatch"}),
        ("ack", "ss:events:main", "123-0"),
    ]
