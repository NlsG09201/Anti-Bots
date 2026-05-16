from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_reader = None


def _get_reader():
    global _reader
    if _reader is not None:
        return _reader

    db_path = Path(settings.geoip_database_path)
    if not db_path.exists():
        return None

    try:
        import geoip2.database
        _reader = geoip2.database.Reader(str(db_path))
        return _reader
    except Exception as e:
        logger.warning("geoip_reader_init_failed", error=str(e))
        return None


class GeoIPService:
    @staticmethod
    def lookup(ip_address: str) -> Optional[Dict[str, Any]]:
        reader = _get_reader()
        if not reader:
            return None

        try:
            response = reader.city(ip_address)
            return {
                "country_code": response.country.iso_code,
                "country_name": response.country.name,
                "city": response.city.name,
                "latitude": response.location.latitude,
                "longitude": response.location.longitude,
                "timezone": response.location.time_zone,
            }
        except Exception:
            return None
