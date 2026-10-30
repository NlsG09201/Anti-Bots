from uuid import uuid4

import pytest

import app.workers.arq_worker as worker_module
from app.events.schemas import PipelineEvent


def _event():
    return PipelineEvent.from_ingest(
        stream_id=uuid4(),
        tenant_id=uuid4(),
        event_type="chat_message",
        metadata={"content": "retry exhaustion"},
    )


@pytest.mark.asyncio
async def test_pipeline_job_failure_dead_letters_and_acks_on_final_attempt(monkeypatch):
    operations = []
    event = _event()
    entry_id = "123-0"

    class FakeStreams:
        def _stream_for_category(self, category):
            assert category == event.category
            return "ss:events:main"

        async def dead_letter(self, **kwargs):
            operations.append(("dead_letter", kwargs))

        async def ack(self, stream_key, source_entry_id):
            operations.append(("ack", stream_key, source_entry_id))

    async def process_failing_event(*_args, **_kwargs):
        raise RuntimeError("processing failed")

    monkeypatch.setattr(worker_module, "EventStreamService", FakeStreams)
    monkeypatch.setattr(worker_module, "process_pipeline_event", process_failing_event)
    monkeypatch.setattr(worker_module.settings, "event_queue_max_tries", 5)

    with pytest.raises(RuntimeError, match="processing failed"):
        await worker_module.process_pipeline_event_job(
            {"job_try": 5}, event.model_dump(mode="json"), entry_id
        )

    assert operations[0][0] == "dead_letter"
    assert operations[0][1]["stream_key"] == "ss:events:main"
    assert operations[0][1]["entry_id"] == entry_id
    assert operations[0][1]["error_type"] == "RuntimeError"
    assert operations[0][1]["fields"] == event.to_stream_fields()
    assert operations[1] == ("ack", "ss:events:main", entry_id)


@pytest.mark.asyncio
async def test_pipeline_job_failure_before_final_attempt_does_not_ack(monkeypatch):
    operations = []
    event = _event()

    class FakeStreams:
        def _stream_for_category(self, _category):
            return "ss:events:main"

        async def dead_letter(self, **kwargs):
            operations.append(("dead_letter", kwargs))

        async def ack(self, *args):
            operations.append(("ack", *args))

    async def process_failing_event(*_args, **_kwargs):
        raise RuntimeError("transient processing failure")

    monkeypatch.setattr(worker_module, "EventStreamService", FakeStreams)
    monkeypatch.setattr(worker_module, "process_pipeline_event", process_failing_event)
    monkeypatch.setattr(worker_module.settings, "event_queue_max_tries", 5)

    with pytest.raises(RuntimeError, match="transient processing failure"):
        await worker_module.process_pipeline_event_job(
            {"job_try": 4}, event.model_dump(mode="json"), "123-0"
        )

    assert operations == []


@pytest.mark.asyncio
async def test_terminal_processor_rejection_is_dead_lettered_and_acked(monkeypatch):
    operations = []
    event = _event()

    class FakeStreams:
        def _stream_for_category(self, _category):
            return "ss:events:main"

        async def dead_letter_rejected_result(self, **kwargs):
            operations.append(("dead_letter", kwargs["result"]))
            operations.append(("ack", kwargs["stream_key"], kwargs["entry_id"]))
            return True

    async def process_rejected_event(*_args, **_kwargs):
        return {"processed": False, "error": "tenant_mismatch"}

    monkeypatch.setattr(worker_module, "EventStreamService", FakeStreams)
    monkeypatch.setattr(worker_module, "process_pipeline_event", process_rejected_event)

    result = await worker_module.process_pipeline_event_job(
        {"job_try": 1}, event.model_dump(mode="json"), "123-0"
    )

    assert result == {
        "processed": False,
        "error": "tenant_mismatch",
        "dead_lettered": True,
    }
    assert operations == [
        ("dead_letter", {"processed": False, "error": "tenant_mismatch"}),
        ("ack", "ss:events:main", "123-0"),
    ]
