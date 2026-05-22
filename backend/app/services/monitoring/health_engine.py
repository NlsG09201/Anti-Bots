"""
Health Monitoring Engine: Tracks heartbeats, latency, and API status in real-time.
Provides data for the SOC dashboard and triggers reconnections.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import get_redis
from app.infrastructure.cache.redis_schema import live_heartbeat_key, live_metrics_key

logger = get_logger(__name__)

class HealthMonitoringEngine:
    async def record_heartbeat(self, stream_id: str, platform: str):
        """Records a live heartbeat for a stream."""
        redis = await get_redis()
        ts = time.time()
        await redis.set(live_heartbeat_key(stream_id), str(ts), ex=60)
        await redis.hset("health:heartbeats", stream_id, str(ts))
        await redis.hset("health:platforms", stream_id, platform)

    async def record_latency(self, stream_id: str, latency_ms: float):
        """Records API latency for a stream."""
        redis = await get_redis()
        await redis.set(f"metrics:latency:{stream_id}", str(latency_ms), ex=300)
        # Keep a rolling average in Redis
        key = f"health:latency:history:{stream_id}"
        await redis.lpush(key, str(latency_ms))
        await redis.ltrim(key, 0, 9) # Keep last 10 samples

    async def record_error(self, stream_id: str, error_type: str):
        """Records an API or socket error."""
        redis = await get_redis()
        await redis.hincrby("health:errors", stream_id, 1)
        await redis.set(f"health:last_error:{stream_id}", error_type, ex=3600)

    async def get_stream_health(self, stream_id: str) -> Dict[str, Any]:
        """Gets comprehensive health data for a stream."""
        redis = await get_redis()
        
        hb = await redis.get(live_heartbeat_key(stream_id))
        latency = await redis.get(f"metrics:latency:{stream_id}")
        last_error = await redis.get(f"health:last_error:{stream_id}")
        error_count = await redis.hget("health:errors", stream_id)
        
        return {
            "stream_id": stream_id,
            "is_healthy": hb is not None,
            "last_heartbeat": float(hb) if hb else None,
            "latency_ms": float(latency) if latency else None,
            "error_count": int(error_count) if error_count else 0,
            "last_error": last_error,
            "status": "online" if hb else "stale"
        }

    async def get_global_status(self) -> Dict[str, Any]:
        """Gets status for all monitored platforms."""
        redis = await get_redis()
        platforms = ["kick", "youtube", "tiktok", "twitch"]
        status = {}
        for p in platforms:
            health = await redis.get(f"health:platform:{p}")
            status[p] = health if health else "unknown"
        return status

_HEALTH: Optional[HealthMonitoringEngine] = None

def get_health_monitoring_engine() -> HealthMonitoringEngine:
    global _HEALTH
    if _HEALTH is None:
        _HEALTH = HealthMonitoringEngine()
    return _HEALTH
