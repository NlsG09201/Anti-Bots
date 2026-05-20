"""Cálculo de risk_score y reputación unificada."""

from typing import Any, Dict, List

from app.services.threat_intel.models import AsnInfo, GeoInfo, ThreatIntelReport


def compute_threat_scores(
    *,
    is_vpn: bool,
    is_proxy: bool,
    is_tor: bool,
    is_datacenter: bool,
    is_residential_proxy: bool,
    is_botnet: bool,
    is_malicious: bool,
    abuse_reports: int,
    reputation_score: float,
    asn: AsnInfo | None,
    sources_count: int,
) -> tuple[float, float, float, List[str], str]:
    """
    Returns (risk_score, reputation_score adjusted, confidence, flags, action).
    """
    risk = 0.0
    flags: List[str] = []

    if is_tor:
        risk += 35.0
        flags.append("tor_exit")
    if is_vpn:
        risk += 22.0
        flags.append("vpn")
    if is_proxy:
        risk += 18.0
        flags.append("proxy")
    if is_residential_proxy:
        risk += 28.0
        flags.append("residential_proxy")
    if is_datacenter:
        risk += 20.0
        flags.append("datacenter_ip")
    if is_botnet:
        risk += 40.0
        flags.append("botnet_suspected")
    if is_malicious:
        risk += 30.0
        flags.append("malicious_reputation")

    if abuse_reports >= 5:
        risk += min(25.0, abuse_reports * 2.0)
        flags.append(f"abuse_reports:{abuse_reports}")

    if asn and asn.risk_keywords:
        risk += min(25.0, len(asn.risk_keywords) * 8.0)
        for kw in asn.risk_keywords[:3]:
            flags.append(f"asn:{kw.lower()}")

    # Reputación baja eleva riesgo
    if reputation_score < 30:
        risk += 25.0
        flags.append("low_reputation")
    elif reputation_score < 50:
        risk += 12.0

    risk = min(100.0, risk)
    confidence = min(1.0, 0.25 + sources_count * 0.2)

    action = "none"
    if risk >= 85:
        action = "block"
    elif risk >= 65:
        action = "quarantine"
    elif risk >= 40:
        action = "monitor"

    return risk, reputation_score, confidence, flags, action


def apply_scores_to_report(report: ThreatIntelReport) -> ThreatIntelReport:
    risk, rep, conf, flags, action = compute_threat_scores(
        is_vpn=report.is_vpn,
        is_proxy=report.is_proxy,
        is_tor=report.is_tor,
        is_datacenter=report.is_datacenter,
        is_residential_proxy=report.is_residential_proxy,
        is_botnet=report.is_botnet,
        is_malicious=report.is_malicious,
        abuse_reports=report.abuse_reports,
        reputation_score=report.reputation_score,
        asn=report.asn,
        sources_count=len(report.sources),
    )
    report.risk_score = round(risk, 2)
    report.reputation_score = round(rep, 2)
    report.confidence = round(conf, 3)
    report.flags = list(dict.fromkeys(report.flags + flags))
    report.recommended_action = action
    report.is_malicious = report.is_malicious or risk >= 70
    return report
