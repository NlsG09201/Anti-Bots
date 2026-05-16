from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.database.models import IPReputation
from app.infrastructure.cache.redis_client import RedisCache
from app.integrations.threat_intel.virustotal import VirusTotalClient
from app.integrations.threat_intel.geoip import GeoIPService

logger = get_logger(__name__)
settings = get_settings()


class ReputationService:
    def __init__(self, db: AsyncSession, cache: Optional[RedisCache] = None):
        self.db = db
        self.cache = cache or RedisCache(prefix="reputation")

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

    async def enrich_ip(self, ip_address: str) -> Dict[str, Any]:
        cache_key = f"ip:{ip_address}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        reputation = await self.get_or_create(ip_address)
        enrichment: Dict[str, Any] = {
            "ip_address": ip_address,
            "reputation_score": reputation.reputation_score,
            "is_proxy": reputation.is_proxy,
            "is_vpn": reputation.is_vpn,
            "is_tor": reputation.is_tor,
            "is_datacenter": reputation.is_datacenter,
            "asn": reputation.asn,
            "country_code": reputation.country_code,
        }

        if settings.abuseipdb_api_key:
            abuse_data = await self._query_abuseipdb(ip_address)
            if abuse_data:
                enrichment.update(abuse_data)
                reputation.abuse_reports = abuse_data.get("abuse_reports", 0)
                reputation.reputation_score = abuse_data.get("reputation_score", reputation.reputation_score)

        if settings.ipqualityscore_api_key:
            iqs_data = await self._query_ipqualityscore(ip_address)
            if iqs_data:
                enrichment.update(iqs_data)
                reputation.is_proxy = iqs_data.get("is_proxy", reputation.is_proxy)
                reputation.is_vpn = iqs_data.get("is_vpn", reputation.is_vpn)
                reputation.is_tor = iqs_data.get("is_tor", reputation.is_tor)
                reputation.is_datacenter = iqs_data.get("is_datacenter", reputation.is_datacenter)

        vt = VirusTotalClient()
        if vt.enabled:
            vt_data = await vt.check_ip(ip_address)
            if vt_data:
                enrichment["virustotal"] = vt_data
                if vt_data.get("is_malicious"):
                    reputation.reputation_score = min(
                        reputation.reputation_score,
                        vt_data.get("reputation_score", 20),
                    )

        geo = GeoIPService.lookup(ip_address)
        if geo:
            enrichment["geo"] = geo
            if not reputation.country_code:
                reputation.country_code = geo.get("country_code")

        reputation.last_seen = datetime.now(timezone.utc)
        await self.db.flush()
        await self.cache.set(cache_key, enrichment, ttl=3600)
        return enrichment

    async def _query_abuseipdb(self, ip_address: str) -> Optional[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.abuseipdb.com/api/v2/check",
                    headers={"Key": settings.abuseipdb_api_key, "Accept": "application/json"},
                    params={"ipAddress": ip_address, "maxAgeInDays": 90},
                )
                if response.status_code != 200:
                    return None
                data = response.json().get("data", {})
                abuse_score = data.get("abuseConfidenceScore", 0)
                return {
                    "abuse_reports": data.get("totalReports", 0),
                    "reputation_score": max(0, 100 - abuse_score),
                    "is_tor": data.get("isTor", False),
                    "country_code": data.get("countryCode"),
                    "asn": data.get("isp"),
                }
        except Exception as e:
            logger.warning("abuseipdb_query_failed", ip=ip_address, error=str(e))
            return None

    async def _query_ipqualityscore(self, ip_address: str) -> Optional[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"https://ipqualityscore.com/api/json/ip/{settings.ipqualityscore_api_key}/{ip_address}",
                    params={"strictness": 1, "allow_public_access_points": True},
                )
                if response.status_code != 200:
                    return None
                data = response.json()
                if not data.get("success"):
                    return None
                fraud_score = data.get("fraud_score", 0)
                return {
                    "is_proxy": data.get("proxy", False),
                    "is_vpn": data.get("vpn", False),
                    "is_tor": data.get("tor", False),
                    "is_datacenter": data.get("host", False) or data.get("recent_abuse", False),
                    "reputation_score": max(0, 100 - fraud_score),
                    "country_code": data.get("country_code"),
                    "asn": data.get("ASN"),
                }
        except Exception as e:
            logger.warning("ipqualityscore_query_failed", ip=ip_address, error=str(e))
            return None

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
        await self.cache.delete(f"ip:{ip_address}")
        return reputation.reputation_score
