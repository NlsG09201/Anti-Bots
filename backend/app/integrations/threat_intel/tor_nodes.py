"""TOR Exit Nodes — Detect TOR exit node IPs."""

from typing import Any, Dict, Optional, Set
from datetime import datetime, timedelta
import json

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import get_redis

logger = get_logger(__name__)
settings = get_settings()

# Cache key for TOR exit nodes
TOR_NODES_CACHE_KEY = "ti:tor:exit_nodes"
TOR_NODES_CACHE_TTL = 86400 * 7  # 7 days


class TorExitNodeService:
    """Detect and track TOR exit nodes."""

    # Onionoo API for TOR exit node information
    ONIONOO_API = "https://onionoo.torproject.org/details"

    @property
    def enabled(self) -> bool:
        return settings.tor_detection_enabled

    async def _fetch_tor_nodes(self) -> Optional[Set[str]]:
        """Fetch current TOR exit nodes from Onionoo API."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    self.ONIONOO_API,
                    params={"type": "relay", "fields": "exit_addresses"},
                )
                if response.status_code != 200:
                    return None

                data = response.json()
                tor_ips = set()

                for relay in data.get("relays", []):
                    if relay.get("exit_addresses"):
                        tor_ips.update(relay["exit_addresses"])

                return tor_ips
        except Exception as exc:
            logger.warning("tor_nodes_fetch_failed", error=str(exc))
            return None

    async def _get_cached_nodes(self) -> Optional[Set[str]]:
        """Get cached TOR exit nodes from Redis."""
        redis = get_redis()
        try:
            cached = await redis.get(TOR_NODES_CACHE_KEY)
            if cached:
                nodes = json.loads(cached)
                return set(nodes)
        except Exception as exc:
            logger.warning("tor_nodes_cache_read_failed", error=str(exc))

        return None

    async def _cache_nodes(self, nodes: Set[str]) -> None:
        """Cache TOR exit nodes in Redis."""
        redis = get_redis()
        try:
            await redis.set(
                TOR_NODES_CACHE_KEY,
                json.dumps(list(nodes)),
                ttl=TOR_NODES_CACHE_TTL,
            )
        except Exception as exc:
            logger.warning("tor_nodes_cache_write_failed", error=str(exc))

    async def refresh_nodes(self) -> Optional[Set[str]]:
        """Refresh TOR exit node list from API."""
        nodes = await self._fetch_tor_nodes()
        if nodes:
            await self._cache_nodes(nodes)
            logger.info("tor_nodes_refreshed", count=len(nodes))
        return nodes

    async def is_exit_node(self, ip_address: str) -> bool:
        """Check if IP is a known TOR exit node."""
        if not self.enabled:
            return False

        # Try cache first
        nodes = await self._get_cached_nodes()

        # If cache empty, fetch fresh
        if nodes is None:
            nodes = await self.refresh_nodes()
            if nodes is None:
                return False

        return ip_address in nodes

    async def check(self, ip_address: str) -> Optional[Dict[str, Any]]:
        """Check if IP is a TOR exit node."""
        if not self.enabled:
            return None

        is_tor = await self.is_exit_node(ip_address)
        if not is_tor:
            return None

        return {
            "source": "tor_exit_nodes",
            "is_tor_exit_node": True,
            "threat_categories": ["tor"],
            "recommendation": "MONITOR",
        }
