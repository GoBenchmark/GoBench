from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from gobench.api.schemas import RunCreate, ScoreResult
from gobench.storage.models import Attempt, Run


class RunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_run(self, payload: RunCreate) -> Run:
        run = Run(run_id=str(uuid.uuid4()), **payload.model_dump())
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def get_run(self, run_id: str) -> Run | None:
        return self.session.get(Run, run_id)

    def mark_completed(self, run_id: str) -> None:
        run = self.get_run(run_id)
        if run:
            run.completed = True
            self.session.commit()

    def list_completed(self) -> list[Run]:
        return list(self.session.scalars(select(Run).where(Run.completed == True)))  # noqa: E712


class AttemptRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_result(self, run_id: str, result: ScoreResult) -> Attempt:
        attempt = Attempt(run_id=run_id, **result.model_dump())
        self.session.add(attempt)
        self.session.commit()
        self.session.refresh(attempt)
        return attempt

    def attempted_position_ids(self, run_id: str) -> set[str]:
        rows = self.session.scalars(select(Attempt.position_id).where(Attempt.run_id == run_id))
        return set(rows)

    def has_attempt(self, run_id: str, position_id: str) -> bool:
        row = self.session.scalar(
            select(Attempt.id).where(Attempt.run_id == run_id, Attempt.position_id == position_id)
        )
        return row is not None

    def results_for_run(self, run_id: str) -> list[ScoreResult]:
        attempts = self.session.scalars(select(Attempt).where(Attempt.run_id == run_id)).all()
        return [
            ScoreResult(
                position_id=attempt.position_id,
                submitted_move=attempt.submitted_move,
                legal=attempt.legal,
                point_loss=attempt.point_loss,
                top1_match=attempt.top1_match,
                top3_match=attempt.top3_match,
                top10_match=attempt.top10_match,
                blunder=attempt.blunder,
                catastrophic_blunder=attempt.catastrophic_blunder,
                phase=attempt.phase,
            )
            for attempt in attempts
        ]
