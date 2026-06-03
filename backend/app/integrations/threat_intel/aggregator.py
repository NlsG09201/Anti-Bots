"""IP Intelligence Aggregator — Unified IP threat assessment."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import get_redis
from app.integrations.threat_intel.abuseipdb import AbuseIPDBClient
from app.integrations.threat_intel.ipinfo import IPInfoClient
from app.integrations.threat_intel.maxmind import MaxMindGeoIP2Service
from app.integrations.threat_intel.ip2location import IP2LocationService
from app.integrations.threat_intel.spamhaus import SpamhausClient
from app.integrations.threat_intel.tor_nodes import TorExitNodeService
from app.integrations.threat_intel.asn_db import ASNDatabase
from app.integrations.threat_intel.virustotal import VirusTotalClient
import json

logger = get_logger(__name__)
settings = get_settings()

CACHE_TTL = 3600  # 1 hour


class IPIntelligenceAggregator:
    """Aggregate threat intelligence from multiple sources."""

    def __init__(self):
        self.abuseipdb = AbuseIPDBClient()
        self.ipinfo = IPInfoClient()
        self.maxmind = MaxMindGeoIP2Service()
        self.ip2location = IP2LocationService()
        self.spamhaus = SpamhausClient()
        self.tor = TorExitNodeService()
        self.asn_db = ASNDatabase()
        self.virustotal = VirusTotalClient()
        self._cache = get_redis()

    async def _get_cached(self, ip_address: str) -> Optional[Dict[str, Any]]:
        """Get cached IP intelligence."""
        cache_key = f"ti:ip:{ip_address}:full"
        try:
            cached = await self._cache.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass
        return None

    async def _cache_result(self, ip_address: str, result: Dict[str, Any]) -> None:
        """Cache IP intelligence result."""
        cache_key = f"ti:ip:{ip_address}:full"
        try:
            await self._cache.set(cache_key, json.dumps(result), ttl=CACHE_TTL)
        except Exception as exc:
            logger.warning("ip_intel_cache_failed", ip=ip_address, error=str(exc))

    async def assess_ip(self, ip_address: str, use_cache: bool = True) -> Dict[str, Any]:
        """Comprehensive IP threat assessment."""
        if use_cache:
            cached = await self._get_cached(ip_address)
            if cached:
                return cached

        result = {
            "ip_address": ip_address,
            "assessment_timestamp": int(__import__("time").time()),
            "sources": {},
            "threats": set(),
            "risk_factors": {},
        }

        # Parallel threat intelligence gathering
        results = await self._gather_all_intelligence(ip_address)

        # Aggregate results
        for source, data in results.items():
            if data:
                result["sources"][source] = data
                if "threat_categories" in data:
                    result["threats"].update(data.get("threat_categories", []))

        # Calculate risk scores
        result["risk_scores"] = self._calculate_risk_scores(result["sources"])
        result["combined_threat_score"] = self._calculate_combined_score(result["risk_scores"])
        result["threats"] = list(result["threats"])
        result["recommendation"] = self._get_recommendation(result["combined_threat_score"])

        # Cache result
        await self._cache_result(ip_address, result)

        return result

    async def _gather_all_intelligence(self, ip_address: str) -> Dict[str, Optional[Dict]]:
        """Gather intelligence from all available sources."""
        # Run all checks in parallel
        import asyncio

        checks = {
            "abuseipdb": self.abuseipdb.check(ip_address) if self.abuseipdb.enabled else None,
            "ipinfo": self.ipinfo.check(ip_address) if self.ipinfo.enabled else None,
            "maxmind": MaxMindGeoIP2Service.full_check(ip_address),
            "ip2location": IP2LocationService.lookup(ip_address),
            "spamhaus": self.spamhaus.check(ip_address),
            "tor": self.tor.check(ip_address),
            "virustotal": self.virustotal.check(ip_address) if self.virustotal.enabled else None,
        }

        # Filter out None coroutines and gather results
        pending = {k: v for k, v in checks.items() if v is not None}
        results = {}

        if pending:
            gathered = await asyncio.gather(*pending.values(), return_exceptions=True)
            for key, result in zip(pending.keys(), gathered):
                if not isinstance(result, Exception):
                    results[key] = result
                else:
                    logger.debug(f"threat_intel_{key}_failed", error=str(result))

        # Add ASN classification
        asn = None
        for source in ["abuseipdb", "ipinfo", "maxmind"]:
            if source in results and "asn_number" in results[source]:
                asn = results[source]["asn_number"]
                break

        if asn:
            asn_result = await self.asn_db.classify_asn(asn)
            results["asn"] = asn_result

        return results

    @staticmethod
    def _calculate_risk_scores(sources: Dict[str, Any]) -> Dict[str, float]:
        """Calculate individual risk scores from each source."""
        scores = {}

        # AbuseIPDB score
        if "abuseipdb" in sources:
            abuse = sources["abuseipdb"]
            score = (abuse.get("abuse_confidence", 0) / 100.0)
            if abuse.get("is_tor"):
                score += 0.3
            if abuse.get("is_datacenter"):
                score += 0.2
            scores["abuseipdb"] = min(1.0, score)

        # IPInfo privacy flags
        if "ipinfo" in sources:
            info = sources["ipinfo"]
            score = 0.0
            if info.get("is_vpn"):
                score += 0.4
            if info.get("is_proxy"):
                score += 0.4
            if info.get("is_tor"):
                score += 0.5
            if info.get("is_datacenter"):
                score += 0.3
            scores["ipinfo"] = min(1.0, score)

        # MaxMind traits
        if "maxmind" in sources:
            mm = sources["maxmind"]
            score = 0.0
            if mm.get("is_anonymous_vpn"):
                score += 0.4
            if mm.get("is_public_proxy"):
                score += 0.4
            if mm.get("is_tor_exit_node"):
                score += 0.5
            if mm.get("is_datacenter_proxy"):
                score += 0.3
            scores["maxmind"] = min(1.0, score)

        # Spamhaus
        if "spamhaus" in sources and sources["spamhaus"].get("is_listed"):
            scores["spamhaus"] = 0.8

        # TOR
        if "tor" in sources and sources["tor"].get("is_tor_exit_node"):
            scores["tor"] = 0.9

        # ASN classification
        if "asn" in sources:
            asn = sources["asn"]
            score = 0.0
            if asn.get("is_datacenter"):
                score += 0.3
            if asn.get("is_vpn"):
                score += 0.3
            scores["asn"] = min(1.0, score)

        return scores

    @staticmethod
    def _calculate_combined_score(risk_scores: Dict[str, float]) -> float:
        """Calculate combined threat score from individual sources."""
        if not risk_scores:
            return 0.0

        # Weight sources by reliability
        weights = {
            "abuseipdb": 0.25,
            "maxmind": 0.25,
            "tor": 0.2,
            "spamhaus": 0.15,
            "ipinfo": 0.1,
            "asn": 0.05,
            "virustotal": 0.1,
        }

        total_score = 0.0
        total_weight = 0.0

        for source, score in risk_scores.items():
            weight = weights.get(source, 0.05)
            total_score += score * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        return min(1.0, total_score / total_weight)

    @staticmethod
    def _get_recommendation(threat_score: float) -> str:
        """Get recommendation based on threat score."""
        if threat_score >= 0.8:
            return "BLOCK"
        elif threat_score >= 0.5:
            return "STRICT_MONITOR"
        elif threat_score >= 0.3:
            return "MONITOR"
        else:
            return "ALLOW"

    async def batch_assess(self, ip_addresses: List[str]) -> Dict[str, Dict[str, Any]]:
        """Assess multiple IPs efficiently."""
        import asyncio

        tasks = [self.assess_ip(ip) for ip in ip_addresses]
        results = await asyncio.gather(*tasks)
        return {ip: result for ip, result in zip(ip_addresses, results)}
