"""Partition event streams for horizontal scale (millions of events/day)."""

from __future__ import annotations

import hashlib
from uuid import UUID

from app.infrastructure.cache.redis_schema import NUM_EVENT_SHARDS, event_stream_key


def shard_index(tenant_id: UUID, stream_id: UUID) -> int:
    """Deterministic shard from tenant + stream (stable routing)."""
    raw = f"{tenant_id}:{stream_id}".encode()
    digest = hashlib.sha256(raw).hexdigest()
    return int(digest[:8], 16) % NUM_EVENT_SHARDS


def resolve_event_stream_name(tenant_id: UUID, stream_id: UUID) -> str:
    return event_stream_key(tenant_id, shard_index(tenant_id, stream_id))
