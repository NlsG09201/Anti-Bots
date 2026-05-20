"""Feature window storage — Redis primary, optional MongoDB archive."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import RedisCache

logger = get_logger(__name__)
settings = get_settings()


class FeatureStore:
    """Rolling feature windows per stream with intelligent cache."""

    def __init__(self) -> None:
        self._redis = RedisCache(prefix="ss:ai")
        self._window_ttl = 3600

    def _key(self, stream_id: str, suffix: str = "window") -> str:
        return f"feat:{stream_id}:{suffix}"

    async def append_event_features(
        self,
        stream_id: str,
        features: Dict[str, float],
        *,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, float]:
        """Append sample and return aggregated window stats."""
        key = self._key(stream_id)
        history: List[Dict[str, float]] = await self._redis.get(key) or []
        history.append(features)
        history = history[-120:]
        await self._redis.set(key, history, ttl=self._window_ttl)

        agg = self._aggregate(history)
        await self._redis.set(self._key(stream_id, "agg"), agg, ttl=self._window_ttl)

        if tenant_id and settings.mongodb_uri:
            await self._archive_mongo(tenant_id, stream_id, features)

        return agg

    def _aggregate(self, history: List[Dict[str, float]]) -> Dict[str, float]:
        if not history:
            return {}
        keys = history[0].keys()
        out: Dict[str, float] = {}
        for k in keys:
            vals = [h.get(k, 0.0) for h in history if k in h]
            if vals:
                out[k] = sum(vals) / len(vals)
                out[f"{k}_max"] = max(vals)
        out["sample_count"] = float(len(history))
        return out

    async def get_window_stats(self, stream_id: str) -> Dict[str, float]:
        agg = await self._redis.get(self._key(stream_id, "agg"))
        return agg if isinstance(agg, dict) else {}

    async def set_prediction(
        self, stream_id: str, assessment: Dict[str, Any], ttl: int = 300
    ) -> None:
        await self._redis.set(f"pred:{stream_id}", assessment, ttl=ttl)

    async def get_prediction(self, stream_id: str) -> Optional[Dict[str, Any]]:
        data = await self._redis.get(f"pred:{stream_id}")
        return data if isinstance(data, dict) else None

    async def _archive_mongo(
        self, tenant_id: str, stream_id: str, features: Dict[str, float]
    ) -> None:
        try:
            from app.infrastructure.mongodb.client import get_mongo_db

            db = await get_mongo_db()
            if db is None:
                return
            await db["ai_features"].insert_one(
                {
                    "tenant_id": tenant_id,
                    "stream_id": stream_id,
                    "features": features,
                }
            )
        except Exception as exc:
            logger.debug("mongo_feature_archive_skip", error=str(exc))
