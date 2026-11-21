from app.api.v1.operations_research import ReviewOptimizationRequest
from app.services.optimization.review_queue import (
    ReviewCandidate,
    optimize_review_queue,
)


def candidate(risk_score: float) -> ReviewCandidate:
    return ReviewCandidate(
        session_id=f"session-{risk_score}",
        stream_name="channel",
        username="viewer",
        risk_score=risk_score,
    )


def test_default_budget_can_select_a_session_at_the_detection_threshold():
    result = optimize_review_queue(
        [candidate(55)],
        capacity_minutes=60,
        minutes_per_review=5,
        false_positive_budget=ReviewOptimizationRequest(
            capacity_minutes=60,
        ).false_positive_budget,
        false_positive_cost=1,
    )

    assert result["candidate_count"] == 1
    assert result["eligible_count"] == 1
    assert result["selected_count"] == 1
    assert result["estimated_exposure_points"] == 45


def test_low_budget_reports_candidates_as_ineligible_instead_of_missing():
    result = optimize_review_queue(
        [candidate(55)],
        capacity_minutes=60,
        minutes_per_review=5,
        false_positive_budget=20,
        false_positive_cost=1,
    )

    assert result["candidate_count"] == 1
    assert result["eligible_count"] == 0
    assert result["selected_count"] == 0


def test_insufficient_capacity_is_distinguishable_from_no_candidates():
    result = optimize_review_queue(
        [candidate(80)],
        capacity_minutes=4,
        minutes_per_review=5,
        false_positive_budget=50,
        false_positive_cost=1,
    )

    assert result["candidate_count"] == 1
    assert result["eligible_count"] == 1
    assert result["max_review_count"] == 0
    assert result["selected_count"] == 0
