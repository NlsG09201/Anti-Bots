"""HTTP client for TwitchBots.info v2 API with retries and rate limiting."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.integrations.twitchbots_info.schemas import TwitchBotsBotRecord, TwitchBotsTypeInfo

logger = get_logger(__name__)
settings = get_settings()

_rate_lock = asyncio.Lock()
_last_request_at: float = 0.0
_type_cache: Dict[int, TwitchBotsTypeInfo] = {}


def _min_interval() -> float:
    rps = max(float(settings.twitchbots_info_rate_limit_rps), 0.5)
    return 1.0 / rps


async def _throttle() -> None:
    global _last_request_at
    async with _rate_lock:
        now = time.monotonic()
        wait = _min_interval() - (now - _last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_at = time.monotonic()


class TwitchBotsInfoClient:
    def __init__(self) -> None:
        base = (settings.twitchbots_info_base_url or "https://api.twitchbots.info/v2").rstrip("/")
        self._base = base
        self._timeout = max(float(settings.twitchbots_info_request_timeout), 5.0)
        self._retries = max(int(settings.twitchbots_info_max_retries), 1)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not settings.twitchbots_info_enabled:
            return None
        url = f"{self._base}{path}"
        last_exc: Optional[Exception] = None
        for attempt in range(self._retries):
            await _throttle()
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.request(method, url, params=params)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as exc:
                last_exc = exc
                await asyncio.sleep(min(2 ** attempt * 0.4, 4.0))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (429, 502, 503, 504):
                    last_exc = exc
                    await asyncio.sleep(min(2 ** attempt * 0.6, 8.0))
                    continue
                logger.warning(
                    "twitchbots_info_http_error",
                    status=exc.response.status_code,
                    path=path,
                )
                return None
            except Exception as exc:
                last_exc = exc
                await asyncio.sleep(min(2 ** attempt * 0.3, 3.0))
        logger.warning(
            "twitchbots_info_request_failed",
            path=path,
            error=str(last_exc)[:150] if last_exc else "unknown",
        )
        return None

    async def get_type(self, type_id: int) -> Optional[TwitchBotsTypeInfo]:
        if type_id in _type_cache:
            return _type_cache[type_id]
        data = await self._request("GET", f"/type/{type_id}")
        if not data:
            return None
        info = TwitchBotsTypeInfo(
            id=int(data.get("id", type_id)),
            name=str(data.get("name") or ""),
            multi_channel=bool(data.get("multiChannel")),
            description=str(data.get("description") or ""),
            active=bool(data.get("active", True)),
        )
        _type_cache[type_id] = info
        return info

    async def get_bot_by_id(self, twitch_id: str) -> Optional[TwitchBotsBotRecord]:
        tid = str(twitch_id).strip()
        if not tid.isdigit():
            return None
        data = await self._request("GET", f"/bot/{tid}")
        if not data or not isinstance(data, dict):
            return None
        type_name = ""
        type_id = data.get("type")
        if type_id is not None:
            tinfo = await self.get_type(int(type_id))
            if tinfo:
                type_name = tinfo.name
        return TwitchBotsBotRecord.from_api(data, type_name=type_name)

    async def get_bots_by_ids(
        self, twitch_ids: List[str]
    ) -> Dict[str, TwitchBotsBotRecord]:
        clean = [str(i).strip() for i in twitch_ids if str(i).strip().isdigit()]
        if not clean:
            return {}
        out: Dict[str, TwitchBotsBotRecord] = {}
        batch_size = max(int(settings.twitchbots_info_batch_size), 1)
        batch_size = min(batch_size, 100)
        for offset in range(0, len(clean), batch_size):
            chunk = clean[offset : offset + batch_size]
            ids_param = ",".join(chunk)
            data = await self._request("GET", "/bot", params={"ids": ids_param})
            if not data:
                continue
            for bot in data.get("bots") or []:
                if not isinstance(bot, dict):
                    continue
                type_name = ""
                type_id = bot.get("type")
                if type_id is not None:
                    tinfo = await self.get_type(int(type_id))
                    if tinfo:
                        type_name = tinfo.name
                rec = TwitchBotsBotRecord.from_api(bot, type_name=type_name)
                if rec.twitch_id:
                    out[rec.twitch_id] = rec
        return out


_client: Optional[TwitchBotsInfoClient] = None


def get_twitchbots_info_client() -> TwitchBotsInfoClient:
    global _client
    if _client is None:
        _client = TwitchBotsInfoClient()
    return _client
