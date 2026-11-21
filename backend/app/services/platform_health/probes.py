"""Lightweight integration probes for Kick / YouTube / TikTok."""

from __future__ import annotations

import time
from typing import List

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.platform_health.circuit_breaker import get_circuit_breaker
from app.domain.platform_health.schemas import IntegrationProbeResult
from app.domain.platform_health.sanitization import sanitize_diagnostic

logger = get_logger(__name__)
settings = get_settings()


async def probe_kick_api() -> IntegrationProbeResult:
    cb = get_circuit_breaker("kick")
    if not cb.allow_request():
        return IntegrationProbeResult(
            platform="kick",
            ok=False,
            circuit_state=cb.state,
            message=f"circuit open: {cb.last_error or 'recent requests failed'}",
        )
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                "https://api.kick.com/swagger/index.html",
                headers={"Accept": "application/json"},
            )
        ms = (time.perf_counter() - t0) * 1000.0
        ok = r.status_code == 200
        if ok:
            cb.record_success()
        else:
            cb.record_failure(f"http_{r.status_code}")
        return IntegrationProbeResult(
            platform="kick",
            ok=ok,
            latency_ms=round(ms, 2),
            circuit_state=cb.state,
            message=f"http_{r.status_code}",
        )
    except Exception as exc:
        detail = sanitize_diagnostic(str(exc), limit=120)
        cb.record_failure(detail)
        return IntegrationProbeResult(
            platform="kick",
            ok=False,
            circuit_state=cb.state,
            message=detail,
        )


async def probe_youtube_api() -> IntegrationProbeResult:
    cb = get_circuit_breaker("youtube")
    if not settings.youtube_api_key:
        return IntegrationProbeResult(
            platform="youtube",
            ok=False,
            circuit_state=cb.state,
            message="YOUTUBE_API_KEY missing",
        )
    if not cb.allow_request():
        return IntegrationProbeResult(
            platform="youtube",
            ok=False,
            circuit_state=cb.state,
            message=f"circuit open: {cb.last_error or 'recent requests failed'}",
        )
    t0 = time.perf_counter()
    try:
        from app.integrations.youtube.client import YouTubeLiveClient

        client = YouTubeLiveClient()
        await client.search_live_by_channel("GoogleDevelopers")
        ms = (time.perf_counter() - t0) * 1000.0
        cb.record_success()
        return IntegrationProbeResult(
            platform="youtube",
            ok=True,
            latency_ms=round(ms, 2),
            circuit_state=cb.state,
            message="ok",
        )
    except Exception as exc:
        detail = sanitize_diagnostic(str(exc), limit=120)
        cb.record_failure(detail)
        return IntegrationProbeResult(
            platform="youtube",
            ok=False,
            circuit_state=cb.state,
            message=detail,
        )


async def probe_tiktok_api() -> IntegrationProbeResult:
    cb = get_circuit_breaker("tiktok")
    return IntegrationProbeResult(
        platform="tiktok",
        ok=False,
        available=False,
        circuit_state=cb.state,
        message="Official live API unavailable",
    )


async def run_all_integration_probes() -> List[IntegrationProbeResult]:
    results = []
    for fn in (probe_kick_api, probe_youtube_api, probe_tiktok_api):
        try:
            results.append(await fn())
        except Exception as exc:
            logger.warning("integration_probe_failed", error=str(exc)[:120])
    return results
