from urllib.parse import urlparse

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings
from app.infrastructure.cache.redis_client import _get_redis_credential_provider

settings = get_settings()
result_backend = settings.celery_result_backend or settings.redis_url


def configure_managed_identity_backend(app: Celery, backend_url: str, auth_mode: str) -> None:
    if auth_mode != "managed_identity":
        return
    parsed = urlparse(backend_url)
    if parsed.scheme not in {"redis", "rediss"}:
        return
    if parsed.scheme != "rediss" or parsed.username is not None or parsed.password is not None:
        raise ValueError(
            "Managed identity Celery Redis backend requires rediss:// without embedded credentials"
        )
    app.conf.redis_backend_use_ssl = {
        "credential_provider": _get_redis_credential_provider(),
        "ssl_cert_reqs": "required",
        "ssl_check_hostname": True,
    }


celery_app = Celery(
    "streamshield",
    broker=settings.celery_broker_url,
    backend=result_backend,
    include=["app.workers.tasks"],
)

configure_managed_identity_backend(
    celery_app,
    result_backend,
    settings.redis_auth_mode,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    task_routes={
        "app.workers.tasks.*": {"queue": "default"},
        "app.workers.tasks.process_*": {"queue": "detection"},
        "app.workers.tasks.enrich_*": {"queue": "enrichment"},
    },
    beat_schedule={
        "correlate-events": {
            "task": "app.workers.tasks.correlate_all_streams",
            "schedule": crontab(minute="*/1"),
        },
        "update-ip-reputations": {
            "task": "app.workers.tasks.refresh_stale_reputations",
            "schedule": crontab(minute="*/15"),
        },
        "cleanup-expired-bans": {
            "task": "app.workers.tasks.cleanup_expired_bans",
            "schedule": crontab(minute="*/5"),
        },
        "detect-coordinated-attacks": {
            "task": "app.workers.tasks.scan_coordinated_attacks",
            "schedule": crontab(minute="*/2"),
        },
    },
)
