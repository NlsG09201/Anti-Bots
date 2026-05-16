from app.services.detection.engine import BotDetectionEngine, EventBatch


def test_headless_fingerprint_detection():
    engine = BotDetectionEngine()
    result = engine.analyze_fingerprint({
        "user_agent": "Mozilla/5.0 HeadlessChrome/120.0",
        "webdriver": True,
        "selenium": True,
        "plugins": [],
        "languages": [],
        "screen_resolution": "800x600",
    })
    assert result.is_threat
    assert result.risk_score >= 50
    assert "selenium" in str(result.evidence).lower() or result.threat_type == "automation"


def test_tor_ip_detection():
    engine = BotDetectionEngine()
    result = engine.analyze_ip({
        "is_tor": True,
        "is_vpn": False,
        "is_proxy": False,
        "is_datacenter": False,
        "reputation_score": 20,
        "abuse_reports": 10,
    })
    assert result.is_threat
    assert result.risk_score >= 40


def test_viewbot_velocity():
    engine = BotDetectionEngine()
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    events = [
        {
            "timestamp": (now + timedelta(seconds=i)).isoformat(),
            "ip_address": f"10.0.0.{i % 3}",
            "fingerprint_hash": "abc123",
        }
        for i in range(60)
    ]
    batch = EventBatch(events=events, stream_id="test")
    result = engine.analyze_viewbot_pattern(batch)
    assert result.risk_score > 0


def test_chat_spam_detection():
    engine = BotDetectionEngine()
    messages = [
        {"platform_user_id": "user1", "content": "spam link", "timestamp": "2024-01-01T00:00:00+00:00"}
        for _ in range(30)
    ]
    result = engine.analyze_chat_spam(messages)
    assert result.risk_score >= 25


def test_aggregate_risk():
    engine = BotDetectionEngine()
    from app.services.detection.engine import DetectionResult
    results = [
        DetectionResult(True, "viewbot", 75.0, 0.8, recommended_action="ban"),
        DetectionResult(True, "automation", 60.0, 0.7, recommended_action="quarantine"),
    ]
    score, threat, action = engine.aggregate_risk(results)
    assert score > 50
    assert threat in ("viewbot", "automation")
    assert action in ("ban", "quarantine", "shadow_ban", "block", "monitor", "mute", "timeout")
