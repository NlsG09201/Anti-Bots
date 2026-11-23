from types import SimpleNamespace

import pytest

from app.integrations.kick.client import KickAPIClient
from app.integrations.tiktok.webcast import UNAVAILABLE_REASON, fetch_tiktok_room
from app.integrations.kick.oauth import DEFAULT_SCOPES, KICK_WEBHOOK_EVENTS
from app.services.platforms.kick_adapter import KickPlatformAdapter
from app.services.platforms.tiktok_adapter import TikTokPlatformAdapter


@pytest.mark.asyncio
async def test_kick_fetches_current_active_chatters(monkeypatch):
    async def active_chatters(_client, channel_id):
        assert channel_id == "12345"
        return [{"username": "chat_user", "user_id": "chat_user", "role": "chatters"}]

    monkeypatch.setattr(KickAPIClient, "get_active_chatters", active_chatters)
    stream = SimpleNamespace(external_id="12345", settings={}, channel_name="channel")

    snapshots = await KickPlatformAdapter().fetch_viewers(stream)

    assert len(snapshots) == 1
    assert snapshots[0].platform_username == "chat_user"
    assert snapshots[0].is_in_chat is True
    assert snapshots[0].metadata["source"] == "kick_chat"


@pytest.mark.asyncio
async def test_tiktok_live_status_is_explicitly_unavailable():
    with pytest.raises(RuntimeError, match="official TikTok API access"):
        await TikTokPlatformAdapter().fetch_live_status(stream=None)


@pytest.mark.asyncio
async def test_tiktok_room_lookup_does_not_fall_back_to_web_scraping():
    with pytest.raises(RuntimeError, match="official TikTok API access"):
        await fetch_tiktok_room("creator")

    assert "TikTok LIVE status and chat are unavailable" in UNAVAILABLE_REASON


def test_kick_webhook_catalog_and_oauth_scope_match_documented_contract():
    assert set(KICK_WEBHOOK_EVENTS) == {
        "chat.message.sent",
        "channel.followed",
        "channel.subscription.new",
        "channel.subscription.renewal",
        "channel.subscription.gifts",
        "livestream.status.updated",
        "livestream.metadata.updated",
        "moderation.banned",
        "channel.reward.redemption.updated",
        "kicks.gifted",
    }
    assert "events:subscribe" in DEFAULT_SCOPES.split()
