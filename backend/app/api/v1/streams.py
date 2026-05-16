from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.api.v1.schemas import (
    DashboardStats,
    EventIngest,
    StreamCreate,
    StreamResponse,
    ViewerSessionResponse,
)
from app.core.exceptions import NotFoundError
from app.infrastructure.database.models import (
    Attack,
    Alert,
    Ban,
    IPReputation,
    Stream,
    StreamEvent,
    ViewerSession,
)
from app.infrastructure.database.session import get_db
from app.services.detection.engine import BotDetectionEngine, EventBatch
from app.services.correlation.service import CorrelationService
from app.services.mitigation.service import MitigationService
from app.services.reputation.service import ReputationService
from app.infrastructure.database.models import AttackType

router = APIRouter(prefix="/streams", tags=["Streams"])
detection_engine = BotDetectionEngine()


@router.post("", response_model=StreamResponse)
async def create_stream(
    data: StreamCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    stream = Stream(
        tenant_id=current_user.tenant_id,
        owner_id=current_user.id,
        platform=data.platform,
        external_id=data.external_id,
        channel_name=data.channel_name,
    )
    db.add(stream)
    await db.flush()
    return stream


@router.get("", response_model=List[StreamResponse])
async def list_streams(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Stream).where(Stream.tenant_id == current_user.tenant_id)
    )
    return result.scalars().all()


@router.get("/{stream_id}", response_model=StreamResponse)
async def get_stream(
    stream_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    stream = await _get_stream(db, stream_id, current_user.tenant_id)
    return stream


@router.post("/{stream_id}/events")
async def ingest_event(
    stream_id: UUID,
    event: EventIngest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    stream = await _get_stream(db, stream_id, current_user.tenant_id)
    correlation = CorrelationService(db)
    reputation_svc = ReputationService(db)

    ip_data = {}
    if event.ip_address:
        ip_data = await reputation_svc.enrich_ip(event.ip_address)

    fp_risk = 0.0
    if event.fingerprint_hash:
        fp_risk = event.metadata.get("fingerprint_risk", 0.0)

    ip_result = detection_engine.analyze_ip(ip_data) if ip_data else None
    risk_score = max(
        ip_result.risk_score if ip_result else 0.0,
        fp_risk,
    )

    stream_event = StreamEvent(
        stream_id=stream.id,
        event_type=event.event_type,
        platform_user_id=event.platform_user_id,
        platform_username=event.platform_username,
        ip_address=event.ip_address,
        fingerprint_hash=event.fingerprint_hash,
        asn=ip_data.get("asn") if ip_data else None,
        country_code=ip_data.get("country_code") if ip_data else None,
        is_proxy=ip_data.get("is_proxy", False),
        is_vpn=ip_data.get("is_vpn", False),
        is_tor=ip_data.get("is_tor", False),
        is_datacenter=ip_data.get("is_datacenter", False),
        risk_score=risk_score,
        event_metadata=event.metadata,
        correlation_id=correlation.generate_correlation_id(),
    )
    db.add(stream_event)
    await db.flush()

    if risk_score >= 50.0:
        attack_type_map = {
            "viewer_join": AttackType.VIEWBOT,
            "follow": AttackType.FOLLOWBOT,
            "chat_message": AttackType.SPAM,
        }
        attack_type = attack_type_map.get(event.event_type, AttackType.COORDINATED)
        attack = await correlation.create_attack_record(
            stream_id=stream.id,
            attack_type=attack_type,
            risk_score=risk_score,
            confidence=ip_result.confidence if ip_result else 0.5,
            evidence={"event_id": str(stream_event.id), **(ip_result.evidence if ip_result else {})},
            source_ips=[event.ip_address] if event.ip_address else [],
            fingerprints=[event.fingerprint_hash] if event.fingerprint_hash else [],
            correlation_id=stream_event.correlation_id,
        )
        await correlation.create_alert(
            tenant_id=current_user.tenant_id,
            attack=attack,
            title=f"Threat detected: {attack_type.value}",
            message=f"Risk score {risk_score:.1f} on stream {stream.channel_name}",
        )

        if risk_score >= 70.0:
            mitigation = MitigationService(db)
            targets = []
            if event.platform_user_id:
                targets.append({"type": "user", "value": event.platform_user_id})
            if event.ip_address:
                targets.append({"type": "ip", "value": event.ip_address})
            if event.fingerprint_hash:
                targets.append({"type": "fingerprint", "value": event.fingerprint_hash})
            await mitigation.progressive_mitigation(
                stream_id=stream.id,
                tenant_id=current_user.tenant_id,
                attack_id=attack.id,
                risk_score=risk_score,
                threat_type=attack_type.value,
                targets=targets,
                evidence=attack.evidence,
            )

    return {"event_id": str(stream_event.id), "risk_score": risk_score}


@router.get("/{stream_id}/viewers", response_model=List[ViewerSessionResponse])
async def list_viewers(
    stream_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await _get_stream(db, stream_id, current_user.tenant_id)
    result = await db.execute(
        select(ViewerSession).where(
            ViewerSession.stream_id == stream_id,
            ViewerSession.is_active == True,
        ).order_by(ViewerSession.risk_score.desc())
    )
    return result.scalars().all()


@router.get("/dashboard/stats", response_model=DashboardStats)
async def dashboard_stats(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user.tenant_id
    streams_result = await db.execute(
        select(Stream.id).where(Stream.tenant_id == tenant_id)
    )
    stream_ids = [r[0] for r in streams_result.all()]

    if not stream_ids:
        return DashboardStats(
            active_attacks=0, total_alerts=0, blocked_ips=0,
            suspected_bots=0, live_viewers=0, risk_score_avg=0.0,
            attacks_last_24h=0, mitigations_applied=0,
        )

    attacks = await db.execute(
        select(func.count(Attack.id)).where(
            Attack.stream_id.in_(stream_ids),
            Attack.status == "active",
        )
    )
    alerts = await db.execute(
        select(func.count(Alert.id)).where(
            Alert.tenant_id == tenant_id,
            Alert.status == "open",
        )
    )
    blocked = await db.execute(
        select(func.count(IPReputation.id)).where(IPReputation.is_blocked == True)
    )
    bots = await db.execute(
        select(func.count(ViewerSession.id)).where(
            ViewerSession.stream_id.in_(stream_ids),
            ViewerSession.is_suspected_bot == True,
            ViewerSession.is_active == True,
        )
    )
    viewers = await db.execute(
        select(func.count(ViewerSession.id)).where(
            ViewerSession.stream_id.in_(stream_ids),
            ViewerSession.is_active == True,
        )
    )
    avg_risk = await db.execute(
        select(func.avg(ViewerSession.risk_score)).where(
            ViewerSession.stream_id.in_(stream_ids),
            ViewerSession.is_active == True,
        )
    )

    return DashboardStats(
        active_attacks=attacks.scalar() or 0,
        total_alerts=alerts.scalar() or 0,
        blocked_ips=blocked.scalar() or 0,
        suspected_bots=bots.scalar() or 0,
        live_viewers=viewers.scalar() or 0,
        risk_score_avg=float(avg_risk.scalar() or 0),
        attacks_last_24h=attacks.scalar() or 0,
        mitigations_applied=0,
    )


async def _get_stream(db: AsyncSession, stream_id: UUID, tenant_id: UUID) -> Stream:
    result = await db.execute(
        select(Stream).where(Stream.id == stream_id, Stream.tenant_id == tenant_id)
    )
    stream = result.scalar_one_or_none()
    if not stream:
        raise NotFoundError("Stream")
    return stream
