from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean

from gobench.api.schemas import ScoreResult
from gobench.core.coordinates import is_pass

GOBENCH_SCORE_TAU = 2.0


def aggregate_metrics(results: list[ScoreResult]) -> dict[str, float | int | None | dict[str, float]]:
    if not results:
        return {
            "count": 0,
            "mean_point_loss": None,
            "gobench_score": None,
            "gobench_score_tau": GOBENCH_SCORE_TAU,
            "legal_move_rate": 0.0,
            "top1_match_rate": 0.0,
            "top3_match_rate": 0.0,
            "top10_match_rate": 0.0,
            "blunder_rate": 0.0,
            "catastrophic_blunder_rate": 0.0,
            "pass_rate": 0.0,
            "phase_mpl": {},
        }

    count = len(results)
    mpl = mean(result.point_loss for result in results)
    phase_losses: dict[str, list[float]] = defaultdict(list)
    for result in results:
        if result.phase:
            phase_losses[result.phase].append(result.point_loss)

    return {
        "count": count,
        "mean_point_loss": mpl,
        "gobench_score": gobench_score(mpl),
        "gobench_score_tau": GOBENCH_SCORE_TAU,
        "legal_move_rate": sum(result.legal for result in results) / count,
        "top1_match_rate": sum(result.top1_match for result in results) / count,
        "top3_match_rate": sum(result.top3_match for result in results) / count,
        "top10_match_rate": sum(result.top10_match for result in results) / count,
        "blunder_rate": sum(result.blunder for result in results) / count,
        "catastrophic_blunder_rate": sum(result.catastrophic_blunder for result in results) / count,
        "pass_rate": sum(is_pass(result.submitted_move) for result in results) / count,
        "phase_mpl": {phase: mean(losses) for phase, losses in phase_losses.items()},
    }


def gobench_score(mean_point_loss: float, tau: float = GOBENCH_SCORE_TAU) -> float:
    return 100.0 * math.exp(-mean_point_loss / tau)
