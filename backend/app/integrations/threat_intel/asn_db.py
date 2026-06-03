"""ASN Database — Autonomous system and datacenter ASN detection."""

from typing import Any, Dict, Optional, Set

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import get_redis
import json

logger = get_logger(__name__)
settings = get_settings()

# Known datacenter ASNs
DATACENTER_ASNS: Set[str] = {
    "16509",  # AWS
    "14061",  # DigitalOcean
    "16276",  # OVH
    "12389",  # Rostelecom
    "8452",   # TeData
    "6939",   # Hurricane Electric
    "174",    # Cogent
    "3352",   # Telenor
    "12856",  # CARRIERTELECOM
    "39798",  # Psychz Networks
    "62904",  # Extenet
    "8473",   # Bahnhof
    "4134",   # China Unicom
    "4837",   # China Unicom
    "64512",  # PRIVATE
    "55836",  # BuyVM
    "399645", # IPXO
    "206453", # IPXO
    "137409", # IPXO
    "46375",  # IPXO  
    "50313",  # INFR
    "45839",  # QuadraNet
    "32489",  # Privex
    "204957", # Contabo
}

# Known VPN provider ASNs
VPN_ASNS: Set[str] = {
    "13335",  # Cloudflare
    "15169",  # Google
    "8075",   # Microsoft
    "22667",  # BT Global
    "2914",   # Verio
    "36385",  # IPVanish
    "41098",  # Astrill
    "57043",  # Mullvad
}

# Proxy/residential proxy networks
PROXY_ASNS: Set[str] = {
    "32934",  # Facebook
    "15169",  # Google
    "16509",  # AWS
    "39798",  # Psychz
    "42708",  # Bright Data
}

CACHE_TTL = 86400 * 30  # 30 days


class ASNDatabase:
    """Autonomous System Number analysis and datacenter detection."""

    def __init__(self):
        self._cache = get_redis()

    async def _load_asn_info(self, asn: str) -> Optional[Dict[str, Any]]:
        """Load ASN information from cache or external source."""
        cache_key = f"ti:asn:{asn}"
        
        try:
            cached = await self._cache.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

        # If no cache, return based on known ASN sets
        return None

    async def classify_asn(self, asn: Optional[str]) -> Dict[str, Any]:
        """Classify an ASN and detect threat characteristics."""
        if not asn:
            return {"asn": None, "is_datacenter": False, "is_vpn": False, "is_proxy": False}

        asn_num = str(asn).replace("AS", "").strip()
        if not asn_num:
            return {"asn": asn_num, "is_datacenter": False, "is_vpn": False, "is_proxy": False}

        return {
            "asn": asn_num,
            "is_datacenter": asn_num in DATACENTER_ASNS,
            "is_vpn": asn_num in VPN_ASNS,
            "is_proxy": asn_num in PROXY_ASNS,
            "threat_categories": self._extract_threats(asn_num),
        }

    @staticmethod
    def _extract_threats(asn: str) -> list:
        """Extract threat categories based on ASN classification."""
        threats = []
        if asn in DATACENTER_ASNS:
            threats.append("datacenter")
        if asn in VPN_ASNS:
            threats.append("vpn")
        if asn in PROXY_ASNS:
            threats.append("proxy")
        return threats

    async def add_datacenter_asn(self, asn: str) -> None:
        """Add ASN to known datacenter list."""
        DATACENTER_ASNS.add(str(asn))
        await self._persist_asns()

    async def add_vpn_asn(self, asn: str) -> None:
        """Add ASN to known VPN provider list."""
        VPN_ASNS.add(str(asn))
        await self._persist_asns()

    async def _persist_asns(self) -> None:
        """Persist ASN classifications to cache."""
        try:
            await self._cache.set(
                "ti:asn:datacenter:list",
                json.dumps(list(DATACENTER_ASNS)),
                ttl=CACHE_TTL,
            )
            await self._cache.set(
                "ti:asn:vpn:list",
                json.dumps(list(VPN_ASNS)),
                ttl=CACHE_TTL,
            )
        except Exception as exc:
            logger.warning("asn_persist_failed", error=str(exc))

    async def batch_classify(self, asns: list) -> Dict[str, Dict[str, Any]]:
        """Classify multiple ASNs efficiently."""
        results = {}
        for asn in asns:
            results[str(asn)] = await self.classify_asn(asn)
        return results
