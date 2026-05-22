"""Viewer flow analysis — viewbot, raid, followbot, engagement heuristics."""

from __future__ import annotations

import time
from typing import Dict, List, Tuple

from app.core.config import get_settings
from app.viewer_flow.schemas import (
    SuspiciousViewerFlow,
    ViewerFlowMetrics,
    ViewerFlowStreamSnapshot,
)
from app.viewer_flow.tracker import EntityFlowState, StreamFlowState

settings = get_settings()


def _count_recent(times_deque, window: float) -> int:
    now = time.monotonic()
    return sum(1 for t in times_deque if now - t <= window)


def analyze_stream(state: StreamFlowState) -> ViewerFlowStreamSnapshot:
    rates = state.rates_in_window(60.0)
    viewers = state.viewers_current
    mpm = rates["messages_per_minute"]
    fpm = rates["follows_per_minute"]
    vpm = rates["viewers_per_minute"]
    engagement = (mpm / max(viewers, 1)) * 100.0
    engagement = min(100.0, engagement)

    growth_velocity = vpm
    suspicious_growth = 0.0
    ai_flags: List[str] = []
    raid_likelihood = 0.0
    bot_probability = 0.0
    threat_score = 0.0

    if viewers >= 80 and engagement < 2.0:
        suspicious_growth += 35.0
        ai_flags.append("silent_mass_audience")
        bot_probability += 0.25
    if vpm >= 120 and engagement < 5.0:
        suspicious_growth += 40.0
        ai_flags.append("impossible_growth")
        bot_probability += 0.35
    if _count_recent(state.spike_times, 300) >= 2:
        suspicious_growth += 20.0
        ai_flags.append("repeated_spikes")
    if _count_recent(state.raid_burst_times, 600) >= 1:
        raid_likelihood = min(1.0, 0.5 + _count_recent(state.raid_burst_times, 600) * 0.2)
        ai_flags.append("raid_pattern")
        threat_score += 25.0
    if fpm >= 15 and mpm < 3.0:
        ai_flags.append("followbot_pattern")
        bot_probability += 0.2
        threat_score += 15.0
    if mpm >= 40:
        ai_flags.append("chat_flood")
        threat_score += 10.0

    silent_est = sum(1 for e in state.entities.values() if e.is_silent)
    if silent_est >= 10 and viewers >= 50:
        ai_flags.append("silent_viewers")
        bot_probability += min(0.4, silent_est / max(viewers, 1))

    coordinated = 0.0
    recent_entities = [
        e for e in state.entities.values() if time.monotonic() - e.first_seen < 90
    ]
    if len(recent_entities) >= 8 and mpm < 2:
        coordinated = min(100.0, len(recent_entities) * 4.0)
        ai_flags.append("coordinated_joins")

    suspicious_growth = min(100.0, suspicious_growth)
    bot_probability = min(1.0, bot_probability)
    threat_score = min(
        100.0,
        threat_score + suspicious_growth * 0.45 + bot_probability * 40.0,
    )
    trust_score = max(0.0, 100.0 - threat_score - bot_probability * 30.0)

    metrics = ViewerFlowMetrics(
        stream_id=state.stream_id,
        platform=state.platform,
        channel_name=state.channel_name,
        is_live=state.is_live,
        viewers_current=viewers,
        viewers_per_minute=round(vpm, 2),
        viewers_new_estimated=state.viewers_new_total,
        viewers_lost_estimated=state.viewers_lost_total,
        messages_per_minute=round(mpm, 2),
        follows_per_minute=round(fpm, 2),
        gifts_per_minute=round(rates["gifts_per_minute"], 2),
        engagement_ratio=round(engagement, 2),
        growth_velocity=round(growth_velocity, 2),
        suspicious_growth_score=round(suspicious_growth, 2),
        bot_probability=round(bot_probability, 4),
        trust_score=round(trust_score, 2),
        threat_score=round(threat_score, 2),
        raid_likelihood=round(raid_likelihood, 4),
        suspicious_score=round(suspicious_growth, 2),
        active_chatters=int(rates["active_chatters"]),
        silent_viewers_estimated=silent_est,
        coordinated_burst_score=round(coordinated, 2),
        ai_flags=ai_flags,
        updated_at=state._now_iso(),
    )

    suspicious = _rank_suspicious_entities(state, metrics)
    history = [
        {"t": state._now_iso(), "count": c}
        for _, c in list(state.viewer_samples)[-40:]
    ]

    return ViewerFlowStreamSnapshot(
        metrics=metrics,
        timeline=list(state.timeline)[-50:],
        suspicious_viewers=suspicious[:30],
        viewer_history=history,
    )


def _rank_suspicious_entities(
    state: StreamFlowState,
    metrics: ViewerFlowMetrics,
) -> List[SuspiciousViewerFlow]:
    rows: List[SuspiciousViewerFlow] = []
    for key, ent in state.entities.items():
        score, reasons = _entity_scores(ent, metrics)
        if score < 25 and not reasons:
            continue
        rows.append(
            SuspiciousViewerFlow(
                username=ent.username,
                platform_user_id=ent.platform_user_id,
                platform=state.platform,
                stream_id=state.stream_id,
                bot_probability=min(1.0, score / 100.0),
                suspicious_score=score,
                trust_score=max(0.0, 100.0 - score),
                reasons=reasons,
                message_count=ent.message_count,
                is_silent=ent.is_silent,
            )
        )
    rows.sort(key=lambda r: r.suspicious_score, reverse=True)
    return rows


def _entity_scores(
    ent: EntityFlowState,
    metrics: ViewerFlowMetrics,
) -> Tuple[float, List[str]]:
    score = 0.0
    reasons: List[str] = []
    if ent.is_silent and metrics.viewers_current >= 30:
        score += 40.0
        reasons.append("silent_in_chat")
    if ent.message_count >= 15 and ent.message_count == ent.join_signals:
        score += 25.0
        reasons.append("repetitive_activity")
    if ent.follow_count >= 3 and ent.message_count == 0:
        score += 30.0
        reasons.append("follow_only_bot")
    age = time.monotonic() - ent.first_seen
    if age < 30 and ent.message_count >= 8:
        score += 20.0
        reasons.append("burst_chat_new_account")
    for hint in ent.risk_hints:
        if hint not in reasons:
            reasons.append(hint)
            score += 15.0
    return min(100.0, score), reasons
