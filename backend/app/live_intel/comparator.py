"""Side-by-side comparison of live streams."""

from __future__ import annotations

from typing import Dict, List

from app.live_intel.schemas import LiveStreamSnapshot, StreamComparisonRow


def compare_streams(
    snapshots: Dict[str, LiveStreamSnapshot],
    stream_ids: List[str],
) -> List[StreamComparisonRow]:
    rows: List[StreamComparisonRow] = []
    for sid in stream_ids:
        s = snapshots.get(sid)
        if not s:
            continue
        rows.append(
            StreamComparisonRow(
                stream_id=s.stream_id,
                channel_name=s.channel_name,
                platform=s.platform,
                viewers=s.viewers,
                messages_per_minute=s.messages_per_minute,
                engagement_score=s.engagement_score,
                growth_velocity=s.growth_velocity,
                bot_probability=s.bot_probability,
                organic_engagement_score=s.organic_engagement_score,
                suspicious_activity_score=s.suspicious_activity_score,
            )
        )
    return rows


def detect_comparison_anomalies(rows: List[StreamComparisonRow]) -> List[str]:
    insights: List[str] = []
    if len(rows) < 2:
        return insights
    viewers = [r.viewers for r in rows]
    engagement = [r.engagement_score for r in rows]
    bots = [r.bot_probability for r in rows]
    max_v, min_v = max(viewers), min(viewers)
    if max_v > 0 and max_v > min_v * 5:
        insights.append(
            "Diferencia extrema de viewers entre canales comparados."
        )
    if max(engagement) - min(engagement) > 40:
        insights.append("Engagement muy desigual — posible audiencia artificial en un canal.")
    if max(bots) > 0.65 and min(bots) < 0.2:
        insights.append("Un canal muestra probabilidad de bot mucho mayor que el resto.")
    return insights[:6]
