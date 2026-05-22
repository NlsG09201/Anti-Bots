"""MongoDB startup — index creation must not block API boot on Render."""

from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def ensure_all_mongo_indexes_safe() -> bool:
    """
    Create MongoDB indexes if Atlas is reachable.
    Returns True on success, False if skipped or failed (API still starts).
    """
    cfg = get_settings()
    uri = (cfg.mongodb_uri or "").strip()
    if not uri or "PEGAR_" in uri:
        logger.info("mongodb_indexes_skipped", reason="no_uri")
        return False

    try:
        from app.threat_intel_engine.mongo_store import ensure_indexes
        from app.live_intel.mongo_store import ensure_live_intel_indexes
        from app.integrations.twitchbots_info.mongo_store import (
            ensure_twitchbots_info_indexes,
        )

        await ensure_indexes()
        await ensure_live_intel_indexes()
        await ensure_twitchbots_info_indexes()
        logger.info("mongodb_startup_indexes_ok")
        return True
    except Exception as exc:
        err = str(exc)
        logger.error(
            "mongodb_startup_indexes_failed",
            error=err[:400],
            hint=(
                "Verify MONGODB_URI (mongodb+srv), URL-encode password, "
                "Atlas Network Access (0.0.0.0/0), and TLS. "
                "API continues without Mongo persistence."
            ),
        )
        return False
