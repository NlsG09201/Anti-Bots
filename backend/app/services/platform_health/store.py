"""Redis-backed platform health persistence."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import RedisCache, optional_get_redis, redis_is_configured
from app.services.platform_health.schemas import (
    IntegrationProbeResult,
    PlatformHealthOverview,
    StreamMonitorHealth,
    SystemHealthSlice,
)

logger = get_logger(__name__)

PREFIX = "pmh"
GLOBAL_KEY = f"{PREFIX}:global"
ISSUES_KEY = f"{PREFIX}:issues"
STREAM_PREFIX = f"{PREFIX}:stream"
ALERT_CD_PREFIX = f"{PREFIX}:alert_cd"


class PlatformHealthStore:
    def __init__(self) -> None:
        self._cache = RedisCache(prefix="ss")

    async def save_stream_health(self, snapshot: StreamMonitorHealth) -> None:
        payload = snapshot.model_dump()
        await self._cache.set(
            f"{STREAM_PREFIX}:{snapshot.stream_id}",
            payload,
            ttl=7200,
        )

    async def load_stream_health(self, stream_id: str) -> Optional[StreamMonitorHealth]:
        raw = await self._cache.get(f"{STREAM_PREFIX}:{stream_id}")
        if not raw:
            return None
        try:
            return StreamMonitorHealth.model_validate(raw)
        except Exception:
            return None

    async def load_all_stream_health(self) -> List[StreamMonitorHealth]:
        if not redis_is_configured():
            return []
        try:
            client = await optional_get_redis()
            if not client:
                return []
            keys = []
            async for key in client.scan_iter(match=f"ss:{STREAM_PREFIX}:*", count=50):
                keys.append(key)
            out: List[StreamMonitorHealth] = []
            for key in keys[:80]:
                sid = key.split(":")[-1]
                snap = await self.load_stream_health(sid)
                if snap:
                    out.append(snap)
            return out
        except Exception as exc:
            logger.debug("pmh_scan_failed", error=str(exc)[:120])
            return []

    async def save_global(
        self,
        system: SystemHealthSlice,
        integrations: List[IntegrationProbeResult],
    ) -> None:
        await self._cache.set(
            GLOBAL_KEY,
            {
                "system": system.model_dump(),
                "integrations": [i.model_dump() for i in integrations],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            ttl=300,
        )

    async def load_global(self) -> tuple[SystemHealthSlice, List[IntegrationProbeResult]]:
        raw = await self._cache.get(GLOBAL_KEY)
        if not raw:
            return SystemHealthSlice(), []
        system = SystemHealthSlice.model_validate(raw.get("system") or {})
        integrations = [
            IntegrationProbeResult.model_validate(i)
            for i in (raw.get("integrations") or [])
        ]
        return system, integrations

    async def record_worker_heartbeat(self, *, process: str = "worker") -> None:
        await self._cache.set(
            f"{PREFIX}:worker_hb",
            {
                "process": process,
                "ts": datetime.now(timezone.utc).isoformat(),
            },
            ttl=120,
        )

    async def worker_is_alive(self, max_age_seconds: int = 90) -> tuple[bool, Optional[str]]:
        raw = await self._cache.get(f"{PREFIX}:worker_hb")
        if not raw:
            return False, None
        ts = raw.get("ts")
        if not ts:
            return False, None
        try:
            seen = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - seen).total_seconds()
            return age <= max_age_seconds, ts
        except Exception:
            return False, ts

    async def push_issue(self, issue: Dict[str, Any], *, max_items: int = 40) -> None:
        issues = await self._cache.get(ISSUES_KEY) or []
        if not isinstance(issues, list):
            issues = []
        issues.insert(0, {**issue, "at": datetime.now(timezone.utc).isoformat()})
        await self._cache.set(ISSUES_KEY, issues[:max_items], ttl=86400)

    async def list_issues(self, limit: int = 30) -> List[Dict[str, Any]]:
        issues = await self._cache.get(ISSUES_KEY) or []
        if not isinstance(issues, list):
            return []
        return issues[:limit]

    async def alert_on_cooldown(self, issue_key: str, cooldown_seconds: int) -> bool:
        """True if alert should be suppressed (still in cooldown)."""
        key = f"{ALERT_CD_PREFIX}:{issue_key}"
        existing = await self._cache.get(key)
        if existing:
            return True
        await self._cache.set(key, {"t": time.time()}, ttl=cooldown_seconds)
        return False

    async def probe_redis_latency(self) -> tuple[bool, Optional[float]]:
        if not redis_is_configured():
            return False, None
        try:
            client = await optional_get_redis()
            if not client:
                return False, None
            t0 = time.perf_counter()
            await client.ping()
            ms = (time.perf_counter() - t0) * 1000.0
            return True, round(ms, 2)
        except Exception:
            return False, None
