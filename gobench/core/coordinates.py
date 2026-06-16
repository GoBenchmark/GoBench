from __future__ import annotations

BOARD_COLUMNS = "ABCDEFGHJKLMNOPQRST"
PASS_MOVES = {"pass", "PASS", "Pass"}


def is_pass(move: str) -> bool:
    return move.strip() in PASS_MOVES


def coord_to_point(coord: str, board_size: int = 19) -> tuple[int, int]:
    value = coord.strip().upper()
    if is_pass(value):
        raise ValueError("pass has no board point")
    if len(value) < 2:
        raise ValueError(f"invalid coordinate: {coord!r}")

    col_letter = value[0]
    if col_letter == "I" or col_letter not in BOARD_COLUMNS[:board_size]:
        raise ValueError(f"invalid column: {coord!r}")

    try:
        row_number = int(value[1:])
    except ValueError as exc:
        raise ValueError(f"invalid row: {coord!r}") from exc

    if row_number < 1 or row_number > board_size:
        raise ValueError(f"row out of range: {coord!r}")

    row = board_size - row_number
    col = BOARD_COLUMNS.index(col_letter)
    return row, col


def point_to_coord(row: int, col: int, board_size: int = 19) -> str:
    if row < 0 or row >= board_size or col < 0 or col >= board_size:
        raise ValueError(f"point out of range: {(row, col)!r}")
    return f"{BOARD_COLUMNS[col]}{board_size - row}"


def normalize_move(move: str) -> str:
    value = move.strip()
    if is_pass(value):
        return "pass"
    row, col = coord_to_point(value)
    return point_to_coord(row, col)
