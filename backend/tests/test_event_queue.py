from types import SimpleNamespace
from uuid import uuid4

import pytest

import arq
import arq.connections
import arq.jobs

from app.events.queue import UNIFIED_QUEUE, enqueue_event_job, get_queue_stats
from app.events.schemas import PipelineEvent
import app.events.queue as queue_module


class FakeRedisSettings:
    @classmethod
    def from_dsn(cls, _dsn):
        return cls()


class FakePool:
    def __init__(
        self,
        result=None,
        error=None,
        close_error=None,
        queue_count=0,
        result_info=None,
        job_status="queued",
    ):
        self.result = result
        self.error = error
        self.close_error = close_error
        self.queue_count = queue_count
        self.result_info = result_info
        self.job_status = job_status
        self.closed = False

    async def enqueue_job(self, *_args, **_kwargs):
        if self.error:
            raise self.error
        return self.result

    async def close(self):
        self.closed = True
        if self.close_error:
            raise self.close_error

    async def zcard(self, _queue_name):
        if self.error:
            raise self.error
        return self.queue_count


class FakeArqJob:
    def __init__(self, _job_id, pool, _queue_name):
        self.pool = pool

    async def result_info(self):
        return self.pool.result_info

    async def status(self):
        return self.pool.job_status


def _event():
    return PipelineEvent.from_ingest(
        stream_id=uuid4(),
        tenant_id=uuid4(),
        event_type="chat_message",
        metadata={"content": "hello"},
    )


@pytest.mark.asyncio
async def test_active_arq_duplicate_is_reported_as_accepted(monkeypatch):
    event = _event()
    pool = FakePool(result=None)  # arq signals an existing job with None

    async def create_pool(_settings):
        return pool

    monkeypatch.setattr(arq, "create_pool", create_pool)
    monkeypatch.setattr(arq.connections, "RedisSettings", FakeRedisSettings)
    monkeypatch.setattr(arq.jobs, "Job", FakeArqJob)
    monkeypatch.setattr(queue_module, "redis_is_configured", lambda: True)
    monkeypatch.setattr(queue_module.settings, "event_queue_enabled", True)

    result = await enqueue_event_job(event, stream_entry_id="123-0")

    assert result == f"{event.category.value}:{event.stream_id}:{event.enqueued_at}"
    assert pool.closed


@pytest.mark.asyncio
async def test_successful_arq_result_is_reported_as_accepted_duplicate(monkeypatch):
    event = _event()
    pool = FakePool(result=None, result_info=SimpleNamespace(success=True))

    async def create_pool(_settings):
        return pool

    monkeypatch.setattr(arq, "create_pool", create_pool)
    monkeypatch.setattr(arq.connections, "RedisSettings", FakeRedisSettings)
    monkeypatch.setattr(arq.jobs, "Job", FakeArqJob)
    monkeypatch.setattr(queue_module, "redis_is_configured", lambda: True)
    monkeypatch.setattr(queue_module.settings, "event_queue_enabled", True)

    result = await enqueue_event_job(event, stream_entry_id="123-0")

    assert result == f"{event.category.value}:{event.stream_id}:{event.enqueued_at}"
    assert pool.closed


@pytest.mark.asyncio
async def test_failed_arq_result_is_not_treated_as_accepted(monkeypatch):
    pool = FakePool(
        result=None,
        result_info=SimpleNamespace(success=False, result=RuntimeError()),
    )

    async def create_pool(_settings):
        return pool

    monkeypatch.setattr(arq, "create_pool", create_pool)
    monkeypatch.setattr(arq.connections, "RedisSettings", FakeRedisSettings)
    monkeypatch.setattr(arq.jobs, "Job", FakeArqJob)
    monkeypatch.setattr(queue_module, "redis_is_configured", lambda: True)
    monkeypatch.setattr(queue_module.settings, "event_queue_enabled", True)

    assert await enqueue_event_job(_event(), stream_entry_id="123-0") is None
    assert pool.closed


@pytest.mark.asyncio
async def test_missing_arq_duplicate_is_not_treated_as_accepted(monkeypatch):
    pool = FakePool(result=None, job_status="not_found")

    async def create_pool(_settings):
        return pool

    monkeypatch.setattr(arq, "create_pool", create_pool)
    monkeypatch.setattr(arq.connections, "RedisSettings", FakeRedisSettings)
    monkeypatch.setattr(arq.jobs, "Job", FakeArqJob)
    monkeypatch.setattr(queue_module, "redis_is_configured", lambda: True)
    monkeypatch.setattr(queue_module.settings, "event_queue_enabled", True)

    assert await enqueue_event_job(_event(), stream_entry_id="123-0") is None
    assert pool.closed


@pytest.mark.asyncio
async def test_pool_close_error_does_not_turn_accepted_job_into_inline_fallback(monkeypatch):
    event = _event()
    pool = FakePool(
        result=SimpleNamespace(job_id="accepted-job"),
        close_error=RuntimeError("close failed"),
    )

    async def create_pool(_settings):
        return pool

    monkeypatch.setattr(arq, "create_pool", create_pool)
    monkeypatch.setattr(arq.connections, "RedisSettings", FakeRedisSettings)
    monkeypatch.setattr(queue_module, "redis_is_configured", lambda: True)
    monkeypatch.setattr(queue_module.settings, "event_queue_enabled", True)

    result = await enqueue_event_job(event)

    assert result == "accepted-job"
    assert pool.closed


@pytest.mark.asyncio
async def test_arq_pool_closes_after_enqueue_failure(monkeypatch):
    pool = FakePool(error=RuntimeError("redis unavailable"))

    async def create_pool(_settings):
        return pool

    monkeypatch.setattr(arq, "create_pool", create_pool)
    monkeypatch.setattr(arq.connections, "RedisSettings", FakeRedisSettings)
    monkeypatch.setattr(queue_module, "redis_is_configured", lambda: True)
    monkeypatch.setattr(queue_module.settings, "event_queue_enabled", True)

    assert await enqueue_event_job(_event()) is None
    assert pool.closed


@pytest.mark.asyncio
async def test_queue_stats_reports_real_depth_and_shared_categories(monkeypatch):
    pool = FakePool(queue_count=6)

    async def create_pool(_settings):
        return pool

    monkeypatch.setattr(arq, "create_pool", create_pool)
    monkeypatch.setattr(arq.connections, "RedisSettings", FakeRedisSettings)
    monkeypatch.setattr(queue_module, "redis_is_configured", lambda: True)
    monkeypatch.setattr(queue_module.settings, "event_queue_enabled", True)

    stats = await get_queue_stats()

    queue_stats = stats["queues"][UNIFIED_QUEUE]
    assert stats["enabled"] is True
    assert queue_stats["queued_count"] == 6
    assert set(queue_stats["categories"]) == {
        category.value for category in queue_module.QUEUE_BY_CATEGORY
    }
    assert pool.closed


@pytest.mark.asyncio
async def test_queue_stats_disabled_does_not_open_redis_pool(monkeypatch):
    async def should_not_create_pool(_settings):
        raise AssertionError("disabled queue must not connect")

    monkeypatch.setattr(arq, "create_pool", should_not_create_pool)
    monkeypatch.setattr(queue_module, "redis_is_configured", lambda: True)
    monkeypatch.setattr(queue_module.settings, "event_queue_enabled", False)

    stats = await get_queue_stats()

    assert stats == {"enabled": False, "configured": True, "queues": {}}


@pytest.mark.asyncio
async def test_queue_stats_does_not_expose_redis_error_detail(monkeypatch):
    pool = FakePool(error=RuntimeError("connection failed with sensitive detail"))

    async def create_pool(_settings):
        return pool

    monkeypatch.setattr(arq, "create_pool", create_pool)
    monkeypatch.setattr(arq.connections, "RedisSettings", FakeRedisSettings)
    monkeypatch.setattr(queue_module, "redis_is_configured", lambda: True)
    monkeypatch.setattr(queue_module.settings, "event_queue_enabled", True)

    stats = await get_queue_stats()

    assert stats["available"] is False
    assert stats["error_type"] == "RuntimeError"
    assert "sensitive detail" not in str(stats)
    assert pool.closed
