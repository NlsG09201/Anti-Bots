"""Exact binary knapsack solver for analyst review prioritization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ReviewCandidate:
    session_id: str
    stream_name: str
    username: str
    risk_score: float


def optimize_review_queue(
    candidates: Iterable[ReviewCandidate],
    capacity_minutes: int,
    minutes_per_review: int,
    false_positive_budget: int,
    false_positive_cost: float = 1.0,
) -> dict:
    """Solve binary knapsack exactly via DP using centi-risk integer units.

    risk_score is a system score, not a calibrated probability. For transparent
    operational use, score/100 is used as a priority proxy and (1-p) as a
    conservative exposure proxy. The analyst still makes all enforcement decisions.
    """
    rows = list(candidates)
    if capacity_minutes < 1 or minutes_per_review < 1:
        raise ValueError("La capacidad y el tiempo por revisión deben ser positivos.")
    if not 0 <= false_positive_budget <= 100:
        raise ValueError("El presupuesto de exposición debe estar entre 0 y 100.")
    if false_positive_cost < 0:
        raise ValueError("El costo de falso positivo no puede ser negativo.")

    # Budget is represented in centi-points, preserving a 0.01-point precision.
    budget = false_positive_budget * 100
    max_reviews = capacity_minutes // minutes_per_review
    dp: dict[tuple[int, int], tuple[float, tuple[int, ...]]] = {(0, 0): (0.0, ())}
    eligible = []
    for candidate in rows:
        p = min(1.0, max(0.0, float(candidate.risk_score) / 100.0))
        exposure = int(round(false_positive_cost * (1.0 - p) * 10000))
        value = p - false_positive_cost * (1.0 - p)
        if exposure > budget or value <= 0:
            continue
        eligible.append((candidate, exposure, value))

    for index, (_, exposure, value) in enumerate(eligible):
        next_dp = dict(dp)
        for (used, count), (score, selected) in dp.items():
            if count >= max_reviews:
                continue
            new_used = used + exposure
            if new_used > budget:
                continue
            new_score = score + value
            key = (new_used, count + 1)
            prior = next_dp.get(key)
            if prior is None or new_score > prior[0]:
                next_dp[key] = (new_score, selected + (index,))
        dp = next_dp

    best_score, chosen = max(dp.values(), key=lambda entry: entry[0])
    selected = [eligible[index][0] for index in chosen]
    selected.sort(key=lambda item: item.risk_score, reverse=True)
    used_minutes = len(selected) * minutes_per_review
    exposure_points = sum(eligible[index][1] for index in chosen) / 100
    return {
        "solver": "exact dynamic programming (0-1 knapsack)",
        "candidate_count": len(rows),
        "eligible_count": len(eligible),
        "selected_count": len(selected),
        "max_review_count": max_reviews,
        "capacity_minutes": capacity_minutes,
        "minutes_per_review": minutes_per_review,
        "used_minutes": used_minutes,
        "unused_minutes": capacity_minutes - used_minutes,
        "false_positive_budget": false_positive_budget,
        "estimated_exposure_points": round(exposure_points, 2),
        "objective_value": round(best_score, 4),
        "selected": [
            {
                "session_id": item.session_id,
                "stream_name": item.stream_name,
                "username": item.username,
                "risk_score": round(float(item.risk_score), 2),
                "priority_proxy": round(min(1.0, max(0.0, float(item.risk_score) / 100)), 4),
            }
            for item in selected
        ],
        "assumptions": [
            "La puntuación de riesgo del sistema se usa como proxy de prioridad; no es una probabilidad calibrada.",
            "Cada revisión consume el mismo tiempo indicado por el analista.",
            "La exposición estimada no es una tasa observada de falsos positivos.",
            "La salida ordena revisión humana y nunca aplica bloqueos automáticamente.",
        ],
    }
