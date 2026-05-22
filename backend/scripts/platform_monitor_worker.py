#!/usr/bin/env python3
"""
Worker dedicado: monitores Kick / YouTube / TikTok (Render background worker).

No expone HTTP. Menor RAM que el API (sin Weka JVM ni IRC Twitch).
"""
from __future__ import annotations

import asyncio
import signal
import sys

from app.core.config import get_settings, invalidate_settings_cache
from app.core.logging import setup_logging, get_logger
from app.core.startup import run_startup_checks
from app.infrastructure.database.init_db import init_database
from app.infrastructure.database.migrations import run_startup_migrations
from app.infrastructure.database.session import engine
from app.infrastructure.cache.redis_client import close_redis
from app.services.monitoring.orchestrator import get_platform_monitor_orchestrator

logger = get_logger(__name__)
_shutdown = asyncio.Event()


def _handle_signal(*_args) -> None:
    _shutdown.set()


async def run_worker() -> None:
    invalidate_settings_cache()
    settings = get_settings()
    setup_logging(settings.app_debug)
    run_startup_checks()

    logger.info(
        "platform_monitor_worker_starting",
        max_streams=settings.platform_monitor_max_streams,
    )

    await init_database(engine)
    await run_startup_migrations(engine)

    if settings.mongodb_uri:
        from app.infrastructure.mongodb.startup import ensure_all_mongo_indexes_safe

        await ensure_all_mongo_indexes_safe()

    orch = get_platform_monitor_orchestrator()
    await orch.start()

    if settings.platform_health_enabled:
        from app.services.platform_health.engine import get_platform_health_engine

        he = get_platform_health_engine()
        he.set_process_label("worker")
        await he.start()
        logger.info("platform_health_engine_in_worker")
    if settings.viewer_flow_enabled:
        from app.viewer_flow import get_viewer_flow_engine

        await get_viewer_flow_engine().start()
        logger.info("viewer_flow_engine_in_worker")

    if settings.live_intel_enabled:
        from app.live_intel import get_live_intel_engine

        await get_live_intel_engine().start()
        logger.info("live_intel_sampler_in_worker")

    await _shutdown.wait()

    logger.info("platform_monitor_worker_shutting_down")
    if settings.platform_health_enabled:
        from app.services.platform_health.engine import get_platform_health_engine

        await get_platform_health_engine().stop()
    if settings.viewer_flow_enabled:
        from app.viewer_flow import get_viewer_flow_engine

        await get_viewer_flow_engine().stop()
    await orch.stop()
    if settings.live_intel_enabled:
        from app.live_intel import get_live_intel_engine

        await get_live_intel_engine().stop()
    await close_redis()
    await engine.dispose()


def main() -> None:
    if sys.platform != "win32":
        loop = asyncio.new_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, _handle_signal)
            except NotImplementedError:
                pass
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
