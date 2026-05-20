"""Tests for J48 training data sources (no DB)."""

from app.ml.weka_j48.features import ViewerMLRow, insights_record_to_features
from app.ml.weka_j48.sources import _dedupe_rows
from app.integrations.twitchinsights.bot_database import TwitchInsightsBotRecord


def test_dedupe_prefers_bot_label():
    rows = [
        ViewerMLRow(features=[0] * 11, label="no", platform_username="user1"),
        ViewerMLRow(features=[1] * 11, label="yes", platform_username="user1"),
    ]
    out = _dedupe_rows(rows)
    assert len(out) == 1
    assert out[0].label == "yes"


def test_insights_features_shape():
    rec = TwitchInsightsBotRecord(
        username="viewbot123",
        channel_count=42,
        last_seen_ts=1700000000,
        is_online_now=True,
    )
    feats = insights_record_to_features(rec)
    assert len(feats) == 11
    assert feats[2] >= 90  # risk_score high for online bot
