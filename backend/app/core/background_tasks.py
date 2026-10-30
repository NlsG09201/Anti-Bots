"""Lifecycle-owned asyncio tasks for application background work."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any


class BackgroundTaskRegistry:
    """Keep task references, report failures, and cancel unfinished work on close."""

    def __init__(self, logger: Any) -> None:
        self._logger = logger
        self._tasks: set[asyncio.Task[Any]] = set()

    def create(self, coroutine: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task[Any]:
        task = asyncio.create_task(coroutine, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._on_done)
        return task

    def _on_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self._logger.error(
                "background_task_failed",
                task=task.get_name(),
                error_type=type(error).__name__,
                error=str(error)[:200],
            )

    async def close(self) -> None:
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
