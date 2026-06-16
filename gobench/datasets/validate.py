from __future__ import annotations

from gobench.api.schemas import Position
from gobench.core.board import Board


def validate_positions(positions: list[Position]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for position in positions:
        if position.position_id in seen:
            errors.append(f"{position.position_id}: duplicate position_id")
        seen.add(position.position_id)
        if position.board_size != 19:
            errors.append(f"{position.position_id}: only board_size=19 is supported")
        if position.rules != "chinese":
            errors.append(f"{position.position_id}: only chinese rules are supported")
        try:
            Board.from_position(position)
        except ValueError as exc:
            errors.append(f"{position.position_id}: {exc}")
    return errors
