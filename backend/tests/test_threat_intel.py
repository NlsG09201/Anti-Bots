"""Tests del módulo ThreatIntel (scoring y merge sin APIs externas)."""

from app.services.threat_intel.asn import analyze_asn, parse_asn_field
from app.services.threat_intel.models import AsnInfo, ThreatIntelReport
from app.services.threat_intel.scoring import apply_scores_to_report, compute_threat_scores


def test_parse_asn_field():
    num, org = parse_asn_field("AS15169 Google LLC")
    assert num == 15169
    assert "Google" in (org or "")


def test_residential_proxy_scoring():
    risk, _, _, flags, action = compute_threat_scores(
        is_vpn=False,
        is_proxy=True,
        is_tor=False,
        is_datacenter=False,
        is_residential_proxy=True,
        is_botnet=False,
        is_malicious=False,
        abuse_reports=0,
        reputation_score=60,
        asn=None,
        sources_count=2,
    )
    assert risk >= 28
    assert "residential_proxy" in flags


def test_botnet_and_tor_high_risk():
    report = ThreatIntelReport(
        ip_address="203.0.113.1",
        is_tor=True,
        is_botnet=True,
        abuse_reports=15,
        reputation_score=20,
        sources=["abuseipdb", "virustotal"],
    )
    report = apply_scores_to_report(report)
    assert report.risk_score >= 70
    assert report.recommended_action in ("block", "quarantine", "monitor")


def test_datacenter_asn_keywords():
    asn_data = analyze_asn(16509, "Amazon Data Services", is_hosting_flag=True)
    assert asn_data["is_datacenter"] is True
    report = ThreatIntelReport(
        ip_address="1.2.3.4",
        is_datacenter=True,
        asn=AsnInfo(**asn_data),
        sources=["ipqualityscore"],
    )
    report = apply_scores_to_report(report)
    assert any("datacenter" in f for f in report.flags)
