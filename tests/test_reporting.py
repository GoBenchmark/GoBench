from __future__ import annotations

import json

from gobench.reporting import (
    filter_run_summaries,
    load_run_summaries,
    render_leaderboard,
    summarize_raw_responses,
    write_run_artifacts,
)


def test_write_run_artifacts_creates_metadata_metrics_and_report(tmp_path):
    metadata = {
        "run_name": "example-run",
        "model": "gpt-test",
        "reasoning_effort": "xhigh",
        "scorer": "katago",
        "suite": "public_dev",
        "suite_visibility": "public_dev_open",
        "primary_metric": "mean_point_loss",
        "created_at": "2026-06-12T00:00:00+00:00",
        "prompt_sha256": "abc123",
        "response_count": 2,
        "response_completed_count": 1,
        "response_incomplete_count": 1,
        "response_error_count": 0,
        "avg_latency_seconds": 3.0,
        "total_tokens": 123,
        "run_elapsed_human": "00:02:03",
    }
    metrics = {
        "count": 2,
        "gobench_score": 50.0,
        "mean_point_loss": 3.5,
        "legal_move_rate": 1.0,
        "top1_match_rate": 0.0,
        "top3_match_rate": 0.5,
        "top10_match_rate": 0.5,
        "blunder_rate": 0.5,
        "catastrophic_blunder_rate": 0.0,
        "pass_rate": 0.0,
        "phase_mpl": {"opening": 1.0},
    }

    summary = write_run_artifacts(tmp_path, metadata, metrics, completed=True, error=None)

    assert summary["completed"] is True
    assert json.loads((tmp_path / "run.json").read_text())["model"] == "gpt-test"
    assert json.loads((tmp_path / "metrics.json").read_text())["metrics"]["gobench_score"] == 50.0
    report = (tmp_path / "report.md").read_text()
    assert "# GoBench Run: example-run" in report
    assert "| GoBench Score | 50 / 100 |" in report
    assert "| opening | 1 |" in report
    assert "## Run Telemetry" in report
    assert "| Run elapsed | 00:02:03 |" in report
    assert "| Total tokens | 123 |" in report


def test_leaderboard_sorts_by_mpl(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    write_run_artifacts(
        first,
        {"run_name": "first", "model": "model-a"},
        {"mean_point_loss": 5.0, "gobench_score": 36.8, "legal_move_rate": 1, "top3_match_rate": 0.2, "blunder_rate": 0.4, "count": 3},
        completed=True,
        error=None,
    )
    write_run_artifacts(
        second,
        {"run_name": "second", "model": "model-b"},
        {"mean_point_loss": 2.0, "gobench_score": 67.0, "legal_move_rate": 1, "top3_match_rate": 0.5, "blunder_rate": 0.1, "count": 3},
        completed=True,
        error=None,
    )

    leaderboard = render_leaderboard(load_run_summaries(tmp_path))

    assert leaderboard.index("second") < leaderboard.index("first")
    assert "| 1 | second | model-b |" in leaderboard


def test_leaderboard_backfills_score_for_old_metrics(tmp_path):
    run_dir = tmp_path / "old"
    run_dir.mkdir()
    (run_dir / "metrics.json").write_text(
        json.dumps({"metrics": {"mean_point_loss": 5.0, "legal_move_rate": 1, "top3_match_rate": 0, "blunder_rate": 0, "count": 1}}),
        encoding="utf-8",
    )

    leaderboard = render_leaderboard(load_run_summaries(tmp_path))

    assert "8.208" in leaderboard


def test_leaderboard_places_empty_runs_last(tmp_path):
    empty = tmp_path / "empty"
    complete = tmp_path / "complete"
    empty.mkdir()
    complete.mkdir()
    write_run_artifacts(
        empty,
        {"run_name": "empty", "model": "model-empty"},
        {"mean_point_loss": None, "gobench_score": None, "legal_move_rate": 0, "top3_match_rate": 0, "blunder_rate": 0, "count": 0},
        completed=False,
        error="no predictions",
    )
    write_run_artifacts(
        complete,
        {"run_name": "complete", "model": "model-complete"},
        {"mean_point_loss": 2.0, "gobench_score": 67.0, "legal_move_rate": 1, "top3_match_rate": 0.5, "blunder_rate": 0.1, "count": 3},
        completed=True,
        error=None,
    )

    leaderboard = render_leaderboard(load_run_summaries(tmp_path))

    assert leaderboard.index("complete") < leaderboard.index("empty")


def test_filter_run_summaries_by_suite_name_count_and_completion(tmp_path):
    complete_v2 = tmp_path / "complete-v2"
    partial_v2 = tmp_path / "partial-v2"
    stale = tmp_path / "stale"
    other_suite = tmp_path / "other-suite-v2"
    for run_dir in (complete_v2, partial_v2, stale, other_suite):
        run_dir.mkdir()
    write_run_artifacts(
        complete_v2,
        {"run_name": "complete-v2", "model": "model-a", "suite": "public_dev"},
        {"mean_point_loss": 1.0, "gobench_score": 60.0, "legal_move_rate": 1, "top3_match_rate": 0, "blunder_rate": 0, "count": 20},
        completed=True,
        error=None,
    )
    write_run_artifacts(
        partial_v2,
        {"run_name": "partial-v2", "model": "model-b", "suite": "public_dev"},
        {"mean_point_loss": 0.1, "gobench_score": 95.0, "legal_move_rate": 1, "top3_match_rate": 0, "blunder_rate": 0, "count": 3},
        completed=True,
        error=None,
    )
    write_run_artifacts(
        stale,
        {"run_name": "stale", "model": "model-c", "suite": "public_dev"},
        {"mean_point_loss": 0.1, "gobench_score": 95.0, "legal_move_rate": 1, "top3_match_rate": 0, "blunder_rate": 0, "count": 20},
        completed=True,
        error=None,
    )
    write_run_artifacts(
        other_suite,
        {"run_name": "other-suite-v2", "model": "model-d", "suite": "other"},
        {"mean_point_loss": 0.1, "gobench_score": 95.0, "legal_move_rate": 1, "top3_match_rate": 0, "blunder_rate": 0, "count": 20},
        completed=True,
        error=None,
    )

    filtered = filter_run_summaries(
        load_run_summaries(tmp_path),
        suite="public_dev",
        min_count=20,
        name_contains="v2",
        completed_only=True,
    )

    assert [summary["run"]["run_name"] for summary in filtered] == ["complete-v2"]


def test_summarize_raw_responses_counts_status_latency_and_usage():
    raw_rows = [
        {
            "status": "completed",
            "latency_seconds": 1.5,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
                "output_tokens_details": {"reasoning_tokens": 7},
            },
        },
        {"status": "incomplete", "latency_seconds": 2.5},
        {"error": "boom", "latency_seconds": 1.0},
    ]

    telemetry = summarize_raw_responses(raw_rows)

    assert telemetry["response_count"] == 3
    assert telemetry["response_completed_count"] == 1
    assert telemetry["response_incomplete_count"] == 1
    assert telemetry["response_error_count"] == 1
    assert telemetry["total_latency_seconds"] == 5.0
    assert telemetry["avg_latency_seconds"] == 1.667
    assert telemetry["input_tokens"] == 10
    assert telemetry["output_tokens"] == 20
    assert telemetry["reasoning_tokens"] == 7
    assert telemetry["total_tokens"] == 30
