"""Tests for TwitchBots.info integration."""

import pytest

from app.integrations.twitchbots_info.client import TwitchBotsInfoClient
from app.integrations.twitchbots_info.schemas import (
    TwitchBotsBotRecord,
    UserReputationScores,
)


@pytest.mark.asyncio
async def test_client_fetch_nightbot():
    client = TwitchBotsInfoClient()
    record = await client.get_bot_by_id("19264788")
    assert record is not None
    assert record.username.lower() == "nightbot"
    assert record.is_known_bot is True


@pytest.mark.asyncio
async def test_client_batch_ids():
    client = TwitchBotsInfoClient()
    hits = await client.get_bots_by_ids(["19264788"])
    assert "19264788" in hits
    assert hits["19264788"].username


def test_reputation_known_bot():
    rec = TwitchBotsBotRecord(
        twitch_id="1",
        username="nightbot",
        type_name="Nightbot",
        type_id=1,
    )
    rep = UserReputationScores.for_known_bot(rec, base_risk=94.0)
    assert rep.bot_known_score == 100.0
    assert rep.suspicious_score >= 88.0
    assert rep.source_detection == "twitchbots_info"
