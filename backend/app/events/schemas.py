"""Esquemas del bus de eventos."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EventCategory(str, Enum):
    VIEWER = "viewer"
    FOLLOW = "follow"
    MESSAGE = "message"
    CONNECTION = "connection"
    SUSPICIOUS = "suspicious"


# Mapeo event_type (ingest) → categoría de cola
EVENT_TYPE_TO_CATEGORY: Dict[str, EventCategory] = {
    "viewer_join": EventCategory.VIEWER,
    "viewer_leave": EventCategory.VIEWER,
    "viewer_pulse": EventCategory.VIEWER,
    "viewer_part": EventCategory.VIEWER,
    "follow": EventCategory.FOLLOW,
    "channel.follow": EventCategory.FOLLOW,
    "chat_message": EventCategory.MESSAGE,
    "channel.chat.message": EventCategory.MESSAGE,
    "connection": EventCategory.CONNECTION,
    "widget_connect": EventCategory.CONNECTION,
    "widget_ping": EventCategory.CONNECTION,
    "stream.online": EventCategory.CONNECTION,
    "stream.offline": EventCategory.CONNECTION,
    "suspicious": EventCategory.SUSPICIOUS,
    "security_flag": EventCategory.SUSPICIOUS,
}


def resolve_category(event_type: str, metadata: Optional[Dict[str, Any]] = None) -> EventCategory:
    if metadata and metadata.get("force_suspicious"):
        return EventCategory.SUSPICIOUS
    pre = (metadata or {}).get("pre_risk_score")
    if pre is not None and float(pre) >= 70:
        return EventCategory.SUSPICIOUS
    return EVENT_TYPE_TO_CATEGORY.get(event_type, EventCategory.VIEWER)


class PipelineEvent(BaseModel):
    """Evento normalizado para Redis Stream y colas de trabajo."""

    stream_id: str
    tenant_id: str
    event_type: str
    category: EventCategory
    platform_user_id: Optional[str] = None
    platform_username: Optional[str] = None
    ip_address: Optional[str] = None
    fingerprint_hash: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    source: str = "api"
    enqueued_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def from_ingest(
        cls,
        *,
        stream_id: UUID,
        tenant_id: UUID,
        event_type: str,
        platform_user_id: Optional[str] = None,
        platform_username: Optional[str] = None,
        ip_address: Optional[str] = None,
        fingerprint_hash: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        source: str = "api",
    ) -> PipelineEvent:
        meta = dict(metadata or {})
        return cls(
            stream_id=str(stream_id),
            tenant_id=str(tenant_id),
            event_type=event_type,
            category=resolve_category(event_type, meta),
            platform_user_id=platform_user_id,
            platform_username=platform_username,
            ip_address=ip_address,
            fingerprint_hash=fingerprint_hash,
            metadata=meta,
            source=source,
        )

    def to_stream_fields(self) -> Dict[str, str]:
        import json

        return {
            "stream_id": self.stream_id,
            "tenant_id": self.tenant_id,
            "event_type": self.event_type,
            "category": self.category.value,
            "platform_user_id": self.platform_user_id or "",
            "platform_username": self.platform_username or "",
            "ip_address": self.ip_address or "",
            "fingerprint_hash": self.fingerprint_hash or "",
            "metadata": json.dumps(self.metadata, separators=(",", ":")),
            "source": self.source,
            "enqueued_at": self.enqueued_at,
        }

    @classmethod
    def from_stream_fields(cls, fields: Dict[str, str]) -> PipelineEvent:
        import json

        meta_raw = fields.get("metadata") or "{}"
        try:
            metadata = json.loads(meta_raw)
        except json.JSONDecodeError:
            metadata = {}
        return cls(
            stream_id=fields["stream_id"],
            tenant_id=fields["tenant_id"],
            event_type=fields["event_type"],
            category=EventCategory(fields.get("category", EventCategory.VIEWER.value)),
            platform_user_id=fields.get("platform_user_id") or None,
            platform_username=fields.get("platform_username") or None,
            ip_address=fields.get("ip_address") or None,
            fingerprint_hash=fields.get("fingerprint_hash") or None,
            metadata=metadata,
            source=fields.get("source", "api"),
            enqueued_at=fields.get("enqueued_at", datetime.now(timezone.utc).isoformat()),
        )
