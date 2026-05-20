from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models import IPReputation
from app.infrastructure.cache.redis_client import RedisCache
logger = get_logger(__name__)


class ReputationService:
    """Fachada de reputación IP — delega en ThreatIntelAnalyzer."""

    def __init__(self, db: AsyncSession, cache: Optional[RedisCache] = None):
        self.db = db
        self.cache = cache or RedisCache(prefix="reputation")
        self._analyzer = None

    def _analyzer_instance(self):
        if self._analyzer is None:
            from app.services.threat_intel.analyzer import ThreatIntelAnalyzer

            self._analyzer = ThreatIntelAnalyzer(self.db)
        return self._analyzer

    async def get_or_create(self, ip_address: str) -> IPReputation:
        result = await self.db.execute(
            select(IPReputation).where(IPReputation.ip_address == ip_address)
        )
        reputation = result.scalar_one_or_none()
        if reputation:
            return reputation

        reputation = IPReputation(ip_address=ip_address, reputation_score=50.0)
        self.db.add(reputation)
        await self.db.flush()
        return reputation

    async def enrich_ip(self, ip_address: str, *, force_refresh: bool = False) -> Dict[str, Any]:
        """Enriquecimiento completo: VPN, proxy, TOR, datacenter, residential, botnet."""
        report = await self._analyzer_instance().analyze(ip_address, force_refresh=force_refresh)
        enrichment: Dict[str, Any] = {
            "ip_address": ip_address,
            "reputation_score": report.reputation_score,
            "risk_score": report.risk_score,
            "confidence": report.confidence,
            "is_proxy": report.is_proxy,
            "is_vpn": report.is_vpn,
            "is_tor": report.is_tor,
            "is_datacenter": report.is_datacenter,
            "is_hosting": report.asn.is_hosting if report.asn else report.is_datacenter,
            "is_residential_proxy": report.is_residential_proxy,
            "is_botnet": report.is_botnet,
            "is_malicious": report.is_malicious,
            "asn": report.asn.number if report.asn else None,
            "asn_organization": report.asn.organization if report.asn else None,
            "country_code": report.geo.country_code if report.geo else None,
            "geo": report.geo.__dict__ if report.geo else {},
            "abuse_reports": report.abuse_reports,
            "threat_categories": report.threat_categories,
            "flags": report.flags,
            "sources": report.sources,
            "recommended_action": report.recommended_action,
            "cached": report.cached,
        }
        return enrichment

    async def update_reputation(
        self,
        ip_address: str,
        delta: float,
        reason: str,
    ) -> float:
        reputation = await self.get_or_create(ip_address)
        reputation.reputation_score = max(0, min(100, reputation.reputation_score + delta))
        meta = reputation.ip_metadata or {}
        history = meta.get("history", [])
        history.append({
            "delta": delta,
            "reason": reason,
            "score": reputation.reputation_score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        meta["history"] = history[-100:]
        reputation.ip_metadata = meta
        await self.db.flush()
        from app.services.threat_intel.cache import ThreatIntelCache

        await ThreatIntelCache().invalidate(ip_address)
        await self.cache.delete(f"ip:{ip_address}")
        return reputation.reputation_score
