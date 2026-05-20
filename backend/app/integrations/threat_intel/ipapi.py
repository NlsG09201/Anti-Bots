"""Fallback ip-api.com (sin API key; límite 45 req/min)."""

from typing import Any, Dict, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.threat_intel.asn import parse_asn_field

logger = get_logger(__name__)
settings = get_settings()


class IPApiClient:
    """https://ip-api.com/docs/api:json"""

    def __init__(self, enabled: Optional[bool] = None):
        self._enabled = (
            enabled if enabled is not None else settings.threat_intel_ipapi_enabled
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def check(self, ip_address: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        try:
            fields = (
                "status,country,countryCode,regionName,city,lat,lon,timezone,"
                "isp,org,as,asname,reverse,mobile,proxy,hosting"
            )
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(
                    f"http://ip-api.com/json/{ip_address}",
                    params={"fields": fields},
                )
                if response.status_code != 200:
                    return None
                data = response.json()
                if data.get("status") != "success":
                    return None

                asn_num, _ = parse_asn_field(data.get("as"))
                return {
                    "source": "ip-api",
                    "country_code": data.get("countryCode"),
                    "country_name": data.get("country"),
                    "city": data.get("city"),
                    "region": data.get("regionName"),
                    "latitude": data.get("lat"),
                    "longitude": data.get("lon"),
                    "timezone": data.get("timezone"),
                    "asn_number": asn_num,
                    "asn_organization": data.get("org") or data.get("asname"),
                    "is_proxy": bool(data.get("proxy", False)),
                    "is_datacenter": bool(data.get("hosting", False)),
                    "is_mobile": bool(data.get("mobile", False)),
                    "isp": data.get("isp"),
                }
        except Exception as exc:
            logger.warning("ipapi_check_failed", ip=ip_address, error=str(exc))
            return None
