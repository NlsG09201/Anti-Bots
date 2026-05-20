"""Caché Redis para threat intelligence (TTL por tipo de resultado)."""

from typing import Any, Dict, Optional

from app.core.config import get_settings
from app.infrastructure.cache.redis_client import RedisCache

settings = get_settings()


class ThreatIntelCache:
    PREFIX = "ti:v1"

    def __init__(self, cache: Optional[RedisCache] = None):
        self._cache = cache or RedisCache(prefix=self.PREFIX)

    def _key(self, ip_address: str) -> str:
        return f"ip:{ip_address}"

    async def get(self, ip_address: str) -> Optional[Dict[str, Any]]:
        return await self._cache.get(self._key(ip_address))

    async def set(
        self,
        ip_address: str,
        payload: Dict[str, Any],
        *,
        high_risk: bool = False,
    ) -> None:
        ttl = (
            settings.threat_intel_cache_ttl_high_risk
            if high_risk
            else settings.threat_intel_cache_ttl_seconds
        )
        await self._cache.set(self._key(ip_address), payload, ttl=ttl)

    async def invalidate(self, ip_address: str) -> None:
        await self._cache.delete(self._key(ip_address))
