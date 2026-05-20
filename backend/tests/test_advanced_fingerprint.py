"""Tests del motor de fingerprinting avanzado."""

import pytest

from app.services.detection.advanced_fingerprint import AdvancedFingerprintEngine


@pytest.fixture
def engine():
    return AdvancedFingerprintEngine()


def test_selenium_and_webdriver_high_risk(engine):
    result = engine.analyze(
        {
            "user_agent": "Mozilla/5.0 Chrome/120.0",
            "platform": "Win32",
            "webdriver": True,
            "selenium": True,
            "canvas_hash": "abc123def",
            "webgl_hash": "gl123",
            "timezone": "America/New_York",
            "timezone_offset_minutes": 300,
            "session_id": "sess-1",
        }
    )
    assert result.risk_score >= 50
    assert result.is_automation
    assert "selenium_marker" in result.automation_flags
    assert result.trust_score < 50
    assert len(result.device_hash) == 64
    assert len(result.fingerprint_hash) == 64
    assert len(result.session_key) == 64


def test_headless_user_agent(engine):
    result = engine.analyze(
        {
            "user_agent": "Mozilla/5.0 HeadlessChrome/120.0",
            "platform": "Linux x86_64",
            "canvas_hash": "abcd12",
        }
    )
    assert result.is_headless
    assert "headless_user_agent" in result.automation_flags


def test_fake_user_agent_platform_mismatch(engine):
    result = engine.analyze(
        {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
            "platform": "Linux x86_64",
            "canvas_hash": "abcd12",
            "webgl_hash": "wgl1",
        }
    )
    assert "ua_platform_mismatch" in result.automation_flags


def test_canvas_spoof_swiftshader(engine):
    result = engine.analyze(
        {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0",
            "platform": "Win32",
            "canvas_hash": "abc",
            "webgl_renderer": "Google SwiftShader",
            "timezone": "Europe/Madrid",
            "timezone_offset_minutes": -60,
        }
    )
    assert "swiftshader_desktop" in result.automation_flags


def test_session_correlation_boost(engine):
    device = engine.compute_device_hash(
        {"canvas_hash": "x", "webgl_hash": "y", "screen_resolution": "1920x1080"}
    )
    sk1 = engine.compute_session_key(device, "tab-a")
    sk2 = engine.compute_session_key(device, "tab-b")
    result = engine.analyze(
        {
            "user_agent": "Mozilla/5.0 Chrome/120",
            "platform": "Win32",
            "canvas_hash": "x",
            "webgl_hash": "y",
            "screen_resolution": "1920x1080",
            "session_id": "tab-b",
        },
        prior_session_keys=[sk1],
    )
    assert sk1 != sk2
    assert result.correlation_strength > 0 or "session_cluster" in result.automation_flags


def test_clean_browser_high_trust(engine):
    result = engine.analyze(
        {
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0",
            "platform": "MacIntel",
            "canvas_hash": "validcanvashash123",
            "webgl_hash": "validwebgl123",
            "audio_hash": "audio1",
            "timezone": "Europe/Madrid",
            "timezone_offset_minutes": -60,
            "plugins_count": 3,
            "session_id": "real-user-1",
        }
    )
    assert result.trust_score >= 70
    assert result.risk_score < 40
