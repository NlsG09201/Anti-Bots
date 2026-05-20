"""Procesador de eventos del pipeline (delega en event_ingest)."""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select

from app.api.v1.schemas import EventIngest
from app.core.logging import get_logger
from app.events.schemas import EventCategory, PipelineEvent
from app.events.realtime import publish_event_processed, publish_suspicious_signal
from app.infrastructure.database.models import Stream
from app.infrastructure.database.session import AsyncSessionLocal
from app.services.ingest.event_ingest import process_stream_event

logger = get_logger(__name__)


async def process_pipeline_event(
    event: PipelineEvent,
    *,
    stream_entry_id: Optional[str] = None,
) -> Dict[str, Any]:
    async with AsyncSessionLocal() as db:
        try:
            stream_uuid = UUID(event.stream_id)
            tenant_uuid = UUID(event.tenant_id)
        except ValueError:
            logger.warning("pipeline_invalid_uuids", stream_id=event.stream_id)
            return {"processed": False, "error": "invalid_ids"}

        result = await db.execute(select(Stream).where(Stream.id == stream_uuid))
        stream = result.scalar_one_or_none()
        if not stream:
            logger.warning("pipeline_stream_not_found", stream_id=event.stream_id)
            return {"processed": False, "error": "stream_not_found"}

        ingest = EventIngest(
            event_type=_normalize_event_type(event.event_type),
            platform_user_id=event.platform_user_id,
            platform_username=event.platform_username,
            ip_address=event.ip_address,
            fingerprint_hash=event.fingerprint_hash,
            metadata=dict(event.metadata),
        )

        outcome = await process_stream_event(
            db,
            stream,
            tenant_uuid,
            ingest,
            source=event.source,
        )
        await db.commit()

        if event.category == EventCategory.SUSPICIOUS or outcome.get("risk_score", 0) >= 70:
            await publish_suspicious_signal(
                event,
                reason="high_risk_ingest",
                score=float(outcome.get("risk_score", 0)),
            )

        await publish_event_processed(event, outcome)

        logger.debug(
            "pipeline_event_processed",
            stream_id=event.stream_id,
            event_type=event.event_type,
            category=event.category.value,
            entry_id=stream_entry_id,
        )
        return {"processed": True, **outcome}


def _normalize_event_type(raw: str) -> str:
    mapping = {
        "channel.follow": "follow",
        "channel.chat.message": "chat_message",
        "stream.online": "viewer_join",
        "stream.offline": "viewer_leave",
    }
    return mapping.get(raw, raw)
