from types import SimpleNamespace

import pytest

import app.events.metrics as metrics
from app.events.streams import STREAM_MAIN, STREAM_PRIORITY


@pytest.mark.asyncio
async def test_refresh_event_pipeline_metrics_exports_depth_and_backlog(monkeypatch):
    queue_name = "ss:queue:events"
    queue_snapshot = {
        "enabled": True,
        "configured": True,
        "available": True,
        "queues": {queue_name: {"queued_count": 11}},
    }
    stream_snapshot = {
        "configured": True,
        STREAM_MAIN: {"available": True, "length": 120, "pending": 8, "consumers": 2},
        STREAM_PRIORITY: {"available": True, "length": 9, "pending": 1, "consumers": 1},
        "dead_letter": {"available": True, "length": 3},
    }

    class FakeStreams:
        async def pending_count(self):
            return stream_snapshot

    monkeypatch.setattr(metrics, "get_queue_stats", lambda: _resolved(queue_snapshot))
    monkeypatch.setattr(metrics, "get_event_bus", lambda: SimpleNamespace(streams=FakeStreams()))
    monkeypatch.setattr(
        metrics,
        "get_settings",
        lambda: SimpleNamespace(event_queue_enabled=True, event_pipeline_enabled=True),
    )

    await metrics.refresh_event_pipeline_metrics()

    assert metrics.EVENT_QUEUE_DEPTH.labels(queue=queue_name)._value.get() == 11
    assert metrics.EVENT_QUEUE_ENABLED.labels(queue=queue_name)._value.get() == 1
    assert metrics.EVENT_QUEUE_AVAILABLE.labels(queue=queue_name)._value.get() == 1
    assert metrics.EVENT_STREAM_LENGTH.labels(stream="main")._value.get() == 120
    assert metrics.EVENT_STREAM_PENDING.labels(stream="main")._value.get() == 8
    assert metrics.EVENT_STREAM_CONSUMERS.labels(stream="priority")._value.get() == 1
    assert metrics.EVENT_STREAM_AVAILABLE.labels(stream="priority")._value.get() == 1
    assert metrics.EVENT_DEAD_LETTER_LENGTH._value.get() == 3
    assert metrics.EVENT_DEAD_LETTER_AVAILABLE._value.get() == 1


@pytest.mark.asyncio
async def test_refresh_event_pipeline_metrics_marks_unavailable_sources(monkeypatch):
    async def disabled_queue_stats():
        return {"enabled": False, "configured": False, "queues": {}}

    class FakeStreams:
        async def pending_count(self):
            return {"configured": False}

    monkeypatch.setattr(metrics, "get_queue_stats", disabled_queue_stats)
    monkeypatch.setattr(metrics, "get_event_bus", lambda: SimpleNamespace(streams=FakeStreams()))
    monkeypatch.setattr(
        metrics,
        "get_settings",
        lambda: SimpleNamespace(event_queue_enabled=False, event_pipeline_enabled=False),
    )

    await metrics.refresh_event_pipeline_metrics()

    assert (
        metrics.EVENT_QUEUE_AVAILABLE.labels(queue="ss:queue:events")._value.get()
        == 0
    )
    assert metrics.EVENT_QUEUE_ENABLED.labels(queue="ss:queue:events")._value.get() == 0
    assert metrics.EVENT_STREAM_ENABLED.labels(stream="main")._value.get() == 0
    assert metrics.EVENT_STREAM_AVAILABLE.labels(stream="main")._value.get() == 0
    assert metrics.EVENT_STREAM_AVAILABLE.labels(stream="priority")._value.get() == 0
    assert metrics.EVENT_DEAD_LETTER_AVAILABLE._value.get() == 0


async def _resolved(value):
    return value
