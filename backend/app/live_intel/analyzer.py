"""Engagement and viewbot heuristics for competitive live streams."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.live_intel.schemas import LiveStreamSnapshot


class LiveIntelAnalyzer:
    def analyze(
        self,
        *,
        viewers: int,
        prev_viewers: int,
        viewers_per_minute: float,
        messages_per_minute: float,
        follows_per_minute: float,
        chatters: int,
        viewer_history: List[Dict[str, Any]],
        rates: Dict[str, float | int],
    ) -> Tuple[LiveStreamSnapshot, List[str]]:
        flags: List[str] = []
        ratio = chatters / max(viewers, 1)
        growth_velocity = viewers_per_minute

        suspicious_growth = False
        if prev_viewers > 0 and viewers - prev_viewers > max(100, prev_viewers * 0.4):
            suspicious_growth = True
            flags.append("viewer_spike")
        if growth_velocity > 150:
            suspicious_growth = True
            flags.append("high_growth_velocity")

        engagement = min(
            100.0,
            ratio * 120 + min(25, messages_per_minute * 0.15) + min(15, chatters * 0.3),
        )
        if viewers > 200 and messages_per_minute < 2:
            flags.append("silent_audience")
        if follows_per_minute > 30:
            flags.append("follow_burst")

        synthetic_p = 0.0
        if viewers > 50 and ratio < 0.003:
            synthetic_p += 0.35
        if suspicious_growth:
            synthetic_p += 0.3
        if messages_per_minute > 180:
            synthetic_p += 0.15
        synthetic_p = min(1.0, synthetic_p)

        suspicious_score = min(
            100.0,
            synthetic_p * 55
            + (35 if suspicious_growth else 0)
            + min(20, follows_per_minute * 0.5),
        )
        organic = max(0.0, min(100.0, engagement - suspicious_score * 0.45))
        bot_p = min(1.0, synthetic_p * 0.6 + (0.25 if suspicious_growth else 0))
        viewbot_p = min(
            1.0,
            (0.4 if suspicious_growth else 0)
            + (0.35 if viewers > 100 and ratio < 0.002 else 0)
            + bot_p * 0.35,
        )
        trust = max(0.0, min(100.0, 100 - suspicious_score - bot_p * 25))

        if len(viewer_history) >= 4:
            counts = [int(h.get("count", 0)) for h in viewer_history[-6:]]
            if counts and max(counts) - min(counts) > 200 and min(counts) > 0:
                deltas = [counts[i] - counts[i - 1] for i in range(1, len(counts))]
                if deltas and max(abs(d) for d in deltas) > 80:
                    flags.append("erratic_viewer_curve")

        snap = LiveStreamSnapshot(
            stream_id="",
            tenant_id="",
            platform="",
            channel_name="",
            viewers=viewers,
            chatters=chatters,
            messages_per_minute=round(messages_per_minute, 2),
            viewers_per_minute=round(viewers_per_minute, 2),
            follows_per_minute=round(follows_per_minute, 2),
            viewer_to_chat_ratio=round(ratio, 5),
            engagement_score=round(engagement, 2),
            growth_velocity=round(growth_velocity, 2),
            organic_engagement_score=round(organic, 2),
            suspicious_activity_score=round(suspicious_score, 2),
            synthetic_audience_probability=round(synthetic_p, 4),
            live_trust_score=round(trust, 2),
            bot_probability=round(bot_p, 4),
            viewbot_probability=round(viewbot_p, 4),
            suspicious_growth=suspicious_growth,
            flags=flags,
        )
        return snap, flags
