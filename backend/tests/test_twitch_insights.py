from app.integrations.twitchinsights.bot_database import _parse_bot_rows
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
