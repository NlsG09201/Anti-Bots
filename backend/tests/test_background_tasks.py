import asyncio

import pytest

from app.core.background_tasks import BackgroundTaskRegistry


class RecordingLogger:
    def __init__(self):
        self.errors = []

    def error(self, event, **fields):
        self.errors.append((event, fields))


@pytest.mark.asyncio
async def test_registry_logs_background_task_failures():
    logger = RecordingLogger()
    registry = BackgroundTaskRegistry(logger)

    async def fail():
        raise RuntimeError("worker broke")

    task = registry.create(fail(), name="failing-worker")
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)  # allow the registered completion callback to run

    assert logger.errors == [
        (
            "background_task_failed",
            {
                "task": "failing-worker",
                "error_type": "RuntimeError",
                "error": "worker broke",
            },
        )
    ]


@pytest.mark.asyncio
async def test_registry_cancels_unfinished_tasks_on_close():
    logger = RecordingLogger()
    registry = BackgroundTaskRegistry(logger)
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def wait_until_cancelled():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    registry.create(wait_until_cancelled(), name="long-running-worker")
    await started.wait()
    await registry.close()

    assert stopped.is_set()
    assert not logger.errors
