"""
Redis key naming and TTL conventions (enterprise real-time layer).

Primary OLTP remains PostgreSQL; Redis handles rate limits, event streams,
baselines, threat-intel cache, and WebSocket pub/sub.
"""

from __future__ import annotations

from uuid import UUID

# TTL seconds
TTL_IP_INTEL = 900
TTL_BASELINE = 3600
TTL_SESSION = 1800
TTL_RATE_LIMIT = 60

NUM_EVENT_SHARDS = 16


def rate_limit_key(ip: str, bucket: str) -> str:
    return f"rl:ip:{ip}:{bucket}"


def ip_intel_key(ip: str) -> str:
    return f"ip:intel:{ip}"


def stream_baseline_key(stream_id: UUID | str) -> str:
    return f"baseline:stream:{stream_id}"


def viewer_window_key(stream_id: UUID | str, window_sec: int = 60) -> str:
    return f"window:viewers:{stream_id}:{window_sec}"


def event_stream_key(tenant_id: UUID | str, shard: int) -> str:
    return f"evt:{tenant_id}:s{shard}"


def pubsub_channel(tenant_id: UUID | str) -> str:
    return f"pub:tenant:{tenant_id}"


def fingerprint_collision_key(stream_id: UUID | str, fp_hash: str) -> str:
    return f"fp:coll:{stream_id}:{fp_hash[:16]}"


def platform_sync_lock(platform: str, stream_id: UUID | str) -> str:
    return f"lock:sync:{platform}:{stream_id}"


def live_discovery_key(platform: str, channel: str) -> str:
    return f"discovery:live:{platform}:{channel.lower()}"


def live_metrics_key(stream_id: UUID | str) -> str:
    return f"metrics:live:{stream_id}"


def live_heartbeat_key(stream_id: UUID | str) -> str:
    return f"hb:live:{stream_id}"
