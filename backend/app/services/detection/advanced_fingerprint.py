"""
Motor de fingerprinting avanzado — detección de automatización, spoofing y correlación.
OWASP: client-side signals are hints; never trust alone for blocking.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

# Mapa aproximado UTC offset (minutos) → zonas IANA comunes (sin DST perfecto)
_TZ_OFFSET_HINTS: Dict[int, Set[str]] = {
    0: {"UTC", "Europe/London", "Africa/Abidjan"},
    -300: {"America/New_York", "America/Toronto", "America/Bogota"},
    -360: {"America/Chicago", "America/Mexico_City"},
    -420: {"America/Denver", "America/Phoenix"},
    -480: {"America/Los_Angeles", "America/Vancouver"},
    60: {"Europe/Berlin", "Europe/Paris", "Europe/Madrid"},
    120: {"Europe/Helsinki", "Africa/Cairo"},
    330: {"Asia/Kolkata"},
    480: {"Asia/Shanghai", "Asia/Singapore"},
    540: {"Asia/Tokyo", "Asia/Seoul"},
}


@dataclass
class AdvancedFingerprintResult:
    device_hash: str
    fingerprint_hash: str
    session_key: str
    trust_score: float
    risk_score: float
    confidence_score: float
    is_automation: bool
    is_headless: bool
    automation_flags: List[str] = field(default_factory=list)
    signals: Dict[str, Any] = field(default_factory=dict)
    correlated_sessions: List[str] = field(default_factory=list)
    correlation_strength: float = 0.0
    recommended_action: str = "none"


class AdvancedFingerprintEngine:
    WEIGHTS = {
        "fake_user_agent": 28.0,
        "canvas_spoof": 22.0,
        "webrtc_anomaly": 18.0,
        "timezone_mismatch": 20.0,
        "webdriver": 32.0,
        "headless": 30.0,
        "selenium": 35.0,
        "puppeteer": 35.0,
        "playwright": 35.0,
        "automation_generic": 25.0,
        "plugin_anomaly": 12.0,
        "client_hints_mismatch": 18.0,
    }

    HEADLESS_UA = re.compile(
        r"headless|phantomjs|slimerjs|splash|electron",
        re.I,
    )
    AUTOMATION_UA = re.compile(
        r"selenium|webdriver|puppeteer|playwright|automationcontrolled|python-requests",
        re.I,
    )

    def analyze(
        self,
        data: Dict[str, Any],
        *,
        server_ip: Optional[str] = None,
        prior_session_keys: Optional[List[str]] = None,
    ) -> AdvancedFingerprintResult:
        flags: List[str] = []
        signals: Dict[str, Any] = {}
        risk = 0.0
        checks_run = 0

        def add(flag: str, weight_key: str, detail: Any = None) -> None:
            nonlocal risk
            flags.append(flag)
            risk += self.WEIGHTS.get(weight_key, 15.0)
            if detail is not None:
                signals[flag] = detail

        ua = (data.get("user_agent") or "").strip()
        platform = (data.get("platform") or "").strip()
        checks_run += 1

        # --- User-Agent falsos / incoherentes ---
        if ua:
            if self.HEADLESS_UA.search(ua):
                add("headless_user_agent", "headless", ua[:120])
            if self.AUTOMATION_UA.search(ua):
                add("automated_user_agent", "automation_generic", ua[:120])
            mismatch = self._ua_platform_mismatch(ua, platform)
            if mismatch:
                add("ua_platform_mismatch", "fake_user_agent", mismatch)
                checks_run += 1
            hint_mismatch = self._client_hints_mismatch(ua, data.get("client_hints") or {})
            if hint_mismatch:
                add("client_hints_mismatch", "client_hints_mismatch", hint_mismatch)
                checks_run += 1
            uad = data.get("user_agent_data") or {}
            if uad:
                brand_mismatch = self._ua_data_mismatch(ua, uad)
                if brand_mismatch:
                    add("ua_data_mismatch", "fake_user_agent", brand_mismatch)
                    checks_run += 1
        else:
            add("missing_user_agent", "fake_user_agent")
            checks_run += 1

        # --- Canvas spoofing ---
        canvas = data.get("canvas_hash") or ""
        canvas_dup = data.get("canvas_duplicate_hash")
        if canvas_dup and canvas and canvas == canvas_dup and data.get("canvas_noise_expected"):
            add("canvas_static_fingerprint", "canvas_spoof", "identical_hashes_with_noise_probe")
        if data.get("canvas_noise_detected") is False and data.get("canvas_noise_expected"):
            add("canvas_noise_blocked", "canvas_spoof")
        if not canvas or len(str(canvas)) < 6:
            add("canvas_missing", "canvas_spoof")
        webgl_renderer = (data.get("webgl_renderer") or "").lower()
        if "swiftshader" in webgl_renderer and "mobile" not in ua.lower():
            add("swiftshader_desktop", "canvas_spoof", webgl_renderer)
        checks_run += 1

        # --- WebRTC anomalies ---
        webrtc = self._analyze_webrtc(data, server_ip)
        signals["webrtc"] = webrtc
        if webrtc.get("anomaly"):
            add(webrtc["anomaly"], "webrtc_anomaly", webrtc)
        checks_run += 1

        # --- Timezone inconsistencies ---
        tz_issue = self._timezone_inconsistency(data)
        if tz_issue:
            add("timezone_inconsistency", "timezone_mismatch", tz_issue)
        checks_run += 1

        # --- Automation frameworks ---
        if data.get("webdriver"):
            add("webdriver_property", "webdriver")
        if data.get("selenium"):
            add("selenium_marker", "selenium")
        if data.get("puppeteer"):
            add("puppeteer_marker", "puppeteer")
        if data.get("playwright"):
            add("playwright_marker", "playwright")

        headless_hints = data.get("headless_hints") or {}
        if headless_hints.get("chrome_headless"):
            add("chrome_headless_flag", "headless", headless_hints)
        if headless_hints.get("missing_chrome_runtime"):
            add("missing_chrome_runtime", "headless")
        if headless_hints.get("permissions_anomaly"):
            add("permissions_anomaly", "headless", headless_hints.get("permissions_anomaly"))

        plugins_count = data.get("plugins_count")
        if plugins_count is not None and "chrome" in ua.lower() and plugins_count == 0:
            add("chrome_zero_plugins", "plugin_anomaly", plugins_count)

        if data.get("outer_dimensions_zero"):
            add("zero_window_dimensions", "headless")

        checks_run += max(len(flags), 1)
        risk = min(risk, 100.0)
        trust_score = round(max(0.0, 100.0 - risk), 2)
        confidence_score = round(min(1.0, checks_run / 12.0), 3)

        device_hash = self.compute_device_hash(data)
        fingerprint_hash = self.compute_fingerprint_hash(data)
        session_id = (data.get("session_id") or "anonymous").strip()
        session_key = self.compute_session_key(device_hash, session_id)

        correlated: List[str] = []
        correlation_strength = 0.0
        if prior_session_keys:
            correlated = [k for k in prior_session_keys if k != session_key]
            if correlated:
                correlation_strength = min(1.0, len(correlated) / 5.0)
                flags.append("session_cluster")
                risk = min(100.0, risk + 10.0 * correlation_strength)

        is_automation = any(
            f in flags
            for f in (
                "webdriver_property",
                "selenium_marker",
                "puppeteer_marker",
                "playwright_marker",
                "automated_user_agent",
                "headless_user_agent",
            )
        )
        is_headless = any("headless" in f for f in flags)

        action = "none"
        if risk >= 80:
            action = "block"
        elif risk >= 60:
            action = "quarantine"
        elif risk >= 40:
            action = "monitor"

        return AdvancedFingerprintResult(
            device_hash=device_hash,
            fingerprint_hash=fingerprint_hash,
            session_key=session_key,
            trust_score=trust_score,
            risk_score=round(risk, 2),
            confidence_score=confidence_score,
            is_automation=is_automation,
            is_headless=is_headless,
            automation_flags=flags,
            signals=signals,
            correlated_sessions=correlated[:20],
            correlation_strength=round(correlation_strength, 3),
            recommended_action=action,
        )

    def compute_device_hash(self, data: Dict[str, Any]) -> str:
        stable = {
            "canvas": data.get("canvas_hash"),
            "webgl": data.get("webgl_hash"),
            "audio": data.get("audio_hash"),
            "screen": data.get("screen_resolution"),
            "platform": data.get("platform"),
            "languages": data.get("languages") or data.get("language"),
            "timezone": data.get("timezone"),
            "hardware": data.get("hardware_concurrency"),
        }
        return self._hash_payload(stable)

    def compute_fingerprint_hash(self, data: Dict[str, Any]) -> str:
        return self._hash_payload(data)

    def compute_session_key(self, device_hash: str, session_id: str) -> str:
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        raw = f"{device_hash}|{session_id}|{day}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _hash_payload(payload: Dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _ua_platform_mismatch(self, ua: str, platform: str) -> Optional[str]:
        if not platform:
            return None
        ua_l = ua.lower()
        plat_l = platform.lower()
        if "win" in ua_l and "linux" in plat_l:
            return f"ua_windows_vs_platform_{platform}"
        if "macintosh" in ua_l and "win" in plat_l:
            return f"ua_mac_vs_platform_{platform}"
        if "linux" in ua_l and "win" in plat_l:
            return f"ua_linux_vs_platform_{platform}"
        if "iphone" in ua_l and "win" in plat_l:
            return f"ua_ios_vs_platform_{platform}"
        return None

    def _client_hints_mismatch(self, ua: str, hints: Dict[str, Any]) -> Optional[str]:
        if not hints:
            return None
        ch_platform = (hints.get("platform") or "").lower()
        ua_l = ua.lower()
        if ch_platform == "windows" and "linux" in ua_l and "android" not in ua_l:
            return "sec_ch_platform_windows_vs_ua_linux"
        if ch_platform == "android" and "iphone" in ua_l:
            return "sec_ch_platform_android_vs_ua_ios"
        return None

    def _ua_data_mismatch(self, ua: str, uad: Dict[str, Any]) -> Optional[str]:
        brands = uad.get("brands") or []
        if not brands:
            return None
        brand_names = " ".join(
            str(b.get("brand", b) if isinstance(b, dict) else b).lower() for b in brands
        )
        ua_l = ua.lower()
        if "chrome" in brand_names and "firefox" in ua_l and "chrome" not in ua_l:
            return "brands_chrome_ua_firefox"
        if "chromium" in brand_names and "safari" in ua_l and "chrome" not in ua_l:
            return "brands_chromium_ua_safari_only"
        return None

    def _timezone_inconsistency(self, data: Dict[str, Any]) -> Optional[str]:
        tz_name = (data.get("timezone") or "").strip()
        offset = data.get("timezone_offset_minutes")
        if offset is None or not tz_name:
            return None
        try:
            offset = int(offset)
        except (TypeError, ValueError):
            return "invalid_timezone_offset"

        # Intl offset is opposite sign to JS getTimezoneOffset in some docs — normalize
        # JS: UTC+1 → getTimezoneOffset() = -60
        lookup_offsets = {offset, -offset, abs(offset)}
        expected_ranges: Set[str] = set()
        for o in lookup_offsets:
            expected_ranges |= _TZ_OFFSET_HINTS.get(int(o), set())
        if expected_ranges and tz_name not in expected_ranges:
            # tolerancia DST: comprobar prefijo de región
            region = tz_name.split("/")[0] if "/" in tz_name else tz_name
            if not any(region in z for z in expected_ranges):
                return {
                    "timezone": tz_name,
                    "offset_minutes": offset,
                    "expected_approx": list(expected_ranges)[:3],
                }
        return None

    def _analyze_webrtc(
        self, data: Dict[str, Any], server_ip: Optional[str]
    ) -> Dict[str, Any]:
        local_ips: List[str] = list(data.get("webrtc_local_ips") or [])
        public_ip = data.get("webrtc_public_ip")
        mdns = data.get("webrtc_mdns_host")
        failed = data.get("webrtc_failed", False)

        out: Dict[str, Any] = {
            "local_ips": local_ips,
            "public_ip": public_ip,
            "mdns": mdns,
            "failed": failed,
        }

        if failed and not local_ips and not public_ip:
            out["anomaly"] = "webrtc_unavailable"
            return out

        if local_ips and not any(
            ip.startswith(("10.", "172.", "192.168.", "127.")) for ip in local_ips
        ):
            out["anomaly"] = "webrtc_non_private_local_ips"
            return out

        if mdns and ".local" not in str(mdns).lower():
            out["anomaly"] = "webrtc_invalid_mdns"
            return out

        if server_ip and public_ip and public_ip != server_ip:
            out["server_ip_diff"] = {"webrtc": public_ip, "server": server_ip}

        return out
