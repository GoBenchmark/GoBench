from gobench.api.schemas import Position
from gobench.katago.mock_client import MockKataGoClient


def test_mock_scoring_is_deterministic():
    position = Position(position_id="stable", to_move="B", black=["D4"], white=["Q16"])
    scorer = MockKataGoClient()
    first = scorer.score_move(position, "R14")
    second = scorer.score_move(position, "R14")
    assert first == second


def test_mock_scoring_penalizes_illegal_move():
    position = Position(position_id="illegal", to_move="B", black=["D4"], white=[])
    result = MockKataGoClient().score_move(position, "D4")
    assert not result.legal
    assert result.point_loss == 50.0
    assert result.catastrophic_blunder
