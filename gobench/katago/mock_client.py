from __future__ import annotations

import hashlib
import random

from gobench.api.schemas import CandidateEval, Position, ScoreResult
from gobench.core.coordinates import BOARD_COLUMNS, normalize_move
from gobench.core.legality import is_legal_move
from gobench.core.scoring import ILLEGAL_MOVE_PENALTY


class MockKataGoClient:
    """Deterministic fake scorer for development and tests."""

    def analyze_position(self, position: Position) -> list[CandidateEval]:
        seed = stable_int(f"{position.position_id}:{position.to_move}:candidates")
        rng = random.Random(seed)
        moves: list[str] = []
        attempts = 0
        while len(moves) < 10 and attempts < 500:
            attempts += 1
            move = f"{rng.choice(BOARD_COLUMNS)}{rng.randint(1, position.board_size)}"
            if move not in moves and is_legal_move(position, move):
                moves.append(move)
        if is_legal_move(position, "pass") and "pass" not in moves:
            moves.append("pass")

        base_score = 10.0 + (stable_int(position.position_id) % 700) / 100.0
        candidates: list[CandidateEval] = []
        for rank, move in enumerate(moves[:10]):
            candidates.append(
                CandidateEval(
                    move=move,
                    score_lead=round(base_score - rank * 0.9, 3),
                    winrate=max(0.01, min(0.99, 0.75 - rank * 0.035)),
                    policy=round(max(0.01, 0.35 - rank * 0.025), 3),
                    visits=max(1, 1000 - rank * 80),
                )
            )
        return candidates

    def score_move(self, position: Position, submitted_move: str) -> ScoreResult:
        try:
            move = normalize_move(submitted_move)
        except ValueError:
            return self._illegal_result(position, submitted_move)

        if not is_legal_move(position, move):
            return self._illegal_result(position, move)

        candidates = self.analyze_position(position)
        candidate_moves = [candidate.move for candidate in candidates]
        best_score = max((candidate.score_lead for candidate in candidates), default=0.0)

        if move in candidate_moves:
            candidate = candidates[candidate_moves.index(move)]
            point_loss = max(0.0, best_score - candidate.score_lead)
        else:
            point_loss = 1.0 + (stable_int(f"{position.position_id}:{move}:loss") % 2400) / 100.0

        point_loss = round(point_loss, 3)
        return ScoreResult(
            position_id=position.position_id,
            submitted_move=move,
            legal=True,
            point_loss=point_loss,
            top1_match=bool(candidate_moves and move == candidate_moves[0]),
            top3_match=move in candidate_moves[:3],
            top10_match=move in candidate_moves[:10],
            blunder=point_loss > 5,
            catastrophic_blunder=point_loss > 15,
            phase=position.phase,
        )

    def _illegal_result(self, position: Position, move: str) -> ScoreResult:
        return ScoreResult(
            position_id=position.position_id,
            submitted_move=move,
            legal=False,
            point_loss=ILLEGAL_MOVE_PENALTY,
            top1_match=False,
            top3_match=False,
            top10_match=False,
            blunder=True,
            catastrophic_blunder=True,
            phase=position.phase,
        )


def stable_int(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:16], 16)
