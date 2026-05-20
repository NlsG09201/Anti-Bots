"""
Orquestador de threat intelligence: VPN, proxy, TOR, datacenter, residential proxy, botnets.
Integra APIs externas + GeoIP + Redis + persistencia en PostgreSQL.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.database.models import IPReputation
from app.integrations.threat_intel.abuseipdb import AbuseIPDBClient
from app.integrations.threat_intel.geoip import GeoIPService
from app.integrations.threat_intel.ipapi import IPApiClient
from app.integrations.threat_intel.ipqualityscore import IPQualityScoreClient
from app.integrations.threat_intel.virustotal import VirusTotalClient
from app.services.threat_intel.asn import analyze_asn
from app.services.threat_intel.cache import ThreatIntelCache
from app.services.threat_intel.models import AsnInfo, GeoInfo, ThreatIntelReport
from app.services.threat_intel.scoring import apply_scores_to_report

logger = get_logger(__name__)
settings = get_settings()


class ThreatIntelAnalyzer:
    def __init__(
        self,
        db: AsyncSession,
        cache: Optional[ThreatIntelCache] = None,
    ):
        self.db = db
        self.cache = cache or ThreatIntelCache()

    async def analyze(
        self,
        ip_address: str,
        *,
        force_refresh: bool = False,
    ) -> ThreatIntelReport:
        if not ip_address or ip_address == "unknown":
            return ThreatIntelReport(
                ip_address=ip_address or "unknown",
                flags=["invalid_ip"],
                risk_score=0.0,
            )

        if not force_refresh:
            cached = await self.cache.get(ip_address)
            if cached:
                report = self._report_from_dict(cached)
                report.cached = True
                return report

        provider_results = await self._query_providers(ip_address)
        report = self._merge_provider_results(ip_address, provider_results)

        geo_local = GeoIPService.lookup(ip_address)
        if geo_local:
            report.geo = GeoInfo(
                country_code=geo_local.get("country_code") or report.geo.country_code if report.geo else None,
                country_name=geo_local.get("country_name"),
                city=geo_local.get("city") or (report.geo.city if report.geo else None),
                latitude=geo_local.get("latitude"),
                longitude=geo_local.get("longitude"),
                timezone=geo_local.get("timezone"),
            )
            if not report.sources or "maxmind" not in report.sources:
                report.sources.append("maxmind")

        report = apply_scores_to_report(report)
        report.analyzed_at = datetime.now(timezone.utc).isoformat()

        await self._persist_to_db(ip_address, report)
        payload = report.to_dict()
        payload["raw_providers"] = report.raw_providers
        await self.cache.set(
            ip_address,
            payload,
            high_risk=report.risk_score >= 65,
        )
        return report

    async def analyze_batch(
        self,
        ip_addresses: List[str],
        *,
        force_refresh: bool = False,
    ) -> List[ThreatIntelReport]:
        tasks = [self.analyze(ip, force_refresh=force_refresh) for ip in ip_addresses[:50]]
        return await asyncio.gather(*tasks)

    async def _query_providers(self, ip_address: str) -> Dict[str, Any]:
        abuse = AbuseIPDBClient()
        iqs = IPQualityScoreClient()
        vt = VirusTotalClient()
        ipapi = IPApiClient()

        async def _run(name: str, coro):
            try:
                return await coro
            except Exception as exc:
                logger.warning("threat_intel_provider_error", provider=name, error=str(exc))
                return None

        tasks = []
        names: List[str] = []
        if abuse.enabled:
            tasks.append(_run("abuseipdb", abuse.check(ip_address)))
            names.append("abuseipdb")
        if iqs.enabled:
            tasks.append(_run("ipqualityscore", iqs.check(ip_address)))
            names.append("ipqualityscore")
        if vt.enabled:
            tasks.append(_run("virustotal", vt.check_ip(ip_address)))
            names.append("virustotal")
        if ipapi.enabled:
            tasks.append(_run("ip-api", ipapi.check(ip_address)))
            names.append("ip-api")

        if not tasks:
            return {}

        results = await asyncio.gather(*tasks)
        return {name: result for name, result in zip(names, results) if result}

    def _merge_provider_results(
        self,
        ip_address: str,
        providers: Dict[str, Any],
    ) -> ThreatIntelReport:
        report = ThreatIntelReport(ip_address=ip_address, raw_providers=providers)
        reputation_scores: List[float] = []

        abuse = providers.get("abuseipdb") or {}
        if abuse:
            report.sources.append("abuseipdb")
            report.abuse_reports = max(report.abuse_reports, abuse.get("abuse_reports", 0))
            report.is_tor = report.is_tor or abuse.get("is_tor", False)
            report.is_datacenter = report.is_datacenter or abuse.get("is_datacenter", False)
            reputation_scores.append(abuse.get("reputation_score", 50))
            report.threat_categories.extend(abuse.get("threat_categories", []))

        iqs = providers.get("ipqualityscore") or {}
        if iqs:
            report.sources.append("ipqualityscore")
            report.is_proxy = report.is_proxy or iqs.get("is_proxy", False)
            report.is_vpn = report.is_vpn or iqs.get("is_vpn", False)
            report.is_tor = report.is_tor or iqs.get("is_tor", False)
            report.is_datacenter = report.is_datacenter or iqs.get("is_datacenter", False)
            report.is_residential_proxy = report.is_residential_proxy or iqs.get(
                "is_residential_proxy", False
            )
            report.is_botnet = report.is_botnet or iqs.get("is_botnet", False)
            reputation_scores.append(iqs.get("reputation_score", 50))
            report.threat_categories.extend(iqs.get("threat_categories", []))
            if not report.geo:
                report.geo = GeoInfo(
                    country_code=iqs.get("country_code"),
                    city=iqs.get("city"),
                    region=iqs.get("region"),
                    latitude=iqs.get("latitude"),
                    longitude=iqs.get("longitude"),
                )

        vt = providers.get("virustotal") or {}
        if vt:
            report.sources.append("virustotal")
            if vt.get("is_malicious"):
                report.is_malicious = True
                report.is_botnet = True
                report.threat_categories.append("malware_reputation")
            reputation_scores.append(vt.get("reputation_score", 50))
            if vt.get("as_owner") and not report.asn:
                asn_data = analyze_asn(None, vt.get("as_owner"))
                report.asn = AsnInfo(**asn_data)

        ipapi = providers.get("ip-api") or {}
        if ipapi:
            report.sources.append("ip-api")
            report.is_proxy = report.is_proxy or ipapi.get("is_proxy", False)
            report.is_datacenter = report.is_datacenter or ipapi.get("is_datacenter", False)
            if not report.geo:
                report.geo = GeoInfo(
                    country_code=ipapi.get("country_code"),
                    country_name=ipapi.get("country_name"),
                    city=ipapi.get("city"),
                    region=ipapi.get("region"),
                    latitude=ipapi.get("latitude"),
                    longitude=ipapi.get("longitude"),
                    timezone=ipapi.get("timezone"),
                )

        # ASN consolidado
        asn_num = None
        asn_org = None
        hosting = False
        for src in (abuse, iqs, ipapi, vt):
            if not src:
                continue
            if src.get("asn_number"):
                asn_num = src.get("asn_number")
            if src.get("asn_organization"):
                asn_org = src.get("asn_organization")
            if src.get("is_datacenter") or src.get("hosting_provider"):
                hosting = True

        asn_data = analyze_asn(asn_num, asn_org, is_hosting_flag=hosting or report.is_datacenter)
        report.asn = AsnInfo(**asn_data)
        if report.asn.is_datacenter:
            report.is_datacenter = True

        # Heurística residential proxy si no marcado por IQS
        if report.is_proxy and not report.is_vpn and not report.is_tor and not report.is_datacenter:
            report.is_residential_proxy = True
            if "residential_proxy" not in report.threat_categories:
                report.threat_categories.append("residential_proxy")

        # Botnet: VT malicioso o muchos reportes + baja reputación
        if report.abuse_reports >= 10 and (not reputation_scores or min(reputation_scores) < 35):
            report.is_botnet = True

        report.reputation_score = (
            min(reputation_scores) if reputation_scores else 50.0
        )
        report.threat_categories = list(dict.fromkeys(report.threat_categories))
        return report

    async def _get_or_create_reputation(self, ip_address: str) -> IPReputation:
        result = await self.db.execute(
            select(IPReputation).where(IPReputation.ip_address == ip_address)
        )
        row = result.scalar_one_or_none()
        if row:
            return row
        row = IPReputation(ip_address=ip_address, reputation_score=50.0)
        self.db.add(row)
        await self.db.flush()
        return row

    async def _persist_to_db(self, ip_address: str, report: ThreatIntelReport) -> None:
        row = await self._get_or_create_reputation(ip_address)
        row.reputation_score = report.reputation_score
        row.abuse_reports = report.abuse_reports
        row.is_proxy = report.is_proxy
        row.is_vpn = report.is_vpn
        row.is_tor = report.is_tor
        row.is_datacenter = report.is_datacenter
        row.is_hosting = report.asn.is_hosting if report.asn else report.is_datacenter
        row.country_code = report.geo.country_code if report.geo else row.country_code
        if report.asn:
            row.asn = report.asn.number
            row.asn_org = report.asn.organization
        row.threat_categories = report.threat_categories
        row.is_blocked = report.risk_score >= settings.threat_intel_block_threshold
        row.last_seen = datetime.now(timezone.utc)
        meta = row.ip_metadata or {}
        meta["threat_intel"] = {
            "risk_score": report.risk_score,
            "flags": report.flags,
            "is_residential_proxy": report.is_residential_proxy,
            "is_botnet": report.is_botnet,
            "sources": report.sources,
            "analyzed_at": report.analyzed_at,
        }
        row.ip_metadata = meta
        await self.db.flush()

    def _report_from_dict(self, data: Dict[str, Any]) -> ThreatIntelReport:
        asn_raw = data.get("asn") or {}
        geo_raw = data.get("geo") or {}
        return ThreatIntelReport(
            ip_address=data.get("ip_address", ""),
            reputation_score=float(data.get("reputation_score", 50)),
            risk_score=float(data.get("risk_score", 0)),
            confidence=float(data.get("confidence", 0)),
            is_vpn=bool(data.get("is_vpn")),
            is_proxy=bool(data.get("is_proxy")),
            is_tor=bool(data.get("is_tor")),
            is_datacenter=bool(data.get("is_datacenter")),
            is_residential_proxy=bool(data.get("is_residential_proxy")),
            is_botnet=bool(data.get("is_botnet")),
            is_malicious=bool(data.get("is_malicious")),
            asn=AsnInfo(
                number=asn_raw.get("number"),
                organization=asn_raw.get("organization"),
                is_datacenter=asn_raw.get("is_datacenter", False),
                is_hosting=asn_raw.get("is_hosting", False),
                risk_keywords=asn_raw.get("risk_keywords", []),
            ),
            geo=GeoInfo(
                country_code=geo_raw.get("country_code"),
                country_name=geo_raw.get("country_name"),
                city=geo_raw.get("city"),
                region=geo_raw.get("region"),
                latitude=geo_raw.get("latitude"),
                longitude=geo_raw.get("longitude"),
                timezone=geo_raw.get("timezone"),
            ),
            abuse_reports=int(data.get("abuse_reports", 0)),
            threat_categories=list(data.get("threat_categories", [])),
            flags=list(data.get("flags", [])),
            sources=list(data.get("sources", [])),
            recommended_action=data.get("recommended_action", "none"),
            raw_providers=data.get("raw_providers", {}),
            analyzed_at=data.get("analyzed_at"),
        )
