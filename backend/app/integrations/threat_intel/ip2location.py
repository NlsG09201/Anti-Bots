"""IP2Location — Alternative IP geolocation and threat detection."""

from typing import Any, Dict, Optional

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_reader = None


def _get_reader():
    """Initialize IP2Location reader."""
    global _reader

    if _reader is not None:
        return _reader

    try:
        import IP2Location

        db_path = settings.ip2location_db_path
        if not db_path:
            return None

        _reader = IP2Location.IP2Location(db_path)
        return _reader
    except Exception as e:
        logger.warning("ip2location_reader_init_failed", error=str(e))
        return None


class IP2LocationService:
    """IP2Location integration for geolocation and threat detection."""

    @staticmethod
    def lookup(ip_address: str) -> Optional[Dict[str, Any]]:
        """Get IP geolocation from IP2Location database."""
        reader = _get_reader()
        if not reader:
            return None

        try:
            result = reader.get_all(ip_address)

            if not result or result.status == "INVALID_IP":
                return None

            return {
                "source": "ip2location",
                "country_code": result.country_short,
                "country_name": result.country_long,
                "region": result.region,
                "city": result.city,
                "latitude": float(result.latitude) if result.latitude else None,
                "longitude": float(result.longitude) if result.longitude else None,
                "timezone": result.timezone,
                "isp": result.isp,
                "domain": result.domain,
                "netspeed": result.netspeed,
                "usage_type": result.usage_type,
                "asn": result.asn,
                "asn_organization": result.as_name,
                "is_proxy": IP2LocationService._is_proxy(result),
                "proxy_type": result.proxy_type if hasattr(result, "proxy_type") else None,
            }
        except Exception as e:
            logger.warning("ip2location_lookup_failed", ip=ip_address, error=str(e))
            return None

    @staticmethod
    def _is_proxy(result) -> bool:
        """Check if IP is a proxy based on IP2Location result."""
        proxy_type = getattr(result, "proxy_type", "").upper()
        return proxy_type in ("VPN", "TOR", "PUB", "DCH", "RES", "SES")
