"""Ventana deslizante de eventos por stream (Redis o memoria)."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.config import get_settings
from app.infrastructure.cache.redis_client import RedisCache

settings = get_settings()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _utc_now()


class EventWindowStore:
    """Almacena eventos recientes por stream para análisis multi-señal."""

    def __init__(self, window_seconds: Optional[int] = None):
        self.window_seconds = window_seconds or settings.viewbot_window_seconds
        self._cache = RedisCache(prefix="vbwin")

    def _key(self, stream_id: UUID) -> str:
        return f"events:{stream_id}"

    async def push(self, stream_id: UUID, event: Dict[str, Any]) -> None:
        key = self._key(stream_id)
        raw = await self._cache.get(key)
        events: List[Dict[str, Any]] = raw if isinstance(raw, list) else []
        entry = dict(event)
        entry["ts"] = (_parse_ts(entry.get("ts"))).isoformat()
        events.append(entry)
        cutoff = _utc_now().timestamp() - self.window_seconds
        pruned = []
        for e in events:
            try:
                if _parse_ts(e.get("ts")).timestamp() >= cutoff:
                    pruned.append(e)
            except (TypeError, ValueError):
                continue
        await self._cache.set(key, pruned[-500:], ttl=self.window_seconds + 30)

    async def get_events(self, stream_id: UUID) -> List[Dict[str, Any]]:
        raw = await self._cache.get(self._key(stream_id))
        if not isinstance(raw, list):
            return []
        cutoff = _utc_now().timestamp() - self.window_seconds
        out: List[Dict[str, Any]] = []
        for e in raw:
            try:
                if _parse_ts(e.get("ts")).timestamp() >= cutoff:
                    out.append(e)
            except (TypeError, ValueError):
                continue
        return out
