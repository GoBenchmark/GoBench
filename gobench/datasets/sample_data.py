from __future__ import annotations

from gobench.api.schemas import MoveSubmission, Position
from gobench.core.board import Board, EMPTY
from gobench.core.coordinates import BOARD_COLUMNS, coord_to_point
from gobench.core.legality import is_legal_move

PHASES = ["opening", "early_middle", "late_middle", "endgame"]
OPENING_MOVES: list[tuple[str, str]] = [
    ("B", "D4"),
    ("W", "Q16"),
    ("B", "Q4"),
    ("W", "D16"),
    ("B", "K10"),
    ("W", "C6"),
    ("B", "R14"),
    ("W", "F17"),
    ("B", "P3"),
    ("W", "C14"),
]
PUBLIC_DEV_MIN_TARGET_MOVES = 5
PUBLIC_DEV_MAX_TARGET_MOVES = 199
PUBLIC_DEV_DEFAULT_COUNT = 10
SYNTHETIC_GAME_LENGTH = 220


def make_toy_positions(n: int) -> list[Position]:
    game = make_synthetic_game(SYNTHETIC_GAME_LENGTH)
    targets = target_stone_counts(n)
    positions: list[Position] = []
    for index, history_len in enumerate(targets):
        history = game[:history_len]
        black = [move for color, move in history if color == "B"]
        white = [move for color, move in history if color == "W"]
        to_move = "B" if history[-1][0] == "W" else "W"
        positions.append(
            Position(
                position_id=f"dev_{index + 1:06d}",
                to_move=to_move,
                black=black,
                white=white,
                move_history=history,
                phase=phase_for_stone_count(history_len),
            )
        )
    return positions


def make_example_predictions(positions: list[Position]) -> list[MoveSubmission]:
    fallback_moves = ["R14", "C6", "K10", "Q10", "pass"]
    return [
        MoveSubmission(
            position_id=position.position_id,
            move=example_move_for_position(
                position,
                [
                    *rotate(synthetic_board_order(), index * 17),
                    *[move for move in rotate(fallback_moves, index) if move != "pass"],
                    "pass",
                ],
            ),
        )
        for index, position in enumerate(positions)
    ]


def example_move_for_position(position: Position, preferred_moves: list[str]) -> str:
    for move in preferred_moves:
        if is_legal_move(position, move):
            return move
    return "pass"


def rotate(values: list[str], offset: int) -> list[str]:
    split = offset % len(values)
    return [*values[split:], *values[:split]]


def target_stone_counts(
    n: int,
    min_target_moves: int = PUBLIC_DEV_MIN_TARGET_MOVES,
    max_target_moves: int = PUBLIC_DEV_MAX_TARGET_MOVES,
) -> list[int]:
    if n < 1:
        return []
    if n == 1:
        return [min_target_moves]
    return [
        round(min_target_moves + index * (max_target_moves - min_target_moves) / (n - 1))
        for index in range(n)
    ]


def phase_for_stone_count(stone_count: int) -> str:
    if stone_count <= 40:
        return "opening"
    if stone_count <= 100:
        return "early_middle"
    if stone_count <= 160:
        return "late_middle"
    return "endgame"


def make_synthetic_game(length: int) -> list[tuple[str, str]]:
    moves: list[str] = []
    seen: set[str] = set()

    def add(move: str) -> bool:
        if move not in seen:
            seen.add(move)
            moves.append(move)
            return True
        return False

    for _, move in OPENING_MOVES:
        add(move)

    candidates = [move for move in synthetic_board_order() if move not in seen]
    while len(moves) < length and candidates:
        for index, move in enumerate(candidates):
            if static_position_has_liberties(moves + [move]):
                add(move)
                candidates.pop(index)
                break
        else:
            break

    colors = ["B", "W"]
    return [(colors[index % 2], move) for index, move in enumerate(moves[:length])]


def synthetic_board_order() -> list[str]:
    candidates: list[tuple[tuple[int, int], str]] = []
    for row in range(19):
        for col in range(19):
            coordinate = f"{BOARD_COLUMNS[col]}{19 - row}"
            spread_key = (row * 37 + col * 17) % (19 * 19)
            center_distance = abs(row - 9) + abs(col - 9)
            candidates.append(((spread_key, center_distance), coordinate))
    return [coordinate for _, coordinate in sorted(candidates)]


def static_position_has_liberties(moves: list[str]) -> bool:
    board = Board()
    for index, move in enumerate(moves):
        row, col = coord_to_point(move)
        board.grid[row][col] = "B" if index % 2 == 0 else "W"

    visited: set[tuple[int, int]] = set()
    for row, values in enumerate(board.grid):
        for col, value in enumerate(values):
            if value == EMPTY or (row, col) in visited:
                continue
            group, liberties = board.group_and_liberties(row, col)
            visited.update(group)
            if not liberties:
                return False
    return True
