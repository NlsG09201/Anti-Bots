from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AnalystUser, CurrentUser
from app.api.v1.schemas import (
    AdvancedFingerprintResponse,
    AdvancedFingerprintSubmit,
    FingerprintResponse,
    FingerprintSubmit,
)
from app.infrastructure.database.session import get_db
from app.services.detection.engine import BotDetectionEngine
from app.services.detection.fingerprint_service import analyze_fingerprint_payload
from app.infrastructure.security.client_ip import resolve_client_ip
from app.infrastructure.security.ip_analysis import analyze_client_ip

router = APIRouter(prefix="/detection", tags=["Detection"])
engine = BotDetectionEngine()


@router.post("/fingerprint", response_model=FingerprintResponse)
async def submit_fingerprint(
    data: FingerprintSubmit,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    client_ip, ip_meta = resolve_client_ip(request)
    advanced = await analyze_fingerprint_payload(
        db,
        data.model_dump(exclude_none=True),
        server_ip=client_ip if client_ip != "unknown" else None,
        persist=True,
    )
    if client_ip and client_ip != "unknown":
        ip_intel = await analyze_client_ip(
            db, client_ip, spoof_risk=bool(ip_meta.get("xff_spoof_risk"))
        )
        advanced.risk_score = min(
            100.0,
            max(advanced.risk_score, ip_intel.get("risk_score", 0)),
        )
        for flag in ip_intel.get("flags", []):
            if flag not in advanced.automation_flags:
                advanced.automation_flags.append(flag)

    await db.flush()
    return FingerprintResponse(
        hash=advanced.fingerprint_hash,
        risk_score=advanced.risk_score,
        is_headless=advanced.is_headless,
        is_blocked=advanced.is_blocked,
        automation_flags=advanced.automation_flags,
    )


@router.post("/fingerprint/advanced", response_model=AdvancedFingerprintResponse)
async def submit_advanced_fingerprint(
    data: AdvancedFingerprintSubmit,
    request: Request,
    current_user: AnalystUser,
    db: AsyncSession = Depends(get_db),
):
    client_ip, ip_meta = resolve_client_ip(request)
    stream_uuid = None
    if data.stream_id:
        try:
            stream_uuid = UUID(data.stream_id)
        except ValueError:
            stream_uuid = None

    result = await analyze_fingerprint_payload(
        db,
        data.model_dump(exclude_none=True),
        tenant_id=current_user.tenant_id,
        server_ip=client_ip if client_ip != "unknown" else None,
        persist=True,
        stream_id=stream_uuid,
    )
    if client_ip and client_ip != "unknown":
        ip_intel = await analyze_client_ip(
            db, client_ip, spoof_risk=bool(ip_meta.get("xff_spoof_risk"))
        )
        result.risk_score = min(
            100.0,
            max(result.risk_score, ip_intel.get("risk_score", 0)),
        )
    await db.flush()
    return result


@router.post("/analyze-ip")
async def analyze_ip(
    ip_address: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    from app.services.threat_intel import ThreatIntelAnalyzer

    report = await ThreatIntelAnalyzer(db).analyze(ip_address)
    return report.to_dict()


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
