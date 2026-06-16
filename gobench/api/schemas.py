from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Color = Literal["B", "W"]


class Position(BaseModel):
    position_id: str
    board_size: int = 19
    rules: str = "chinese"
    komi: float = 7.5
    to_move: Color
    black: list[str] = Field(default_factory=list)
    white: list[str] = Field(default_factory=list)
    move_history: list[tuple[Color, str]] = Field(default_factory=list)
    phase: str | None = None


class MoveSubmission(BaseModel):
    position_id: str
    move: str


class CandidateEval(BaseModel):
    move: str
    score_lead: float
    winrate: float | None = None
    policy: float | None = None
    visits: int | None = None


class ScoreResult(BaseModel):
    position_id: str
    submitted_move: str
    legal: bool
    point_loss: float
    top1_match: bool
    top3_match: bool
    top10_match: bool
    blunder: bool
    catastrophic_blunder: bool
    phase: str | None = None


class RunCreate(BaseModel):
    model_name: str
    model_version: str
    track: str = "pure_llm"
    notes: str | None = None


class RunCreated(BaseModel):
    run_id: str


class AcceptedResponse(BaseModel):
    accepted: bool
