from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    model_name: Mapped[str] = mapped_column(String, nullable=False)
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    track: Mapped[str] = mapped_column(String, nullable=False, default="pure_llm")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed: Mapped[bool] = mapped_column(Boolean, default=False)


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    position_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    submitted_move: Mapped[str] = mapped_column(String, nullable=False)
    legal: Mapped[bool] = mapped_column(Boolean, nullable=False)
    point_loss: Mapped[float] = mapped_column(Float, nullable=False)
    top1_match: Mapped[bool] = mapped_column(Boolean, nullable=False)
    top3_match: Mapped[bool] = mapped_column(Boolean, nullable=False)
    top10_match: Mapped[bool] = mapped_column(Boolean, nullable=False)
    blunder: Mapped[bool] = mapped_column(Boolean, nullable=False)
    catastrophic_blunder: Mapped[bool] = mapped_column(Boolean, nullable=False)
    phase: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
