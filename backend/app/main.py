from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, ORJSONResponse
from prometheus_client import Counter, Histogram, generate_latest
from starlette.responses import Response

from app.api.v1 import auth, attacks, detection, mfa, streams, twitch_integration, users, webhooks
from app.api.websocket import routes as ws_routes
from app.core.config import get_settings
from app.core.exceptions import StreamShieldError
from app.core.logging import setup_logging, get_logger
from app.core.startup import run_startup_checks
from app.infrastructure.cache.redis_client import close_redis
from app.infrastructure.database.session import engine
from app.infrastructure.database.base import Base
from app.infrastructure.security.csrf import CSRFMiddleware
from app.infrastructure.security.middleware import (
    AntiDDoSMiddleware,
    DistributedRateLimitMiddleware,
    RequestTimingMiddleware,
    SecurityHeadersMiddleware,
)
from starlette.middleware.trustedhost import TrustedHostMiddleware

settings = get_settings()
setup_logging(settings.app_debug)
logger = get_logger(__name__)

REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_startup_checks()
    logger.info("starting_application", env=settings.app_env)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
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
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining"],
    max_age=3600,
)
app.add_middleware(CSRFMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AntiDDoSMiddleware)
app.add_middleware(DistributedRateLimitMiddleware)
app.add_middleware(RequestTimingMiddleware)

API_PREFIX = f"/api/{settings.app_api_version}"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(mfa.router, prefix=API_PREFIX)
app.include_router(twitch_integration.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(streams.router, prefix=API_PREFIX)
app.include_router(attacks.router, prefix=API_PREFIX)
app.include_router(detection.router, prefix=API_PREFIX)
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
