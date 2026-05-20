"""
Base de viewbots de Twitch Insights (https://twitchinsights.net/bots).

API documentada en el propio sitio (DataTables):
  - GET https://api.twitchinsights.net/v1/bots/all
  - GET https://api.twitchinsights.net/v1/bots/online

Cada entrada: [username, channels_seen_in, last_seen_unix]
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Set

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

TI_BOTS_ALL_URL = "https://api.twitchinsights.net/v1/bots/all"
TI_BOTS_ONLINE_URL = "https://api.twitchinsights.net/v1/bots/online"
TI_ATTRIBUTION = "https://twitchinsights.net/bots"


@dataclass(frozen=True)
class TwitchInsightsBotRecord:
    username: str
    channel_count: int
    last_seen_ts: int
    is_online_now: bool

    @property
    def last_seen_iso(self) -> str:
        if self.last_seen_ts <= 0:
            return ""
        return datetime.fromtimestamp(self.last_seen_ts, tz=timezone.utc).strftime("%Y-%m-%d")


def _parse_bot_rows(rows: list) -> Dict[str, TwitchInsightsBotRecord]:
    out: Dict[str, TwitchInsightsBotRecord] = {}
    for row in rows or []:
        if not isinstance(row, (list, tuple)) or len(row) < 1:
            continue
        username = str(row[0]).strip()
        if not username:
            continue
        channel_count = int(row[1]) if len(row) > 1 and row[1] is not None else 0
        last_seen = int(row[2]) if len(row) > 2 and row[2] is not None else 0
        key = username.lower()
        out[key] = TwitchInsightsBotRecord(
            username=username,
            channel_count=channel_count,
            last_seen_ts=last_seen,
            is_online_now=False,
        )
    return out


class TwitchInsightsBotDatabase:
    """Cache en memoria de la lista comunitaria de viewbots (Twitch Insights)."""

    def __init__(self) -> None:
        self._bots: Dict[str, TwitchInsightsBotRecord] = {}
        self._online: Set[str] = set()
        self._loaded_at: float = 0.0
        self._load_lock = asyncio.Lock()

    @property
    def size(self) -> int:
        return len(self._bots)

    @property
    def online_count(self) -> int:
        return len(self._online)

    @property
    def is_stale(self) -> bool:
        if not self._bots:
            return True
        ttl = max(settings.twitch_insights_cache_hours, 1) * 3600
        return (time.monotonic() - self._loaded_at) >= ttl

    def lookup(self, username: str) -> Optional[TwitchInsightsBotRecord]:
        if not username:
            return None
        return self._bots.get(username.lower())

    async def ensure_loaded(self) -> bool:
        if not settings.twitch_insights_enabled:
            return False
        if self._bots and not self.is_stale:
            return True
        async with self._load_lock:
            if self._bots and not self.is_stale:
                return True
            return await self._refresh()

    async def _refresh(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                all_resp, online_resp = await asyncio.gather(
                    client.get(TI_BOTS_ALL_URL),
                    client.get(TI_BOTS_ONLINE_URL),
                )
            all_resp.raise_for_status()
            online_resp.raise_for_status()
            all_data = all_resp.json()
            online_data = online_resp.json()

            bots = _parse_bot_rows(all_data.get("bots") or [])
            online_keys = {
                str(row[0]).strip().lower()
                for row in (online_data.get("bots") or [])
                if isinstance(row, (list, tuple)) and row
            }
            self._online = online_keys
            for key in online_keys:
                if key in bots:
                    rec = bots[key]
                    bots[key] = TwitchInsightsBotRecord(
                        username=rec.username,
                        channel_count=rec.channel_count,
                        last_seen_ts=rec.last_seen_ts,
                        is_online_now=True,
                    )

            self._bots = bots
            self._loaded_at = time.monotonic()
            logger.info(
                "twitch_insights_db_loaded",
                total=len(self._bots),
                online=len(self._online),
            )
            return True
        except Exception as exc:
            logger.warning("twitch_insights_db_refresh_failed", error=str(exc))
            return bool(self._bots)


_db_singleton: Optional[TwitchInsightsBotDatabase] = None


def get_twitch_insights_db() -> TwitchInsightsBotDatabase:
    global _db_singleton
    if _db_singleton is None:
        _db_singleton = TwitchInsightsBotDatabase()
    return _db_singleton
