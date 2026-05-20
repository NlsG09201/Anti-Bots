"""API de threat intelligence (VPN, proxy, TOR, datacenter, botnets)."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AnalystUser, get_db
from app.services.threat_intel import ThreatIntelAnalyzer

router = APIRouter(prefix="/threat-intel", tags=["Threat Intelligence"])


class ThreatIntelBatchRequest(BaseModel):
    ip_addresses: List[str] = Field(..., min_length=1, max_length=50)


@router.get("/analyze")
async def analyze_ip_threat(
    ip_address: str = Query(..., min_length=7, max_length=45),
    force_refresh: bool = Query(False),
    current_user: AnalystUser = None,
    db: AsyncSession = Depends(get_db),
):
    analyzer = ThreatIntelAnalyzer(db)
    report = await analyzer.analyze(ip_address, force_refresh=force_refresh)
    return report.to_dict()


@router.post("/analyze/batch")
async def analyze_ip_batch(
    body: ThreatIntelBatchRequest,
    force_refresh: bool = Query(False),
    current_user: AnalystUser = None,
    db: AsyncSession = Depends(get_db),
):
    analyzer = ThreatIntelAnalyzer(db)
    reports = await analyzer.analyze_batch(body.ip_addresses, force_refresh=force_refresh)
    return {"results": [r.to_dict() for r in reports], "count": len(reports)}
