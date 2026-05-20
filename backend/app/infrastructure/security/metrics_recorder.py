"""Contadores de bloqueos y eventos de seguridad (Redis / memoria)."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.infrastructure.cache.redis_client import RedisCache

BLOCK_REASONS = (
    "scanner_404",
    "rate_limit_429",
    "headers_403",
    "spoof_403",
    "automation_403",
    "widget_blocked_403",
    "payload_413",
    "query_414",
    "replay_400",
)

TTL_SECONDS = 72 * 3600


class SecurityMetricsRecorder:
    def __init__(self, cache: Optional[RedisCache] = None):
        self._cache = cache or RedisCache(prefix="sec")

    @staticmethod
    def hour_bucket(dt: Optional[datetime] = None) -> str:
        t = dt or datetime.now(timezone.utc)
        return t.astimezone(timezone.utc).strftime("%Y%m%d%H")

    async def record(self, reason: str, *, tenant_id: Optional[str] = None) -> None:
        bucket = self.hour_bucket()
        await self._cache.incr(f"blk:{reason}:{bucket}", ttl=TTL_SECONDS)
        if tenant_id:
            await self._cache.incr(
                f"tenant:{tenant_id}:blk:{reason}:{bucket}",
                ttl=TTL_SECONDS,
            )

    async def _get_count(self, key: str) -> int:
        raw = await self._cache.get(key)
        if raw is None:
            return 0
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    async def sum_reasons(self, reasons: List[str], hours: int) -> int:
        total = 0
        now = datetime.now(timezone.utc)
        for i in range(hours):
            dt = now - timedelta(hours=hours - 1 - i)
            bucket = self.hour_bucket(dt)
            for reason in reasons:
                total += await self._get_count(f"blk:{reason}:{bucket}")
        return total

    async def timeline(
        self,
        reasons: List[str],
        hours: int,
        *,
        tenant_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Serie horaria agregada de bloqueos."""
        now = datetime.now(timezone.utc)
        prefix = f"tenant:{tenant_id}:blk" if tenant_id else "blk"
        points: List[Dict[str, Any]] = []

        for i in range(hours):
            dt = now - timedelta(hours=hours - 1 - i)
            bucket = self.hour_bucket(dt)
            count = 0
            for reason in reasons:
                count += await self._get_count(f"{prefix}:{reason}:{bucket}")
            points.append(
                {
                    "time": dt.strftime("%H:00"),
                    "blocks": count,
                    "iso_hour": dt.isoformat(),
                }
            )
        return points

    async def summary(self, hours: int, *, tenant_id: Optional[str] = None) -> Dict[str, int]:
        reasons_403 = ["headers_403", "spoof_403", "automation_403", "widget_blocked_403"]
        out: Dict[str, int] = {
            "blocks_429": await self._sum_single("rate_limit_429", hours, tenant_id),
            "blocks_403": 0,
            "blocks_widget": await self._sum_single("widget_blocked_403", hours, tenant_id),
            "blocks_replay": await self._sum_single("replay_400", hours, tenant_id),
            "blocks_payload": await self._sum_single("payload_413", hours, tenant_id),
        }
        for r in reasons_403:
            out["blocks_403"] += await self._sum_single(r, hours, tenant_id)
        return out

    async def _sum_single(
        self, reason: str, hours: int, tenant_id: Optional[str]
    ) -> int:
        now = datetime.now(timezone.utc)
        prefix = f"tenant:{tenant_id}:blk" if tenant_id else "blk"
        total = 0
        for i in range(hours):
            dt = now - timedelta(hours=hours - 1 - i)
            bucket = self.hour_bucket(dt)
            total += await self._get_count(f"{prefix}:{reason}:{bucket}")
        return total

    async def top_block_reasons(
        self, hours: int, *, tenant_id: Optional[str] = None, limit: int = 8
    ) -> List[Dict[str, Any]]:
        ranked: List[Dict[str, Any]] = []
        for reason in BLOCK_REASONS:
            total = await self._sum_single(reason, hours, tenant_id)
            if total > 0:
                ranked.append({"reason": reason, "count": total})
        ranked.sort(key=lambda x: x["count"], reverse=True)
        return ranked[:limit]


_recorder: Optional[SecurityMetricsRecorder] = None


def get_security_metrics_recorder() -> SecurityMetricsRecorder:
    global _recorder
    if _recorder is None:
        _recorder = SecurityMetricsRecorder()
    return _recorder
