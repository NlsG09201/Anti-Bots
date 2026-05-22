import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, ORJSONResponse
from prometheus_client import Counter, Histogram, generate_latest
from starlette.responses import Response

from app.api.v1 import (
    auth,
    attacks,
    ai_insights,
    detection,
    ai_intel,
    enterprise,
    soc,
    events_pipeline,
    mfa,
    security,
    streams,
    threat_intel,
    twitch_integration,
    users,
    webhooks,
    widget,
    weka_ml,
)
from app.api.websocket import routes as ws_routes
from app.core.config import get_settings, invalidate_settings_cache
from app.core.exceptions import StreamShieldError
from app.core.logging import setup_logging, get_logger
from app.core.startup import run_startup_checks
from app.infrastructure.cache.redis_client import close_redis
from app.infrastructure.database.init_db import init_database
from app.infrastructure.database.session import engine
from app.infrastructure.security.csrf import CSRFMiddleware
from app.infrastructure.security.gateway import SecurityGatewayMiddleware
from app.infrastructure.security.middleware import (
    RequestTimingMiddleware,
    SecurityHeadersMiddleware,
)
from starlette.middleware.trustedhost import TrustedHostMiddleware

settings = get_settings()
setup_logging(settings.app_debug)
logger = get_logger(__name__)

REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"])


async def _background_channel_monitor() -> None:
    """Monitorea canales en vivo (IRC + picos de viewers) de forma rotativa."""
    from sqlalchemy import select

    from app.infrastructure.database.models import Stream
    from app.infrastructure.database.session import AsyncSessionLocal
    from app.services.monitoring.channel_monitor import ChannelMonitorService
    from app.services.streams.helpers import stream_monitor_mode

    from app.core.config import get_settings as _gs

    cfg = _gs()
    idx = 0
    scan_every = max(cfg.background_attack_scan_interval, 2)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Stream))
                streams = [
                    s for s in result.scalars().all()
                    if s.is_live
                    and (
                        stream_monitor_mode(s)
                        or s.oauth_token_encrypted
                        or s.platform.value in ("kick", "youtube", "tiktok")
                    )
                ]
                if streams:
                    stream = streams[idx % len(streams)]
                    idx += 1
                    monitor = ChannelMonitorService(db)
                    if stream.platform.value in ("kick", "youtube", "tiktok"):
                        from app.services.platforms.sync_service import PlatformSyncService
                        from app.services.streams.helpers import sync_stream_live_status

                        stream = await sync_stream_live_status(db, stream)
                        if stream.is_live:
                            await PlatformSyncService(db).sync_viewers(stream)
                    elif idx % scan_every == 0:
                        await monitor.run_cycle(stream, stream.tenant_id, irc_duration=45.0)
                    else:
                        await monitor.run_quick_sync(stream, stream.tenant_id)
                    await db.commit()
        except Exception as exc:
            logger.warning("background_monitor_error", error=str(exc))
        await asyncio.sleep(55)


@asynccontextmanager
async def lifespan(app: FastAPI):
    invalidate_settings_cache()
    run_startup_checks()
    logger.info("starting_application", env=get_settings().app_env)
    monitor_task = None
    try:
        await init_database(engine)
        from app.infrastructure.database.migrations import run_startup_migrations

        await run_startup_migrations(engine)
        from app.core.config import get_settings as _gs
        from app.integrations.twitchinsights.bot_database import get_twitch_insights_db

        _cfg = _gs()
        if _cfg.twitch_insights_enabled:
            asyncio.create_task(get_twitch_insights_db().ensure_loaded())
        if (
            _cfg.weka_j48_enabled
            and _cfg.weka_python_enabled
            and _cfg.weka_jvm_eager_start
        ):
            from app.ml.weka_j48.runtime import warm_weka_jvm

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: warm_weka_jvm(
                    java_home=_cfg.weka_java_home or "",
                    max_heap=_cfg.weka_jvm_max_heap,
                ),
            )
        monitor_task = asyncio.create_task(_background_channel_monitor())
        platform_monitor_task = None
        from app.core.config import get_settings as _gs2

        if _gs2().platform_monitor_enabled:
            from app.services.monitoring.orchestrator import get_platform_monitor_orchestrator

            platform_monitor_task = asyncio.create_task(
                get_platform_monitor_orchestrator().start()
            )
        from app.workers.pipeline_consumer import start_pipeline_consumer
        from app.workers.realtime_subscriber import start_realtime_subscriber

        await start_pipeline_consumer()
        await start_realtime_subscriber()
    except Exception as exc:
        logger.error(
            "database_startup_failed",
            error=str(exc),
            hint="Check DATABASE_URL in Render Environment (Neon pooler + sslmode=require)",
        )
        raise
    yield
    if monitor_task:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
    from app.services.monitoring.orchestrator import get_platform_monitor_orchestrator

    await get_platform_monitor_orchestrator().stop()
    from app.workers.pipeline_consumer import stop_pipeline_consumer
    from app.workers.realtime_subscriber import stop_realtime_subscriber

    await stop_pipeline_consumer()
    await stop_realtime_subscriber()
    await close_redis()
    await engine.dispose()
    logger.info("application_shutdown")


app = FastAPI(
    title=settings.app_name,
    description="Enterprise Anti-Bot Security Platform for Streamers",
    version="1.0.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

if settings.is_production:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.trusted_hosts_list,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Stream-Key"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining"],
    max_age=3600,
)
app.add_middleware(CSRFMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SecurityGatewayMiddleware)
app.add_middleware(RequestTimingMiddleware)

API_PREFIX = f"/api/{settings.app_api_version}"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(mfa.router, prefix=API_PREFIX)
app.include_router(twitch_integration.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(streams.router, prefix=API_PREFIX)
app.include_router(widget.router, prefix=API_PREFIX)
app.include_router(attacks.router, prefix=API_PREFIX)
app.include_router(detection.router, prefix=API_PREFIX)
app.include_router(security.router, prefix=API_PREFIX)
app.include_router(enterprise.router, prefix=API_PREFIX)
app.include_router(soc.router, prefix=API_PREFIX)
app.include_router(ai_intel.router, prefix=API_PREFIX)
app.include_router(weka_ml.router, prefix=API_PREFIX)
app.include_router(threat_intel.router, prefix=API_PREFIX)
app.include_router(events_pipeline.router, prefix=API_PREFIX)
app.include_router(ai_insights.router, prefix=API_PREFIX)
app.include_router(webhooks.router, prefix=API_PREFIX)
app.include_router(ws_routes.router)


@app.exception_handler(StreamShieldError)
async def streamshield_exception_handler(request: Request, exc: StreamShieldError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message},
    )


@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.app_name, "version": "1.0.0"}


@app.get("/metrics")
async def metrics():
    if not settings.prometheus_enabled:
        return Response(status_code=404)
    return Response(content=generate_latest(), media_type="text/plain")


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "version": "1.0.0",
        "docs": "/docs",
        "api": API_PREFIX,
    }
