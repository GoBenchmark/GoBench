from __future__ import annotations

from typing import Protocol

from gobench.api.schemas import CandidateEval, Position, ScoreResult

ILLEGAL_MOVE_PENALTY = 50.0


class ScorerProtocol(Protocol):
    def analyze_position(self, position: Position) -> list[CandidateEval]:
        ...

    def score_move(self, position: Position, submitted_move: str) -> ScoreResult:
        ...
