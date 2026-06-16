from __future__ import annotations

from gobench.api.schemas import CandidateEval, Position, ScoreResult
from gobench.core.coordinates import BOARD_COLUMNS
from gobench.core.legality import is_legal_move
from gobench.datasets.sample_data import target_stone_counts
from gobench.datasets.validate import validate_positions
from gobench.katago.selfplay import SelfPlayConfig, choose_selfplay_move, make_katago_selfplay_positions


class FakeSelfPlayScorer:
    def analyze_position(self, position: Position) -> list[CandidateEval]:
        moves: list[CandidateEval] = []
        rank = 0
        for row in range(1, position.board_size + 1):
            for col in BOARD_COLUMNS[: position.board_size]:
                move = f"{col}{row}"
                if is_legal_move(position, move):
                    moves.append(
                        CandidateEval(
                            move=move,
                            score_lead=10.0 - rank * 0.1,
                            policy=max(0.001, 0.2 - rank * 0.002),
                            visits=max(1, 200 - rank),
                        )
                    )
                    rank += 1
                    if len(moves) >= 30:
                        return moves
        return moves

    def score_move(self, position: Position, submitted_move: str) -> ScoreResult:
        return ScoreResult(
            position_id=position.position_id,
            submitted_move=submitted_move,
            legal=is_legal_move(position, submitted_move),
            point_loss=0.0,
            top1_match=True,
            top3_match=True,
            top10_match=True,
            blunder=False,
            catastrophic_blunder=False,
            phase=position.phase,
        )


def test_katago_selfplay_positions_use_independent_target_depths():
    positions = make_katago_selfplay_positions(
        FakeSelfPlayScorer(),
        SelfPlayConfig(count=3, seed=7, top_k=5, policy_temperature=1.0),
    )

    assert [position.position_id for position in positions] == ["dev_000001", "dev_000002", "dev_000003"]
    assert [len(position.move_history) for position in positions] == target_stone_counts(3)
    assert validate_positions(positions) == []
    assert positions[0].move_history != positions[1].move_history[: len(positions[0].move_history)]


def test_katago_selfplay_can_target_official_300_move_range():
    positions = make_katago_selfplay_positions(
        FakeSelfPlayScorer(),
        SelfPlayConfig(count=5, seed=7, top_k=5, policy_temperature=1.0, max_target_moves=300),
    )

    assert [len(position.move_history) for position in positions] == target_stone_counts(5, 5, 300)
    assert len(positions[-1].move_history) == 300


def test_katago_selfplay_seed_is_reproducible():
    first = make_katago_selfplay_positions(
        FakeSelfPlayScorer(),
        SelfPlayConfig(count=2, seed=99, top_k=6, policy_temperature=0.8),
    )
    second = make_katago_selfplay_positions(
        FakeSelfPlayScorer(),
        SelfPlayConfig(count=2, seed=99, top_k=6, policy_temperature=0.8),
    )

    assert [position.move_history for position in first] == [position.move_history for position in second]


def test_katago_selfplay_reports_progress():
    events: list[tuple[str, str, int, int]] = []
    make_katago_selfplay_positions(
        FakeSelfPlayScorer(),
        SelfPlayConfig(count=1, seed=11, top_k=3, policy_temperature=0.5),
        progress_callback=lambda progress: events.append(
            (progress.event, progress.position_id, progress.played_moves, progress.target_moves)
        ),
    )

    assert events[0] == ("start", "dev_000001", 0, 5)
    assert events[-1] == ("complete", "dev_000001", 5, 5)
    assert [event[0] for event in events].count("move") == 5


def test_choose_selfplay_move_filters_pass_and_illegal_moves():
    position = Position(position_id="choice", to_move="B", black=["D4"], white=[])
    candidates = [
        CandidateEval(move="pass", score_lead=11.0, policy=0.9),
        CandidateEval(move="D4", score_lead=10.0, policy=0.8),
        CandidateEval(move="Q16", score_lead=9.0, policy=0.7),
    ]

    move = choose_selfplay_move(
        position=position,
        candidates=candidates,
        rng=__import__("random").Random(1),
        top_k=3,
        policy_temperature=0.0,
    )

    assert move == "Q16"
