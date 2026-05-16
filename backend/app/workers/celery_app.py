from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "streamshield",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend or settings.redis_url,
    include=["app.workers.tasks"],
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
