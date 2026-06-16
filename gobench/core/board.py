from __future__ import annotations

from dataclasses import dataclass

from gobench.api.schemas import Position
from gobench.core.coordinates import coord_to_point, is_pass

EMPTY = "."
BLACK = "B"
WHITE = "W"


def opponent(color: str) -> str:
    return WHITE if color == BLACK else BLACK


@dataclass
class Board:
    size: int = 19
    grid: list[list[str]] | None = None

    def __post_init__(self) -> None:
        if self.grid is None:
            self.grid = [[EMPTY for _ in range(self.size)] for _ in range(self.size)]

    @classmethod
    def from_position(cls, position: Position) -> "Board":
        board = cls(size=position.board_size)
        for coord in position.black:
            row, col = coord_to_point(coord, position.board_size)
            board.grid[row][col] = BLACK
        for coord in position.white:
            row, col = coord_to_point(coord, position.board_size)
            if board.grid[row][col] != EMPTY:
                raise ValueError(f"overlapping stone at {coord}")
            board.grid[row][col] = WHITE
        return board

    def copy(self) -> "Board":
        return Board(self.size, [row[:] for row in self.grid])

    def neighbors(self, row: int, col: int) -> list[tuple[int, int]]:
        points: list[tuple[int, int]] = []
        for next_row, next_col in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
            if 0 <= next_row < self.size and 0 <= next_col < self.size:
                points.append((next_row, next_col))
        return points

    def group_and_liberties(self, row: int, col: int) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
        color = self.grid[row][col]
        if color == EMPTY:
            return set(), {(row, col)}

        group: set[tuple[int, int]] = set()
        liberties: set[tuple[int, int]] = set()
        stack = [(row, col)]
        while stack:
            point = stack.pop()
            if point in group:
                continue
            group.add(point)
            for neighbor in self.neighbors(*point):
                value = self.grid[neighbor[0]][neighbor[1]]
                if value == EMPTY:
                    liberties.add(neighbor)
                elif value == color and neighbor not in group:
                    stack.append(neighbor)
        return group, liberties

    def remove_group(self, group: set[tuple[int, int]]) -> None:
        for row, col in group:
            self.grid[row][col] = EMPTY

    def play_move(self, color: str, move: str) -> tuple[bool, "Board"]:
        if is_pass(move):
            return True, self.copy()

        try:
            row, col = coord_to_point(move, self.size)
        except ValueError:
            return False, self.copy()

        if self.grid[row][col] != EMPTY:
            return False, self.copy()

        next_board = self.copy()
        next_board.grid[row][col] = color

        for next_row, next_col in next_board.neighbors(row, col):
            if next_board.grid[next_row][next_col] == opponent(color):
                group, liberties = next_board.group_and_liberties(next_row, next_col)
                if not liberties:
                    next_board.remove_group(group)

        _, own_liberties = next_board.group_and_liberties(row, col)
        if not own_liberties:
            return False, self.copy()

        return True, next_board
