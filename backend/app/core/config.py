import os
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_RENDER_SECRET_ENV = Path("/etc/secrets/.env")


def render_secret_env_path() -> Path | None:
    return _RENDER_SECRET_ENV if _RENDER_SECRET_ENV.is_file() else None


def invalidate_settings_cache() -> None:
    get_settings.cache_clear()


def _bootstrap_render_environ() -> None:
    """Carga Secret File de Render en os.environ antes de leer Settings."""
    if not os.getenv("RENDER"):
        return
    secret = render_secret_env_path()
    if not secret:
        return
    for line in secret.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _resolve_env_file() -> str | None:
    if os.getenv("RENDER"):
        secret = render_secret_env_path()
        return str(secret) if secret else None
    local = Path(".env")
    return str(local) if local.is_file() else None


def _strip_wrapping_quotes(value: object) -> object:
    if isinstance(value, str) and len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "StreamShield"
    app_env: str = "development"
    app_debug: bool = False
    app_secret_key: str = Field(
        default="dev-secret-key-change-in-production-min-32-chars",
        min_length=32,
    )
    app_api_version: str = "v1"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_cors_origins: str = "http://localhost:3000"
    app_frontend_url: str = "http://localhost:3000"
    app_public_url: str = "http://localhost:8000"

    database_url: str = "postgresql+asyncpg://streamshield:streamshield_secure_password@localhost:5432/streamshield"
    redis_url: str = "redis://:redis_secure_password@localhost:6379/0"
    celery_broker_url: str = "amqp://streamshield:rabbitmq_secure_password@localhost:5672//"
    celery_result_backend: str = ""

    jwt_secret_key: str = Field(
        default="dev-jwt-secret-key-change-in-production-32",
        min_length=32,
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    aes_encryption_key: str = Field(
        default="dev-aes-encryption-key-32bytes!!",
        min_length=32,
    )

    twitch_client_id: str = ""
    twitch_client_secret: str = ""
    twitch_redirect_uri: str = ""
    twitch_webhook_secret: str = ""
    twitch_eventsub_callback_url: str = ""

    kick_client_id: str = ""
    kick_client_secret: str = ""
    kick_redirect_uri: str = ""

    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_redirect_uri: str = ""
    youtube_api_key: str = ""

    discord_webhook_url: str = ""
    cloudflare_api_token: str = ""
    cloudflare_zone_id: str = ""

    abuseipdb_api_key: str = ""
    ipqualityscore_api_key: str = ""
    virustotal_api_key: str = ""
    maxmind_license_key: str = ""
    geoip_database_path: str = "/app/data/GeoLite2-City.mmdb"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    ai_enabled: bool = True

    twitch_insights_enabled: bool = True
    twitch_insights_cache_hours: int = 6

    auto_twitch_ban_enabled: bool = True
    bot_suspected_attack_threshold: int = 5
    background_attack_scan_interval: int = 3
    viewer_load_irc_seconds: float = 35.0

    viewbot_realtime_enabled: bool = True
    viewbot_window_seconds: int = 120
    viewbot_alert_threshold: float = 50.0
    viewbot_auto_block_threshold: float = 85.0
    viewbot_ml_enabled: bool = True

    rate_limit_per_minute: int = 100
    rate_limit_burst: int = 20
    fail2ban_max_attempts: int = 5
    fail2ban_window_seconds: int = 300

    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    trusted_hosts: str = "localhost,127.0.0.1"

    cloudflare_auto_block: bool = False
    cloudflare_block_risk_threshold: float = 85.0

    otel_exporter_otlp_endpoint: str = "http://otel-collector:4317"
    prometheus_enabled: bool = True

    @field_validator(
        "database_url",
        "app_secret_key",
        "jwt_secret_key",
        "aes_encryption_key",
        "twitch_webhook_secret",
        mode="before",
    )
    @classmethod
    def strip_env_quotes(cls, v: object) -> object:
        return _strip_wrapping_quotes(v)

    @field_validator("cookie_samesite", mode="before")
    @classmethod
    def validate_samesite(cls, v: str) -> str:
        if v is None or (isinstance(v, str) and not v.strip()):
            return "lax"
        allowed = {"lax", "strict", "none"}
        if str(v).lower() not in allowed:
            raise ValueError(f"cookie_samesite must be one of {allowed}")
        return str(v).lower()

    @field_validator("redis_url", "celery_broker_url", "celery_result_backend", mode="before")
    @classmethod
    def ignore_redis_placeholders(cls, v: str) -> str:
        if v and "PEGAR_" in str(v):
            return ""
        return v or ""

    @field_validator("celery_result_backend", mode="before")
    @classmethod
    def default_celery_backend(cls, v: str, info) -> str:
        if not v and "redis_url" in info.data:
            return info.data["redis_url"]
        return v or ""

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.app_cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def model_post_init(self, __context) -> None:
        if self.is_production and not self.cookie_secure:
            object.__setattr__(self, "cookie_secure", True)

    @property
    def trusted_hosts_list(self) -> List[str]:
        return [h.strip() for h in self.trusted_hosts.split(",") if h.strip()]


@lru_cache
def get_settings() -> Settings:
    _bootstrap_render_environ()
    env_file = _resolve_env_file()
    if env_file:
        return Settings(_env_file=env_file)
    return Settings()
