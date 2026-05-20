"""Consumer asyncio: Redis Streams → procesamiento / cola arq."""

from __future__ import annotations

import asyncio
import uuid

from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.bus import get_event_bus, handle_stream_message
from app.infrastructure.cache.redis_client import redis_is_configured

logger = get_logger(__name__)
settings = get_settings()

_consumer_task: asyncio.Task | None = None
_consumer_name = f"api-{uuid.uuid4().hex[:8]}"


async def _consumer_loop() -> None:
    bus = get_event_bus()
    logger.info(
        "event_pipeline_consumer_started",
        consumer=_consumer_name,
        batch=settings.event_consumer_batch_size,
    )
    while True:
        try:
            batch = await bus.streams.read_batch(_consumer_name)
            if not batch:
                await asyncio.sleep(0.05)
                continue
            tasks = [
                handle_stream_message(stream_key, entry_id, event)
                for stream_key, entry_id, event in batch
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("event_consumer_loop_error", error=str(exc))
            await asyncio.sleep(1.0)


async def start_pipeline_consumer() -> asyncio.Task | None:
    global _consumer_task
    if not settings.event_pipeline_enabled or not redis_is_configured():
        logger.info("event_pipeline_consumer_skipped", reason="disabled_or_no_redis")
        return None
    if _consumer_task and not _consumer_task.done():
        return _consumer_task
    _consumer_task = asyncio.create_task(_consumer_loop())
    return _consumer_task


async def stop_pipeline_consumer() -> None:
    global _consumer_task
    if _consumer_task:
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass
        _consumer_task = None
