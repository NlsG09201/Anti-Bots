"""Cross-platform identity correlation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.threat_intel_engine.hashing import normalize_username
from app.threat_intel_engine.mongo_store import ThreatIntelMongoStore


class CrossPlatformCorrelator:
    def __init__(self, store: ThreatIntelMongoStore) -> None:
        self._store = store

    async def register_identity(
        self,
        tenant_id: str,
        *,
        platform: str,
        username: Optional[str],
        entity_key: str,
    ) -> None:
        un = normalize_username(username)
        if not un:
            return
        await self._store.link_cross_platform(
            tenant_id, un, platform, entity_key
        )

    async def find_matches(
        self,
        tenant_id: str,
        username: Optional[str],
    ) -> List[Dict[str, Any]]:
        un = normalize_username(username)
        if not un:
            return []
        docs = await self._store.cross_platform_matches(tenant_id, un)
        out = []
        for d in docs:
            platforms = d.get("platforms") or []
            if len(platforms) >= 2:
                out.append(
                    {
                        "canonical_username": d.get("canonical_username"),
                        "platforms": platforms,
                        "entity_keys": (d.get("entity_keys") or [])[:10],
                        "multi_platform": True,
                    }
                )
        return out
