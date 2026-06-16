from __future__ import annotations

import json
import subprocess
import sys

from gobench.api.schemas import Position
from gobench.katago.analysis_client import DEFAULT_KATAGO_MAX_VISITS, KataGoAnalysisClient


FAKE_KATAGO = r"""
import json
import sys

for line in sys.stdin:
    query = json.loads(line)
    allow_moves = query.get("allowMoves") or []
    if allow_moves:
        move = allow_moves[0]["moves"][0]
        move_infos = [{"move": move, "scoreLead": 2.0, "winrate": 0.45, "prior": 0.01, "visits": 32}]
    else:
        move_infos = [
            {"move": "D4", "scoreLead": 10.0, "winrate": 0.80, "prior": 0.30, "visits": 100},
            {"move": "Q16", "scoreLead": 6.0, "winrate": 0.60, "prior": 0.20, "visits": 80},
        ]
    print(json.dumps({
        "id": query["id"],
        "isDuringSearch": False,
        "moveInfos": move_infos,
        "rootInfo": {"currentPlayer": query.get("initialPlayer", "B"), "scoreLead": 10.0},
        "turnNumber": 0,
    }), flush=True)
"""


def fake_process() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", FAKE_KATAGO],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_make_query_uses_static_stones_side_to_move_and_query_overrides():
    client = KataGoAnalysisClient(process=fake_process(), max_visits=11, analysis_pv_len=3)
    position = Position(
        position_id="katago_query",
        to_move="W",
        black=["D4"],
        white=["Q16"],
    )
    query = client.make_query(position)
    try:
        assert query["initialStones"] == [["B", "D4"], ["W", "Q16"]]
        assert query["initialPlayer"] == "W"
        assert query["moves"] == []
        assert query["rules"] == "Chinese"
        assert query["maxVisits"] == 11
        assert query["analysisPVLen"] == 3
        assert query["overrideSettings"]["reportAnalysisWinratesAs"] == "SIDETOMOVE"
    finally:
        client.close()


def test_default_max_visits_is_2048(monkeypatch):
    monkeypatch.delenv("KATAGO_MAX_VISITS", raising=False)
    client = KataGoAnalysisClient(process=fake_process())
    try:
        query = client.make_query(Position(position_id="default_visits", to_move="B"))
        assert query["maxVisits"] == DEFAULT_KATAGO_MAX_VISITS == 2048
    finally:
        client.close()


def test_analyze_position_parses_katago_move_infos():
    client = KataGoAnalysisClient(process=fake_process())
    position = Position(position_id="katago_analyze", to_move="B")
    try:
        candidates = client.analyze_position(position)
        assert [candidate.move for candidate in candidates] == ["D4", "Q16"]
        assert candidates[0].score_lead == 10.0
        assert candidates[0].policy == 0.30
    finally:
        client.close()


def test_score_move_uses_forced_analysis_when_candidate_absent():
    client = KataGoAnalysisClient(process=fake_process())
    position = Position(position_id="katago_score", to_move="B")
    try:
        top = client.score_move(position, "D4")
        candidate = client.score_move(position, "Q16")
        forced = client.score_move(position, "R14")
        assert top.point_loss == 0.0
        assert top.top1_match
        assert candidate.point_loss == 4.0
        assert candidate.top3_match
        assert forced.point_loss == 8.0
        assert not forced.top10_match
    finally:
        client.close()


def test_point_loss_uses_best_score_lead_not_katago_order():
    client = KataGoAnalysisClient(process=fake_process())
    position = Position(position_id="katago_score_baseline", to_move="B")
    try:
        candidates = client.analyze_position(position)
        candidates[0].score_lead = 10.0
        candidates[1].score_lead = 12.0
        client.analyze_position = lambda _: candidates  # type: ignore[method-assign]

        utility_best = client.score_move(position, "D4")
        point_best = client.score_move(position, "Q16")

        assert utility_best.top1_match
        assert utility_best.point_loss == 2.0
        assert not point_best.top1_match
        assert point_best.point_loss == 0.0
    finally:
        client.close()
