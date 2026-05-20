"""Bus de eventos: publicación unificada (Stream + cola + métricas)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from prometheus_client import Counter, Histogram

from app.api.v1.schemas import EventIngest
from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.processor import process_pipeline_event
from app.events.queue import enqueue_event_job
from app.events.schemas import PipelineEvent
from app.events.streams import EventStreamService
from app.infrastructure.cache.redis_client import redis_is_configured

logger = get_logger(__name__)
settings = get_settings()

EVENTS_PUBLISHED = Counter(
    "streamshield_events_published_total",
    "Events published to the pipeline",
    ["category", "source"],
)
EVENTS_PROCESSED = Counter(
    "streamshield_events_processed_total",
    "Events processed by the pipeline",
    ["category", "status"],
)
EVENT_PROCESS_LATENCY = Histogram(
    "streamshield_event_process_seconds",
    "Event processing latency",
    ["category"],
)

_bus_instance: Optional["EventBus"] = None


class EventBus:
    def __init__(self) -> None:
        self.streams = EventStreamService()

    async def publish(self, event: PipelineEvent) -> Dict[str, Any]:
        EVENTS_PUBLISHED.labels(
            category=event.category.value,
            source=event.source,
        ).inc()

        entry_id: Optional[str] = None

        if redis_is_configured():
            entry_id = await self.streams.publish(event)

        return {
            "accepted": True,
            "stream_entry_id": entry_id,
            "category": event.category.value,
            "async": settings.event_pipeline_enabled and redis_is_configured(),
        }

    async def publish_from_ingest(
        self,
        *,
        stream_id: UUID,
        tenant_id: UUID,
        event: EventIngest,
        source: str = "api",
    ) -> Dict[str, Any]:
        pipeline_event = PipelineEvent.from_ingest(
            stream_id=stream_id,
            tenant_id=tenant_id,
            event_type=event.event_type,
            platform_user_id=event.platform_user_id,
            platform_username=event.platform_username,
            ip_address=event.ip_address,
            fingerprint_hash=event.fingerprint_hash,
            metadata=event.metadata,
            source=source,
        )
        return await self.publish(pipeline_event)

    async def publish_batch(self, events: List[PipelineEvent]) -> List[Dict[str, Any]]:
        if not events:
            return []
        if redis_is_configured():
            ids = await self.streams.publish_batch(events)
            return [
                {"accepted": True, "stream_entry_id": eid, "category": ev.category.value}
                for ev, eid in zip(events, ids)
            ]
        return [{"accepted": False} for _ in events]


def get_event_bus() -> EventBus:
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = EventBus()
    return _bus_instance


async def ingest_event(
    db,
    stream,
    tenant_id: UUID,
    event: EventIngest,
    *,
    source: str = "api",
) -> Dict[str, Any]:
    """
    Punto de entrada unificado: pipeline async o procesamiento síncrono legacy.
    """
    if settings.event_pipeline_enabled and redis_is_configured():
        bus = get_event_bus()
        meta = await bus.publish_from_ingest(
            stream_id=stream.id,
            tenant_id=tenant_id,
            event=event,
            source=source,
        )
        if settings.event_pipeline_sync_fallback:
            from app.services.ingest.event_ingest import process_stream_event

            result = await process_stream_event(db, stream, tenant_id, event, source=source)
            return {**result, **meta, "dual_write": True}
        return {
            "event_id": None,
            "risk_score": 0.0,
            "attack_created": False,
            "queued": True,
            **meta,
        }

    from app.services.ingest.event_ingest import process_stream_event

    return await process_stream_event(db, stream, tenant_id, event, source=source)


async def handle_stream_message(
    stream_key: str,
    entry_id: str,
    event: PipelineEvent,
) -> None:
    """Procesamiento inline desde el consumer (cuando arq no está activo)."""
    import time

    start = time.perf_counter()
    try:
        if settings.event_queue_enabled:
            job_id = await enqueue_event_job(event, stream_entry_id=entry_id)
            if job_id:
                bus = get_event_bus()
                await bus.streams.ack(stream_key, entry_id)
                EVENTS_PROCESSED.labels(category=event.category.value, status="queued").inc()
                return

        await process_pipeline_event(event, stream_entry_id=entry_id)
        bus = get_event_bus()
        await bus.streams.ack(stream_key, entry_id)
        EVENTS_PROCESSED.labels(category=event.category.value, status="ok").inc()
    except Exception as exc:
        EVENTS_PROCESSED.labels(category=event.category.value, status="error").inc()
        logger.exception("pipeline_handle_failed", error=str(exc), entry_id=entry_id)
    finally:
        EVENT_PROCESS_LATENCY.labels(category=event.category.value).observe(
            time.perf_counter() - start
        )
