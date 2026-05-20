from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.api.v1.schemas import FingerprintResponse, FingerprintSubmit
from app.core.security import hash_fingerprint
from app.infrastructure.database.models import Fingerprint
from app.infrastructure.database.session import get_db
from app.services.detection.engine import BotDetectionEngine
from app.infrastructure.security.client_ip import resolve_client_ip
from app.infrastructure.security.ip_analysis import analyze_client_ip
from app.services.reputation.service import ReputationService

router = APIRouter(prefix="/detection", tags=["Detection"])
engine = BotDetectionEngine()


@router.post("/fingerprint", response_model=FingerprintResponse)
async def submit_fingerprint(
    data: FingerprintSubmit,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    fp_dict = data.model_dump()
    fp_hash = hash_fingerprint(fp_dict)

    result = await db.execute(select(Fingerprint).where(Fingerprint.hash == fp_hash))
    fingerprint = result.scalar_one_or_none()

    detection = engine.analyze_fingerprint(fp_dict)
    client_ip, ip_meta = resolve_client_ip(request)
    if client_ip and client_ip != "unknown":
        ip_intel = await analyze_client_ip(
            db, client_ip, spoof_risk=bool(ip_meta.get("xff_spoof_risk"))
        )
        detection.risk_score = min(
            100.0,
            max(detection.risk_score, ip_intel.get("risk_score", 0)),
        )
        for flag in ip_intel.get("flags", []):
            detection.evidence.setdefault("checks", []).append(flag)
    automation_flags = list(detection.evidence.get("checks", []))

    if fingerprint:
        fingerprint.occurrence_count += 1
        fingerprint.risk_score = max(fingerprint.risk_score, detection.risk_score)
        if detection.evidence.get("checks"):
            existing = set(fingerprint.automation_flags or [])
            fingerprint.automation_flags = list(existing | set(automation_flags))
    else:
        fingerprint = Fingerprint(
            hash=fp_hash,
            canvas_hash=data.canvas_hash,
            webgl_hash=data.webgl_hash,
            audio_hash=data.audio_hash,
            screen_resolution=data.screen_resolution,
            timezone=data.timezone,
            language=data.language,
            platform=data.platform,
            plugins=data.plugins,
            fonts=data.fonts,
            is_headless=detection.evidence.get("checks", []) != [],
            is_selenium=data.selenium,
            is_puppeteer=data.puppeteer,
            is_playwright=data.playwright,
            automation_flags=automation_flags,
            risk_score=detection.risk_score,
            fp_metadata=detection.evidence,
        )
        db.add(fingerprint)

    await db.flush()
    return FingerprintResponse(
        hash=fp_hash,
        risk_score=fingerprint.risk_score,
        is_headless=fingerprint.is_headless,
        is_blocked=fingerprint.is_blocked,
        automation_flags=fingerprint.automation_flags or [],
    )


@router.post("/analyze-ip")
async def analyze_ip(
    ip_address: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    reputation_svc = ReputationService(db)
    ip_data = await reputation_svc.enrich_ip(ip_address)
    result = engine.analyze_ip(ip_data)
    return {
        "ip_address": ip_address,
        "is_threat": result.is_threat,
        "threat_type": result.threat_type,
        "risk_score": result.risk_score,
        "confidence": result.confidence,
        "evidence": result.evidence,
        "recommended_action": result.recommended_action,
        "enrichment": ip_data,
    }


@router.post("/analyze-batch")
async def analyze_event_batch(
    stream_id: str,
    events: list,
    event_type: str = "viewer_join",
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    from app.services.detection.engine import EventBatch

    batch = EventBatch(events=events, stream_id=stream_id)
    results = []

    if event_type == "viewer_join":
        results.append(engine.analyze_viewbot_pattern(batch))
    elif event_type == "chat_message":
        results.append(engine.analyze_chat_spam(events))
    elif event_type == "follow":
        results.append(engine.analyze_follow_burst(events))

    combined_score, threat_type, action = engine.aggregate_risk(results)
    return {
        "combined_risk_score": combined_score,
        "threat_type": threat_type,
        "recommended_action": action,
        "individual_results": [
            {
                "is_threat": r.is_threat,
                "threat_type": r.threat_type,
                "risk_score": r.risk_score,
                "confidence": r.confidence,
                "evidence": r.evidence,
            }
            for r in results
        ],
    }
