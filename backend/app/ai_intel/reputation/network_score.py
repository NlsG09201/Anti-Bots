"""Advanced Network Reputation Scoring System."""

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import json

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.cache.redis_client import get_redis

logger = get_logger(__name__)
settings = get_settings()

CACHE_TTL = 86400  # 24 hours
LONG_TERM_CACHE_TTL = 86400 * 30  # 30 days


class NetworkReputationScorer:
    """
    Advanced reputation scoring for IPs, ASNs, and networks.
    
    Scores (0-100):
    - 0-20: Highly suspicious/malicious
    - 20-40: Suspicious
    - 40-60: Unknown/neutral
    - 60-80: Good reputation
    - 80-100: Trusted
    """

    def __init__(self):
        self._cache = get_redis()
        self._decay_factor = 0.95  # Daily decay factor for incident-based scores

    # ============= VPN Score =============

    async def calculate_vpn_score(
        self,
        is_vpn: bool = False,
        vpn_provider_asn: Optional[str] = None,
        recent_incidents: int = 0,
        is_commercial: bool = True,
    ) -> float:
        """
        Calculate VPN score (0-100).
        
        Higher = more likely to be VPN.
        Lower = more likely to be legitimate IP.
        """
        score = 50.0  # Neutral baseline

        # VPN detection flag
        if is_vpn:
            score += 30

        # Commercial VPN providers are more trusted
        if is_commercial and is_vpn:
            score -= 10  # Reduce suspicion for known providers

        # Recent abuse incidents
        if recent_incidents > 0:
            incident_penalty = min(20, recent_incidents * 2)
            score -= incident_penalty

        return max(0, min(100, score))

    # ============= Proxy Score =============

    async def calculate_proxy_score(
        self,
        is_proxy: bool = False,
        is_residential_proxy: bool = False,
        proxy_type: Optional[str] = None,
        abuse_reports: int = 0,
    ) -> float:
        """
        Calculate Proxy score (0-100).
        
        Residential proxies are more suspicious.
        Regular proxies score differently based on type.
        """
        score = 50.0  # Neutral baseline

        if is_proxy:
            score += 25

        # Residential proxies are highly suspicious
        if is_residential_proxy:
            score += 35

        # Specific proxy types
        if proxy_type:
            proxy_type = proxy_type.lower()
            if proxy_type in ("datacenter", "commercial"):
                score -= 10
            elif proxy_type == "residential":
                score += 20

        # Abuse reports
        if abuse_reports > 0:
            report_penalty = min(25, abuse_reports * 3)
            score -= report_penalty

        return max(0, min(100, score))

    # ============= Datacenter Score =============

    async def calculate_datacenter_score(
        self,
        is_datacenter: bool = False,
        datacenter_asn: Optional[str] = None,
        asn_in_datacenter_list: bool = False,
        provider_trust_level: float = 0.5,
    ) -> float:
        """
        Calculate Datacenter score (0-100).
        
        Legitimate datacenter usage is usually low threat.
        But can be used for botting with many low-trust providers.
        """
        score = 50.0  # Neutral baseline

        if not is_datacenter and not asn_in_datacenter_list:
            return 70.0  # Regular ISP, higher trust

        # Known datacenter networks
        if is_datacenter or asn_in_datacenter_list:
            score += 25

        # Provider trust affects score
        # High trust providers (AWS, GCP) get lower scores
        # Low trust (bullet hosting, etc.) get higher
        trust_adjustment = (1.0 - provider_trust_level) * 30
        score += trust_adjustment

        return max(0, min(100, score))

    # ============= TOR Score =============

    async def calculate_tor_score(
        self,
        is_tor_exit_node: bool = False,
        is_tor_relay: bool = False,
        recent_tor_usage: bool = False,
    ) -> float:
        """
        Calculate TOR score (0-100).
        
        TOR usage is typically high threat in streaming context.
        """
        score = 50.0

        if is_tor_exit_node:
            score += 45

        if is_tor_relay:
            score += 30

        if recent_tor_usage:
            score += 15

        return max(0, min(100, score))

    # ============= Combined Reputation Score =============

    async def calculate_reputation_score(
        self,
        ip_address: str,
        vpn_score: Optional[float] = None,
        proxy_score: Optional[float] = None,
        datacenter_score: Optional[float] = None,
        tor_score: Optional[float] = None,
        abuse_confidence: float = 0.0,
        is_whitelisted: bool = False,
        historical_risk: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive reputation score.
        
        Combines all threat dimensions into unified score.
        """
        # Check cache
        cache_key = f"net_rep:{ip_address}"
        cached = await self._get_cached_reputation(cache_key)
        if cached and not historical_risk:
            return cached

        # Calculate individual dimensions if not provided
        if vpn_score is None:
            vpn_score = await self.calculate_vpn_score()
        if proxy_score is None:
            proxy_score = await self.calculate_proxy_score()
        if datacenter_score is None:
            datacenter_score = await self.calculate_datacenter_score()
        if tor_score is None:
            tor_score = await self.calculate_tor_score()

        # Maximum threat from any dimension
        max_threat = max(vpn_score, proxy_score, tor_score)

        # Weight the scores
        weights = {
            "tor": 0.35,
            "vpn": 0.25,
            "proxy": 0.25,
            "datacenter": 0.15,
        }

        # Normalize to 0-1 scale and apply weights
        threat_components = {
            "tor_component": (tor_score / 100.0) * weights["tor"],
            "vpn_component": (vpn_score / 100.0) * weights["vpn"],
            "proxy_component": (proxy_score / 100.0) * weights["proxy"],
            "datacenter_component": (datacenter_score / 100.0) * weights["datacenter"],
        }

        # Combined threat score
        combined_threat = sum(threat_components.values())

        # Apply abuse confidence
        if abuse_confidence > 0:
            combined_threat = min(1.0, combined_threat + (abuse_confidence * 0.3))

        # Apply whitelist
        if is_whitelisted:
            combined_threat = max(0, combined_threat - 0.2)

        # Apply historical decay
        if historical_risk:
            # Older incidents decay over time
            combined_threat = combined_threat * 0.7 + historical_risk * 0.3

        # Convert to 0-100 scale for reputation (inverted)
        reputation_score = (1.0 - combined_threat) * 100

        result = {
            "ip_address": ip_address,
            "reputation_score": reputation_score,
            "threat_score": combined_threat * 100,
            "dimension_scores": {
                "vpn_score": vpn_score,
                "proxy_score": proxy_score,
                "datacenter_score": datacenter_score,
                "tor_score": tor_score,
            },
            "components": threat_components,
            "recommendation": self._get_reputation_recommendation(reputation_score),
            "confidence": self._calculate_confidence(vpn_score, proxy_score, tor_score),
            "timestamp": int(__import__("time").time()),
        }

        # Cache result
        await self._cache_reputation(cache_key, result)

        return result

    async def calculate_batch_reputation(
        self,
        ips_with_intel: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Calculate reputation for multiple IPs efficiently."""
        results = {}

        for ip, intel in ips_with_intel.items():
            # Extract scores from intel data
            vpn_score = intel.get("vpn_score")
            proxy_score = intel.get("proxy_score")
            datacenter_score = intel.get("datacenter_score")
            tor_score = intel.get("tor_score")

            reputation = await self.calculate_reputation_score(
                ip,
                vpn_score=vpn_score,
                proxy_score=proxy_score,
                datacenter_score=datacenter_score,
                tor_score=tor_score,
                abuse_confidence=intel.get("abuse_confidence", 0.0),
                is_whitelisted=intel.get("is_whitelisted", False),
                historical_risk=intel.get("historical_risk"),
            )
            results[ip] = reputation

        return results

    @staticmethod
    def _get_reputation_recommendation(reputation_score: float) -> str:
        """Get recommendation based on reputation score."""
        if reputation_score <= 20:
            return "BLOCK_ALL_ACTIVITY"
        elif reputation_score <= 40:
            return "BLOCK_SUSPICIOUS_PATTERNS"
        elif reputation_score <= 60:
            return "MONITOR_CLOSELY"
        elif reputation_score <= 80:
            return "STANDARD_MONITORING"
        else:
            return "ALLOW"

    @staticmethod
    def _calculate_confidence(vpn: float, proxy: float, tor: float) -> float:
        """Calculate confidence in the reputation assessment."""
        # Higher variance in scores = lower confidence
        scores = [vpn, proxy, tor]
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        std_dev = variance ** 0.5

        # Normalize std_dev to 0-1 confidence
        confidence = max(0, 1.0 - (std_dev / 100.0) * 0.5)
        return confidence

    async def _get_cached_reputation(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached reputation score."""
        try:
            cached = await self._cache.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass
        return None

    async def _cache_reputation(self, cache_key: str, result: Dict[str, Any]) -> None:
        """Cache reputation score."""
        try:
            await self._cache.set(cache_key, json.dumps(result), ttl=CACHE_TTL)
        except Exception as exc:
            logger.warning("reputation_cache_failed", error=str(exc))

    async def decay_scores_for_ip(self, ip_address: str) -> None:
        """Apply daily decay to historical risk scores."""
        cache_key = f"net_rep:{ip_address}"
        cached = await self._get_cached_reputation(cache_key)

        if cached:
            # Apply decay
            cached["threat_score"] *= self._decay_factor
            cached["reputation_score"] = (1.0 - (cached["threat_score"] / 100.0)) * 100
            await self._cache_reputation(cache_key, cached)
