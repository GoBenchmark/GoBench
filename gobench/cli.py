from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import uvicorn
import yaml

from gobench import __version__
from gobench.api.schemas import CandidateEval, MoveSubmission, Position, ScoreResult
from gobench.core.metrics import aggregate_metrics
from gobench.core.scorer_factory import create_scorer
from gobench.datasets.loader import append_jsonl, load_positions, load_predictions, read_jsonl_model, write_jsonl
from gobench.datasets.sample_data import make_example_predictions, make_toy_positions
from gobench.datasets.validate import validate_positions
from gobench.katago.analysis_client import KataGoAnalysisClient, KataGoAnalysisError, KataGoConfigError
from gobench.katago.mock_client import MockKataGoClient
from gobench.katago.selfplay import SelfPlayConfig, make_katago_selfplay_positions
from gobench.profiles import (
    ModelProfile,
    SuiteProfile,
    apply_suite_environment,
    list_profiles,
    load_model_profile,
    load_suite_profile,
)
from gobench.reporting import (
    filter_run_summaries,
    load_run_summaries,
    render_leaderboard,
    render_markdown_report,
    summarize_raw_responses,
    write_run_artifacts,
)
from gobench.visualization import suite_from_run, write_run_visualization

DEFAULT_PROMPT_TEMPLATE = "prompts/pure_llm_json_v1.txt"
DEFAULT_BUILTIN_MODEL_PROFILE = "models/gpt-5.5-xhigh.yaml"
DEFAULT_LOCAL_MODEL_PROFILE = ".gobench/model.yaml"
DEFAULT_ENV_FILE = ".env.local"

MODEL_PRESETS: dict[str, dict[str, Any]] = {
    "openai": {
        "provider": "openai",
        "model": "gpt-5.5",
        "reasoning_effort": "xhigh",
        "api_key_env": "OPENAI_API_KEY",
    },
    "claude-opus": {
        "provider": "anthropic",
        "model": "claude-opus-4-8",
        "api_key_env": "ANTHROPIC_API_KEY",
        "api_base": "https://api.anthropic.com",
    },
    "deepseek": {
        "provider": "openai-chat",
        "model": "deepseek-v4-pro",
        "reasoning_effort": "high",
        "api_key_env": "DEEPSEEK_API_KEY",
        "api_base": "https://api.deepseek.com",
    },
    "gemini": {
        "provider": "openai-chat",
        "model": "gemini-3.5-flash",
        "reasoning_effort": "high",
        "api_key_env": "GEMINI_API_KEY",
        "api_base": "https://generativelanguage.googleapis.com/v1beta/openai",
    },
    "openrouter": {
        "provider": "openai-chat",
        "model": "~openai/gpt-latest",
        "api_key_env": "OPENROUTER_API_KEY",
        "api_base": "https://openrouter.ai/api/v1",
    },
    "minimax": {
        "provider": "openai-chat",
        "model": "minimax/minimax-m3",
        "api_key_env": "OPENROUTER_API_KEY",
        "api_base": "https://openrouter.ai/api/v1",
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="gobench")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)

    validate_parser = subparsers.add_parser("validate-data")
    validate_parser.add_argument("path")

    eval_parser = subparsers.add_parser("eval-file")
    eval_parser.add_argument("--positions", required=True)
    eval_parser.add_argument("--predictions", required=True)
    eval_parser.add_argument("--labels")

    toy_parser = subparsers.add_parser("make-toy-data")
    toy_parser.add_argument("--out", required=True)
    toy_parser.add_argument("--n", type=int, default=20)

    selfplay_parser = subparsers.add_parser("make-katago-selfplay-data")
    selfplay_parser.add_argument("--out", required=True)
    selfplay_parser.add_argument("--n", type=int, default=20)
    selfplay_parser.add_argument("--env-file", default=".env.local")
    selfplay_parser.add_argument("--visits", type=int, default=128)
    selfplay_parser.add_argument("--analysis-pv-len", type=int, default=8)
    selfplay_parser.add_argument("--top-k", type=int, default=5)
    selfplay_parser.add_argument("--policy-temperature", type=float, default=0.5)
    selfplay_parser.add_argument("--min-target-moves", type=int, default=5)
    selfplay_parser.add_argument("--max-target-moves", type=int, default=199)
    selfplay_parser.add_argument("--seed", type=int, default=42)
    selfplay_parser.add_argument("--label-scorer", choices=["mock", "katago", "none"], default="mock")
    selfplay_parser.add_argument("--label-visits", type=int)

    precompute_parser = subparsers.add_parser("precompute-labels")
    precompute_parser.add_argument("--positions", required=True)
    precompute_parser.add_argument("--out", required=True)

    subparsers.add_parser("list-presets", help="list built-in model provider presets")

    configure_parser = subparsers.add_parser(
        "configure",
        help="write a local model profile and .env.local for easier runs",
    )
    configure_parser.add_argument("--preset", choices=sorted(MODEL_PRESETS), help="provider/model preset")
    configure_parser.add_argument("--provider", choices=["openai", "anthropic", "openai-chat"], help="model provider")
    configure_parser.add_argument("--model", help="model id sent to the provider API")
    configure_parser.add_argument("--api-key-env", help="environment variable that stores the API key")
    configure_parser.add_argument("--api-base", help="base URL for Anthropic or OpenAI-compatible APIs")
    configure_parser.add_argument("--reasoning-effort", help="reasoning effort when the provider supports it")
    configure_parser.add_argument("--temperature", type=float, help="optional sampling temperature")
    configure_parser.add_argument("--max-output-tokens", type=int, help="maximum response tokens")
    configure_parser.add_argument("--prompt-template", default=DEFAULT_PROMPT_TEMPLATE, help="prompt template path")
    configure_parser.add_argument("--api-key", help="API key to save in the local env file")
    configure_parser.add_argument("--scorer", choices=["mock", "katago"], default="mock", help="local scorer env default")
    configure_parser.add_argument("--katago-bin", help="path to the KataGo binary for real scoring")
    configure_parser.add_argument("--katago-model", help="path to the KataGo model for real scoring")
    configure_parser.add_argument(
        "--katago-config",
        default="configs/katago_gobench_official.cfg",
        help="KataGo analysis config path",
    )
    configure_parser.add_argument("--katago-max-visits", type=int, default=2048, help="KataGo visits per position")
    configure_parser.add_argument("--katago-analysis-pv-len", type=int, default=12, help="KataGo PV length")
    configure_parser.add_argument("--profile-path", default=DEFAULT_LOCAL_MODEL_PROFILE, help="local profile path")
    configure_parser.add_argument("--env-file", default=DEFAULT_ENV_FILE, help="local env file path")
    configure_parser.add_argument("--force", action="store_true", help="overwrite an existing local profile")

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--model-profile")
    doctor_parser.add_argument("--suite", default="suites/public_dev.yaml")
    doctor_parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)

    release_parser = subparsers.add_parser("release-check")
    release_parser.add_argument("--public-suite", default="suites/public_dev.yaml")
    release_parser.add_argument("--official-suite", default="suites/official_v0_1.yaml")
    release_parser.add_argument("--public-count", type=int, default=10)
    release_parser.add_argument("--official-count", type=int, default=50)

    subparsers.add_parser("list-models")
    subparsers.add_parser("list-suites")

    generate_parser = subparsers.add_parser("generate")
    add_profile_run_parser(generate_parser)
    generate_parser.add_argument("--continue-existing", action="store_true")
    add_retry_errors_parser(generate_parser)

    score_parser = subparsers.add_parser("score")
    score_parser.add_argument("--suite", default="suites/public_dev.yaml")
    score_parser.add_argument("--run-dir")
    score_parser.add_argument("--predictions")
    score_parser.add_argument("--out")

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("run_dir")

    visualize_parser = subparsers.add_parser("visualize")
    visualize_parser.add_argument("run_dir")
    visualize_parser.add_argument("--suite")
    visualize_parser.add_argument("--top-k", type=int, default=5)
    visualize_parser.add_argument("--refresh-candidates", action="store_true")
    visualize_parser.add_argument("--env-file", default=".env.local")
    visualize_parser.add_argument("--open", action="store_true")

    run_parser = subparsers.add_parser("run")
    add_profile_run_parser(run_parser)
    run_parser.add_argument("--continue-existing", action="store_true")
    add_retry_errors_parser(run_parser)
    add_run_visualization_parser(run_parser, default_visualize=True, default_open=True)

    run_openai_parser = subparsers.add_parser("run-openai")
    add_model_run_parser(run_openai_parser)
    add_run_visualization_parser(run_openai_parser)
    run_model_parser = subparsers.add_parser("run-model")
    add_model_run_parser(run_model_parser)
    add_run_visualization_parser(run_model_parser)

    leaderboard_parser = subparsers.add_parser("leaderboard")
    leaderboard_parser.add_argument("runs_dir", nargs="?", default="data/runs")
    leaderboard_parser.add_argument("--suite")
    leaderboard_parser.add_argument("--min-count", type=int)
    leaderboard_parser.add_argument("--name-contains")
    leaderboard_parser.add_argument("--completed-only", action="store_true")

    args = parser.parse_args()
    try:
        if args.command == "serve":
            uvicorn.run("gobench.api.main:app", host=args.host, port=args.port, reload=False)
        elif args.command == "validate-data":
            cmd_validate_data(args.path)
        elif args.command == "eval-file":
            cmd_eval_file(args.positions, args.predictions, args.labels)
        elif args.command == "make-toy-data":
            cmd_make_toy_data(args.out, args.n)
        elif args.command == "make-katago-selfplay-data":
            cmd_make_katago_selfplay_data(
                args.out,
                args.n,
                args.env_file,
                args.visits,
                args.analysis_pv_len,
                args.top_k,
                args.policy_temperature,
                args.min_target_moves,
                args.max_target_moves,
                args.seed,
                args.label_scorer,
                args.label_visits,
            )
        elif args.command == "precompute-labels":
            cmd_precompute_labels(args.positions, args.out)
        elif args.command == "list-presets":
            print(json.dumps(list_model_presets(), indent=2, sort_keys=True))
        elif args.command == "configure":
            cmd_configure(
                preset=args.preset,
                provider=args.provider,
                model=args.model,
                api_key_env=args.api_key_env,
                api_base=args.api_base,
                reasoning_effort=args.reasoning_effort,
                temperature=args.temperature,
                max_output_tokens=args.max_output_tokens,
                prompt_template=args.prompt_template,
                api_key=args.api_key,
                scorer=args.scorer,
                katago_bin=args.katago_bin,
                katago_model=args.katago_model,
                katago_config=args.katago_config,
                katago_max_visits=args.katago_max_visits,
                katago_analysis_pv_len=args.katago_analysis_pv_len,
                profile_path=args.profile_path,
                env_file=args.env_file,
                force=args.force,
            )
        elif args.command == "doctor":
            cmd_doctor(args.model_profile, args.suite, args.env_file)
        elif args.command == "release-check":
            cmd_release_check(args.public_suite, args.official_suite, args.public_count, args.official_count)
        elif args.command == "list-models":
            print(json.dumps(list_profiles("models"), indent=2, sort_keys=True))
        elif args.command == "list-suites":
            print(json.dumps(list_profiles("suites"), indent=2, sort_keys=True))
        elif args.command == "generate":
            cmd_generate(args.model_profile, args.suite, args.out, args.env_file, args.continue_existing, args.retry_errors)
        elif args.command == "score":
            cmd_score(args.suite, args.run_dir, args.predictions, args.out)
        elif args.command == "report":
            cmd_report(args.run_dir)
        elif args.command == "visualize":
            cmd_visualize(
                args.run_dir,
                args.suite,
                args.top_k,
                args.refresh_candidates,
                args.env_file,
                args.open,
            )
        elif args.command == "run":
            cmd_run_profile(
                args.model_profile,
                args.suite,
                args.out,
                args.env_file,
                args.continue_existing,
                args.retry_errors,
                args.visualize,
                args.open,
                args.visualize_top_k,
                args.refresh_candidates,
            )
        elif args.command in {"run-openai", "run-model"}:
            cmd_run_openai(
                args.positions,
                args.model,
                args.reasoning_effort,
                args.temperature,
                args.limit,
                args.max_output_tokens,
                args.prompt_template,
                args.out,
                args.env_file,
                args.visualize,
                args.open,
                args.visualize_top_k,
                args.refresh_candidates,
            )
        elif args.command == "leaderboard":
            cmd_leaderboard(
                args.runs_dir,
                suite=args.suite,
                min_count=args.min_count,
                name_contains=args.name_contains,
                completed_only=args.completed_only,
            )
    except (KataGoConfigError, KataGoAnalysisError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def add_profile_run_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model-profile")
    parser.add_argument("--suite", default="suites/public_dev.yaml")
    parser.add_argument("--out")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)


def add_model_run_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--positions", default="data/public_dev/positions.jsonl")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--max-output-tokens", type=int, default=2000)
    parser.add_argument("--prompt-template", default=DEFAULT_PROMPT_TEMPLATE)
    parser.add_argument("--out", default="data/runs/openai_test")
    parser.add_argument("--env-file", default=".env.local")


def add_retry_errors_parser(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--retry-errors",
        dest="retry_errors",
        action="store_true",
        default=True,
        help="Retry positions with prior OpenAI errors; default behavior",
    )
    group.add_argument(
        "--no-retry-errors",
        dest="retry_errors",
        action="store_false",
        help="Pause before retrying positions with prior OpenAI errors",
    )


class DisableVisualizationAction(argparse.Action):
    def __init__(self, option_strings: list[str], dest: str, **kwargs: Any) -> None:
        super().__init__(option_strings=option_strings, dest=dest, nargs=0, **kwargs)

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | None,
        option_string: str | None = None,
    ) -> None:
        setattr(namespace, self.dest, False)
        setattr(namespace, "open", False)


class OpenVisualizationAction(argparse.Action):
    def __init__(self, option_strings: list[str], dest: str, **kwargs: Any) -> None:
        super().__init__(option_strings=option_strings, dest=dest, nargs=0, **kwargs)

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | None,
        option_string: str | None = None,
    ) -> None:
        setattr(namespace, self.dest, True)
        setattr(namespace, "visualize", True)


def add_run_visualization_parser(
    parser: argparse.ArgumentParser,
    default_visualize: bool = False,
    default_open: bool = False,
) -> None:
    parser.set_defaults(visualize=default_visualize, open=default_open)
    parser.add_argument("--visualize", dest="visualize", action="store_true", help="Write visualization after the run")
    parser.add_argument(
        "--no-visualize",
        dest="visualize",
        action=DisableVisualizationAction,
        help="Do not write or open visualization after the run",
    )
    parser.add_argument(
        "--open",
        dest="open",
        action=OpenVisualizationAction,
        help="Open visualization after the run; implies --visualize",
    )
    parser.add_argument("--no-open", dest="open", action="store_false", help="Write visualization without opening a browser")
    parser.add_argument("--visualize-top-k", type=int, default=5)
    parser.add_argument("--refresh-candidates", action="store_true")


def cmd_validate_data(path: str) -> None:
    positions = load_positions(path)
    errors = validate_positions(positions)
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, indent=2))
        raise SystemExit(1)
    print(json.dumps({"valid": True, "count": len(positions)}, indent=2))


def cmd_eval_file(positions_path: str, predictions_path: str, labels_path: str | None = None) -> None:
    positions = {position.position_id: position for position in load_positions(positions_path)}
    predictions = load_predictions(predictions_path)
    label_map: dict[tuple[str, str], ScoreResult] = {}
    if labels_path:
        for label in read_jsonl_model(labels_path, ScoreResult):
            label_map[(label.position_id, label.submitted_move)] = label

    scorer = create_scorer()
    results = []
    try:
        for prediction in predictions:
            position = positions[prediction.position_id]
            cached = label_map.get((prediction.position_id, prediction.move))
            results.append(cached or scorer.score_move(position, prediction.move))
    finally:
        close = getattr(scorer, "close", None)
        if close:
            close()

    print(json.dumps(aggregate_metrics(results), indent=2, sort_keys=True))


def cmd_make_toy_data(out: str, n: int) -> None:
    out_dir = Path(out)
    positions = make_toy_positions(n)
    predictions = make_example_predictions(positions)
    scorer = MockKataGoClient()
    labels = [scorer.score_move(position, prediction.move) for position, prediction in zip(positions, predictions)]
    write_jsonl(out_dir / "positions.jsonl", positions)
    write_jsonl(out_dir / "example_predictions.jsonl", predictions)
    write_jsonl(out_dir / "labels.jsonl", labels)
    print(json.dumps({"positions": len(positions), "out": str(out_dir)}, indent=2))


def cmd_make_katago_selfplay_data(
    out: str,
    n: int,
    env_file: str,
    visits: int,
    analysis_pv_len: int,
    top_k: int,
    policy_temperature: float,
    min_target_moves: int,
    max_target_moves: int,
    seed: int,
    label_scorer: str,
    label_visits: int | None,
) -> None:
    if n < 1:
        raise SystemExit("--n must be >= 1")
    if visits < 1:
        raise SystemExit("--visits must be >= 1")
    if analysis_pv_len < 1:
        raise SystemExit("--analysis-pv-len must be >= 1")
    if top_k < 1:
        raise SystemExit("--top-k must be >= 1")
    if policy_temperature < 0:
        raise SystemExit("--policy-temperature must be >= 0")
    if min_target_moves < 1:
        raise SystemExit("--min-target-moves must be >= 1")
    if max_target_moves < min_target_moves:
        raise SystemExit("--max-target-moves must be >= --min-target-moves")

    load_env_file(env_file)
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    generator = KataGoAnalysisClient(max_visits=visits, analysis_pv_len=analysis_pv_len)
    try:
        positions = make_katago_selfplay_positions(
            generator,
            SelfPlayConfig(
                count=n,
                seed=seed,
                top_k=top_k,
                policy_temperature=policy_temperature,
                min_target_moves=min_target_moves,
                max_target_moves=max_target_moves,
            ),
            progress_callback=print_selfplay_progress,
        )
    finally:
        generator.close()

    predictions = make_example_predictions(positions)
    write_jsonl(out_dir / "positions.jsonl", positions)
    write_jsonl(out_dir / "example_predictions.jsonl", predictions)

    labels_count = 0
    if label_scorer != "none":
        scorer = (
            KataGoAnalysisClient(max_visits=label_visits, analysis_pv_len=analysis_pv_len)
            if label_scorer == "katago"
            else MockKataGoClient()
        )
        try:
            labels = [scorer.score_move(position, prediction.move) for position, prediction in zip(positions, predictions)]
        finally:
            close = getattr(scorer, "close", None)
            if close:
                close()
        labels_count = len(labels)
        write_jsonl(out_dir / "labels.jsonl", labels)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "generator": "katago-analysis-selfplay",
        "positions": len(positions),
        "target_moves": [len(position.move_history) for position in positions],
        "stone_counts": [len(position.black) + len(position.white) for position in positions],
        "seed": seed,
        "top_k": top_k,
        "policy_temperature": policy_temperature,
        "min_target_moves": min_target_moves,
        "max_target_moves": max_target_moves,
        "katago_generation_visits": visits,
        "katago_analysis_pv_len": analysis_pv_len,
        "label_scorer": label_scorer,
        "label_visits": label_visits,
        "katago_bin": os.getenv("KATAGO_BIN"),
        "katago_model": os.getenv("KATAGO_MODEL"),
        "katago_config": os.getenv("KATAGO_CONFIG"),
    }
    (out_dir / "selfplay_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    print(
        json.dumps(
            {
                "positions": len(positions),
                "labels": labels_count,
                "out": str(out_dir),
                "target_moves": manifest["target_moves"],
                "stone_counts": manifest["stone_counts"],
            },
            indent=2,
        )
    )


def print_selfplay_progress(progress: Any) -> None:
    prefix = f"[selfplay] {progress.position_index}/{progress.total_positions} {progress.position_id}"
    if progress.event == "start":
        print(f"{prefix} target={progress.target_moves} start", file=sys.stderr, flush=True)
    elif progress.event == "move" and progress.played_moves % 10 == 0:
        print(
            f"{prefix} played={progress.played_moves}/{progress.target_moves} last={progress.move}",
            file=sys.stderr,
            flush=True,
        )
    elif progress.event == "complete":
        print(f"{prefix} complete played={progress.played_moves}/{progress.target_moves}", file=sys.stderr, flush=True)


def cmd_precompute_labels(positions_path: str, out: str) -> None:
    scorer = create_scorer()
    rows: list[dict[str, Any]] = []
    try:
        for position in load_positions(positions_path):
            rows.append(
                {
                    "position_id": position.position_id,
                    "candidates": [candidate.model_dump() for candidate in scorer.analyze_position(position)],
                }
            )
    finally:
        close = getattr(scorer, "close", None)
        if close:
            close()
    write_jsonl(out, rows)
    candidate_count = sum(len(row["candidates"]) for row in rows)
    print(json.dumps({"positions": len(rows), "candidates": candidate_count, "out": out}, indent=2))


def cmd_configure(
    preset: str | None,
    provider: str | None,
    model: str | None,
    api_key_env: str | None,
    api_base: str | None,
    reasoning_effort: str | None,
    temperature: float | None,
    max_output_tokens: int | None,
    prompt_template: str,
    api_key: str | None,
    scorer: str,
    katago_bin: str | None,
    katago_model: str | None,
    katago_config: str,
    katago_max_visits: int,
    katago_analysis_pv_len: int,
    profile_path: str,
    env_file: str,
    force: bool,
) -> None:
    preset_values = dict(MODEL_PRESETS.get(preset or "openai", {}))
    provider = provider or preset_values.get("provider") or "openai"
    model = model or preset_values.get("model") or "gpt-5.5"
    api_key_env = api_key_env or preset_values.get("api_key_env") or default_api_key_env(provider)
    api_base = api_base or preset_values.get("api_base")
    reasoning_effort = reasoning_effort if reasoning_effort is not None else preset_values.get("reasoning_effort")
    max_output_tokens = max_output_tokens or 20000

    profile = Path(profile_path)
    if profile.exists() and not force:
        raise SystemExit(f"{profile} already exists; pass --force to overwrite it")
    if max_output_tokens < 1:
        raise SystemExit("--max-output-tokens must be >= 1")
    if katago_max_visits < 1:
        raise SystemExit("--katago-max-visits must be >= 1")
    if katago_analysis_pv_len < 1:
        raise SystemExit("--katago-analysis-pv-len must be >= 1")

    profile.parent.mkdir(parents=True, exist_ok=True)
    profile_data: dict[str, Any] = {
        "name": profile.stem,
        "provider": provider,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "prompt_template": prompt_template,
        "api_key_env": api_key_env,
    }
    if api_base:
        profile_data["api_base"] = api_base
    profile.write_text(yaml.safe_dump(profile_data, sort_keys=False), encoding="utf-8")

    env_updates = {
        "GOBENCH_SCORER": scorer,
        "GOBENCH_DB": "./data/gobench.sqlite",
    }
    if api_key:
        env_updates[api_key_env] = api_key
    if scorer == "katago":
        if katago_bin:
            env_updates["KATAGO_BIN"] = katago_bin
        if katago_model:
            env_updates["KATAGO_MODEL"] = katago_model
        env_updates["KATAGO_CONFIG"] = katago_config
        env_updates["KATAGO_MAX_VISITS"] = str(katago_max_visits)
        env_updates["KATAGO_ANALYSIS_PV_LEN"] = str(katago_analysis_pv_len)
        env_updates["KATAGO_REPORT_ANALYSIS_AS"] = "SIDETOMOVE"
    write_env_updates(Path(env_file), env_updates)

    next_steps = [
        "python -m gobench.cli generate --suite suites/public_dev.yaml --out data/runs/my-model-public-dev",
    ]
    if scorer == "katago":
        next_steps = [
            "python -m gobench.cli doctor",
            "python -m gobench.cli run --suite suites/public_dev.yaml --out data/runs/my-model-public-dev",
        ]
    else:
        next_steps.append(
            "for scored benchmark results, rerun configure with --force --scorer katago --katago-bin ... --katago-model ..."
        )

    print(
        json.dumps(
            {
                "ok": True,
                "model_profile": str(profile),
                "env_file": env_file,
                "preset": preset or "openai",
                "provider": provider,
                "model": model,
                "api_key_env": api_key_env,
                "api_key": "written" if api_key else "unchanged",
                "scorer": scorer,
                "next_steps": next_steps,
            },
            indent=2,
        )
    )


def list_model_presets() -> list[dict[str, Any]]:
    return [{"name": name, **values} for name, values in sorted(MODEL_PRESETS.items())]


def default_api_key_env(provider: str) -> str:
    return {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openai-chat": "OPENAI_API_KEY",
    }.get(provider, "OPENAI_API_KEY")


def resolve_default_model_profile(value: str | None) -> str:
    if value:
        return value
    local = Path(DEFAULT_LOCAL_MODEL_PROFILE)
    if local.exists():
        return str(local)
    return DEFAULT_BUILTIN_MODEL_PROFILE


def write_env_updates(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(updates)
    new_lines: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in remaining:
            new_lines.append(f"{key}={remaining.pop(key)}")
        else:
            new_lines.append(line)
    for key, value in remaining.items():
        new_lines.append(f"{key}={value}")
    path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def cmd_doctor(model_profile_path: str | None, suite_path: str, env_file: str) -> None:
    load_env_file(env_file)
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str | None = None) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    try:
        model_profile = load_model_profile(resolve_default_model_profile(model_profile_path))
        add("model_profile", True, str(model_profile.path))
    except Exception as exc:
        model_profile = None
        add("model_profile", False, str(exc))

    try:
        suite = load_suite_profile(suite_path)
        add("suite", True, str(suite.path))
        positions = load_suite_positions(suite)
        add("suite_positions", True, f"{len(positions)} positions loaded")
    except Exception as exc:
        suite = None
        add("suite", False, str(exc))

    if model_profile:
        key_env = model_profile.api_key_env or default_api_key_env(model_profile.provider)
        add("api_key", bool(os.getenv(key_env)), f"{key_env}: {'present' if os.getenv(key_env) else 'missing'}")
        if model_profile.provider in {"anthropic", "openai-chat"}:
            add("api_base", bool(model_profile.api_base), model_profile.api_base)

    if suite and suite.scorer.startswith("katago"):
        apply_suite_environment(suite)
        katago_bin = os.getenv("KATAGO_BIN")
        katago_model = os.getenv("KATAGO_MODEL")
        katago_config = os.getenv("KATAGO_CONFIG")
        add("katago_bin", bool(katago_bin and Path(katago_bin).exists()), katago_bin)
        add("katago_model", bool(katago_model and Path(katago_model).exists()), katago_model)
        add("katago_config", bool(katago_config and Path(katago_config).exists()), katago_config)
        if katago_bin and Path(katago_bin).exists():
            try:
                version = subprocess.run([katago_bin, "version"], capture_output=True, text=True, timeout=10)
                add("katago_version", version.returncode == 0, version.stdout.splitlines()[0] if version.stdout else version.stderr[:200])
            except Exception as exc:
                add("katago_version", False, str(exc))

    try:
        Path("data/runs").mkdir(parents=True, exist_ok=True)
        probe = Path("data/runs/.doctor-write-test")
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        add("runs_dir_writable", True, "data/runs")
    except Exception as exc:
        add("runs_dir_writable", False, str(exc))

    ok = all(check["ok"] for check in checks)
    print(json.dumps({"ok": ok, "checks": checks}, indent=2, sort_keys=True))
    if not ok:
        raise SystemExit(1)


def cmd_release_check(public_suite_path: str, official_suite_path: str, public_count: int, official_count: int) -> None:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str | None = None) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    try:
        public_suite = load_suite_profile(public_suite_path)
        public_positions = load_positions(public_suite.positions)
        public_errors = validate_positions(public_positions)
        add("public_suite_loads", True, str(public_suite.path))
        add("public_suite_visibility", public_suite.visibility == "public_dev_open", public_suite.visibility)
        add("public_suite_max_positions", public_suite.max_positions == public_count, str(public_suite.max_positions))
        add("public_positions_count", len(public_positions) == public_count, str(len(public_positions)))
        add("public_positions_validate", not public_errors, "; ".join(public_errors[:5]) if public_errors else None)
        add("public_canary", bool(public_suite.canary and "gobench-public-dev-canary" in public_suite.canary), public_suite.canary)
        check_optional_jsonl_count("public_example_predictions", Path("data/public_dev/example_predictions.jsonl"), public_count, checks)
        check_optional_jsonl_count("public_labels", Path("data/public_dev/labels.jsonl"), public_count, checks)
    except Exception as exc:
        add("public_suite_loads", False, str(exc))

    try:
        official_suite = load_suite_profile(official_suite_path)
        add("official_suite_loads", True, str(official_suite.path))
        add("official_suite_visibility", official_suite.visibility == "official_hidden", official_suite.visibility)
        add("official_suite_max_positions", official_suite.max_positions == official_count, str(official_suite.max_positions))
        official_positions_path = Path(official_suite.positions)
        add("official_suite_data_ignored", path_is_ignored(official_positions_path), official_suite.positions)
        if official_positions_path.exists():
            official_positions = load_positions(official_positions_path)
            official_errors = validate_positions(official_positions)
            add("official_positions_count", len(official_positions) == official_count, str(len(official_positions)))
            add(
                "official_positions_validate",
                not official_errors,
                "; ".join(official_errors[:5]) if official_errors else None,
            )
    except Exception as exc:
        add("official_suite_loads", False, str(exc))

    for path in [Path(".env.local"), Path("private"), Path("data/runs"), Path("analysis_logs"), Path("data/gobench.sqlite")]:
        add(f"ignored_{path}", path_is_ignored(path), str(path))

    for path in [
        Path("README.md"),
        Path("BENCHMARK.md"),
        Path("LICENSE"),
        Path("CITATION.cff"),
        Path("CONTRIBUTING.md"),
        Path("SECURITY.md"),
        Path(".github/workflows/tests.yml"),
    ]:
        add(f"release_file_{path}", path.exists(), str(path))

    ok = all(check["ok"] for check in checks)
    print(json.dumps({"ok": ok, "checks": checks}, indent=2, sort_keys=True))
    if not ok:
        raise SystemExit(1)


def check_optional_jsonl_count(name: str, path: Path, expected_count: int, checks: list[dict[str, Any]]) -> None:
    if not path.exists():
        checks.append({"name": name, "ok": False, "detail": f"missing: {path}"})
        return
    count = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    checks.append({"name": name, "ok": count == expected_count, "detail": str(count)})


def path_is_ignored(path: Path) -> bool:
    result = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=Path.cwd(), capture_output=True)
    if result.returncode == 0:
        return True
    return path_matches_gitignore(path, Path(".gitignore"))


def path_matches_gitignore(path: Path, gitignore_path: Path) -> bool:
    if not gitignore_path.exists():
        return False
    value = path.as_posix().rstrip("/")
    for raw_line in gitignore_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        anchored = line.startswith("/")
        pattern = line.lstrip("/").rstrip("/")
        if not pattern:
            continue
        if raw_line.rstrip().endswith("/"):
            if value == pattern or value.startswith(f"{pattern}/"):
                return True
            continue
        if anchored and fnmatch.fnmatch(value, pattern):
            return True
        if fnmatch.fnmatch(value, pattern) or fnmatch.fnmatch(Path(value).name, pattern):
            return True
    return False


def cmd_generate(
    model_profile_path: str | None,
    suite_path: str,
    out: str | None,
    env_file: str,
    continue_existing: bool,
    retry_errors: bool,
) -> None:
    load_env_file(env_file)
    model_profile = load_model_profile(resolve_default_model_profile(model_profile_path))
    suite = load_suite_profile(suite_path)
    out_dir = Path(out) if out else default_run_dir(model_profile, suite)
    generate_from_profile(model_profile, suite, out_dir, continue_existing, retry_errors)


def cmd_score(
    suite_path: str,
    run_dir: str | None,
    predictions: str | None,
    out: str | None,
) -> None:
    suite = load_suite_profile(suite_path)
    out_dir = Path(out or run_dir or "data/runs/scored_predictions")
    predictions_path = Path(predictions) if predictions else out_dir / "predictions.jsonl"
    summary = score_predictions_for_suite(suite, predictions_path, out_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))


def cmd_report(run_dir: str) -> None:
    run_path = Path(run_dir)
    metrics_path = run_path / "metrics.json"
    if not metrics_path.exists():
        raise SystemExit(f"missing metrics file: {metrics_path}")
    summary = json.loads(metrics_path.read_text(encoding="utf-8"))
    (run_path / "report.md").write_text(render_markdown_report(summary), encoding="utf-8")
    print(json.dumps({"report": str(run_path / "report.md")}, indent=2))


def cmd_visualize(
    run_dir: str,
    suite_path: str | None,
    top_k: int,
    refresh_candidates: bool,
    env_file: str,
    open_browser: bool,
) -> None:
    if top_k < 1:
        raise SystemExit("--top-k must be >= 1")
    load_env_file(env_file)
    run_path = Path(run_dir)
    suite = suite_from_run(run_path, suite_path)
    html_path = write_run_visualization(
        run_path,
        suite,
        top_k=top_k,
        open_browser=open_browser,
        refresh_candidates=refresh_candidates,
    )
    print(json.dumps({"visualization": str(html_path), "visualization_url": html_url(html_path)}, indent=2))


def maybe_add_run_visualization(
    summary: dict[str, Any],
    out_dir: Path,
    suite: SuiteProfile,
    visualize: bool,
    open_browser: bool,
    top_k: int,
    refresh_candidates: bool,
) -> None:
    if not (visualize or open_browser):
        return
    if top_k < 1:
        raise SystemExit("--visualize-top-k must be >= 1")
    html_path = write_run_visualization(
        out_dir,
        suite,
        top_k=top_k,
        open_browser=open_browser,
        refresh_candidates=refresh_candidates,
    )
    summary["visualization"] = str(html_path)
    summary["visualization_url"] = html_url(html_path)


def maybe_add_successful_run_visualization(
    summary: dict[str, Any],
    out_dir: Path,
    suite: SuiteProfile,
    visualize: bool,
    open_browser: bool,
    top_k: int,
    refresh_candidates: bool,
) -> None:
    if not summary.get("completed"):
        return
    maybe_add_run_visualization(summary, out_dir, suite, visualize, open_browser, top_k, refresh_candidates)


def html_url(path: Path) -> str:
    return path.resolve().as_uri()


class LiveTimer:
    active: "LiveTimer | None" = None

    def __init__(self, label: str, out_dir: Path) -> None:
        self.label = label
        self.out_dir = out_dir
        self.started_at = time.monotonic()
        self.inline = timer_style_is_inline()
        self.interval = timer_interval_seconds(self.inline)
        self.enabled = self.interval > 0 and not timer_style_is_off()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_line = ""

    def __enter__(self) -> "LiveTimer":
        self.started_at = time.monotonic()
        if not self.enabled:
            return self
        LiveTimer.active = self
        self._emit("start")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self.enabled:
            return
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        if self.inline:
            self._clear_line()
        LiveTimer.active = None
        self._emit("finish")

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self._emit("timer")

    def _emit(self, event: str) -> None:
        elapsed = time.monotonic() - self.started_at
        if self.inline and event != "finish":
            self._write_inline(timer_line(self.label, self.out_dir, elapsed))
            return
        print(timer_event_line(event, self.label, self.out_dir, elapsed), file=sys.stderr, flush=True)

    def _write_inline(self, line: str) -> None:
        with self._lock:
            padding = max(0, len(self._last_line) - len(line))
            sys.stderr.write("\r" + line + (" " * padding))
            sys.stderr.flush()
            self._last_line = line

    def _clear_line(self) -> None:
        with self._lock:
            if self._last_line:
                sys.stderr.write("\r" + (" " * len(self._last_line)) + "\r")
                sys.stderr.flush()
                self._last_line = ""

    def clear_for_log(self) -> None:
        if self.inline:
            self._clear_line()

    def redraw_after_log(self) -> None:
        if self.inline and not self._stop.is_set():
            self._write_inline(timer_line(self.label, self.out_dir, time.monotonic() - self.started_at))


def timer_style_is_inline() -> bool:
    style = os.getenv("GOBENCH_TIMER_STYLE", "auto").strip().lower()
    if style in {"off", "none", "false", "0"}:
        return False
    if style == "inline":
        return True
    if style == "lines":
        return False
    return sys.stderr.isatty()


def timer_style_is_off() -> bool:
    return os.getenv("GOBENCH_TIMER_STYLE", "auto").strip().lower() in {"off", "none", "false", "0"}


def timer_interval_seconds(inline: bool) -> float:
    default = "1" if inline else "60"
    value = os.getenv("GOBENCH_TIMER_INTERVAL_SECONDS", default)
    try:
        interval = float(value)
    except ValueError as exc:
        raise RuntimeError(f"GOBENCH_TIMER_INTERVAL_SECONDS must be numeric, got {value!r}") from exc
    if interval < 0:
        raise RuntimeError("GOBENCH_TIMER_INTERVAL_SECONDS must be >= 0")
    return interval


def timer_line(label: str, out_dir: Path, elapsed: float) -> str:
    return f"[GoBench] {label} elapsed {format_duration(elapsed)} | {out_dir}"


def timer_event_line(event: str, label: str, out_dir: Path, elapsed: float) -> str:
    if event == "finish":
        return f"[GoBench] {label} finished in {format_duration(elapsed)} | {out_dir}"
    if event == "start":
        return f"[GoBench] {label} started | {out_dir}"
    return f"[GoBench] {label} elapsed {format_duration(elapsed)} | {out_dir}"


def print_stderr_progress(payload: dict[str, Any]) -> None:
    active = LiveTimer.active
    if active:
        active.clear_for_log()
    line = json.dumps(payload) if progress_format_is_json() else progress_line(payload)
    print(line, file=sys.stderr, flush=True)
    if active:
        active.redraw_after_log()


def print_stdout_json(payload: dict[str, Any], *, indent: int | None = None, sort_keys: bool = False) -> None:
    active = LiveTimer.active
    if active:
        active.clear_for_log()
    print(json.dumps(payload, indent=indent, sort_keys=sort_keys), flush=True)
    if active:
        active.redraw_after_log()


def progress_format_is_json() -> bool:
    return os.getenv("GOBENCH_PROGRESS_FORMAT", "text").strip().lower() == "json"


def progress_line(payload: dict[str, Any]) -> str:
    stage = payload.get("stage")
    if stage == "score":
        if payload.get("skipped"):
            return (
                f"[GoBench] score skip {payload.get('index', '?')}/{payload.get('count', '?')} "
                f"{payload.get('position_id', 'unknown')} reason={payload.get('reason', 'cached_result')}"
            )
        return (
            f"[GoBench] score {payload.get('index', '?')}/{payload.get('count', '?')} "
            f"{payload.get('position_id', 'unknown')} move={payload.get('move', 'n/a')}"
        )
    if stage == "score_cache":
        return f"[GoBench] score cache reused {payload.get('cached', 0)}/{payload.get('count', '?')} existing results"
    if stage == "generate_cache":
        return f"[GoBench] generate cache reused {payload.get('cached', 0)}/{payload.get('count', '?')} existing predictions"
    if stage == "generate_blocked":
        return (
            f"[GoBench] generate paused: {payload.get('blocked', 0)} prior error(s); "
            "rerun without --no-retry-errors to try again"
        )
    if stage == "generate" and payload.get("skipped"):
        return (
            f"[GoBench] generate skip {payload.get('position_id', 'unknown')} "
            f"reason={payload.get('reason', 'unknown')}"
        )
    return "[GoBench] " + " ".join(f"{key}={value}" for key, value in payload.items())


def format_duration(seconds: float | int | None) -> str:
    if not isinstance(seconds, (int, float)):
        return "n/a"
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def finalize_run_elapsed(summary: dict[str, Any], out_dir: Path, started_at: float) -> None:
    elapsed = round(time.monotonic() - started_at, 3)
    run = summary.setdefault("run", {})
    run["run_elapsed_seconds"] = elapsed
    run["run_elapsed_human"] = format_duration(elapsed)
    write_summary_files(summary, out_dir)


def write_summary_files(summary: dict[str, Any], out_dir: Path) -> None:
    run = summary.setdefault("run", {})
    (out_dir / "run.json").write_text(json.dumps(run, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "metrics.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "report.md").write_text(render_markdown_report(summary), encoding="utf-8")


def checkpoint_generation_row(
    out_dir: Path,
    predictions: list[MoveSubmission],
    raw_rows: list[dict[str, Any]],
    prediction: MoveSubmission,
    raw_row: dict[str, Any],
    append_only: bool,
) -> None:
    if append_only:
        append_jsonl(out_dir / "predictions.jsonl", prediction)
        append_jsonl(out_dir / "raw_responses.jsonl", raw_row)
        return
    write_jsonl(out_dir / "predictions.jsonl", predictions)
    write_jsonl(out_dir / "raw_responses.jsonl", raw_rows)


def checkpoint_score_results(out_dir: Path, results: list[ScoreResult], preserve_existing: bool) -> None:
    target = out_dir / "results.partial.jsonl" if preserve_existing else out_dir / "results.jsonl"
    write_jsonl(target, results)


def finalize_score_results(out_dir: Path, results: list[ScoreResult]) -> None:
    write_jsonl(out_dir / "results.jsonl", results)
    partial_path = out_dir / "results.partial.jsonl"
    if partial_path.exists():
        partial_path.unlink()


def cmd_run_profile(
    model_profile_path: str | None,
    suite_path: str,
    out: str | None,
    env_file: str,
    continue_existing: bool,
    retry_errors: bool,
    visualize: bool,
    open_browser: bool,
    visualize_top_k: int,
    refresh_candidates: bool,
) -> None:
    load_env_file(env_file)
    model_profile = load_model_profile(resolve_default_model_profile(model_profile_path))
    suite = load_suite_profile(suite_path)
    out_dir = Path(out) if out else default_run_dir(model_profile, suite)
    with LiveTimer("run", out_dir) as timer:
        generation_error = generate_from_profile(model_profile, suite, out_dir, continue_existing, retry_errors)
        summary = score_predictions_for_suite(suite, out_dir / "predictions.jsonl", out_dir, generation_error)
        finalize_run_elapsed(summary, out_dir, timer.started_at)
        maybe_add_successful_run_visualization(
            summary,
            out_dir,
            suite,
            visualize,
            open_browser,
            visualize_top_k,
            refresh_candidates,
        )
        write_summary_files(summary, out_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))


def cmd_run_openai(
    positions_path: str,
    model: str,
    reasoning_effort: str,
    temperature: float | None,
    limit: int,
    max_output_tokens: int,
    prompt_template: str,
    out: str,
    env_file: str,
    visualize: bool,
    open_browser: bool,
    visualize_top_k: int,
    refresh_candidates: bool,
) -> None:
    load_env_file(env_file)
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set")

    with LiveTimer("run-openai", Path(out)) as timer:
        summary = run_openai_impl(
            positions_path,
            model,
            reasoning_effort,
            temperature,
            limit,
            max_output_tokens,
            prompt_template,
            out,
            visualize,
            open_browser,
            visualize_top_k,
            refresh_candidates,
            timer.started_at,
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


def run_openai_impl(
    positions_path: str,
    model: str,
    reasoning_effort: str,
    temperature: float | None,
    limit: int,
    max_output_tokens: int,
    prompt_template: str,
    out: str,
    visualize: bool,
    open_browser: bool,
    visualize_top_k: int,
    refresh_candidates: bool,
    run_started_at: float,
) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set")

    all_positions = load_positions(positions_path)
    positions = all_positions[:limit]
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    system_prompt = load_prompt_template(prompt_template)
    prompt_sha256 = sha256_text(system_prompt)

    metadata = build_run_metadata(
        out_dir=out_dir,
        model=model,
        reasoning_effort=reasoning_effort,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        prompt_template=prompt_template,
        prompt_sha256=prompt_sha256,
        positions_path=positions_path,
        requested_positions=len(positions),
        available_positions=len(all_positions),
    )

    predictions: list[MoveSubmission] = []
    raw_rows: list[dict[str, Any]] = []
    error: str | None = None
    with httpx.Client(timeout=openai_timeout_seconds()) as client:
        for position in positions:
            started = time.time()
            try:
                text, response_id, status, usage = request_openai_move(
                    client,
                    api_key,
                    model,
                    reasoning_effort,
                    temperature,
                    max_output_tokens,
                    system_prompt,
                    position,
                )
                move = parse_move_text(text, status)
            except RuntimeError as exc:
                error = str(exc)
                raw_rows.append(
                    {
                        "position_id": position.position_id,
                        "error": error,
                        "latency_seconds": round(time.time() - started, 3),
                    }
                )
                break
            prediction = MoveSubmission(position_id=position.position_id, move=move)
            raw_row = {
                "position_id": position.position_id,
                "response_id": response_id,
                "status": status,
                "raw_text": text,
                "parsed_move": move,
                "usage": usage,
                "latency_seconds": round(time.time() - started, 3),
            }
            predictions.append(prediction)
            raw_rows.append(raw_row)
            checkpoint_generation_row(out_dir, predictions, raw_rows, prediction, raw_row, append_only=len(predictions) > 1)
            print_stdout_json({"position_id": position.position_id, "move": move})

    scored_positions = positions[: len(predictions)]
    results: list[ScoreResult] = []
    preserve_existing_results = (out_dir / "results.jsonl").exists()
    scorer = create_scorer() if predictions else None
    try:
        for index, (position, prediction) in enumerate(zip(scored_positions, predictions), start=1):
            print_stderr_progress(
                {
                    "stage": "score",
                    "index": index,
                    "count": len(predictions),
                    "position_id": position.position_id,
                    "move": prediction.move,
                }
            )
            if scorer is None:
                raise RuntimeError("internal error: scorer was not initialized")
            results.append(scorer.score_move(position, prediction.move))
            checkpoint_score_results(out_dir, results, preserve_existing_results)
    finally:
        if scorer is not None:
            close = getattr(scorer, "close", None)
            if close:
                close()
    metrics = aggregate_metrics(results)
    metadata["positions_scored"] = len(results)
    metadata.update(summarize_raw_responses(raw_rows))
    metadata["completed_at"] = datetime.now(timezone.utc).isoformat()

    write_jsonl(out_dir / "predictions.jsonl", predictions)
    finalize_score_results(out_dir, results)
    write_jsonl(out_dir / "raw_responses.jsonl", raw_rows)
    summary = write_run_artifacts(out_dir, metadata, metrics, completed=error is None, error=error)
    finalize_run_elapsed(summary, out_dir, run_started_at)
    if visualize or open_browser:
        suite = SuiteProfile(
            path=Path(positions_path),
            name=Path(positions_path).stem,
            positions=positions_path,
            max_positions=limit,
            scorer=os.getenv("GOBENCH_SCORER", "mock").lower(),
            katago_max_visits=env_int_optional("KATAGO_MAX_VISITS"),
            katago_analysis_pv_len=env_int_optional("KATAGO_ANALYSIS_PV_LEN"),
        )
        maybe_add_run_visualization(summary, out_dir, suite, visualize, open_browser, visualize_top_k, refresh_candidates)
        write_summary_files(summary, out_dir)
    return summary


def generate_from_profile(
    model_profile: ModelProfile,
    suite: SuiteProfile,
    out_dir: Path,
    continue_existing: bool,
    retry_errors: bool = True,
) -> str | None:
    if model_profile.provider not in {"openai", "anthropic", "openai-chat"}:
        raise SystemExit(f"unsupported provider for generate: {model_profile.provider}")
    api_key_env = model_profile.api_key_env or default_api_key_env(model_profile.provider)
    api_key = os.getenv(api_key_env)
    if not api_key:
        raise SystemExit(f"{api_key_env} is not set")

    positions = load_suite_positions(suite)
    out_dir.mkdir(parents=True, exist_ok=True)
    system_prompt = load_prompt_template(model_profile.prompt_template)
    prompt_sha256 = sha256_text(system_prompt)

    predictions = load_predictions(out_dir / "predictions.jsonl") if continue_existing and (out_dir / "predictions.jsonl").exists() else []
    raw_rows = load_jsonl_dicts(out_dir / "raw_responses.jsonl") if continue_existing and (out_dir / "raw_responses.jsonl").exists() else []
    existing_raw_response_count = len(raw_rows)
    recovered_prediction_count = recover_completed_raw_predictions(
        predictions,
        raw_rows,
        {position.position_id for position in positions},
    )
    predicted_ids = {prediction.position_id for prediction in predictions}
    unresolved_errors = latest_unresolved_errors(raw_rows, predicted_ids)
    existing_prediction_count = len(predictions)
    new_prediction_count = 0
    error: str | None = None

    metadata = build_run_metadata_from_profiles(
        out_dir=out_dir,
        model_profile=model_profile,
        suite=suite,
        prompt_sha256=prompt_sha256,
        available_positions=len(load_positions(suite.positions)),
        requested_positions=len(positions),
    )
    if continue_existing:
        validate_continue_existing(out_dir, metadata)
        preserve_existing_run_metadata(metadata, load_run_metadata(out_dir))

    pending_positions: list[Position] = []
    existing_skip_count = 0
    for position in positions:
        if position.position_id in predicted_ids:
            existing_skip_count += 1
        else:
            pending_positions.append(position)
    if existing_skip_count:
        print_stderr_progress({"stage": "generate_cache", "cached": existing_skip_count, "count": len(positions)})

    blocked_by_prior_errors = continue_existing and bool(unresolved_errors) and not retry_errors
    if blocked_by_prior_errors:
        error = first_unresolved_error_for_positions(unresolved_errors, positions)
        print_stderr_progress(
            {
                "stage": "generate_blocked",
                "blocked": len(unresolved_errors),
                "count": len(positions),
            }
        )

    if pending_positions and not blocked_by_prior_errors:
        with httpx.Client(timeout=openai_timeout_seconds()) as client:
            for position in pending_positions:
                started = time.time()
                try:
                    text, response_id, status, usage = request_model_move(
                        client,
                        model_profile,
                        api_key,
                        system_prompt,
                        position,
                    )
                    move = parse_move_text(text, status)
                except RuntimeError as exc:
                    error = str(exc)
                    raw_rows.append(
                        {
                            "position_id": position.position_id,
                            "error": error,
                            "latency_seconds": round(time.time() - started, 3),
                        }
                    )
                    break
                prediction = MoveSubmission(position_id=position.position_id, move=move)
                raw_row = {
                    "position_id": position.position_id,
                    "response_id": response_id,
                    "status": status,
                    "raw_text": text,
                    "parsed_move": move,
                    "usage": usage,
                    "latency_seconds": round(time.time() - started, 3),
                }
                predictions.append(prediction)
                new_prediction_count += 1
                raw_rows.append(raw_row)
                append_only = continue_existing or new_prediction_count > 1
                checkpoint_generation_row(out_dir, predictions, raw_rows, prediction, raw_row, append_only=append_only)
                print_stdout_json({"position_id": position.position_id, "move": move})

    metadata["positions_generated"] = len(predictions)
    metadata["positions_existing"] = existing_prediction_count
    metadata["positions_recovered_from_raw"] = recovered_prediction_count
    metadata["positions_blocked_by_errors"] = len(unresolved_errors) if blocked_by_prior_errors else 0
    metadata["retry_errors"] = retry_errors
    metadata["positions_generated_new"] = new_prediction_count
    metadata["positions_pending"] = max(0, len(positions) - len(predictions))
    metadata["raw_responses_existing"] = existing_raw_response_count
    metadata["raw_responses_new"] = len(raw_rows) - existing_raw_response_count
    metadata.update(summarize_raw_responses(raw_rows))
    metadata.update(prefix_keys("new", summarize_raw_responses(raw_rows[existing_raw_response_count:])))
    metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
    metadata["generation_error"] = error
    write_jsonl(out_dir / "predictions.jsonl", predictions)
    write_jsonl(out_dir / "raw_responses.jsonl", raw_rows)
    (out_dir / "run.json").write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    print_stdout_json(
        {
            "out": str(out_dir),
            "generated": len(predictions),
            "generated_new": new_prediction_count,
            "existing": existing_prediction_count,
            "pending": metadata["positions_pending"],
            "run": metadata,
        },
        indent=2,
        sort_keys=True,
    )
    return error


def score_predictions_for_suite(
    suite: SuiteProfile,
    predictions_path: Path,
    out_dir: Path,
    generation_error: str | None = None,
) -> dict[str, Any]:
    apply_suite_environment(suite)
    out_dir.mkdir(parents=True, exist_ok=True)
    positions = {position.position_id: position for position in load_suite_positions(suite)}
    predictions = load_predictions(predictions_path)
    metadata = load_run_metadata(out_dir)
    cached_results = load_reusable_score_results(out_dir, suite, metadata)
    results: list[ScoreResult] = []
    scoreable_predictions = [prediction for prediction in predictions if prediction.position_id in positions]
    scoreable_count = len(scoreable_predictions)
    cached_score_count = 0
    new_score_count = 0
    cache_reported = False
    preserve_existing_results = (out_dir / "results.jsonl").exists()
    scorer = None
    try:
        for prediction in scoreable_predictions:
            position = positions[prediction.position_id]
            cached = cached_results.get((prediction.position_id, prediction.move))
            if cached is not None:
                results.append(cached)
                cached_score_count += 1
                continue
            if cached_score_count and not cache_reported:
                print_stderr_progress({"stage": "score_cache", "cached": cached_score_count, "count": scoreable_count})
                cache_reported = True
            if scorer is None:
                scorer = create_scorer()
            print_stderr_progress(
                {
                    "stage": "score",
                    "index": len(results) + 1,
                    "count": scoreable_count,
                    "position_id": position.position_id,
                    "move": prediction.move,
                }
            )
            results.append(scorer.score_move(position, prediction.move))
            new_score_count += 1
            checkpoint_score_results(out_dir, results, preserve_existing_results)
        if cached_score_count and not cache_reported:
            print_stderr_progress({"stage": "score_cache", "cached": cached_score_count, "count": scoreable_count})
    finally:
        if scorer is not None:
            close = getattr(scorer, "close", None)
            if close:
                close()

    metadata.setdefault("run_name", out_dir.name)
    metadata.setdefault("gobench_version", __version__)
    metadata.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    metadata.setdefault("model", "custom_predictions")
    metadata.setdefault("provider", "file")
    generation_error = generation_error or metadata.get("generation_error") or infer_generation_error(out_dir)
    metadata["suite"] = suite.name
    metadata["suite_path"] = str(suite.path)
    metadata["suite_visibility"] = suite.visibility
    metadata["suite_canary"] = suite.canary
    metadata["scorer"] = suite.scorer
    metadata["primary_metric"] = suite.primary_metric or "mean_point_loss"
    metadata["positions_scored"] = len(results)
    metadata["positions_score_cached"] = cached_score_count
    metadata["positions_scored_new"] = new_score_count
    metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
    metadata["generation_error"] = generation_error
    metadata["katago_max_visits"] = os.getenv("KATAGO_MAX_VISITS")
    metadata["katago_analysis_pv_len"] = os.getenv("KATAGO_ANALYSIS_PV_LEN")
    raw_path = out_dir / "raw_responses.jsonl"
    if raw_path.exists():
        metadata.update(summarize_raw_responses(load_jsonl_dicts(raw_path)))

    finalize_score_results(out_dir, results)
    completed = metadata.get("generation_error") is None and len(results) > 0
    return write_run_artifacts(
        out_dir,
        metadata,
        aggregate_metrics(results),
        completed=completed,
        error=metadata.get("generation_error"),
    )


def cmd_leaderboard(
    runs_dir: str,
    suite: str | None = None,
    min_count: int | None = None,
    name_contains: str | None = None,
    completed_only: bool = False,
) -> None:
    summaries = load_run_summaries(Path(runs_dir))
    summaries = filter_run_summaries(
        summaries,
        suite=suite,
        min_count=min_count,
        name_contains=name_contains,
        completed_only=completed_only,
    )
    print(render_leaderboard(summaries))


def load_env_file(path: str) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env_int_optional(name: str) -> int | None:
    value = os.getenv(name)
    if not value:
        return None
    return int(value)


def prefix_keys(prefix: str, values: dict[str, Any]) -> dict[str, Any]:
    return {f"{prefix}_{key}": value for key, value in values.items()}


def request_model_move(
    client: httpx.Client,
    model_profile: ModelProfile,
    api_key: str,
    system_prompt: str,
    position: Position,
) -> tuple[str, str | None, str | None, dict[str, Any] | None]:
    if model_profile.provider == "openai":
        return request_openai_move(
            client,
            api_key,
            model_profile.model,
            model_profile.reasoning_effort or "",
            model_profile.temperature,
            model_profile.max_output_tokens,
            system_prompt,
            position,
        )
    if model_profile.provider == "anthropic":
        return request_anthropic_move(client, api_key, model_profile, system_prompt, position)
    if model_profile.provider == "openai-chat":
        return request_openai_chat_move(client, api_key, model_profile, system_prompt, position)
    raise SystemExit(f"unsupported provider for generate: {model_profile.provider}")


def request_openai_move(
    client: httpx.Client,
    api_key: str,
    model: str,
    reasoning_effort: str,
    temperature: float | None,
    max_output_tokens: int,
    system_prompt: str,
    position: Position,
) -> tuple[str, str | None, str | None, dict[str, Any] | None]:
    payload: dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": position.model_dump_json(),
            },
        ],
        "max_output_tokens": max_output_tokens,
    }
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}
    if temperature is not None:
        payload["temperature"] = temperature

    try:
        response = client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"OpenAI API timeout for {position.position_id}: {exc}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"OpenAI API request failed for {position.position_id}: {exc}") from exc
    if response.status_code >= 400:
        raise RuntimeError(f"OpenAI API error {response.status_code}: {response.text[:1200]}")
    data = response.json()
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
    return extract_response_text(data), data.get("id"), data.get("status"), usage


def request_openai_chat_move(
    client: httpx.Client,
    api_key: str,
    model_profile: ModelProfile,
    system_prompt: str,
    position: Position,
) -> tuple[str, str | None, str | None, dict[str, Any] | None]:
    api_base = (model_profile.api_base or "https://api.openai.com/v1").rstrip("/")
    payload: dict[str, Any] = {
        "model": model_profile.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": position.model_dump_json()},
        ],
        "max_tokens": model_profile.max_output_tokens,
        "stream": False,
    }
    if model_profile.reasoning_effort:
        payload["reasoning_effort"] = model_profile.reasoning_effort
    if model_profile.temperature is not None:
        payload["temperature"] = model_profile.temperature

    try:
        response = client.post(
            f"{api_base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"{model_profile.provider} API timeout for {position.position_id}: {exc}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"{model_profile.provider} API request failed for {position.position_id}: {exc}") from exc
    if response.status_code >= 400:
        raise RuntimeError(f"{model_profile.provider} API error {response.status_code}: {response.text[:1200]}")
    data = response.json()
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") if isinstance(choice, dict) else {}
    text = message.get("content") if isinstance(message, dict) and isinstance(message.get("content"), str) else ""
    status = "completed" if text.strip() else choice.get("finish_reason") if isinstance(choice, dict) else None
    return text, data.get("id"), status, usage


def request_anthropic_move(
    client: httpx.Client,
    api_key: str,
    model_profile: ModelProfile,
    system_prompt: str,
    position: Position,
) -> tuple[str, str | None, str | None, dict[str, Any] | None]:
    api_base = (model_profile.api_base or "https://api.anthropic.com").rstrip("/")
    payload: dict[str, Any] = {
        "model": model_profile.model,
        "system": system_prompt,
        "messages": [{"role": "user", "content": position.model_dump_json()}],
        "max_tokens": model_profile.max_output_tokens,
    }
    if model_profile.temperature is not None:
        payload["temperature"] = model_profile.temperature
    try:
        response = client.post(
            f"{api_base}/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"Anthropic API timeout for {position.position_id}: {exc}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Anthropic API request failed for {position.position_id}: {exc}") from exc
    if response.status_code >= 400:
        raise RuntimeError(f"Anthropic API error {response.status_code}: {response.text[:1200]}")
    data = response.json()
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
    return extract_anthropic_text(data), data.get("id"), "completed", usage


def extract_response_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    texts: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if isinstance(content.get("text"), str):
                texts.append(content["text"])
    return "\n".join(texts)


def extract_anthropic_text(data: dict[str, Any]) -> str:
    texts: list[str] = []
    for item in data.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
            texts.append(item["text"])
    return "\n".join(texts)


def openai_timeout_seconds() -> float:
    value = os.getenv("OPENAI_TIMEOUT_SECONDS", "90")
    try:
        timeout = float(value)
    except ValueError as exc:
        raise RuntimeError(f"OPENAI_TIMEOUT_SECONDS must be numeric, got {value!r}") from exc
    if timeout <= 0:
        raise RuntimeError("OPENAI_TIMEOUT_SECONDS must be positive")
    return timeout


def parse_move_text(text: str, status: str | None = None) -> str:
    if status != "completed" or not text.strip():
        return "__invalid__"
    try:
        payload = json.loads(text)
        if isinstance(payload, dict) and isinstance(payload.get("move"), str):
            return payload["move"]
    except json.JSONDecodeError:
        pass
    match = re.search(r'"move"\s*:\s*"([^"]+)"', text)
    if match:
        return match.group(1)
    stripped = text.strip().strip("`")
    return stripped or "__invalid__"


def recover_completed_raw_predictions(
    predictions: list[MoveSubmission],
    raw_rows: list[dict[str, Any]],
    valid_position_ids: set[str],
) -> int:
    predicted_ids = {prediction.position_id for prediction in predictions}
    recovered = 0
    for row in raw_rows:
        position_id = row.get("position_id")
        if not isinstance(position_id, str) or position_id not in valid_position_ids or position_id in predicted_ids:
            continue
        if row.get("status") != "completed":
            continue
        move = row.get("parsed_move")
        if not isinstance(move, str) or not move.strip():
            raw_text = row.get("raw_text")
            if not isinstance(raw_text, str):
                continue
            move = parse_move_text(raw_text, row.get("status"))
        predictions.append(MoveSubmission(position_id=position_id, move=move))
        predicted_ids.add(position_id)
        recovered += 1
    return recovered


def load_prompt_template(path: str) -> str:
    return Path(path).read_text(encoding="utf-8").strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_run_metadata(
    out_dir: Path,
    model: str,
    reasoning_effort: str,
    temperature: float | None,
    max_output_tokens: int,
    prompt_template: str,
    prompt_sha256: str,
    positions_path: str,
    requested_positions: int,
    available_positions: int,
) -> dict[str, Any]:
    return {
        "run_name": out_dir.name,
        "gobench_version": __version__,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "model": model,
        "provider": "openai",
        "reasoning_effort": reasoning_effort,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "prompt_template": prompt_template,
        "prompt_sha256": prompt_sha256,
        "positions_path": positions_path,
        "positions_requested": requested_positions,
        "positions_available": available_positions,
        "positions_scored": 0,
        "scorer": os.getenv("GOBENCH_SCORER", "mock").lower(),
        "katago_bin": os.getenv("KATAGO_BIN"),
        "katago_model": os.getenv("KATAGO_MODEL"),
        "katago_config": os.getenv("KATAGO_CONFIG"),
        "katago_max_visits": os.getenv("KATAGO_MAX_VISITS"),
        "katago_analysis_pv_len": os.getenv("KATAGO_ANALYSIS_PV_LEN"),
        "katago_report_analysis_as": os.getenv("KATAGO_REPORT_ANALYSIS_AS", "SIDETOMOVE"),
    }


def build_run_metadata_from_profiles(
    out_dir: Path,
    model_profile: ModelProfile,
    suite: SuiteProfile,
    prompt_sha256: str,
    available_positions: int,
    requested_positions: int,
) -> dict[str, Any]:
    return {
        "run_name": out_dir.name,
        "gobench_version": __version__,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "model": model_profile.model,
        "model_profile": model_profile.name,
        "model_profile_path": str(model_profile.path),
        "provider": model_profile.provider,
        "api_key_env": model_profile.api_key_env,
        "api_base": model_profile.api_base,
        "reasoning_effort": model_profile.reasoning_effort,
        "temperature": model_profile.temperature,
        "max_output_tokens": model_profile.max_output_tokens,
        "prompt_template": model_profile.prompt_template,
        "prompt_sha256": prompt_sha256,
        "suite": suite.name,
        "suite_path": str(suite.path),
        "suite_visibility": suite.visibility,
        "suite_canary": suite.canary,
        "positions_path": suite.positions,
        "positions_requested": requested_positions,
        "positions_available": available_positions,
        "positions_generated": 0,
        "positions_scored": 0,
        "scorer": suite.scorer,
        "primary_metric": suite.primary_metric or "mean_point_loss",
        "katago_bin": os.getenv("KATAGO_BIN"),
        "katago_model": os.getenv("KATAGO_MODEL"),
        "katago_config": os.getenv("KATAGO_CONFIG"),
        "katago_max_visits": suite.katago_max_visits,
        "katago_analysis_pv_len": suite.katago_analysis_pv_len,
        "katago_report_analysis_as": os.getenv("KATAGO_REPORT_ANALYSIS_AS", "SIDETOMOVE"),
    }


def load_suite_positions(suite: SuiteProfile) -> list[Position]:
    positions = load_positions(suite.positions)
    if suite.max_positions is not None:
        return positions[: suite.max_positions]
    return positions


def load_jsonl_dicts(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_reusable_score_results(
    out_dir: Path,
    suite: SuiteProfile,
    metadata: dict[str, Any],
) -> dict[tuple[str, str], ScoreResult]:
    results_path = out_dir / "results.jsonl"
    if not results_path.exists() or not score_cache_is_compatible(suite, metadata):
        return {}
    reusable: dict[tuple[str, str], ScoreResult] = {}
    for result in read_jsonl_model(results_path, ScoreResult):
        reusable[(result.position_id, result.submitted_move)] = result
    return reusable


def score_cache_is_compatible(suite: SuiteProfile, metadata: dict[str, Any]) -> bool:
    current = current_score_cache_signature(suite)
    return all(normalize_metadata_value(metadata.get(key)) == normalize_metadata_value(value) for key, value in current.items())


def current_score_cache_signature(suite: SuiteProfile) -> dict[str, Any]:
    signature: dict[str, Any] = {"scorer": suite.scorer}
    if suite.scorer.startswith("katago"):
        signature.update(
            {
                "katago_max_visits": os.getenv("KATAGO_MAX_VISITS"),
                "katago_analysis_pv_len": os.getenv("KATAGO_ANALYSIS_PV_LEN"),
                "katago_report_analysis_as": os.getenv("KATAGO_REPORT_ANALYSIS_AS", "SIDETOMOVE"),
            }
        )
        for metadata_key, env_key in (("katago_model", "KATAGO_MODEL"), ("katago_config", "KATAGO_CONFIG")):
            value = os.getenv(env_key)
            if value:
                signature[metadata_key] = value
    return signature


def normalize_metadata_value(value: Any) -> str:
    return "" if value is None else str(value)


def load_run_metadata(out_dir: Path) -> dict[str, Any]:
    path = out_dir / "run.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


CONTINUE_COMPATIBILITY_FIELDS = [
    "model",
    "model_profile",
    "model_profile_path",
    "provider",
    "api_key_env",
    "api_base",
    "reasoning_effort",
    "temperature",
    "max_output_tokens",
    "prompt_template",
    "prompt_sha256",
    "suite",
    "suite_path",
    "positions_path",
    "positions_requested",
]


def validate_continue_existing(out_dir: Path, current_metadata: dict[str, Any]) -> None:
    has_checkpoint = any((out_dir / name).exists() for name in ("predictions.jsonl", "raw_responses.jsonl", "results.jsonl"))
    previous = load_run_metadata(out_dir)
    if not previous:
        if has_checkpoint:
            raise SystemExit(
                f"refusing --continue-existing for {out_dir}: checkpoint files exist but run.json is missing"
            )
        return

    mismatches = []
    for field in CONTINUE_COMPATIBILITY_FIELDS:
        previous_value = previous.get(field)
        current_value = current_metadata.get(field)
        if previous_value != current_value:
            mismatches.append(f"{field}: existing={previous_value!r}, current={current_value!r}")
    if mismatches:
        details = "; ".join(mismatches)
        raise SystemExit(
            f"refusing --continue-existing for {out_dir}: checkpoint metadata does not match current run ({details}). "
            "Use a different --out directory or delete the old checkpoint."
        )


PRESERVE_ON_CONTINUE_FIELDS = [
    "created_at",
    "katago_bin",
    "katago_model",
    "katago_config",
    "katago_max_visits",
    "katago_analysis_pv_len",
    "katago_report_analysis_as",
]


def preserve_existing_run_metadata(current_metadata: dict[str, Any], previous_metadata: dict[str, Any]) -> None:
    for field in PRESERVE_ON_CONTINUE_FIELDS:
        previous_value = previous_metadata.get(field)
        if previous_value in (None, ""):
            continue
        if field == "created_at" or current_metadata.get(field) in (None, ""):
            current_metadata[field] = previous_value


def infer_generation_error(out_dir: Path) -> str | None:
    raw_path = out_dir / "raw_responses.jsonl"
    if not raw_path.exists():
        return None
    raw_rows = load_jsonl_dicts(raw_path)
    prediction_path = out_dir / "predictions.jsonl"
    resolved_ids = {prediction.position_id for prediction in load_predictions(prediction_path)} if prediction_path.exists() else set()
    errors = latest_unresolved_errors(raw_rows, resolved_ids)
    return next(iter(errors.values()), None)


def latest_unresolved_errors(raw_rows: list[dict[str, Any]], resolved_ids: set[str]) -> dict[str, str]:
    errors: dict[str, str] = {}
    for row in raw_rows:
        position_id = row.get("position_id")
        if not isinstance(position_id, str):
            continue
        if position_id in resolved_ids or row.get("status") == "completed":
            errors.pop(position_id, None)
            continue
        if row.get("error"):
            errors[position_id] = str(row["error"])
    return errors


def first_unresolved_error_for_positions(errors: dict[str, str], positions: list[Position]) -> str | None:
    for position in positions:
        error = errors.get(position.position_id)
        if error:
            return error
    return next(iter(errors.values()), None)


def default_run_dir(model_profile: ModelProfile, suite: SuiteProfile) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("data/runs") / f"{suite.name}-{model_profile.name}-{stamp}"


if __name__ == "__main__":
    main()
