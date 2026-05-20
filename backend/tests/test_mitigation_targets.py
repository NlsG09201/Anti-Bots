from app.services.mitigation.targets import dedupe_targets, session_to_user_target
from app.infrastructure.database.models import ViewerSession


def test_session_to_user_target_prefers_numeric_id():
    s = ViewerSession(
        stream_id="00000000-0000-0000-0000-000000000001",
        platform_user_id="12345678",
        platform_username="bot_user",
        ip_address="twitch:chat",
        risk_score=90,
    )
    assert session_to_user_target(s) == {"type": "user", "value": "12345678"}


def test_session_to_user_target_login_fallback():
    s = ViewerSession(
        stream_id="00000000-0000-0000-0000-000000000001",
        platform_user_id="bot_user",
        platform_username="BotUser",
        ip_address="twitch:chat",
        risk_score=90,
    )
    assert session_to_user_target(s) == {"type": "user_login", "value": "BotUser"}


def test_dedupe_targets():
    raw = [
        {"type": "ip", "value": "1.2.3.4"},
        {"type": "ip", "value": "1.2.3.4"},
        {"type": "user", "value": "99"},
    ]
    assert len(dedupe_targets(raw)) == 2
