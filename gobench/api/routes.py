from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from gobench.api.schemas import AcceptedResponse, MoveSubmission, Position, RunCreate, RunCreated
from gobench.core.metrics import aggregate_metrics
from gobench.core.scoring import ScorerProtocol
from gobench.core.scorer_factory import create_scorer
from gobench.datasets.loader import load_positions
from gobench.datasets.sample_data import make_toy_positions
from gobench.storage.db import get_session
from gobench.storage.repositories import AttemptRepository, RunRepository

router = APIRouter()


@lru_cache(maxsize=1)
def get_scorer() -> ScorerProtocol:
    return create_scorer()


def get_private_positions() -> list[Position]:
    path = Path(os.getenv("GOBENCH_PRIVATE_POSITIONS", "./data/private_test/positions.jsonl"))
    if path.exists():
        return load_positions(path)
    return make_toy_positions(20)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/runs", response_model=RunCreated)
def create_run(payload: RunCreate, session: Session = Depends(get_session)) -> RunCreated:
    run = RunRepository(session).create_run(payload)
    return RunCreated(run_id=run.run_id)


@router.get("/runs/{run_id}/next", response_model=Optional[Position])
def next_position(
    run_id: str,
    session: Session = Depends(get_session),
    private_positions: list[Position] = Depends(get_private_positions),
) -> Position | None:
    runs = RunRepository(session)
    if runs.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")

    attempts = AttemptRepository(session)
    attempted = attempts.attempted_position_ids(run_id)
    for position in private_positions:
        if position.position_id not in attempted:
            return position

    runs.mark_completed(run_id)
    return None


@router.post("/runs/{run_id}/submit", response_model=AcceptedResponse)
def submit_move(
    run_id: str,
    payload: MoveSubmission,
    session: Session = Depends(get_session),
    private_positions: list[Position] = Depends(get_private_positions),
) -> AcceptedResponse:
    runs = RunRepository(session)
    if runs.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")

    positions = {position.position_id: position for position in private_positions}
    position = positions.get(payload.position_id)
    if position is None:
        raise HTTPException(status_code=404, detail="position not found")

    attempts = AttemptRepository(session)
    if attempts.has_attempt(run_id, payload.position_id):
        raise HTTPException(status_code=409, detail="position already submitted for this run")

    result = get_scorer().score_move(position, payload.move)
    attempts.add_result(run_id, result)
    if len(attempts.attempted_position_ids(run_id)) >= len(positions):
        runs.mark_completed(run_id)
    return AcceptedResponse(accepted=True)


@router.get("/runs/{run_id}/report")
def run_report(run_id: str, session: Session = Depends(get_session)) -> dict:
    if RunRepository(session).get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    return aggregate_metrics(AttemptRepository(session).results_for_run(run_id))


@router.get("/leaderboard")
def leaderboard(session: Session = Depends(get_session)) -> list[dict]:
    runs = RunRepository(session).list_completed()
    rows = []
    attempts = AttemptRepository(session)
    for run in runs:
        metrics = aggregate_metrics(attempts.results_for_run(run.run_id))
        rows.append(
            {
                "run_id": run.run_id,
                "model_name": run.model_name,
                "model_version": run.model_version,
                "track": run.track,
                **metrics,
            }
        )
    return sorted(rows, key=lambda row: row["mean_point_loss"])
