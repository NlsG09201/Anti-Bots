"""Prometheus gauges for queue and Redis Stream health."""

from __future__ import annotations

import asyncio

from prometheus_client import Gauge

from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.bus import get_event_bus
from app.events.queue import get_queue_stats
from app.events.streams import STREAM_DEAD_LETTER, STREAM_MAIN, STREAM_PRIORITY

logger = get_logger(__name__)

EVENT_QUEUE_DEPTH = Gauge(
    "streamshield_event_queue_depth",
    "Number of queued arq jobs waiting to be processed.",
    ["queue"],
)
EVENT_QUEUE_ENABLED = Gauge(
    "streamshield_event_queue_enabled",
    "Whether event queue processing is enabled by configuration.",
    ["queue"],
)
EVENT_QUEUE_AVAILABLE = Gauge(
    "streamshield_event_queue_available",
    "Whether queue depth was successfully collected (1) or unavailable/disabled (0).",
    ["queue"],
)
EVENT_STREAM_ENABLED = Gauge(
    "streamshield_event_stream_enabled",
    "Whether the Redis Stream pipeline is enabled by configuration.",
    ["stream"],
)
EVENT_STREAM_LENGTH = Gauge(
    "streamshield_event_stream_length",
    "Number of retained entries in a Redis Stream.",
    ["stream"],
)
EVENT_STREAM_PENDING = Gauge(
    "streamshield_event_stream_pending",
    "Number of unacknowledged entries in a Redis consumer group.",
    ["stream"],
)
EVENT_STREAM_CONSUMERS = Gauge(
    "streamshield_event_stream_consumers",
    "Number of active Redis Stream consumer group members.",
    ["stream"],
)
EVENT_STREAM_AVAILABLE = Gauge(
    "streamshield_event_stream_available",
    "Whether Redis Stream statistics were successfully collected.",
    ["stream"],
)
EVENT_DEAD_LETTER_LENGTH = Gauge(
    "streamshield_event_dead_letter_length",
    "Number of retained malformed events in the dead-letter stream.",
)
EVENT_DEAD_LETTER_AVAILABLE = Gauge(
    "streamshield_event_dead_letter_available",
    "Whether dead-letter stream depth was successfully collected.",
)


async def refresh_event_pipeline_metrics() -> None:
    """Refresh gauges from Redis; values are independent of API status polling."""
    queue_stats = await get_queue_stats()
    queue_payload = queue_stats.get("queues", {})
    queue_enabled = bool(get_settings().event_queue_enabled)
    queue_available = bool(
        queue_enabled
        and queue_stats.get("configured")
        and queue_stats.get("available", True)
        and queue_payload
    )
    if queue_available:
        for queue_name, data in queue_payload.items():
            EVENT_QUEUE_DEPTH.labels(queue=queue_name).set(data["queued_count"])
            EVENT_QUEUE_AVAILABLE.labels(queue=queue_name).set(1)

    # The event system currently has one arq queue; keep a stable label when
    # the queue is disabled or Redis stats cannot be queried.
    known_queue = next(iter(queue_payload), "ss:queue:events")
    EVENT_QUEUE_ENABLED.labels(queue=known_queue).set(int(queue_enabled))
    if not queue_available:
        EVENT_QUEUE_AVAILABLE.labels(queue=known_queue).set(0)

    stream_stats = await get_event_bus().streams.pending_count()
    stream_enabled = bool(get_settings().event_pipeline_enabled)
    for stream_name, stream_key in (
        ("main", STREAM_MAIN),
        ("priority", STREAM_PRIORITY),
    ):
        snapshot = stream_stats.get(stream_key, {})
        EVENT_STREAM_ENABLED.labels(stream=stream_name).set(int(stream_enabled))
        available = bool(
            stream_enabled
            and stream_stats.get("configured")
            and snapshot.get("available")
        )
        EVENT_STREAM_AVAILABLE.labels(stream=stream_name).set(int(available))
        if available:
            EVENT_STREAM_LENGTH.labels(stream=stream_name).set(snapshot.get("length", 0))
            pending = snapshot.get("pending")
            if pending is not None:
                EVENT_STREAM_PENDING.labels(stream=stream_name).set(pending)
            consumers = snapshot.get("consumers")
            if consumers is not None:
                EVENT_STREAM_CONSUMERS.labels(stream=stream_name).set(consumers)

    dead_letter = stream_stats.get("dead_letter", {})
    dead_letter_available = bool(
        stream_enabled
        and stream_stats.get("configured")
        and dead_letter.get("available")
    )
    EVENT_DEAD_LETTER_AVAILABLE.set(int(dead_letter_available))
    if dead_letter_available:
        EVENT_DEAD_LETTER_LENGTH.set(dead_letter.get("length", 0))


async def event_pipeline_metrics_loop(interval_seconds: int) -> None:
    """Collect queue metrics periodically for Prometheus scrapes."""
    interval = max(int(interval_seconds), 5)
    while True:
        try:
            await refresh_event_pipeline_metrics()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "event_pipeline_metrics_refresh_failed",
                error_type=type(exc).__name__,
            )
        await asyncio.sleep(interval)
