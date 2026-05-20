"""
Enterprise network policy: VPN, proxy, TOR, datacenter, automation, geo block.
Integrates threat intel with detection ingest and gateway decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.config import get_settings

settings = get_settings()


@dataclass
class NetworkPolicyResult:
    allowed: bool
    risk_score: float
    threat_type: str
    flags: List[str] = field(default_factory=list)
    recommended_action: str = "allow"
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "risk_score": self.risk_score,
            "threat_type": self.threat_type,
            "flags": self.flags,
            "recommended_action": self.recommended_action,
            "evidence": self.evidence,
        }


class NetworkPolicyEngine:
    """
    Unified policy for bots, proxies, VPNs, and automation at ingest time.
    """

    WEIGHT_PROXY = 22.0
    WEIGHT_VPN = 18.0
    WEIGHT_TOR = 35.0
    WEIGHT_DATACENTER = 15.0
    WEIGHT_BOTNET = 30.0
    WEIGHT_RESIDENTIAL_PROXY = 25.0
    WEIGHT_AUTOMATION = 28.0
    BLOCK_THRESHOLD = 70.0
    CHALLENGE_THRESHOLD = 45.0

    def evaluate(
        self,
        *,
        ip_intel: Optional[Dict[str, Any]] = None,
        fingerprint_flags: Optional[List[str]] = None,
        automation_detected: bool = False,
    ) -> NetworkPolicyResult:
        flags: List[str] = []
        score = 0.0
        intel = ip_intel or {}

        if intel.get("is_tor"):
            score += self.WEIGHT_TOR
            flags.append("tor_exit")
        if intel.get("is_vpn"):
            score += self.WEIGHT_VPN
            flags.append("vpn")
        if intel.get("is_proxy"):
            score += self.WEIGHT_PROXY
            flags.append("proxy")
        if intel.get("is_residential_proxy"):
            score += self.WEIGHT_RESIDENTIAL_PROXY
            flags.append("residential_proxy")
        if intel.get("is_datacenter"):
            score += self.WEIGHT_DATACENTER
            flags.append("datacenter")
        if intel.get("is_botnet"):
            score += self.WEIGHT_BOTNET
            flags.append("botnet")

        country = (intel.get("country_code") or intel.get("country") or "").upper()
        if country and country in settings.security_blocked_countries_list:
            score = min(100.0, score + 40.0)
            flags.append(f"blocked_country:{country}")

        for f in fingerprint_flags or []:
            if any(
                x in f.lower()
                for x in ("webdriver", "headless", "selenium", "puppeteer", "playwright")
            ):
                score += self.WEIGHT_AUTOMATION
                flags.append(f"fp:{f}")
                break

        if automation_detected:
            score += self.WEIGHT_AUTOMATION
            flags.append("automation_header")

        score = min(100.0, score)
        flags = list(dict.fromkeys(flags))

        if score >= self.BLOCK_THRESHOLD:
            action = "block"
            allowed = False
            threat = "malicious_network"
        elif score >= self.CHALLENGE_THRESHOLD:
            action = "challenge"
            allowed = True
            threat = "suspicious_network"
        else:
            action = "allow"
            allowed = True
            threat = "none"

        return NetworkPolicyResult(
            allowed=allowed,
            risk_score=round(score, 2),
            threat_type=threat,
            flags=flags,
            recommended_action=action,
            evidence={"ip_intel": intel, "automation_detected": automation_detected},
        )
