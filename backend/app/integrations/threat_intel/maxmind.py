"""MaxMind GeoIP2 — Enhanced geolocation and threat detection."""

from typing import Any, Dict, Optional

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_readers = {}


def _get_reader(db_type: str = "city"):
    """Get or initialize GeoIP2 reader."""
    global _readers

    if db_type in _readers:
        return _readers[db_type]

    try:
        import geoip2.database

        if db_type == "city":
            path = settings.maxmind_city_db_path
        elif db_type == "asn":
            path = settings.maxmind_asn_db_path
        else:
            return None

        if not path:
            return None

        reader = geoip2.database.Reader(path)
        _readers[db_type] = reader
        return reader
    except Exception as e:
        logger.warning(f"maxmind_{db_type}_reader_init_failed", error=str(e))
        return None


class MaxMindGeoIP2Service:
    """MaxMind GeoIP2 integration for detailed IP analysis."""

    @staticmethod
    def city_lookup(ip_address: str) -> Optional[Dict[str, Any]]:
        """Get detailed city-level geolocation."""
        reader = _get_reader("city")
        if not reader:
            return None

        try:
            response = reader.city(ip_address)
            return {
                "source": "maxmind_city",
                "country_code": response.country.iso_code,
                "country_name": response.country.name,
                "is_in_eu": response.country.is_in_european_union,
                "region": response.subdivisions[0].iso_code if response.subdivisions else None,
                "region_name": response.subdivisions[0].name if response.subdivisions else None,
                "city": response.city.name,
                "latitude": response.location.latitude,
                "longitude": response.location.longitude,
                "accuracy_radius_km": response.location.accuracy_radius,
                "timezone": response.location.time_zone,
                "is_anonymous_vpn": response.traits.is_anonymous_vpn,
                "is_satellite_provider": response.traits.is_satellite_provider,
                "is_residential_proxy": response.traits.is_residential_proxy,
                "is_public_proxy": response.traits.is_public_proxy,
                "is_tor_exit_node": response.traits.is_tor_exit_node,
                "is_datacenter_proxy": response.traits.is_datacenter_proxy,
                "threat_categories": MaxMindGeoIP2Service._extract_threats(response),
            }
        except Exception as e:
            logger.debug("maxmind_city_lookup_failed", ip=ip_address, error=str(e))
            return None

    @staticmethod
    def asn_lookup(ip_address: str) -> Optional[Dict[str, Any]]:
        """Get ASN and autonomous system information."""
        reader = _get_reader("asn")
        if not reader:
            return None

        try:
            response = reader.asn(ip_address)
            return {
                "source": "maxmind_asn",
                "asn_number": response.autonomous_system_number,
                "asn_organization": response.autonomous_system_organization,
            }
        except Exception as e:
            logger.debug("maxmind_asn_lookup_failed", ip=ip_address, error=str(e))
            return None

    @staticmethod
    def _extract_threats(response) -> list:
        """Extract threat categories from MaxMind response."""
        threats = []
        if response.traits.is_anonymous_vpn:
            threats.append("vpn")
        if response.traits.is_public_proxy or response.traits.is_residential_proxy:
            threats.append("proxy")
        if response.traits.is_tor_exit_node:
            threats.append("tor")
        if response.traits.is_datacenter_proxy:
            threats.append("datacenter")
        if response.traits.is_satellite_provider:
            threats.append("satellite")
        return threats

    @staticmethod
    async def full_check(ip_address: str) -> Optional[Dict[str, Any]]:
        """Get combined city and ASN information."""
        city = MaxMindGeoIP2Service.city_lookup(ip_address)
        asn = MaxMindGeoIP2Service.asn_lookup(ip_address)

        if not city:
            return None

        result = city.copy()
        if asn:
            result.update(asn)

        return result
