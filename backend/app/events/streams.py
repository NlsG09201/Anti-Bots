"""Redis Streams — buffer de alto rendimiento para el pipeline."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.schemas import EventCategory, PipelineEvent
from app.infrastructure.cache.redis_client import get_redis, redis_is_configured

logger = get_logger(__name__)
settings = get_settings()

STREAM_MAIN = "ss:events:main"
STREAM_PRIORITY = "ss:events:priority"
STREAM_DEAD_LETTER = "ss:events:dead-letter"
CONSUMER_GROUP = "ss-processors"


class EventStreamService:
    """XADD / XREADGROUP / XACK con trimming automático."""

    def __init__(self) -> None:
        self._group_ready: set[str] = set()
        self._claim_cursors: Dict[str, str] = {}

    def _stream_for_category(self, category: EventCategory) -> str:
        if category == EventCategory.SUSPICIOUS:
            return STREAM_PRIORITY
        return STREAM_MAIN

    async def ensure_consumer_group(self, stream_key: str) -> None:
        if not redis_is_configured() or stream_key in self._group_ready:
            return
        client = await get_redis()
        try:
            await client.xgroup_create(
                stream_key,
                CONSUMER_GROUP,
                id="0",
                mkstream=True,
            )
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        self._group_ready.add(stream_key)

    async def publish(self, event: PipelineEvent) -> Optional[str]:
        if not redis_is_configured():
            return None
        stream_key = self._stream_for_category(event.category)
        client = await get_redis()
        entry_id = await client.xadd(
            stream_key,
            event.to_stream_fields(),
            maxlen=settings.event_stream_max_len,
            approximate=True,
        )
        return entry_id

    async def publish_batch(self, events: List[PipelineEvent]) -> List[Optional[str]]:
        if not redis_is_configured() or not events:
            return []
        client = await get_redis()
        pipe = client.pipeline()
        keys: List[str] = []
        for event in events:
            sk = self._stream_for_category(event.category)
            keys.append(sk)
            pipe.xadd(
                sk,
                event.to_stream_fields(),
                maxlen=settings.event_stream_max_len,
                approximate=True,
            )
        ids = await pipe.execute()
        return ids

    async def read_batch(
        self,
        consumer_name: str,
        *,
        count: Optional[int] = None,
        block_ms: Optional[int] = None,
    ) -> List[Tuple[str, str, PipelineEvent]]:
        if not redis_is_configured():
            return []
        count = count or settings.event_consumer_batch_size
        block_ms = block_ms if block_ms is not None else settings.event_consumer_block_ms
        client = await get_redis()
        out: List[Tuple[str, str, PipelineEvent]] = []

        for stream_key in (STREAM_PRIORITY, STREAM_MAIN):
            await self.ensure_consumer_group(stream_key)
            min_idle_ms = max(
                settings.event_consumer_claim_idle_ms,
                settings.event_queue_job_timeout_seconds * 1000 + 30_000,
            )
            claimed = await client.xautoclaim(
                stream_key,
                CONSUMER_GROUP,
                consumer_name,
                min_idle_time=min_idle_ms,
                start_id=self._claim_cursors.get(stream_key, "0-0"),
                count=count,
            )
            self._claim_cursors[stream_key] = claimed[0] or "0-0"
            reclaimed = claimed[1] if len(claimed) > 1 else []
            await self._append_parsed_messages(stream_key, reclaimed, out)
            raw = await client.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=consumer_name,
                streams={stream_key: ">"},
                count=count,
                block=block_ms if stream_key == STREAM_MAIN else 1,
            )
            if not raw:
                continue
            for _sname, messages in raw:
                await self._append_parsed_messages(stream_key, messages, out)
        return out

    async def _append_parsed_messages(
        self,
        stream_key: str,
        messages: List[Tuple[str, Dict[str, Any]]],
        out: List[Tuple[str, str, PipelineEvent]],
    ) -> None:
        for entry_id, fields in messages:
            try:
                event = PipelineEvent.from_stream_fields(fields)
                out.append((stream_key, entry_id, event))
            except Exception as exc:
                await self.dead_letter(
                    stream_key=stream_key,
                    entry_id=entry_id,
                    fields=fields,
                    error_type=type(exc).__name__,
                )
                await self.ack(stream_key, entry_id)
                logger.warning(
                    "event_stream_entry_dead_lettered",
                    error_type=type(exc).__name__,
                    entry_id=entry_id,
                )

    async def dead_letter(
        self,
        *,
        stream_key: str,
        entry_id: str,
        fields: Dict[str, Any],
        error_type: str,
    ) -> None:
        """Persist an unparseable entry before acknowledging its source message."""
        client = await get_redis()

        def text(value: Any) -> str:
            return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)

        original_fields = {text(key): text(value) for key, value in fields.items()}
        await client.xadd(
            STREAM_DEAD_LETTER,
            {
                "source_stream": stream_key,
                "source_entry_id": text(entry_id),
                "error_type": error_type[:80],
                "original_fields": json.dumps(original_fields, separators=(",", ":")),
            },
            maxlen=settings.event_stream_max_len,
            approximate=True,
        )

    async def ack(self, stream_key: str, entry_id: str) -> None:
        if not redis_is_configured():
            return
        client = await get_redis()
        await client.xack(stream_key, CONSUMER_GROUP, entry_id)

    async def pending_count(self) -> Dict[str, Any]:
        if not redis_is_configured():
            return {"configured": False}
        client = await get_redis()
        stats: Dict[str, Any] = {"configured": True}
        for stream_key in (STREAM_MAIN, STREAM_PRIORITY):
            try:
                info = await client.xinfo_stream(stream_key)
                stats[stream_key] = {
                    "length": info.get("length", 0),
                    "groups": info.get("groups", 0),
                }
            except Exception:
                stats[stream_key] = {"length": 0}
        return stats
