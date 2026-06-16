from __future__ import annotations

import json

from gobench.api.schemas import MoveSubmission, ScoreResult
from gobench.cli import html_url, maybe_add_run_visualization
from gobench.datasets.loader import write_jsonl
from gobench.datasets.sample_data import make_toy_positions
from gobench.profiles import SuiteProfile
from gobench.visualization import write_run_visualization


def test_write_run_visualization_creates_html_and_candidate_cache(tmp_path, monkeypatch):
    monkeypatch.delenv("GOBENCH_SCORER", raising=False)
    positions = make_toy_positions(2)
    positions_path = tmp_path / "positions.jsonl"
    write_jsonl(positions_path, positions)

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_name": "viz-test",
                "model": "model-a",
                "suite": "public_dev",
                "run_elapsed_human": "00:03:21",
                "positions_requested": 2,
                "positions_scored": 2,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "metrics.json").write_text(
        json.dumps({"metrics": {"gobench_score": 90.0, "mean_point_loss": 0.2, "count": 2}}),
        encoding="utf-8",
    )
    write_jsonl(
        run_dir / "predictions.jsonl",
        [
            MoveSubmission(position_id=positions[0].position_id, move="R14"),
            MoveSubmission(position_id=positions[1].position_id, move="K16"),
        ],
    )
    write_jsonl(
        run_dir / "results.jsonl",
        [
            ScoreResult(
                position_id=positions[0].position_id,
                submitted_move="R14",
                legal=True,
                point_loss=0.2,
                top1_match=False,
                top3_match=True,
                top10_match=True,
                blunder=False,
                catastrophic_blunder=False,
                phase="opening",
            ),
            ScoreResult(
                position_id=positions[1].position_id,
                submitted_move="K16",
                legal=True,
                point_loss=1.3,
                top1_match=False,
                top3_match=False,
                top10_match=False,
                blunder=False,
                catastrophic_blunder=False,
                phase="early_middle",
            ),
        ],
    )
    write_jsonl(
        run_dir / "raw_responses.jsonl",
        [
            {"position_id": positions[0].position_id, "status": "completed", "raw_text": '{"move":"R14"}'},
            {"position_id": positions[1].position_id, "status": "completed", "raw_text": '{"move":"K16"}'},
        ],
    )
    suite = SuiteProfile(
        path=tmp_path / "suite.yaml",
        name="public_dev",
        positions=str(positions_path),
        max_positions=2,
        scorer="mock",
        katago_max_visits=None,
        katago_analysis_pv_len=None,
    )

    html_path = write_run_visualization(run_dir, suite, top_k=3)

    page = html_path.read_text(encoding="utf-8")
    assert html_path.name == "index.html"
    assert "viz-test" in page
    assert "board-svg" in page
    assert "candidate-marker" in page
    assert "model-marker" in page
    assert "status-badge" in page
    assert "status-completed" in page
    assert "Scoring complete 2/2" in page
    assert "completion-complete" in page
    assert "00:03:21" in page
    assert (run_dir / "katago_candidates.jsonl").exists()


def test_write_run_visualization_includes_error_status_badge(tmp_path, monkeypatch):
    monkeypatch.delenv("GOBENCH_SCORER", raising=False)
    positions = make_toy_positions(1)
    positions_path = tmp_path / "positions.jsonl"
    write_jsonl(positions_path, positions)

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps({"run_name": "viz-error", "positions_requested": 2, "positions_scored": 1}),
        encoding="utf-8",
    )
    (run_dir / "metrics.json").write_text(json.dumps({"metrics": {"count": 1}}), encoding="utf-8")
    write_jsonl(run_dir / "predictions.jsonl", [MoveSubmission(position_id=positions[0].position_id, move="__invalid__")])
    write_jsonl(
        run_dir / "results.jsonl",
        [
            ScoreResult(
                position_id=positions[0].position_id,
                submitted_move="__invalid__",
                legal=False,
                point_loss=50.0,
                top1_match=False,
                top3_match=False,
                top10_match=False,
                blunder=True,
                catastrophic_blunder=True,
                phase="opening",
            )
        ],
    )
    write_jsonl(
        run_dir / "raw_responses.jsonl",
        [{"position_id": positions[0].position_id, "error": "OpenAI API error 429: insufficient_quota"}],
    )
    suite = SuiteProfile(
        path=tmp_path / "suite.yaml",
        name="public_dev",
        positions=str(positions_path),
        max_positions=1,
        scorer="mock",
        katago_max_visits=None,
        katago_analysis_pv_len=None,
    )

    html_path = write_run_visualization(run_dir, suite, top_k=3)
    page = html_path.read_text(encoding="utf-8")

    assert "status-error" in page
    assert "missing response" in page
    assert "Scoring incomplete 1/2" in page
    assert "completion-incomplete" in page


def test_write_run_visualization_analyzes_only_scored_positions(tmp_path, monkeypatch):
    monkeypatch.delenv("GOBENCH_SCORER", raising=False)
    positions = make_toy_positions(3)
    positions_path = tmp_path / "positions.jsonl"
    write_jsonl(positions_path, positions)

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(json.dumps({"run_name": "partial-viz"}), encoding="utf-8")
    (run_dir / "metrics.json").write_text(json.dumps({"metrics": {"count": 1}}), encoding="utf-8")
    write_jsonl(run_dir / "predictions.jsonl", [MoveSubmission(position_id=positions[0].position_id, move="R14")])
    write_jsonl(
        run_dir / "results.jsonl",
        [
            ScoreResult(
                position_id=positions[0].position_id,
                submitted_move="R14",
                legal=True,
                point_loss=0.2,
                top1_match=False,
                top3_match=True,
                top10_match=True,
                blunder=False,
                catastrophic_blunder=False,
                phase="opening",
            )
        ],
    )
    suite = SuiteProfile(
        path=tmp_path / "suite.yaml",
        name="public_dev",
        positions=str(positions_path),
        max_positions=3,
        scorer="mock",
        katago_max_visits=None,
        katago_analysis_pv_len=None,
    )

    write_run_visualization(run_dir, suite, top_k=3)
    rows = [
        json.loads(line)
        for line in (run_dir / "katago_candidates.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert [row["position_id"] for row in rows] == [positions[0].position_id]


def test_maybe_add_run_visualization_updates_summary(tmp_path, monkeypatch):
    monkeypatch.delenv("GOBENCH_SCORER", raising=False)
    positions = make_toy_positions(1)
    positions_path = tmp_path / "positions.jsonl"
    write_jsonl(positions_path, positions)

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(json.dumps({"run_name": "viz-run"}), encoding="utf-8")
    (run_dir / "metrics.json").write_text(json.dumps({"metrics": {"count": 1}}), encoding="utf-8")
    write_jsonl(run_dir / "predictions.jsonl", [MoveSubmission(position_id=positions[0].position_id, move="R14")])
    write_jsonl(
        run_dir / "results.jsonl",
        [
            ScoreResult(
                position_id=positions[0].position_id,
                submitted_move="R14",
                legal=True,
                point_loss=0.2,
                top1_match=False,
                top3_match=True,
                top10_match=True,
                blunder=False,
                catastrophic_blunder=False,
                phase="opening",
            )
        ],
    )
    suite = SuiteProfile(
        path=tmp_path / "suite.yaml",
        name="public_dev",
        positions=str(positions_path),
        max_positions=1,
        scorer="mock",
        katago_max_visits=None,
        katago_analysis_pv_len=None,
    )
    summary: dict[str, object] = {}

    maybe_add_run_visualization(summary, run_dir, suite, visualize=True, open_browser=False, top_k=2, refresh_candidates=False)

    assert summary["visualization"] == str(run_dir / "visualization" / "index.html")
    assert summary["visualization_url"] == (run_dir / "visualization" / "index.html").resolve().as_uri()
    assert (run_dir / "visualization" / "index.html").exists()


def test_html_url_is_absolute_file_url(tmp_path):
    path = tmp_path / "visualization" / "index.html"

    assert html_url(path).startswith("file://")
    assert html_url(path).endswith("/visualization/index.html")
