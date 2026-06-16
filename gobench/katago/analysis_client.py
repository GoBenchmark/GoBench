from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from gobench.api.schemas import CandidateEval, Position, ScoreResult
from gobench.core.coordinates import normalize_move
from gobench.core.legality import is_legal_move
from gobench.core.scoring import ILLEGAL_MOVE_PENALTY
from gobench.katago.parser import parse_candidate_evals

DEFAULT_KATAGO_MAX_VISITS = 2048


class KataGoAnalysisClient:
    """Client for KataGo's JSON analysis engine protocol."""

    def __init__(
        self,
        katago_bin: str | None = None,
        model: str | None = None,
        config: str | None = None,
        max_visits: int | None = None,
        analysis_pv_len: int | None = None,
        report_analysis_as: str | None = None,
        extra_args: Sequence[str] | None = None,
        process: subprocess.Popen | None = None,
    ) -> None:
        self.katago_bin = katago_bin or os.getenv("KATAGO_BIN")
        self.model = model or os.getenv("KATAGO_MODEL")
        self.config = config or os.getenv("KATAGO_CONFIG")
        self.max_visits = max_visits or env_int("KATAGO_MAX_VISITS") or DEFAULT_KATAGO_MAX_VISITS
        self.analysis_pv_len = analysis_pv_len or env_int("KATAGO_ANALYSIS_PV_LEN")
        self.report_analysis_as = report_analysis_as or os.getenv("KATAGO_REPORT_ANALYSIS_AS", "SIDETOMOVE")
        self.extra_args = list(extra_args or [])
        self._process = process
        self._stderr_lines: list[str] = []
        self._stderr_thread: threading.Thread | None = None

    def __enter__(self) -> "KataGoAnalysisClient":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def analyze_position(self, position: Position) -> list[CandidateEval]:
        response = self.query(position)
        return parse_candidate_evals(response)

    def score_move(self, position: Position, submitted_move: str) -> ScoreResult:
        try:
            move = normalize_move(submitted_move)
        except ValueError:
            return self._illegal_result(position, submitted_move)

        if not is_legal_move(position, move):
            return self._illegal_result(position, move)

        candidates = self.analyze_position(position)
        if not candidates:
            raise KataGoAnalysisError(f"KataGo returned no candidate moves for {position.position_id}")

        candidate_moves = [candidate.move for candidate in candidates]
        best_score = max(candidate.score_lead for candidate in candidates)
        if move in candidate_moves:
            submitted_score = candidates[candidate_moves.index(move)].score_lead
        else:
            forced = self.analyze_forced_move(position, move)
            submitted_score = forced.score_lead

        point_loss = round(max(0.0, best_score - submitted_score), 3)
        return ScoreResult(
            position_id=position.position_id,
            submitted_move=move,
            legal=True,
            point_loss=point_loss,
            top1_match=move == candidate_moves[0],
            top3_match=move in candidate_moves[:3],
            top10_match=move in candidate_moves[:10],
            blunder=point_loss > 5,
            catastrophic_blunder=point_loss > 15,
            phase=position.phase,
        )

    def analyze_forced_move(self, position: Position, move: str) -> CandidateEval:
        response = self.query(
            position,
            extra={
                "allowMoves": [
                    {
                        "player": position.to_move,
                        "moves": [move],
                        "untilDepth": 1,
                    }
                ]
            },
        )
        candidates = parse_candidate_evals(response)
        for candidate in candidates:
            if candidate.move == move:
                return candidate
        if candidates:
            return candidates[0]
        raise KataGoAnalysisError(f"KataGo returned no forced analysis for {position.position_id}:{move}")

    def query(self, position: Position, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        query = self.make_query(position, extra=extra)
        return self.query_raw(query)

    def query_raw(self, query: dict[str, Any]) -> dict[str, Any]:
        process = self.start()
        assert process.stdin is not None
        assert process.stdout is not None
        process.stdin.write(json.dumps(query, separators=(",", ":")) + "\n")
        process.stdin.flush()

        query_id = query["id"]
        while True:
            line = process.stdout.readline()
            if line == "":
                stderr = self.recent_stderr()
                raise KataGoAnalysisError(f"KataGo exited before responding to {query_id}. stderr: {stderr}")
            try:
                response = json.loads(line)
            except json.JSONDecodeError as exc:
                raise KataGoAnalysisError(f"KataGo returned invalid JSON: {line[:400]}") from exc

            if response.get("id") != query_id:
                continue
            if "error" in response:
                raise KataGoAnalysisError(f"KataGo query failed: {response['error']}")
            if response.get("isDuringSearch") is True:
                continue
            return response

    def make_query(self, position: Position, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        query: dict[str, Any] = {
            "id": f"{position.position_id}:{uuid.uuid4().hex}",
            "initialStones": self.initial_stones(position),
            "moves": [],
            "initialPlayer": position.to_move,
            "rules": "Chinese",
            "komi": position.komi,
            "boardXSize": position.board_size,
            "boardYSize": position.board_size,
        }
        if self.max_visits is not None:
            query["maxVisits"] = self.max_visits
        if self.analysis_pv_len is not None:
            query["analysisPVLen"] = self.analysis_pv_len
        if self.report_analysis_as:
            query["overrideSettings"] = {"reportAnalysisWinratesAs": self.report_analysis_as}
        if extra:
            query = merge_query_dicts(query, extra)
        return query

    def initial_stones(self, position: Position) -> list[list[str]]:
        stones: list[list[str]] = []
        for move in position.black:
            stones.append(["B", normalize_move(move)])
        for move in position.white:
            stones.append(["W", normalize_move(move)])
        return stones

    def start(self) -> subprocess.Popen:
        if self._process is not None and self._process.poll() is None:
            return self._process
        self.validate_config()
        command = [
            self.katago_bin,
            "analysis",
            "-config",
            self.config,
            "-model",
            self.model,
            *self.extra_args,
        ]
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._start_stderr_reader()
        return self._process

    def close(self) -> None:
        if self._process is None:
            return
        process = self._process
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self._process = None

    def validate_config(self) -> None:
        missing = []
        for label, value in (("KATAGO_BIN", self.katago_bin), ("KATAGO_MODEL", self.model), ("KATAGO_CONFIG", self.config)):
            if not value:
                missing.append(label)
            elif label == "KATAGO_BIN":
                if not Path(value).exists() and shutil.which(value) is None:
                    missing.append(f"{label} path not found: {value}")
            elif not Path(value).exists():
                missing.append(f"{label} path not found: {value}")
        if missing:
            raise KataGoConfigError("KataGo is not configured: " + "; ".join(missing))

    def _start_stderr_reader(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return

        def read_stderr() -> None:
            assert process.stderr is not None
            for line in process.stderr:
                self._stderr_lines.append(line.rstrip())
                if len(self._stderr_lines) > 50:
                    del self._stderr_lines[:25]

        self._stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        self._stderr_thread.start()

    def recent_stderr(self) -> str:
        return "\n".join(self._stderr_lines[-10:])

    def _illegal_result(self, position: Position, move: str) -> ScoreResult:
        return ScoreResult(
            position_id=position.position_id,
            submitted_move=move,
            legal=False,
            point_loss=ILLEGAL_MOVE_PENALTY,
            top1_match=False,
            top3_match=False,
            top10_match=False,
            blunder=True,
            catastrophic_blunder=True,
            phase=position.phase,
        )


class KataGoConfigError(RuntimeError):
    pass


class KataGoAnalysisError(RuntimeError):
    pass


def env_int(name: str) -> int | None:
    value = os.getenv(name)
    if not value:
        return None
    return int(value)


def merge_query_dicts(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in extra.items():
        if key == "overrideSettings" and isinstance(value, dict):
            override_settings = dict(merged.get("overrideSettings", {}))
            override_settings.update(value)
            merged[key] = override_settings
        else:
            merged[key] = value
    return merged
