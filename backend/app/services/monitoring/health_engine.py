"""
Health Monitoring Engine: Tracks heartbeats, latency, and API status in real-time.
Provides data for the SOC dashboard and triggers reconnections.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import optional_get_redis, report_redis_error
from app.infrastructure.cache.redis_schema import live_heartbeat_key

logger = get_logger(__name__)


class HealthMonitoringEngine:
    async def record_heartbeat(self, stream_id: str, platform: str):
        """Record monitoring heartbeats when shared Redis is available."""
        client = await optional_get_redis()
        if client is None:
            return
        ts = time.time()
        try:
            await client.set(live_heartbeat_key(stream_id), str(ts), ex=60)
            await client.hset("health:heartbeats", stream_id, str(ts))
            await client.hset("health:platforms", stream_id, platform)
        except Exception as exc:
            report_redis_error(exc)

    async def record_latency(self, stream_id: str, latency_ms: float):
        """Record latency without letting the telemetry store break polling."""
        client = await optional_get_redis()
        if client is None:
            return
        try:
            await client.set(f"metrics:latency:{stream_id}", str(latency_ms), ex=300)
            key = f"health:latency:history:{stream_id}"
            await client.lpush(key, str(latency_ms))
            await client.ltrim(key, 0, 9)
        except Exception as exc:
            report_redis_error(exc)

    async def record_error(self, stream_id: str, error_type: str):
        """Record platform errors when Redis is available."""
        client = await optional_get_redis()
        if client is None:
            return
        try:
            await client.hincrby("health:errors", stream_id, 1)
            await client.set(f"health:last_error:{stream_id}", error_type, ex=3600)
        except Exception as exc:
            report_redis_error(exc)

    async def get_stream_health(self, stream_id: str) -> Dict[str, Any]:
        """Return an unavailable state rather than raising when Redis is down."""
        client = await optional_get_redis()
        if client is None:
            return {
                "stream_id": stream_id,
                "is_healthy": None,
                "last_heartbeat": None,
                "latency_ms": None,
                "error_count": 0,
                "last_error": None,
                "status": "unavailable",
            }
        try:
            hb = await client.get(live_heartbeat_key(stream_id))
            latency = await client.get(f"metrics:latency:{stream_id}")
            last_error = await client.get(f"health:last_error:{stream_id}")
            error_count = await client.hget("health:errors", stream_id)
        except Exception as exc:
            report_redis_error(exc)
            hb = latency = last_error = error_count = None

        return {
            "stream_id": stream_id,
            "is_healthy": hb is not None,
            "last_heartbeat": float(hb) if hb else None,
            "latency_ms": float(latency) if latency else None,
            "error_count": int(error_count) if error_count else 0,
            "last_error": last_error,
            "status": "online" if hb else "stale",
        }

    async def get_global_status(self) -> Dict[str, Any]:
        """Return unknown integration states while shared Redis is unavailable."""
        platforms = ["kick", "youtube", "tiktok", "twitch"]
        client = await optional_get_redis()
        if client is None:
            return {platform: "unknown" for platform in platforms}
        status = {}
        for platform in platforms:
            try:
                health = await client.get(f"health:platform:{platform}")
                status[platform] = health if health else "unknown"
            except Exception as exc:
                report_redis_error(exc)
                status[platform] = "unknown"
        return status


_HEALTH: Optional[HealthMonitoringEngine] = None


def get_health_monitoring_engine() -> HealthMonitoringEngine:
    global _HEALTH
    if _HEALTH is None:
        _HEALTH = HealthMonitoringEngine()
    return _HEALTH
