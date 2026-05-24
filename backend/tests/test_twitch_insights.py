import pytest

from app.integrations.twitchinsights.bot_database import _parse_bot_rows
from app.infrastructure.database.models import Platform, Stream, Tenant, User
from app.services.detection import viewer_bot_screening as screening_module
from app.services.detection.viewer_bot_screening import ViewerBotScreeningService


def test_parse_bot_rows():
    rows = [["Slocool", 26012, 1565348543], ["decafsmurf", 5742, 1536468472]]
    parsed = _parse_bot_rows(rows)
    assert "slocool" in parsed
    assert parsed["slocool"].channel_count == 26012
    assert parsed["decafsmurf"].last_seen_ts == 1536468472


def test_local_verdict_twitch_insights_hit():
    svc = ViewerBotScreeningService()
    from app.integrations.twitchinsights.bot_database import TwitchInsightsBotRecord

    rec = TwitchInsightsBotRecord(
        username="test_viewbot",
        channel_count=120,
        last_seen_ts=1715883379,
        is_online_now=True,
    )
    verdict = svc._local_verdict("test_viewbot", rec)
    assert verdict["is_malicious"] is True
    assert verdict["source"] == "twitch_insights"
    assert verdict["risk_score"] >= 90
    assert "Twitch Insights" in verdict["risk_description"]


@pytest.mark.asyncio
async def test_screen_and_update_sessions_ignores_twitchbots_batch_failures(
    db_session,
    monkeypatch,
):
    tenant = Tenant(name="Test Tenant", slug="test-tenant")
    user = User(
        tenant=tenant,
        email="streamer@test.com",
        username="streamer",
        hashed_password="hashed",
    )
    stream = Stream(
        tenant=tenant,
        owner=user,
        platform=Platform.TWITCH,
        external_id="123",
        channel_name="testchannel",
        settings={},
    )
    db_session.add_all([tenant, user, stream])
    await db_session.flush()

    class DummyInsightsDb:
        size = 0

        async def ensure_loaded(self):
            return True

        def lookup(self, _username):
            return None

    class FailingTwitchBotsService:
        enabled = True

        async def verify_batch(self, *args, **kwargs):
            raise RuntimeError("twitchbots unavailable")

    async def fake_analyze_usernames(self, channel_name, usernames, *, tbi_verdicts=None):
        assert channel_name == "testchannel"
        assert usernames == ["viewer123"]
        assert tbi_verdicts == {}
        return {}

    monkeypatch.setattr(
        screening_module,
        "get_twitch_insights_db",
        lambda: DummyInsightsDb(),
    )
    monkeypatch.setattr(
        screening_module,
        "get_twitchbots_verification_service",
        lambda: FailingTwitchBotsService(),
    )
    monkeypatch.setattr(
        ViewerBotScreeningService,
        "analyze_usernames",
        fake_analyze_usernames,
    )

    result = await ViewerBotScreeningService().screen_and_update_sessions(
        db_session,
        stream.id,
        stream.channel_name,
        [{"username": "viewer123"}],
    )

    assert result["screened"] == 1
    assert result["flagged"] == 0
    assert result["twitchbots_info_matched"] == 0
