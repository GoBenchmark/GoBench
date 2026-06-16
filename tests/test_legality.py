from gobench.api.schemas import Position
from gobench.core.board import Board
from gobench.core.legality import is_legal_move


def test_empty_occupied_and_pass_legality():
    position = Position(position_id="p1", to_move="B", black=["D4"], white=[])
    assert is_legal_move(position, "Q16")
    assert not is_legal_move(position, "D4")
    assert is_legal_move(position, "pass")


def test_capture_logic():
    position = Position(
        position_id="capture",
        to_move="B",
        black=["D5", "C4", "E4"],
        white=["D4"],
    )
    board = Board.from_position(position)
    legal, next_board = board.play_move("B", "D3")
    assert legal
    row, col = 15, 3  # D4
    assert next_board.grid[row][col] == "."


def test_suicide_prevention():
    position = Position(
        position_id="suicide",
        to_move="B",
        black=[],
        white=["D5", "C4", "E4", "D3"],
    )
    assert not is_legal_move(position, "D4")
