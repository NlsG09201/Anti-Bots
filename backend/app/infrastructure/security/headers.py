"""Validación de cabeceras HTTP y detección de automatización (OWASP API4, ASVS V13)."""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fastapi import Request

from app.core.config import get_settings

settings = get_settings()

BOT_UA_PATTERNS = re.compile(
    r"(bot|crawler|spider|scraper|curl|wget|python-requests|go-http|java/|libwww|"
    r"headless|selenium|puppeteer|playwright|phantomjs|httpclient)",
    re.I,
)

SUSPICIOUS_PATHS = re.compile(
    r"(\.\./|/etc/passwd|/proc/|union\s+select|<script|javascript:)",
    re.I,
)


@dataclass
class HeaderValidationResult:
    allowed: bool
    risk_score: float = 0.0
    flags: List[str] = field(default_factory=list)
    automation_detected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "risk_score": self.risk_score,
            "flags": self.flags,
            "automation_detected": self.automation_detected,
        }


def validate_request_headers(request: Request, *, is_widget: bool = False) -> HeaderValidationResult:
    result = HeaderValidationResult(allowed=True)
    path = request.url.path
    method = request.method.upper()

    if any(request.url.path.startswith(p) for p in ("/health", "/metrics")):
        return result

    host = request.headers.get("host", "")
    if host and ("\r" in host or "\n" in host or "@" in host):
        result.flags.append("host_header_anomaly")
        result.risk_score += 40.0
        result.allowed = False

    content_type = request.headers.get("content-type", "")
    if method in ("POST", "PUT", "PATCH") and path.startswith("/api"):
        if not is_widget and "application/json" not in content_type.lower():
            if "multipart" not in content_type.lower():
                result.flags.append("missing_json_content_type")
                result.risk_score += 8.0

    ua = request.headers.get("user-agent", "")
    if path.startswith("/api") and not is_widget:
        if not ua:
            result.flags.append("missing_user_agent")
            result.risk_score += 25.0
            if settings.security_block_empty_ua:
                result.allowed = False
        elif BOT_UA_PATTERNS.search(ua):
            result.flags.append("automated_user_agent")
            result.automation_detected = True
            result.risk_score += 30.0

    # Sec-Fetch-* (navegadores modernos; ausencia con UA de Chrome = sospechoso)
    if ua and "chrome" in ua.lower() and not is_widget and path.startswith("/api/v1/auth"):
        if not request.headers.get("sec-fetch-site") and settings.security_strict_browser_headers:
            result.flags.append("missing_sec_fetch")
            result.risk_score += 12.0
            result.automation_detected = True

    accept = request.headers.get("accept", "")
    if ua and "mozilla" in ua.lower() and not accept and not is_widget:
        result.flags.append("missing_accept")
        result.risk_score += 10.0

    # Cabeceras de automatización explícitas
    for header in ("X-Automation", "X-WebDriver", "X-Selenium", "X-Puppeteer"):
        if request.headers.get(header):
            result.flags.append(f"automation_header:{header}")
            result.automation_detected = True
            result.risk_score += 35.0

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        pass
    elif method == "POST" and path.startswith("/api/v1/detection"):
        if not request.headers.get("authorization") and not request.headers.get("cookie"):
            result.flags.append("unauthenticated_detection_post")
            result.risk_score += 5.0

    query = str(request.url.query)
    if SUSPICIOUS_PATHS.search(path) or SUSPICIOUS_PATHS.search(query):
        result.flags.append("injection_pattern_in_url")
        result.risk_score += 50.0
        result.allowed = False

    if result.risk_score >= settings.security_header_block_threshold:
        result.allowed = False

    result.risk_score = min(result.risk_score, 100.0)
    return result
