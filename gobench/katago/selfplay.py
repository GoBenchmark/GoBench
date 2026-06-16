from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass

from gobench.api.schemas import CandidateEval, Position
from gobench.core.board import BLACK, EMPTY, WHITE, Board, opponent
from gobench.core.coordinates import is_pass, normalize_move, point_to_coord
from gobench.core.legality import is_legal_move
from gobench.core.scoring import ScorerProtocol
from gobench.datasets.sample_data import phase_for_stone_count, target_stone_counts


@dataclass(frozen=True)
class SelfPlayConfig:
    count: int = 20
    seed: int = 42
    top_k: int = 5
    policy_temperature: float = 0.5
    min_target_moves: int = 5
    max_target_moves: int = 199


@dataclass(frozen=True)
class SelfPlayProgress:
    event: str
    position_index: int
    total_positions: int
    position_id: str
    target_moves: int
    played_moves: int
    move: str | None = None


ProgressCallback = Callable[[SelfPlayProgress], None]


def make_katago_selfplay_positions(
    scorer: ScorerProtocol,
    config: SelfPlayConfig,
    progress_callback: ProgressCallback | None = None,
) -> list[Position]:
    targets = target_stone_counts(config.count, config.min_target_moves, config.max_target_moves)
    positions: list[Position] = []
    for index, target in enumerate(targets):
        position_id = f"dev_{index + 1:06d}"
        if progress_callback:
            progress_callback(
                SelfPlayProgress(
                    event="start",
                    position_index=index + 1,
                    total_positions=len(targets),
                    position_id=position_id,
                    target_moves=target,
                    played_moves=0,
                )
            )
        position = play_selfplay_prefix(
            scorer=scorer,
            position_id=position_id,
            target_moves=target,
            rng=random.Random(config.seed + index * 1009),
            top_k=config.top_k,
            policy_temperature=config.policy_temperature,
            position_index=index + 1,
            total_positions=len(targets),
            progress_callback=progress_callback,
        )
        positions.append(position)
        if progress_callback:
            progress_callback(
                SelfPlayProgress(
                    event="complete",
                    position_index=index + 1,
                    total_positions=len(targets),
                    position_id=position_id,
                    target_moves=target,
                    played_moves=len(position.move_history),
                )
            )
    return positions


def play_selfplay_prefix(
    scorer: ScorerProtocol,
    position_id: str,
    target_moves: int,
    rng: random.Random,
    top_k: int,
    policy_temperature: float,
    position_index: int = 1,
    total_positions: int = 1,
    progress_callback: ProgressCallback | None = None,
) -> Position:
    board = Board()
    to_move = BLACK
    history: list[tuple[str, str]] = []

    while len(history) < target_moves:
        position = position_from_board(
            board=board,
            position_id=f"{position_id}_ply_{len(history) + 1:03d}",
            to_move=to_move,
            move_history=history,
            phase=phase_for_stone_count(len(history) + 1),
        )
        candidates = scorer.analyze_position(position)
        move = choose_selfplay_move(position, candidates, rng, top_k, policy_temperature)
        legal, next_board = board.play_move(to_move, move)
        if not legal:
            raise ValueError(f"selected illegal self-play move {move!r} for {position.position_id}")

        history.append((to_move, move))
        if progress_callback:
            progress_callback(
                SelfPlayProgress(
                    event="move",
                    position_index=position_index,
                    total_positions=total_positions,
                    position_id=position_id,
                    target_moves=target_moves,
                    played_moves=len(history),
                    move=move,
                )
            )
        board = next_board
        to_move = opponent(to_move)

    return position_from_board(
        board=board,
        position_id=position_id,
        to_move=to_move,
        move_history=history,
        phase=phase_for_stone_count(target_moves),
    )


def choose_selfplay_move(
    position: Position,
    candidates: list[CandidateEval],
    rng: random.Random,
    top_k: int,
    policy_temperature: float,
) -> str:
    legal_candidates: list[CandidateEval] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            move = normalize_move(candidate.move)
        except ValueError:
            continue
        if is_pass(move) or move in seen or not is_legal_move(position, move):
            continue
        seen.add(move)
        legal_candidates.append(candidate.model_copy(update={"move": move}))

    if not legal_candidates:
        raise ValueError(f"KataGo returned no legal non-pass moves for {position.position_id}")

    choices = legal_candidates[: max(1, top_k)]
    if policy_temperature <= 0:
        return choices[0].move

    weights = candidate_weights(choices, policy_temperature)
    return rng.choices([candidate.move for candidate in choices], weights=weights, k=1)[0]


def candidate_weights(candidates: list[CandidateEval], policy_temperature: float) -> list[float]:
    weights: list[float] = []
    for rank, candidate in enumerate(candidates):
        if candidate.policy is not None and candidate.policy > 0:
            weights.append(candidate.policy ** (1.0 / policy_temperature))
        else:
            weights.append(math.exp(-rank / policy_temperature))
    if not any(weight > 0 for weight in weights):
        return [1.0 for _ in candidates]
    return weights


def position_from_board(
    board: Board,
    position_id: str,
    to_move: str,
    move_history: list[tuple[str, str]],
    phase: str,
) -> Position:
    black: list[str] = []
    white: list[str] = []
    for row, values in enumerate(board.grid):
        for col, value in enumerate(values):
            if value == EMPTY:
                continue
            move = point_to_coord(row, col, board.size)
            if value == BLACK:
                black.append(move)
            elif value == WHITE:
                white.append(move)
    return Position(
        position_id=position_id,
        to_move=to_move,
        black=black,
        white=white,
        move_history=move_history[:],
        phase=phase,
    )
