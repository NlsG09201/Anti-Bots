import sys
from urllib.parse import urlsplit

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

INSECURE_DEFAULTS = {
    "dev-secret-key-change-in-production-min-32-chars",
    "dev-jwt-secret-key-change-in-production-32",
    "dev-aes-encryption-key-32bytes!!",
    "change-me-to-64-char-random-secret-key-for-production-use-only",
    "change-me-jwt-secret-key-min-32-chars",
    "change-me-32-byte-aes-key-here!!",
    "streamshield_secure_password",
    "redis_secure_password",
    "rabbitmq_secure_password",
}


def validate_production_settings() -> list[str]:
    settings = get_settings()
    errors: list[str] = []

    if not settings.is_production:
        return errors

    if settings.app_debug:
        errors.append("APP_DEBUG must be false in production")

    for name, value in [
        ("APP_SECRET_KEY", settings.app_secret_key),
        ("JWT_SECRET_KEY", settings.jwt_secret_key),
        ("AES_ENCRYPTION_KEY", settings.aes_encryption_key),
    ]:
        if value in INSECURE_DEFAULTS:
            errors.append(f"{name} uses an insecure default value")

    origins = settings.cors_origins_list
    if not origins:
        errors.append("APP_CORS_ORIGINS must contain at least one production origin")
    for origin in origins:
        parsed_origin = urlsplit(origin)
        if origin == "*":
            errors.append("APP_CORS_ORIGINS must not allow every origin in production")
        elif parsed_origin.scheme != "https" or not parsed_origin.netloc:
            errors.append(f"APP_CORS_ORIGINS must use HTTPS in production: {origin}")
        elif parsed_origin.hostname in {"localhost", "127.0.0.1", "::1"}:
            errors.append("APP_CORS_ORIGINS must not include loopback origins in production")

    trusted_hosts = settings.trusted_hosts_list
    if not trusted_hosts:
        errors.append("TRUSTED_HOSTS must contain explicit production hosts")
    for host in trusted_hosts:
        if host == "*":
            errors.append("TRUSTED_HOSTS must not allow every host in production")
        elif host.lower() in {"localhost", "127.0.0.1", "::1"}:
            errors.append("TRUSTED_HOSTS must not include loopback hosts in production")

    if not settings.cookie_secure and settings.is_production:
        errors.append("COOKIE_SECURE must be true in production (HTTPS required)")

    if settings.database_url.startswith("sqlite"):
        errors.append("SQLite is not allowed in production; use PostgreSQL")

    if "localhost" in settings.database_url or "127.0.0.1" in settings.database_url:
        errors.append(
            "DATABASE_URL points to localhost — set Neon URL in Render Environment"
        )

    redis_tcp_configured = bool(settings.redis_url) and not (
        "PEGAR_" in settings.redis_url
        or settings.redis_url.startswith("redis://:redis")
        or "localhost" in settings.redis_url
        or "127.0.0.1" in settings.redis_url
    )
    redis_rest_configured = bool(
        settings.upstash_redis_rest_url.startswith("https://")
        and settings.upstash_redis_rest_token
    )
    if not redis_tcp_configured and not redis_rest_configured:
        logger.warning(
            "redis_not_configured",
            hint="Set REDIS_URL or UPSTASH_REDIS_REST_URL/UPSTASH_REDIS_REST_TOKEN",
        )
    elif not redis_tcp_configured and redis_rest_configured:
        logger.warning(
            "redis_tcp_not_configured",
            hint="Upstash REST supports cache commands only; set REDIS_URL for arq, Redis Streams, and realtime pub/sub",
        )

    return errors


def run_startup_checks() -> None:
    settings = get_settings()
    errors = validate_production_settings()

    if errors:
        for err in errors:
            logger.error("startup_validation_failed", error=err)
            print(f"startup_validation_failed: {err}", flush=True)
        if settings.is_production:
            print(
                "Render: set DATABASE_URL, APP_SECRET_KEY, JWT_SECRET_KEY, AES_ENCRYPTION_KEY "
                "in Dashboard -> Environment (import deploy/render.import.env).",
                flush=True,
            )
            sys.exit(1)

    logger.info(
        "startup_checks_passed",
        env=settings.app_env,
        integrations={
            "abuseipdb": bool(settings.abuseipdb_api_key),
            "ipqualityscore": bool(settings.ipqualityscore_api_key),
            "virustotal": bool(settings.virustotal_api_key),
            "threat_intel_ipapi": settings.threat_intel_ipapi_enabled,
            "event_pipeline": settings.event_pipeline_enabled,
            "event_queue_arq": settings.event_queue_enabled,
            "openai": settings.ai_enabled and bool(settings.openai_api_key and settings.openai_model),
            "cloudflare": bool(settings.cloudflare_api_token and settings.cloudflare_zone_id),
            "twitch": bool(settings.twitch_client_id),
            "discord": bool(settings.discord_webhook_url),
        },
    )
