"""Modelos de salida para análisis de threat intelligence."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AsnInfo:
    number: Optional[int] = None
    organization: Optional[str] = None
    is_datacenter: bool = False
    is_hosting: bool = False
    risk_keywords: List[str] = field(default_factory=list)


@dataclass
class GeoInfo:
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone: Optional[str] = None


@dataclass
class ThreatIntelReport:
    ip_address: str
    reputation_score: float = 50.0
    risk_score: float = 0.0
    confidence: float = 0.0

    is_vpn: bool = False
    is_proxy: bool = False
    is_tor: bool = False
    is_datacenter: bool = False
    is_residential_proxy: bool = False
    is_botnet: bool = False
    is_malicious: bool = False

    asn: Optional[AsnInfo] = None
    geo: Optional[GeoInfo] = None

    abuse_reports: int = 0
    threat_categories: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    recommended_action: str = "none"

    raw_providers: Dict[str, Any] = field(default_factory=dict)
    cached: bool = False
    analyzed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ip_address": self.ip_address,
            "reputation_score": self.reputation_score,
            "risk_score": self.risk_score,
            "confidence": self.confidence,
            "is_vpn": self.is_vpn,
            "is_proxy": self.is_proxy,
            "is_tor": self.is_tor,
            "is_datacenter": self.is_datacenter,
            "is_residential_proxy": self.is_residential_proxy,
            "is_botnet": self.is_botnet,
            "is_malicious": self.is_malicious,
            "asn": {
                "number": self.asn.number if self.asn else None,
                "organization": self.asn.organization if self.asn else None,
                "is_datacenter": self.asn.is_datacenter if self.asn else False,
                "is_hosting": self.asn.is_hosting if self.asn else False,
                "risk_keywords": self.asn.risk_keywords if self.asn else [],
            },
            "geo": {
                "country_code": self.geo.country_code if self.geo else None,
                "country_name": self.geo.country_name if self.geo else None,
                "city": self.geo.city if self.geo else None,
                "region": self.geo.region if self.geo else None,
                "latitude": self.geo.latitude if self.geo else None,
                "longitude": self.geo.longitude if self.geo else None,
                "timezone": self.geo.timezone if self.geo else None,
            },
            "abuse_reports": self.abuse_reports,
            "threat_categories": self.threat_categories,
            "flags": self.flags,
            "sources": self.sources,
            "recommended_action": self.recommended_action,
            "cached": self.cached,
            "analyzed_at": self.analyzed_at,
        }
