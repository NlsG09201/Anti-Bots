"""Optional MongoDB for AI feature archive and training datasets."""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_client: Any = None
_db: Any = None
_connect_failed: bool = False


def _motor_client_kwargs(uri: str) -> dict:
    """Atlas TLS on Render/Docker: use certifi CA bundle when available."""
    kwargs: dict = {
        "maxPoolSize": 20,
        "serverSelectionTimeoutMS": 8000,
        "connectTimeoutMS": 10000,
    }
    if uri.startswith("mongodb+srv://") or "mongodb.net" in uri:
        try:
            import certifi

            kwargs["tlsCAFile"] = certifi.where()
        except ImportError:
            pass
    return kwargs


async def get_mongo_db() -> Optional[Any]:
    global _client, _db, _connect_failed
    uri = (settings.mongodb_uri or "").strip()
    if not uri or "PEGAR_" in uri:
        return None
    if _connect_failed:
        return None
    if _db is not None:
        return _db
    try:
        from motor.motor_asyncio import AsyncIOMotorClient

        _client = AsyncIOMotorClient(uri, **_motor_client_kwargs(uri))
        parsed = urlparse(uri)
        db_name = (parsed.path or "").strip("/") or "streamshield"
        _db = _client[db_name]
        await _client.admin.command("ping")
        return _db
    except Exception as exc:
        _connect_failed = True
        if _client:
            try:
                _client.close()
            except Exception:
                pass
        _client = None
        _db = None
        logger.warning("mongodb_unavailable", error=str(exc)[:300])
        return None


async def close_mongo() -> None:
    global _client, _db, _connect_failed
    if _client:
        try:
            _client.close()
        except Exception:
            pass
    _client = None
    _db = None
    _connect_failed = False
