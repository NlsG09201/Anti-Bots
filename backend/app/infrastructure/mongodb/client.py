"""Optional MongoDB for AI feature archive and training datasets."""

from __future__ import annotations

from typing import Any, Optional

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_client: Any = None
_db: Any = None


async def get_mongo_db() -> Optional[Any]:
    global _client, _db
    uri = (settings.mongodb_uri or "").strip()
    if not uri or "PEGAR_" in uri:
        return None
    if _db is not None:
        return _db
    try:
        from motor.motor_asyncio import AsyncIOMotorClient

        _client = AsyncIOMotorClient(uri, maxPoolSize=20)
        _db = _client.get_default_database()
        return _db
    except Exception as exc:
        logger.warning("mongodb_unavailable", error=str(exc))
        return None


async def close_mongo() -> None:
    global _client, _db
    if _client:
        _client.close()
    _client = None
    _db = None
