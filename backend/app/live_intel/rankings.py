"""Dynamic rankings for competitive live streams."""

from __future__ import annotations

from typing import List

from app.live_intel.schemas import LiveStreamSnapshot, StreamRankingEntry


def build_rankings(
    snapshots: List[LiveStreamSnapshot],
) -> dict[str, List[StreamRankingEntry]]:
    live = [s for s in snapshots if s.is_live]

    def rank_list(
        items: List[LiveStreamSnapshot],
        key: str,
        metric: str,
        reverse: bool = True,
    ) -> List[StreamRankingEntry]:
        sorted_items = sorted(
            items,
            key=lambda x: getattr(x, key, 0),
            reverse=reverse,
        )[:15]
        out: List[StreamRankingEntry] = []
        for i, s in enumerate(sorted_items, start=1):
            out.append(
                StreamRankingEntry(
                    stream_id=s.stream_id,
                    channel_name=s.channel_name,
                    platform=s.platform,
                    rank=i,
                    score=float(getattr(s, key, 0)),
                    metric=metric,
                    is_live=s.is_live,
                )
            )
        return out

    return {
        "most_suspicious": rank_list(live, "suspicious_activity_score", "suspicious"),
        "most_organic": rank_list(live, "organic_engagement_score", "organic"),
        "healthiest_engagement": rank_list(live, "engagement_score", "engagement"),
        "abnormal_growth": rank_list(live, "growth_velocity", "growth_velocity"),
        "highest_viewbot_risk": rank_list(live, "viewbot_probability", "viewbot"),
    }
