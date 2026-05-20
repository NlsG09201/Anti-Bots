"""Cliente AbuseIPDB — reputación, TOR, reportes de abuso."""

from typing import Any, Dict, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.threat_intel.asn import parse_asn_field

logger = get_logger(__name__)
settings = get_settings()


class AbuseIPDBClient:
    BASE_URL = "https://api.abuseipdb.com/api/v2/check"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.abuseipdb_api_key

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def check(self, ip_address: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.BASE_URL,
                    headers={"Key": self.api_key, "Accept": "application/json"},
                    params={
                        "ipAddress": ip_address,
                        "maxAgeInDays": 90,
                        "verbose": True,
                    },
                )
                if response.status_code != 200:
                    return None
                data = response.json().get("data", {})
                abuse_score = int(data.get("abuseConfidenceScore", 0))
                isp = data.get("isp") or data.get("domain") or ""
                asn_num, asn_org = parse_asn_field(data.get("asn") or isp)
                usage = (data.get("usageType") or "").lower()
                categories = []
                if data.get("isTor"):
                    categories.append("tor")
                if "hosting" in usage or "datacenter" in usage:
                    categories.append("datacenter")
                if abuse_score >= 75:
                    categories.append("abuse_high")

                return {
                    "source": "abuseipdb",
                    "abuse_reports": int(data.get("totalReports", 0)),
                    "abuse_confidence": abuse_score,
                    "reputation_score": max(0, 100 - abuse_score),
                    "is_tor": bool(data.get("isTor", False)),
                    "is_datacenter": "hosting" in usage or "datacenter" in usage,
                    "country_code": data.get("countryCode"),
                    "asn_number": asn_num,
                    "asn_organization": asn_org or isp,
                    "usage_type": data.get("usageType"),
                    "threat_categories": categories,
                    "is_whitelisted": bool(data.get("isWhitelisted", False)),
                }
        except Exception as exc:
            logger.warning("abuseipdb_check_failed", ip=ip_address, error=str(exc))
            return None
