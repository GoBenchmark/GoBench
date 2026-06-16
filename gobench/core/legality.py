from __future__ import annotations

from gobench.api.schemas import Position
from gobench.core.board import Board
from gobench.core.coordinates import normalize_move


def is_legal_move(position: Position, move: str) -> bool:
    try:
        normalized = normalize_move(move)
    except ValueError:
        return False
    board = Board.from_position(position)
    legal, _ = board.play_move(position.to_move, normalized)
    return legal
