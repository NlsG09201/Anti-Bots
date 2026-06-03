"""IPInfo API — IP reputation, VPN/Proxy detection, geolocation."""

from typing import Any, Dict, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class IPInfoClient:
    """IPInfo integration for comprehensive IP intelligence."""

    BASE_URL = "https://ipinfo.io"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.ipinfo_api_key

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def check(self, ip_address: str) -> Optional[Dict[str, Any]]:
        """Get IP information from IPInfo."""
        if not self.enabled:
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/{ip_address}/json",
                    params={"token": self.api_key},
                )
                if response.status_code != 200:
                    return None

                data = response.json()
                
                # Parse privacy detection if available
                privacy = data.get("privacy", {})
                is_vpn = bool(privacy.get("vpn", False))
                is_proxy = bool(privacy.get("proxy", False))
                is_tor = bool(privacy.get("tor", False))
                is_relay = bool(privacy.get("relay", False))

                # Parse hosting detection
                hosting = data.get("hosting", {})
                is_datacenter = bool(hosting.get("host", False))
                host_name = hosting.get("host", "")
                host_type = hosting.get("type", "")

                # Parse ASN
                asn_info = data.get("asn", {})
                asn_number = asn_info.get("asn", "").replace("AS", "")
                asn_org = asn_info.get("name", "")

                return {
                    "source": "ipinfo",
                    "country_code": data.get("country"),
                    "country_name": data.get("country_name", ""),
                    "region": data.get("region"),
                    "city": data.get("city"),
                    "latitude": float(data.get("latitude", 0)),
                    "longitude": float(data.get("longitude", 0)),
                    "timezone": data.get("timezone"),
                    "asn_number": asn_number,
                    "asn_organization": asn_org,
                    "is_vpn": is_vpn,
                    "is_proxy": is_proxy,
                    "is_tor": is_tor,
                    "is_relay": is_relay,
                    "is_datacenter": is_datacenter,
                    "host_name": host_name,
                    "host_type": host_type,
                    "company": data.get("company", {}).get("name", ""),
                    "isp": data.get("org", ""),
                    "threat_categories": self._extract_threats(
                        is_vpn, is_proxy, is_tor, is_datacenter
                    ),
                }
        except Exception as exc:
            logger.warning("ipinfo_check_failed", ip=ip_address, error=str(exc))
            return None

    @staticmethod
    def _extract_threats(is_vpn: bool, is_proxy: bool, is_tor: bool, is_datacenter: bool) -> list:
        """Extract threat categories from detection results."""
        threats = []
        if is_vpn:
            threats.append("vpn")
        if is_proxy:
            threats.append("proxy")
        if is_tor:
            threats.append("tor")
        if is_datacenter:
            threats.append("datacenter")
        return threats
