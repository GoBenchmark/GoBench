from gobench.core.board import Board, EMPTY
from gobench.core.legality import is_legal_move
from gobench.datasets.sample_data import make_example_predictions, make_toy_positions, target_stone_counts
from gobench.datasets.validate import validate_positions


def test_public_dev_positions_span_full_game_density():
    positions = make_toy_positions(20)
    counts = [len(position.black) + len(position.white) for position in positions]

    assert counts == target_stone_counts(20)
    assert counts[0] == 5
    assert counts[-1] == 199
    assert all(left < right for left, right in zip(counts, counts[1:]))
    assert {position.phase for position in positions} == {
        "opening",
        "early_middle",
        "late_middle",
        "endgame",
    }
    assert validate_positions(positions) == []


def test_public_dev_static_boards_have_no_dead_groups():
    for position in make_toy_positions(20):
        board = Board.from_position(position)
        visited: set[tuple[int, int]] = set()
        for row, values in enumerate(board.grid):
            for col, value in enumerate(values):
                if value == EMPTY or (row, col) in visited:
                    continue
                group, liberties = board.group_and_liberties(row, col)
                visited.update(group)
                assert liberties, f"{position.position_id} has a no-liberty group"


def test_example_predictions_are_legal_for_full_game_positions():
    positions = make_toy_positions(20)
    predictions = make_example_predictions(positions)
    by_id = {position.position_id: position for position in positions}

    assert len(predictions) == len(positions)
    for prediction in predictions:
        assert is_legal_move(by_id[prediction.position_id], prediction.move)
