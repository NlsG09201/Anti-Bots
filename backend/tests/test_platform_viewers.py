import pytest

from app.infrastructure.database.models import Platform, Stream, Tenant, User
from app.integrations.twitch.chat_filters import is_valid_chat_presence
from app.services.detection.viewer_bot_screening import ViewerBotScreeningService
from app.services.viewers.session import ViewerSessionService


def test_platform_chat_names_accept_display_names_beyond_twitch_login_rules():
    assert is_valid_chat_presence("María del Mar", "youtube_live_chat")
    assert is_valid_chat_presence("User.Name", "kick_chat")
    assert not is_valid_chat_presence("Injected\nName", "youtube_live_chat")
    assert not is_valid_chat_presence("Name/Other", "irc")


@pytest.mark.asyncio
async def test_kick_chat_snapshots_are_listed_without_inflating_join_risk(db_session):
    tenant = Tenant(name="Test Tenant", slug="platform-test")
    owner = User(
        tenant=tenant,
        email="platform-test@example.com",
        username="platformtest",
        hashed_password="hashed",
    )
    stream = Stream(
        tenant=tenant,
        owner=owner,
        platform=Platform.KICK,
        external_id="channel-slug",
        channel_name="Channel Name",
        settings={},
    )
    db_session.add_all([tenant, owner, stream])
    await db_session.flush()

    service = ViewerSessionService(db_session)
    for _ in range(6):
        await service.upsert_chat_viewer(
            stream.id,
            "Viewer Name",
            platform_user_id="kick-user-1",
            joins=0,
            messages=0,
            source="kick_chat",
        )

    viewers = await service.list_active(stream.id)

    assert len(viewers) == 1
    assert viewers[0].platform_username == "Viewer Name"
    assert viewers[0].risk_score == 0
    assert viewers[0].is_suspected_bot is False


@pytest.mark.asyncio
async def test_non_twitch_screening_does_not_use_twitch_only_bot_catalog(monkeypatch):
    def fail_if_twitch_catalog_is_loaded():
        raise AssertionError("Kick screening must not depend on Twitch Insights")

    monkeypatch.setattr(
        "app.services.detection.viewer_bot_screening.get_twitch_insights_db",
        fail_if_twitch_catalog_is_loaded,
    )

    verdicts = await ViewerBotScreeningService().analyze_usernames(
        "Kick channel",
        ["ordinaryviewer", "viewerbot123"],
        platform="kick",
    )

    assert verdicts["ordinaryviewer"]["classification"] == "no_strong_signals"
    assert verdicts["viewerbot123"]["classification"] == "review"
    assert verdicts["viewerbot123"]["is_malicious"] is False


@pytest.mark.asyncio
async def test_screening_does_not_flag_review_classification_as_confirmed_bot(
    db_session,
    monkeypatch,
):
    tenant = Tenant(name="Review Tenant", slug="review-tenant")
    owner = User(
        tenant=tenant,
        email="review@example.com",
        username="reviewowner",
        hashed_password="hashed",
    )
    stream = Stream(
        tenant=tenant,
        owner=owner,
        platform=Platform.KICK,
        external_id="kick-channel",
        channel_name="Kick Channel",
        settings={},
    )
    db_session.add_all([tenant, owner, stream])
    await db_session.flush()

    sessions = ViewerSessionService(db_session)
    await sessions.upsert_chat_viewer(
        stream.id,
        "viewerbot123",
        source="kick_chat",
    )

    class DummyInsightsDb:
        size = 0

    async def fake_analyze(self, channel, usernames, *, tbi_verdicts=None, platform="twitch"):
        return {
            username.lower(): {
                "classification": "review",
                "is_malicious": False,
                "risk_score": 55,
                "source": "pattern_db",
            }
            for username in usernames
        }

    monkeypatch.setattr(
        "app.services.detection.viewer_bot_screening.get_twitch_insights_db",
        lambda: DummyInsightsDb(),
    )
    monkeypatch.setattr(
        ViewerBotScreeningService,
        "analyze_usernames",
        fake_analyze,
    )

    result = await ViewerBotScreeningService().screen_and_update_sessions(
        db_session,
        stream.id,
        stream.channel_name,
        [{"username": "viewerbot123"}],
    )
    viewer = (await sessions.list_active(stream.id))[0]

    assert result["review_required"] == 1
    assert result["flagged"] == 0
    assert viewer.is_suspected_bot is False


@pytest.mark.asyncio
async def test_monitor_status_does_not_label_unidentified_viewers_as_bots(
    db_session,
    monkeypatch,
):
    tenant = Tenant(name="Status Tenant", slug="status-tenant")
    owner = User(
        tenant=tenant,
        email="status@example.com",
        username="statusowner",
        hashed_password="hashed",
    )
    stream = Stream(
        tenant=tenant,
        owner=owner,
        platform=Platform.YOUTUBE,
        external_id="youtube-video",
        channel_name="YouTube Channel",
        viewer_count=300,
        settings={},
    )
    db_session.add_all([tenant, owner, stream])
    await db_session.flush()

    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "app.api.v1.streams.ViewerSessionService.count_active",
        AsyncMock(return_value={"total": 20, "talking": 5, "suspected": 2}),
    )
    monkeypatch.setattr(
        "app.services.monitoring.proxy_intel.collect_proxy_threats",
        AsyncMock(return_value={"proxy_ips": [], "event_count": 0}),
    )

    from app.api.v1.streams import monitor_status

    result = await monitor_status(stream.id, owner, db_session)

    assert result["viewers_not_identifiable"] == 280
    assert "silent_viewbots_estimate" not in result
    assert "no se clasifican como bots" in result["note"].lower()
