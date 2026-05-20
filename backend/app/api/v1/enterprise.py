"""Enterprise platform APIs: multi-platform sync, anomaly, network policy."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AnalystUser, get_db
from app.infrastructure.database.models import Stream
from app.infrastructure.security.ip_analysis import analyze_client_ip
from app.services.detection.anomaly_intelligence import AnomalyIntelligenceService
from app.services.platforms.registry import get_platform_adapter
from app.services.platforms.sync_service import PlatformSyncService
from app.services.security.network_policy import NetworkPolicyEngine

router = APIRouter(prefix="/enterprise", tags=["Enterprise"])


@router.get("/platforms")
async def list_platform_capabilities(_user: AnalystUser):
    """Supported platforms and adapter capabilities."""
    from app.infrastructure.database.models import Platform

    items = []
    for platform in (Platform.TWITCH, Platform.KICK, Platform.YOUTUBE):
        adapter = get_platform_adapter(platform)
        items.append({
            "platform": platform.value,
            "oauth": await adapter.supports_oauth(),
            "live_status": True,
            "viewer_sync": True,
        })
    return {"platforms": items}


@router.post("/streams/{stream_id}/sync/platform")
async def sync_platform_viewers(
    stream_id: UUID,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
):
    """Sync viewers via platform adapter (Twitch / Kick / YouTube)."""
    result = await db.execute(
        select(Stream).where(
            Stream.id == stream_id,
            Stream.tenant_id == current_user.tenant_id,
        )
    )
    stream = result.scalar_one_or_none()
    if not stream:
        raise HTTPException(status_code=404, detail="Stream not found")

    summary = await PlatformSyncService(db).sync_viewers(stream)
    await db.commit()
    return summary


@router.post("/network-policy/evaluate")
async def evaluate_network_policy(
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
    ip_address: Optional[str] = None,
    automation_detected: bool = False,
):
    """Evaluate VPN/proxy/TOR/datacenter policy for an IP."""
    intel = {}
    if ip_address:
        intel = await analyze_client_ip(db, ip_address)
    result = NetworkPolicyEngine().evaluate(
        ip_intel=intel.get("enrichment") or intel,
        automation_detected=automation_detected,
    )
    return result.to_dict()


@router.post("/streams/{stream_id}/anomaly/assess")
async def assess_stream_anomaly(
    stream_id: UUID,
    current_user: AnalystUser,
    joins_per_minute: float = 0,
    unique_ip_ratio: float = 1.0,
    proxy_ratio: float = 0,
    fingerprint_collision_ratio: float = 0,
    chat_participation_ratio: float = 0.5,
):
    """Score current behavioral window against stream baseline."""
    svc = AnomalyIntelligenceService()
    assessment = await svc.assess_window(
        str(stream_id),
        joins_per_minute=joins_per_minute,
        unique_ip_ratio=unique_ip_ratio,
        proxy_ratio=proxy_ratio,
        fingerprint_collision_ratio=fingerprint_collision_ratio,
        chat_participation_ratio=chat_participation_ratio,
    )
    return assessment.to_dict()
