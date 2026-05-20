"""Redis Streams — buffer de alto rendimiento para el pipeline."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.schemas import EventCategory, PipelineEvent
from app.infrastructure.cache.redis_client import get_redis, redis_is_configured

logger = get_logger(__name__)
settings = get_settings()

STREAM_MAIN = "ss:events:main"
STREAM_PRIORITY = "ss:events:priority"
CONSUMER_GROUP = "ss-processors"


class EventStreamService:
    """XADD / XREADGROUP / XACK con trimming automático."""

    def __init__(self) -> None:
        self._group_ready: set[str] = set()

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
                for entry_id, fields in messages:
                    try:
                        event = PipelineEvent.from_stream_fields(fields)
                        out.append((stream_key, entry_id, event))
                    except Exception as exc:
                        logger.warning(
                            "event_stream_parse_failed",
                            error=str(exc),
                            entry_id=entry_id,
                        )
        return out

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
