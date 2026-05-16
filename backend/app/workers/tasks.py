import asyncio
from datetime import datetime, timezone

from app.workers.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.workers.tasks.process_stream_event", bind=True, max_retries=3)
def process_stream_event(self, stream_id: str, event_data: dict):
    async def _process():
        from app.infrastructure.database.session import AsyncSessionLocal
        from app.services.detection.engine import BotDetectionEngine, EventBatch
        from app.services.correlation.service import CorrelationService
        from app.services.mitigation.service import MitigationService
        from uuid import UUID

        engine = BotDetectionEngine()
        async with AsyncSessionLocal() as db:
            batch = EventBatch(events=[event_data], stream_id=stream_id)
            result = engine.analyze_viewbot_pattern(batch)
            if result.is_threat:
                correlation = CorrelationService(db)
                from app.infrastructure.database.models import AttackType
                attack = await correlation.create_attack_record(
                    stream_id=UUID(stream_id),
                    attack_type=AttackType.VIEWBOT,
                    risk_score=result.risk_score,
                    confidence=result.confidence,
                    evidence=result.evidence,
                    source_ips=[event_data.get("ip_address", "")],
                    fingerprints=[event_data.get("fingerprint_hash", "")],
                )
                await db.commit()
                logger.info("attack_detected_async", attack_id=str(attack.id))
        return {"processed": True, "risk_score": result.risk_score}

    return run_async(_process())


@celery_app.task(name="app.workers.tasks.correlate_all_streams")
def correlate_all_streams():
    async def _correlate():
        from app.infrastructure.database.session import AsyncSessionLocal
        from sqlalchemy import select
        from app.infrastructure.database.models import Stream
        from app.services.correlation.service import CorrelationService

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Stream).where(Stream.is_live == True))
            streams = result.scalars().all()
            for stream in streams:
                correlation = CorrelationService(db)
                correlations = await correlation.correlate_events(stream.id)
                coordinated = await correlation.find_coordinated_attacks(stream.id)
                if coordinated:
                    logger.warning(
                        "coordinated_attack_detected",
                        stream_id=str(stream.id),
                        score=coordinated["coordination_score"],
                    )
            await db.commit()
        return {"streams_checked": len(streams)}

    return run_async(_correlate())


@celery_app.task(name="app.workers.tasks.refresh_stale_reputations")
def refresh_stale_reputations():
    async def _refresh():
        from app.infrastructure.database.session import AsyncSessionLocal
        from sqlalchemy import select
        from datetime import timedelta
        from app.infrastructure.database.models import IPReputation
        from app.services.reputation.service import ReputationService

        stale_since = datetime.now(timezone.utc) - timedelta(hours=24)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(IPReputation).where(IPReputation.last_seen < stale_since).limit(100)
            )
            ips = result.scalars().all()
            svc = ReputationService(db)
            for ip in ips:
                await svc.enrich_ip(ip.ip_address)
            await db.commit()
        return {"refreshed": len(ips)}

    return run_async(_refresh())


@celery_app.task(name="app.workers.tasks.cleanup_expired_bans")
def cleanup_expired_bans():
    async def _cleanup():
        from app.infrastructure.database.session import AsyncSessionLocal
        from sqlalchemy import select, update
        from app.infrastructure.database.models import Ban

        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Ban)
                .where(Ban.expires_at < now, Ban.is_active == True)
                .values(is_active=False)
            )
            await db.commit()
        return {"cleaned": True}

    return run_async(_cleanup())


@celery_app.task(name="app.workers.tasks.scan_coordinated_attacks")
def scan_coordinated_attacks():
    return correlate_all_streams()


@celery_app.task(name="app.workers.tasks.send_discord_alert")
def send_discord_alert(title: str, message: str, severity: str):
    async def _send():
        from app.integrations.discord.webhook import DiscordNotifier
        notifier = DiscordNotifier()
        await notifier.send_alert(title, message, severity)
        return {"sent": True}

    return run_async(_send())
