import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.ensemble import IsolationForest

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DetectionResult:
    is_threat: bool
    threat_type: str
    risk_score: float
    confidence: float
    evidence: Dict[str, Any] = field(default_factory=dict)
    recommended_action: str = "none"


@dataclass
class EventBatch:
    events: List[Dict[str, Any]]
    stream_id: str
    window_seconds: int = 60


class BotDetectionEngine:
    HEADLESS_INDICATORS = [
        "headless", "phantomjs", "selenium", "webdriver",
        "puppeteer", "playwright", "automationcontrolled",
    ]

    AUTOMATION_PLUGINS = ["selenium", "webdriver", "chrome-lighthouse"]

    WEIGHTS = {
        "headless_browser": 25.0,
        "automation_framework": 30.0,
        "proxy_vpn_tor": 20.0,
        "datacenter_ip": 15.0,
        "fingerprint_collision": 20.0,
        "synchronized_timing": 25.0,
        "view_velocity": 20.0,
        "chat_spam": 15.0,
        "follow_burst": 20.0,
        "asn_reputation": 15.0,
        "entropy_anomaly": 10.0,
        "behavioral_anomaly": 20.0,
    }

    def __init__(self):
        self._isolation_forest = IsolationForest(
            contamination=0.1,
            random_state=42,
            n_estimators=100,
        )
        self._model_trained = False

    def analyze_fingerprint(self, fp_data: Dict[str, Any]) -> DetectionResult:
        score = 0.0
        evidence: Dict[str, Any] = {"checks": []}

        ua = (fp_data.get("user_agent") or "").lower()
        for indicator in self.HEADLESS_INDICATORS:
            if indicator in ua:
                score += self.WEIGHTS["headless_browser"]
                evidence["checks"].append(f"headless_ua:{indicator}")
                break

        if fp_data.get("webdriver", False):
            score += self.WEIGHTS["automation_framework"]
            evidence["checks"].append("webdriver_detected")

        if fp_data.get("selenium", False):
            score += self.WEIGHTS["automation_framework"]
            evidence["checks"].append("selenium_detected")

        if fp_data.get("puppeteer", False):
            score += self.WEIGHTS["automation_framework"]
            evidence["checks"].append("puppeteer_detected")

        if fp_data.get("playwright", False):
            score += self.WEIGHTS["automation_framework"]
            evidence["checks"].append("playwright_detected")

        plugins = fp_data.get("plugins", []) or []
        if len(plugins) == 0 and "chrome" in ua:
            score += 10.0
            evidence["checks"].append("no_plugins_chrome")

        languages = fp_data.get("languages", [])
        if isinstance(languages, list) and len(languages) == 0:
            score += 5.0
            evidence["checks"].append("no_languages")

        screen = fp_data.get("screen_resolution", "")
        if screen in ("800x600", "1024x768", "0x0"):
            score += 8.0
            evidence["checks"].append(f"suspicious_screen:{screen}")

        if fp_data.get("occurrence_count", 1) > 10:
            score += self.WEIGHTS["fingerprint_collision"]
            evidence["checks"].append(f"high_collision:{fp_data['occurrence_count']}")

        score = min(score, 100.0)
        evidence["raw_score"] = score

        return DetectionResult(
            is_threat=score >= 50.0,
            threat_type="automation" if score >= 50.0 else "none",
            risk_score=score,
            confidence=min(score / 100.0, 1.0),
            evidence=evidence,
            recommended_action="quarantine" if score >= 70 else "monitor",
        )

    def analyze_ip(self, ip_data: Dict[str, Any]) -> DetectionResult:
        score = 0.0
        evidence: Dict[str, Any] = {"checks": []}

        if ip_data.get("is_tor"):
            score += self.WEIGHTS["proxy_vpn_tor"]
            evidence["checks"].append("tor_exit_node")

        if ip_data.get("is_vpn"):
            score += self.WEIGHTS["proxy_vpn_tor"] * 0.7
            evidence["checks"].append("vpn_detected")

        if ip_data.get("is_proxy"):
            score += self.WEIGHTS["proxy_vpn_tor"] * 0.5
            evidence["checks"].append("proxy_detected")

        if ip_data.get("is_datacenter") or ip_data.get("is_hosting"):
            score += self.WEIGHTS["datacenter_ip"]
            evidence["checks"].append("datacenter_ip")

        reputation = ip_data.get("reputation_score", 50.0)
        if reputation < 30:
            score += self.WEIGHTS["asn_reputation"]
            evidence["checks"].append(f"low_reputation:{reputation}")

        abuse_reports = ip_data.get("abuse_reports", 0)
        if abuse_reports > 5:
            score += min(abuse_reports * 2, 20)
            evidence["checks"].append(f"abuse_reports:{abuse_reports}")

        score = min(score, 100.0)
        return DetectionResult(
            is_threat=score >= 40.0,
            threat_type="malicious_ip" if score >= 40.0 else "none",
            risk_score=score,
            confidence=min(score / 100.0, 1.0),
            evidence=evidence,
            recommended_action="block" if score >= 80 else "quarantine" if score >= 50 else "monitor",
        )

    def analyze_viewbot_pattern(self, batch: EventBatch) -> DetectionResult:
        events = batch.events
        if len(events) < 5:
            return DetectionResult(False, "none", 0.0, 0.0)

        timestamps = [
            datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
            if isinstance(e.get("timestamp"), str)
            else e.get("timestamp", datetime.now(timezone.utc))
            for e in events
        ]
        ips = [e.get("ip_address") for e in events if e.get("ip_address")]
        fingerprints = [e.get("fingerprint_hash") for e in events if e.get("fingerprint_hash")]

        score = 0.0
        evidence: Dict[str, Any] = {"event_count": len(events)}

        if len(events) > 50:
            window = (max(timestamps) - min(timestamps)).total_seconds()
            if window > 0:
                velocity = len(events) / window
                evidence["view_velocity"] = velocity
                if velocity > 2.0:
                    score += self.WEIGHTS["view_velocity"]
                    evidence["pattern"] = "high_velocity_views"

        unique_ips = len(set(ips))
        if len(ips) > 10 and unique_ips / len(ips) < 0.3:
            score += 15.0
            evidence["ip_concentration"] = unique_ips / len(ips)

        unique_fps = len(set(fingerprints))
        if len(fingerprints) > 10 and unique_fps < 3:
            score += self.WEIGHTS["fingerprint_collision"]
            evidence["fingerprint_collision"] = unique_fps

        intervals = []
        sorted_ts = sorted(timestamps)
        for i in range(1, len(sorted_ts)):
            intervals.append((sorted_ts[i] - sorted_ts[i - 1]).total_seconds())

        if len(intervals) >= 3:
            std_dev = statistics.stdev(intervals)
            mean_interval = statistics.mean(intervals)
            if mean_interval > 0:
                cv = std_dev / mean_interval
                evidence["timing_cv"] = cv
                if cv < 0.1 and len(intervals) > 10:
                    score += self.WEIGHTS["synchronized_timing"]
                    evidence["pattern"] = "synchronized_joins"

        score = min(score, 100.0)
        return DetectionResult(
            is_threat=score >= 45.0,
            threat_type="viewbot" if score >= 45.0 else "none",
            risk_score=score,
            confidence=min(score / 100.0, 1.0),
            evidence=evidence,
            recommended_action="ban" if score >= 80 else "quarantine" if score >= 55 else "monitor",
        )

    def analyze_chat_spam(self, messages: List[Dict[str, Any]]) -> DetectionResult:
        if len(messages) < 3:
            return DetectionResult(False, "none", 0.0, 0.0)

        score = 0.0
        evidence: Dict[str, Any] = {"message_count": len(messages)}

        users = defaultdict(int)
        for msg in messages:
            users[msg.get("platform_user_id", "unknown")] += 1

        max_msgs = max(users.values()) if users else 0
        if max_msgs > 20:
            score += self.WEIGHTS["chat_spam"]
            evidence["max_messages_per_user"] = max_msgs

        contents = [m.get("content", "") for m in messages]
        unique_ratio = len(set(contents)) / len(contents) if contents else 1
        if unique_ratio < 0.2:
            score += 15.0
            evidence["duplicate_content_ratio"] = unique_ratio

        timestamps = [
            datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
            if isinstance(m.get("timestamp"), str)
            else m.get("timestamp", datetime.now(timezone.utc))
            for m in messages
        ]
        if len(timestamps) >= 2:
            window = (max(timestamps) - min(timestamps)).total_seconds()
            if window > 0 and len(messages) / window > 1.0:
                score += 10.0
                evidence["message_rate"] = len(messages) / window

        score = min(score, 100.0)
        return DetectionResult(
            is_threat=score >= 40.0,
            threat_type="spam" if score >= 40.0 else "none",
            risk_score=score,
            confidence=min(score / 100.0, 1.0),
            evidence=evidence,
            recommended_action="mute" if score >= 60 else "timeout" if score >= 40 else "monitor",
        )

    def analyze_follow_burst(self, follows: List[Dict[str, Any]]) -> DetectionResult:
        if len(follows) < 5:
            return DetectionResult(False, "none", 0.0, 0.0)

        score = 0.0
        evidence: Dict[str, Any] = {"follow_count": len(follows)}

        timestamps = sorted(
            datetime.fromisoformat(f["timestamp"].replace("Z", "+00:00"))
            if isinstance(f.get("timestamp"), str)
            else f.get("timestamp", datetime.now(timezone.utc))
            for f in follows
        )
        window = (timestamps[-1] - timestamps[0]).total_seconds()
        if window < 60 and len(follows) > 20:
            score += self.WEIGHTS["follow_burst"]
            evidence["burst_rate"] = len(follows) / max(window, 1)

        account_ages = [f.get("account_age_days", 365) for f in follows]
        young_accounts = sum(1 for age in account_ages if age < 7)
        if young_accounts / len(follows) > 0.7:
            score += 15.0
            evidence["young_account_ratio"] = young_accounts / len(follows)

        score = min(score, 100.0)
        return DetectionResult(
            is_threat=score >= 50.0,
            threat_type="followbot" if score >= 50.0 else "none",
            risk_score=score,
            confidence=min(score / 100.0, 1.0),
            evidence=evidence,
            recommended_action="ban" if score >= 75 else "shadow_ban" if score >= 55 else "monitor",
        )

    def compute_entropy(self, values: List[str]) -> float:
        if not values:
            return 0.0
        counts: Dict[str, int] = defaultdict(int)
        for v in values:
            counts[v] += 1
        total = len(values)
        entropy = 0.0
        for count in counts.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)
        return entropy

    def ml_anomaly_detect(self, feature_vectors: List[List[float]]) -> List[bool]:
        if len(feature_vectors) < 10:
            return [False] * len(feature_vectors)

        X = np.array(feature_vectors)
        if not self._model_trained:
            self._isolation_forest.fit(X)
            self._model_trained = True

        predictions = self._isolation_forest.predict(X)
        return [p == -1 for p in predictions]

    def aggregate_risk(
        self,
        results: List[DetectionResult],
    ) -> Tuple[float, str, str]:
        if not results:
            return 0.0, "none", "none"

        threat_results = [r for r in results if r.is_threat]
        if not threat_results:
            max_score = max(r.risk_score for r in results)
            return max_score, "none", "monitor"

        max_result = max(threat_results, key=lambda r: r.risk_score)
        combined_score = min(
            sum(r.risk_score for r in threat_results) / len(threat_results) * 1.2,
            100.0,
        )
        threat_types = [r.threat_type for r in threat_results if r.threat_type != "none"]
        primary_threat = max(set(threat_types), key=threat_types.count) if threat_types else "unknown"

        actions = [r.recommended_action for r in threat_results]
        action_priority = {"ban": 5, "block": 5, "quarantine": 4, "shadow_ban": 3, "mute": 2, "timeout": 2, "monitor": 1, "none": 0}
        best_action = max(actions, key=lambda a: action_priority.get(a, 0))

        return combined_score, primary_threat, best_action
