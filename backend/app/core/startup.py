import sys

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

    if "localhost" in settings.app_cors_origins and settings.is_production:
        logger.warning("cors_contains_localhost_in_production")

    if not settings.cookie_secure and settings.is_production:
        errors.append("COOKIE_SECURE must be true in production (HTTPS required)")

    if settings.database_url.startswith("sqlite"):
        errors.append("SQLite is not allowed in production; use PostgreSQL")

    if "localhost" in settings.database_url or "127.0.0.1" in settings.database_url:
        errors.append(
            "DATABASE_URL points to localhost — set Neon URL in Render Environment"
        )

    if not settings.redis_url or (
        "PEGAR_" in settings.redis_url
        or settings.redis_url.startswith("redis://:redis")
        or "localhost" in settings.redis_url
    ):
        logger.warning(
            "redis_not_configured",
            hint="Set REDIS_URL (Upstash rediss://) for distributed rate limiting",
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
            "cloudflare": bool(settings.cloudflare_api_token and settings.cloudflare_zone_id),
            "twitch": bool(settings.twitch_client_id),
            "discord": bool(settings.discord_webhook_url),
        },
    )
