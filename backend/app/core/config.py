from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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

    rate_limit_per_minute: int = 100
    rate_limit_burst: int = 20
    fail2ban_max_attempts: int = 5
    fail2ban_window_seconds: int = 300

    # Cookies (production: secure=true, samesite=strict)
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    trusted_hosts: str = "localhost,127.0.0.1"

    # Auto-block IPs at Cloudflare edge when risk >= threshold
    cloudflare_auto_block: bool = False
    cloudflare_block_risk_threshold: float = 85.0

    otel_exporter_otlp_endpoint: str = "http://otel-collector:4317"
    prometheus_enabled: bool = True

    @field_validator("cookie_samesite")
    @classmethod
    def validate_samesite(cls, v: str) -> str:
        allowed = {"lax", "strict", "none"}
        if v.lower() not in allowed:
            raise ValueError(f"cookie_samesite must be one of {allowed}")
        return v.lower()

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
    return Settings()
