"""Análisis de IP: proxy, VPN, TOR, ASN y reputación (capa sobre ReputationService)."""

from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.threat_intel import ThreatIntelAnalyzer

logger = get_logger(__name__)
settings = get_settings()


async def analyze_client_ip(
    db: AsyncSession,
    ip_address: str,
    *,
    spoof_risk: bool = False,
) -> Dict[str, Any]:
    """
    Enriquece IP y devuelve score unificado + flags ASN/proxy/VPN/TOR/botnet.
    """
    if not ip_address or ip_address == "unknown":
        return {
            "ip_address": ip_address,
            "risk_score": 0.0,
            "is_threat": False,
            "flags": ["invalid_ip"],
        }

    report = await ThreatIntelAnalyzer(db).analyze(ip_address)
    flags: list[str] = list(report.flags)
    score = report.risk_score

    if spoof_risk:
        flags.append("ip_spoof_risk")
        score = min(100.0, score + 20.0)

    country = report.geo.country_code if report.geo else None
    if country and country.upper() in settings.security_blocked_countries_list:
        flags.append(f"blocked_country:{country}")
        score = min(100.0, score + 15.0)

    enrichment = report.to_dict()

    return {
        "ip_address": ip_address,
        "risk_score": round(score, 2),
        "is_threat": score >= 45.0,
        "threat_type": "malicious_ip" if report.is_malicious else "none",
        "recommended_action": report.recommended_action,
        "flags": list(dict.fromkeys(flags)),
        "enrichment": enrichment,
        "asn": report.asn.number if report.asn else None,
        "asn_organization": report.asn.organization if report.asn else None,
        "country_code": country,
        "is_proxy": report.is_proxy,
        "is_vpn": report.is_vpn,
        "is_tor": report.is_tor,
        "is_datacenter": report.is_datacenter,
        "is_residential_proxy": report.is_residential_proxy,
        "is_botnet": report.is_botnet,
        "reputation_score": report.reputation_score,
        "confidence": report.confidence,
    }
