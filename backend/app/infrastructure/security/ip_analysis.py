"""Análisis de IP: proxy, VPN, TOR, ASN y reputación (capa sobre ReputationService)."""

from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.detection.engine import BotDetectionEngine
from app.services.reputation.service import ReputationService

logger = get_logger(__name__)
settings = get_settings()
_engine = BotDetectionEngine()


async def analyze_client_ip(
    db: AsyncSession,
    ip_address: str,
    *,
    spoof_risk: bool = False,
) -> Dict[str, Any]:
    """
    Enriquece IP y devuelve score unificado + flags ASN/proxy/VPN.
    """
    if not ip_address or ip_address == "unknown":
        return {
            "ip_address": ip_address,
            "risk_score": 0.0,
            "is_threat": False,
            "flags": ["invalid_ip"],
        }

    reputation_svc = ReputationService(db)
    enrichment = await reputation_svc.enrich_ip(ip_address)
    detection = _engine.analyze_ip(enrichment)

    flags: list[str] = list(detection.evidence.get("checks", []))
    score = detection.risk_score

    if spoof_risk:
        flags.append("ip_spoof_risk")
        score = min(100.0, score + 20.0)

    asn = enrichment.get("asn")
    if asn:
        asn_str = str(asn).upper()
        for keyword in settings.security_blocked_asn_keywords_list:
            if keyword and keyword in asn_str:
                flags.append(f"blocked_asn:{keyword}")
                score = min(100.0, score + 25.0)

    if enrichment.get("is_tor"):
        flags.append("tor_exit")
    if enrichment.get("is_vpn"):
        flags.append("vpn")
    if enrichment.get("is_proxy"):
        flags.append("proxy")
    if enrichment.get("is_datacenter"):
        flags.append("datacenter")

    geo = enrichment.get("geo") or {}
    country = enrichment.get("country_code") or geo.get("country_code")
    if country and country.upper() in settings.security_blocked_countries_list:
        flags.append(f"blocked_country:{country}")
        score = min(100.0, score + 15.0)

    return {
        "ip_address": ip_address,
        "risk_score": round(score, 2),
        "is_threat": score >= 45.0,
        "threat_type": detection.threat_type,
        "recommended_action": detection.recommended_action,
        "flags": flags,
        "enrichment": enrichment,
        "asn": asn,
        "country_code": country,
        "is_proxy": enrichment.get("is_proxy", False),
        "is_vpn": enrichment.get("is_vpn", False),
        "is_tor": enrichment.get("is_tor", False),
        "is_datacenter": enrichment.get("is_datacenter", False),
    }
