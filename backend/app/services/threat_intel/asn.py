"""Utilidades de análisis ASN."""

import re
from typing import Any, Dict, Optional, Tuple

from app.core.config import get_settings

settings = get_settings()

_ASN_RE = re.compile(r"AS(\d+)", re.I)

DATACENTER_KEYWORDS = (
    "AMAZON",
    "AWS",
    "GOOGLE",
    "GCP",
    "MICROSOFT",
    "AZURE",
    "DIGITALOCEAN",
    "HETZNER",
    "OVH",
    "CLOUDFLARE",
    "LINODE",
    "VULTR",
    "ORACLE",
    "ALIBABA",
    "TENCENT",
    "HOSTING",
    "DATACENTER",
    "COLOCATION",
    "SERVER",
    "CLOUD",
)


def parse_asn_field(value: Any) -> Tuple[Optional[int], Optional[str]]:
    if value is None:
        return None, None
    if isinstance(value, int):
        return value, None
    text = str(value).strip()
    match = _ASN_RE.search(text)
    if match:
        org = _ASN_RE.sub("", text).strip() or None
        return int(match.group(1)), org
    if text.isdigit():
        return int(text), None
    return None, text or None


def analyze_asn(
    asn_number: Optional[int],
    organization: Optional[str],
    *,
    is_hosting_flag: bool = False,
) -> Dict[str, Any]:
    org_upper = (organization or "").upper()
    keywords = list(settings.security_blocked_asn_keywords_list)
    matched = [k for k in keywords if k and k in org_upper]
    for kw in DATACENTER_KEYWORDS:
        if kw in org_upper and kw not in matched:
            matched.append(kw)

    is_datacenter = is_hosting_flag or bool(matched)
    return {
        "number": asn_number,
        "organization": organization,
        "is_datacenter": is_datacenter,
        "is_hosting": is_hosting_flag or is_datacenter,
        "risk_keywords": matched[:10],
    }
