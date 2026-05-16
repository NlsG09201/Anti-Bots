from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AnalystUser, CurrentUser
from app.api.v1.schemas import AttackResponse, AlertResponse, BanCreate, BanResponse, MitigationRequest
from app.core.exceptions import NotFoundError
from app.infrastructure.database.models import Alert, Attack, Ban, Stream
from app.infrastructure.database.session import get_db
from app.services.mitigation.service import MitigationService
from app.services.correlation.service import CorrelationService

router = APIRouter(tags=["Attacks & Security"])


@router.get("/attacks", response_model=List[AttackResponse])
async def list_attacks(
    current_user: CurrentUser,
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Attack)
        .join(Stream, Attack.stream_id == Stream.id)
        .where(Stream.tenant_id == current_user.tenant_id)
        .order_by(Attack.created_at.desc())
        .limit(100)
    )
    if status:
        query = query.where(Attack.status == status)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/attacks/{attack_id}", response_model=AttackResponse)
async def get_attack(
    attack_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Attack)
        .join(Stream, Attack.stream_id == Stream.id)
        .where(Attack.id == attack_id, Stream.tenant_id == current_user.tenant_id)
    )
    attack = result.scalar_one_or_none()
    if not attack:
        raise NotFoundError("Attack")
    return attack


@router.post("/attacks/{attack_id}/mitigate")
async def mitigate_attack(
    attack_id: UUID,
    data: MitigationRequest,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Attack)
        .join(Stream, Attack.stream_id == Stream.id)
        .where(Attack.id == attack_id, Stream.tenant_id == current_user.tenant_id)
    )
    attack = result.scalar_one_or_none()
    if not attack:
        raise NotFoundError("Attack")

    mitigation = MitigationService(db)
    action = data.action or mitigation.determine_action(attack.risk_score, attack.attack_type.value)
    bans = await mitigation.apply_mitigation(
        stream_id=attack.stream_id,
        tenant_id=current_user.tenant_id,
        attack_id=attack.id,
        action=action,
        targets=data.targets,
        evidence=attack.evidence,
        duration_hours=data.duration_hours,
    )
    return {"action": action.value, "bans_created": len(bans)}


@router.get("/alerts", response_model=List[AlertResponse])
async def list_alerts(
    current_user: CurrentUser,
    status: Optional[str] = Query("open"),
    db: AsyncSession = Depends(get_db),
):
    query = select(Alert).where(Alert.tenant_id == current_user.tenant_id)
    if status:
        query = query.where(Alert.status == status)
    result = await db.execute(query.order_by(Alert.created_at.desc()).limit(100))
    return result.scalars().all()


@router.patch("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.tenant_id == current_user.tenant_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise NotFoundError("Alert")
    alert.status = "acknowledged"
    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledged_by = current_user.id
    await db.flush()
    return {"status": "acknowledged"}


@router.get("/bans", response_model=List[BanResponse])
async def list_bans(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Ban).where(
            Ban.tenant_id == current_user.tenant_id,
            Ban.is_active == True,
        ).order_by(Ban.created_at.desc()).limit(100)
    )
    return result.scalars().all()


@router.post("/bans", response_model=BanResponse)
async def create_ban(
    data: BanCreate,
    stream_id: UUID,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timedelta, timezone
    expires_at = None
    if data.duration_hours:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=data.duration_hours)

    ban = Ban(
        stream_id=stream_id,
        tenant_id=current_user.tenant_id,
        target_type=data.target_type,
        target_value=data.target_value,
        reason=data.reason,
        ban_type=data.ban_type,
        expires_at=expires_at,
        created_by=current_user.id,
    )
    db.add(ban)
    await db.flush()
    return ban


@router.delete("/bans/{ban_id}")
async def revoke_ban(
    ban_id: UUID,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
):
    mitigation = MitigationService(db)
    success = await mitigation.revoke_ban(ban_id)
    if not success:
        raise NotFoundError("Ban")
    return {"revoked": True}


@router.get("/fingerprints")
async def list_fingerprints(
    current_user: CurrentUser,
    min_risk: float = Query(50.0),
    db: AsyncSession = Depends(get_db),
):
    from app.infrastructure.database.models import Fingerprint
    result = await db.execute(
        select(Fingerprint)
        .where(Fingerprint.risk_score >= min_risk)
        .order_by(Fingerprint.risk_score.desc())
        .limit(100)
    )
    return [
        {
            "hash": fp.hash,
            "risk_score": fp.risk_score,
            "is_headless": fp.is_headless,
            "is_blocked": fp.is_blocked,
            "occurrence_count": fp.occurrence_count,
            "automation_flags": fp.automation_flags,
        }
        for fp in result.scalars().all()
    ]


@router.get("/ips")
async def list_suspicious_ips(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    from app.infrastructure.database.models import IPReputation
    result = await db.execute(
        select(IPReputation)
        .where(IPReputation.reputation_score < 40)
        .order_by(IPReputation.reputation_score)
        .limit(100)
    )
    return [
        {
            "ip_address": ip.ip_address,
            "reputation_score": ip.reputation_score,
            "is_proxy": ip.is_proxy,
            "is_vpn": ip.is_vpn,
            "is_tor": ip.is_tor,
            "is_datacenter": ip.is_datacenter,
            "is_blocked": ip.is_blocked,
            "country_code": ip.country_code,
        }
        for ip in result.scalars().all()
    ]
