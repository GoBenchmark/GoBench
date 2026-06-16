from __future__ import annotations

from gobench.api.schemas import CandidateEval


def parse_candidate_evals(payload: dict) -> list[CandidateEval]:
    """Parse a small subset of KataGo analysis JSON into CandidateEval rows."""
    candidates = []
    for move_info in payload.get("moveInfos", []):
        candidates.append(
            CandidateEval(
                move=move_info["move"],
                score_lead=float(move_info.get("scoreLead", 0.0)),
                winrate=move_info.get("winrate"),
                policy=move_info.get("prior"),
                visits=move_info.get("visits"),
            )
        )
    return candidates
