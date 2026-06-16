from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from gobench.api.schemas import MoveSubmission, Position

T = TypeVar("T", bound=BaseModel)


def read_jsonl_model(path: str | Path, model: type[T]) -> list[T]:
    rows: list[T] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(model.model_validate_json(line))
            except Exception as exc:
                raise ValueError(f"{path}:{line_number}: invalid row: {exc}") from exc
    return rows


def write_jsonl(path: str | Path, rows: list[BaseModel | dict]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(jsonl_row(row))


def append_jsonl(path: str | Path, row: BaseModel | dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(jsonl_row(row))


def jsonl_row(row: BaseModel | dict) -> str:
    if isinstance(row, BaseModel):
        return row.model_dump_json() + "\n"
    return json.dumps(row, separators=(",", ":")) + "\n"


def load_positions(path: str | Path) -> list[Position]:
    return read_jsonl_model(path, Position)


def load_predictions(path: str | Path) -> list[MoveSubmission]:
    return read_jsonl_model(path, MoveSubmission)
