from pathlib import Path

import pytest

from gobench.api.schemas import MoveSubmission, Position, ScoreResult
from gobench.cli import (
    build_run_metadata_from_profiles,
    format_duration,
    generate_from_profile,
    infer_generation_error,
    latest_unresolved_errors,
    openai_timeout_seconds,
    parse_move_text,
    preserve_existing_run_metadata,
    progress_line,
    recover_completed_raw_predictions,
    score_predictions_for_suite,
    sha256_text,
    timer_event_line,
    timer_interval_seconds,
    timer_style_is_off,
    validate_continue_existing,
)
from gobench.datasets.loader import write_jsonl
from gobench.profiles import ModelProfile, SuiteProfile


def test_parse_move_text_treats_incomplete_or_empty_as_invalid():
    assert parse_move_text("", "incomplete") == "__invalid__"
    assert parse_move_text("", "completed") == "__invalid__"


def test_parse_move_text_extracts_json_move_for_completed_response():
    assert parse_move_text('{"move":"R14"}', "completed") == "R14"


def test_openai_timeout_seconds_defaults_to_shorter_timeout(monkeypatch):
    monkeypatch.delenv("OPENAI_TIMEOUT_SECONDS", raising=False)

    assert openai_timeout_seconds() == 90.0


def test_openai_timeout_seconds_validates_env(monkeypatch):
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "0")

    with pytest.raises(RuntimeError):
        openai_timeout_seconds()


def test_format_duration_uses_clock_style():
    assert format_duration(0) == "00:00:00"
    assert format_duration(65.1) == "00:01:05"
    assert format_duration(3661) == "01:01:01"


def test_timer_defaults_are_compact(monkeypatch):
    monkeypatch.delenv("GOBENCH_TIMER_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("GOBENCH_TIMER_STYLE", raising=False)

    assert timer_interval_seconds(inline=True) == 1.0
    assert timer_interval_seconds(inline=False) == 60.0
    assert timer_event_line("timer", "run", Path("data/runs/x"), 65.1) == (
        "[GoBench] run elapsed 00:01:05 | data/runs/x"
    )


def test_timer_can_be_disabled(monkeypatch):
    monkeypatch.setenv("GOBENCH_TIMER_STYLE", "off")

    assert timer_style_is_off()

    monkeypatch.setenv("GOBENCH_TIMER_INTERVAL_SECONDS", "0")

    assert timer_interval_seconds(inline=True) == 0.0


def test_progress_line_is_human_readable():
    assert progress_line({"stage": "score", "index": 2, "count": 8, "position_id": "dev_000002", "move": "D3"}) == (
        "[GoBench] score 2/8 dev_000002 move=D3"
    )
    assert progress_line({"stage": "generate", "position_id": "dev_000001", "skipped": True, "reason": "existing_prediction"}) == (
        "[GoBench] generate skip dev_000001 reason=existing_prediction"
    )
    assert progress_line({"stage": "score_cache", "cached": 10, "count": 10}) == (
        "[GoBench] score cache reused 10/10 existing results"
    )
    assert progress_line({"stage": "generate_cache", "cached": 8, "count": 20}) == (
        "[GoBench] generate cache reused 8/20 existing predictions"
    )
    assert progress_line({"stage": "generate_blocked", "blocked": 1, "count": 20}) == (
        "[GoBench] generate paused: 1 prior error(s); rerun without --no-retry-errors to try again"
    )


def test_recover_completed_raw_predictions_prevents_duplicate_model_calls():
    predictions = [MoveSubmission(position_id="dev_000001", move="R14")]
    raw_rows = [
        {"position_id": "dev_000002", "status": "completed", "raw_text": '{"move":"D4"}'},
        {"position_id": "dev_000003", "status": "completed", "parsed_move": "Q16"},
        {"position_id": "dev_000004", "error": "timeout"},
    ]

    recovered = recover_completed_raw_predictions(predictions, raw_rows, {"dev_000001", "dev_000002", "dev_000003"})

    assert recovered == 2
    assert [(prediction.position_id, prediction.move) for prediction in predictions] == [
        ("dev_000001", "R14"),
        ("dev_000002", "D4"),
        ("dev_000003", "Q16"),
    ]


def test_infer_generation_error_ignores_errors_for_later_predictions(tmp_path):
    write_jsonl(
        tmp_path / "raw_responses.jsonl",
        [
            {"position_id": "dev_000001", "error": "old timeout"},
            {"position_id": "dev_000001", "status": "completed", "parsed_move": "R14"},
            {"position_id": "dev_000002", "error": "still failed"},
        ],
    )
    write_jsonl(tmp_path / "predictions.jsonl", [MoveSubmission(position_id="dev_000001", move="R14")])

    assert infer_generation_error(tmp_path) == "still failed"


def test_latest_unresolved_errors_ignores_completed_positions():
    raw_rows = [
        {"position_id": "dev_000001", "error": "old timeout"},
        {"position_id": "dev_000001", "status": "completed", "parsed_move": "R14"},
        {"position_id": "dev_000002", "error": "still failed"},
        {"position_id": "dev_000003", "error": "also old"},
    ]

    assert latest_unresolved_errors(raw_rows, {"dev_000003"}) == {"dev_000002": "still failed"}


def test_generate_continue_does_not_retry_prior_errors_when_disabled(tmp_path, monkeypatch):
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("Return JSON.", encoding="utf-8")
    positions = [
        Position(position_id="dev_000001", to_move="B"),
        Position(position_id="dev_000002", to_move="W", black=["D4"]),
    ]
    positions_path = tmp_path / "positions.jsonl"
    write_jsonl(positions_path, positions)
    out_dir = tmp_path / "run"
    out_dir.mkdir()
    write_jsonl(out_dir / "predictions.jsonl", [MoveSubmission(position_id="dev_000001", move="R14")])
    write_jsonl(
        out_dir / "raw_responses.jsonl",
        [
            {"position_id": "dev_000001", "status": "completed", "parsed_move": "R14"},
            {"position_id": "dev_000002", "error": "OpenAI API request failed"},
        ],
    )
    model_profile = ModelProfile(
        path=tmp_path / "model.yaml",
        name="model-a",
        provider="openai",
        model="gpt-test",
        reasoning_effort="high",
        temperature=None,
        max_output_tokens=2000,
        prompt_template=str(prompt_path),
    )
    suite = SuiteProfile(tmp_path / "suite.yaml", "suite", str(positions_path), 2, "mock", None, None)
    metadata = build_run_metadata_from_profiles(
        out_dir=out_dir,
        model_profile=model_profile,
        suite=suite,
        prompt_sha256=sha256_text("Return JSON."),
        available_positions=2,
        requested_positions=2,
    )
    (out_dir / "run.json").write_text(__import__("json").dumps(metadata), encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fail_request(*args, **kwargs):
        raise AssertionError("prior failed positions should not be retried when --no-retry-errors is used")

    monkeypatch.setattr("gobench.cli.request_openai_move", fail_request)

    error = generate_from_profile(model_profile, suite, out_dir, continue_existing=True, retry_errors=False)

    assert error == "OpenAI API request failed"
    run = __import__("json").loads((out_dir / "run.json").read_text(encoding="utf-8"))
    assert run["positions_blocked_by_errors"] == 1
    assert run["positions_generated_new"] == 0


def test_preserve_existing_run_metadata_keeps_katago_paths_and_created_at():
    current = {"created_at": "new", "katago_bin": None, "katago_model": "", "katago_max_visits": 2048}
    previous = {
        "created_at": "old",
        "katago_bin": "/opt/homebrew/bin/katago",
        "katago_model": "/models/model.bin.gz",
        "katago_max_visits": "2048",
    }

    preserve_existing_run_metadata(current, previous)

    assert current["created_at"] == "old"
    assert current["katago_bin"] == "/opt/homebrew/bin/katago"
    assert current["katago_model"] == "/models/model.bin.gz"
    assert current["katago_max_visits"] == 2048


def test_score_predictions_reuses_cached_results_without_starting_scorer(tmp_path, monkeypatch):
    positions = [
        Position(position_id="dev_000001", to_move="B"),
        Position(position_id="dev_000002", to_move="W", black=["D4"]),
    ]
    positions_path = tmp_path / "positions.jsonl"
    write_jsonl(positions_path, positions)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_jsonl(
        run_dir / "predictions.jsonl",
        [
            MoveSubmission(position_id="dev_000001", move="R14"),
            MoveSubmission(position_id="dev_000002", move="D16"),
        ],
    )
    write_jsonl(
        run_dir / "results.jsonl",
        [
            ScoreResult(
                position_id="dev_000001",
                submitted_move="R14",
                legal=True,
                point_loss=0.1,
                top1_match=True,
                top3_match=True,
                top10_match=True,
                blunder=False,
                catastrophic_blunder=False,
            ),
            ScoreResult(
                position_id="dev_000002",
                submitted_move="D16",
                legal=True,
                point_loss=1.0,
                top1_match=False,
                top3_match=True,
                top10_match=True,
                blunder=False,
                catastrophic_blunder=False,
            ),
        ],
    )
    (run_dir / "run.json").write_text('{"scorer":"mock"}', encoding="utf-8")

    def fail_create_scorer():
        raise AssertionError("scorer should not be started for fully cached results")

    monkeypatch.setattr("gobench.cli.create_scorer", fail_create_scorer)
    suite = SuiteProfile(tmp_path / "suite.yaml", "suite", str(positions_path), 2, "mock", None, None)

    summary = score_predictions_for_suite(suite, run_dir / "predictions.jsonl", run_dir)

    assert summary["metrics"]["count"] == 2
    assert summary["run"]["positions_score_cached"] == 2
    assert summary["run"]["positions_scored_new"] == 0


def test_score_predictions_recomputes_changed_prediction(tmp_path, monkeypatch):
    positions = [Position(position_id="dev_000001", to_move="B")]
    positions_path = tmp_path / "positions.jsonl"
    write_jsonl(positions_path, positions)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_jsonl(run_dir / "predictions.jsonl", [MoveSubmission(position_id="dev_000001", move="Q16")])
    write_jsonl(
        run_dir / "results.jsonl",
        [
            ScoreResult(
                position_id="dev_000001",
                submitted_move="R14",
                legal=True,
                point_loss=0.1,
                top1_match=True,
                top3_match=True,
                top10_match=True,
                blunder=False,
                catastrophic_blunder=False,
            )
        ],
    )
    (run_dir / "run.json").write_text('{"scorer":"mock"}', encoding="utf-8")
    calls = []

    class FakeScorer:
        def score_move(self, position, submitted_move):
            calls.append((position.position_id, submitted_move))
            return ScoreResult(
                position_id=position.position_id,
                submitted_move=submitted_move,
                legal=True,
                point_loss=2.0,
                top1_match=False,
                top3_match=False,
                top10_match=True,
                blunder=False,
                catastrophic_blunder=False,
            )

        def close(self):
            pass

    monkeypatch.setattr("gobench.cli.create_scorer", lambda: FakeScorer())
    suite = SuiteProfile(tmp_path / "suite.yaml", "suite", str(positions_path), 1, "mock", None, None)

    summary = score_predictions_for_suite(suite, run_dir / "predictions.jsonl", run_dir)

    assert calls == [("dev_000001", "Q16")]
    assert summary["run"]["positions_score_cached"] == 0
    assert summary["run"]["positions_scored_new"] == 1


def test_validate_continue_existing_allows_matching_metadata(tmp_path):
    metadata = {
        "model": "gpt-5.5",
        "model_profile": "gpt-5.5-high",
        "model_profile_path": "models/gpt-5.5-high.yaml",
        "provider": "openai",
        "reasoning_effort": "high",
        "temperature": None,
        "max_output_tokens": 20000,
        "prompt_template": "prompts/pure_llm_json_v1.txt",
        "prompt_sha256": "abc",
        "suite": "public_dev",
        "suite_path": "suites/public_dev.yaml",
        "positions_path": "data/public_dev/positions.jsonl",
        "positions_requested": 20,
    }
    (tmp_path / "run.json").write_text(__import__("json").dumps(metadata), encoding="utf-8")
    (tmp_path / "predictions.jsonl").write_text("", encoding="utf-8")

    validate_continue_existing(tmp_path, dict(metadata))


def test_validate_continue_existing_rejects_changed_model(tmp_path):
    previous = {
        "model": "gpt-5.5",
        "model_profile": "gpt-5.5-high",
        "model_profile_path": "models/gpt-5.5-high.yaml",
        "provider": "openai",
        "reasoning_effort": "high",
        "temperature": None,
        "max_output_tokens": 20000,
        "prompt_template": "prompts/pure_llm_json_v1.txt",
        "prompt_sha256": "abc",
        "suite": "public_dev",
        "suite_path": "suites/public_dev.yaml",
        "positions_path": "data/public_dev/positions.jsonl",
        "positions_requested": 20,
    }
    current = dict(previous)
    current["model_profile"] = "gpt-5.5-low"
    (tmp_path / "run.json").write_text(__import__("json").dumps(previous), encoding="utf-8")
    (tmp_path / "predictions.jsonl").write_text("", encoding="utf-8")

    with pytest.raises(SystemExit, match="checkpoint metadata does not match"):
        validate_continue_existing(tmp_path, current)
