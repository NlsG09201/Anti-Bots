"""Persistencia y correlación de fingerprinting avanzado."""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import AdvancedFingerprintResponse, AdvancedFingerprintSubmit
from app.infrastructure.database.models import Fingerprint, Stream
from app.services.dashboard.metrics import get_tenant_stream_ids
from app.services.detection.advanced_fingerprint import AdvancedFingerprintEngine
from app.services.detection.session_correlation import FingerprintSessionCorrelator

_advanced = AdvancedFingerprintEngine()
_correlator = FingerprintSessionCorrelator()


async def _persist_fingerprint(
    db: AsyncSession,
    *,
    fp_hash: str,
    data: AdvancedFingerprintSubmit,
    result,
) -> Fingerprint:
    row = await db.execute(select(Fingerprint).where(Fingerprint.hash == fp_hash))
    fingerprint = row.scalar_one_or_none()
    flags = list(result.automation_flags)

    meta = {
        "signals": result.signals,
        "device_hash": result.device_hash,
        "session_key": result.session_key,
        "trust_score": result.trust_score,
        "confidence_score": result.confidence_score,
    }

    if fingerprint:
        fingerprint.occurrence_count += 1
        fingerprint.risk_score = max(fingerprint.risk_score, result.risk_score)
        fingerprint.is_headless = fingerprint.is_headless or result.is_headless
        fingerprint.is_selenium = fingerprint.is_selenium or data.selenium
        fingerprint.is_puppeteer = fingerprint.is_puppeteer or data.puppeteer
        fingerprint.is_playwright = fingerprint.is_playwright or data.playwright
        existing = set(fingerprint.automation_flags or [])
        fingerprint.automation_flags = list(existing | set(flags))
        fingerprint.fp_metadata = {**(fingerprint.fp_metadata or {}), **meta}
        if result.risk_score >= 85.0:
            fingerprint.is_blocked = True
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
            is_headless=result.is_headless,
            is_selenium=data.selenium,
            is_puppeteer=data.puppeteer,
            is_playwright=data.playwright,
            automation_flags=flags,
            risk_score=result.risk_score,
            is_blocked=result.risk_score >= 85.0,
            fp_metadata=meta,
        )
        db.add(fingerprint)

    await db.flush()
    return fingerprint


async def analyze_fingerprint_payload(
    db: AsyncSession,
    data: dict,
    *,
    tenant_id: Optional[UUID] = None,
    server_ip: Optional[str] = None,
    persist: bool = True,
    stream_id: Optional[UUID] = None,
) -> AdvancedFingerprintResponse:
    prior: list[str] = []
    device_hash = _advanced.compute_device_hash(data)
    if tenant_id:
        prior = await _correlator.get_linked_sessions(str(tenant_id), device_hash)

    result = _advanced.analyze(data, server_ip=server_ip, prior_session_keys=prior)

    correlation: dict = {}
    if tenant_id:
        correlation = await _correlator.register_session(
            tenant_id=str(tenant_id),
            device_hash=result.device_hash,
            session_key=result.session_key,
            fingerprint_hash=result.fingerprint_hash,
            risk_score=result.risk_score,
        )

    db_corr: dict = {}
    if tenant_id and persist:
        stream_ids = await get_tenant_stream_ids(db, tenant_id)
        if stream_id:
            stream = await db.get(Stream, stream_id)
            if stream and stream.tenant_id == tenant_id:
                stream_ids = [stream_id]
        db_corr = await _correlator.correlate_from_db(
            db,
            fingerprint_hash=result.fingerprint_hash,
            stream_ids=stream_ids,
        )

    is_blocked = result.risk_score >= 85.0
    if persist:
        fields = set(AdvancedFingerprintSubmit.model_fields.keys())
        submit = AdvancedFingerprintSubmit(
            **{k: v for k, v in data.items() if k in fields}
        )
        fp_row = await _persist_fingerprint(
            db,
            fp_hash=result.fingerprint_hash,
            data=submit,
            result=result,
        )
        is_blocked = fp_row.is_blocked

    return AdvancedFingerprintResponse(
        device_hash=result.device_hash,
        fingerprint_hash=result.fingerprint_hash,
        session_key=result.session_key,
        trust_score=result.trust_score,
        risk_score=result.risk_score,
        confidence_score=result.confidence_score,
        is_automation=result.is_automation,
        is_headless=result.is_headless,
        is_blocked=is_blocked,
        automation_flags=result.automation_flags,
        signals=result.signals,
        correlated_sessions=correlation.get("correlated_sessions", []),
        correlation_strength=correlation.get("correlation_strength", 0.0),
        correlation={**correlation, "database": db_corr},
        recommended_action=result.recommended_action,
    )
