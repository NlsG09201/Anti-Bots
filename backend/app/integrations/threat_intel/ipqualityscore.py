"""Cliente IPQualityScore — VPN, proxy, TOR, datacenter, residential, bots."""

from typing import Any, Dict, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.threat_intel.asn import parse_asn_field

logger = get_logger(__name__)
settings = get_settings()


class IPQualityScoreClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.ipqualityscore_api_key

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def check(self, ip_address: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                response = await client.get(
                    f"https://ipqualityscore.com/api/json/ip/{self.api_key}/{ip_address}",
                    params={
                        "strictness": 1,
                        "allow_public_access_points": True,
                        "fast": False,
                        "mobile": True,
                    },
                )
                if response.status_code != 200:
                    return None
                data = response.json()
                if not data.get("success"):
                    return None

                fraud_score = int(data.get("fraud_score", 0))
                is_proxy = bool(data.get("proxy", False))
                is_vpn = bool(data.get("vpn", False) or data.get("active_vpn", False))
                is_tor = bool(data.get("tor", False) or data.get("active_tor", False))
                is_hosting = bool(
                    data.get("host", False)
                    or data.get("hosting_provider", False)
                    or data.get("is_datacenter", False)
                )
                connection_type = (data.get("connection_type") or "").lower()
                is_residential_proxy = (
                    is_proxy
                    and not is_vpn
                    and not is_tor
                    and not is_hosting
                    and ("residential" in connection_type or connection_type == "")
                )
                bot_status = (data.get("bot_status") or "").lower()
                is_bot = bot_status in ("yes", "true", "known_bot") or bool(
                    data.get("is_crawler", False)
                )
                asn_num, asn_org = parse_asn_field(data.get("ASN") or data.get("asn"))

                categories = []
                if is_vpn:
                    categories.append("vpn")
                if is_proxy:
                    categories.append("proxy")
                if is_tor:
                    categories.append("tor")
                if is_hosting:
                    categories.append("datacenter")
                if is_residential_proxy:
                    categories.append("residential_proxy")
                if is_bot:
                    categories.append("bot")
                if data.get("recent_abuse"):
                    categories.append("recent_abuse")

                return {
                    "source": "ipqualityscore",
                    "reputation_score": max(0, 100 - fraud_score),
                    "fraud_score": fraud_score,
                    "is_proxy": is_proxy,
                    "is_vpn": is_vpn,
                    "is_tor": is_tor,
                    "is_datacenter": is_hosting,
                    "is_residential_proxy": is_residential_proxy,
                    "is_botnet": is_bot or (fraud_score >= 90 and data.get("recent_abuse")),
                    "country_code": data.get("country_code"),
                    "asn_number": asn_num,
                    "asn_organization": asn_org or data.get("organization"),
                    "connection_type": data.get("connection_type"),
                    "abuse_velocity": data.get("abuse_velocity"),
                    "threat_categories": categories,
                    "latitude": data.get("latitude"),
                    "longitude": data.get("longitude"),
                    "city": data.get("city"),
                    "region": data.get("region"),
                }
        except Exception as exc:
            logger.warning("ipqualityscore_check_failed", ip=ip_address, error=str(exc))
            return None
