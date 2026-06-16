from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gobench.core.metrics import gobench_score


def write_run_artifacts(
    out_dir: Path,
    metadata: dict[str, Any],
    metrics: dict[str, Any],
    completed: bool,
    error: str | None,
) -> dict[str, Any]:
    summary = {
        "completed": completed,
        "error": error,
        "out": str(out_dir),
        "run": metadata,
        "metrics": metrics,
    }
    (out_dir / "run.json").write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "metrics.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "report.md").write_text(render_markdown_report(summary), encoding="utf-8")
    return summary


def summarize_raw_responses(raw_rows: list[dict[str, Any]]) -> dict[str, Any]:
    response_count = len(raw_rows)
    completed = sum(1 for row in raw_rows if row.get("status") == "completed")
    incomplete = sum(1 for row in raw_rows if row.get("status") and row.get("status") != "completed")
    errors = sum(1 for row in raw_rows if row.get("error"))
    latencies = [row["latency_seconds"] for row in raw_rows if isinstance(row.get("latency_seconds"), (int, float))]

    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    reasoning_tokens = 0
    has_usage = False
    for row in raw_rows:
        usage = row.get("usage")
        if not isinstance(usage, dict):
            continue
        has_usage = True
        input_tokens += int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        output_tokens += int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        total_tokens += int(usage.get("total_tokens") or 0)
        output_details = usage.get("output_tokens_details") or usage.get("completion_tokens_details") or {}
        if isinstance(output_details, dict):
            reasoning_tokens += int(output_details.get("reasoning_tokens") or 0)

    telemetry: dict[str, Any] = {
        "response_count": response_count,
        "response_completed_count": completed,
        "response_incomplete_count": incomplete,
        "response_error_count": errors,
    }
    if latencies:
        telemetry["total_latency_seconds"] = round(sum(latencies), 3)
        telemetry["avg_latency_seconds"] = round(sum(latencies) / len(latencies), 3)
    if has_usage:
        telemetry["input_tokens"] = input_tokens
        telemetry["output_tokens"] = output_tokens
        telemetry["total_tokens"] = total_tokens or input_tokens + output_tokens
        telemetry["reasoning_tokens"] = reasoning_tokens
    return telemetry


def render_markdown_report(summary: dict[str, Any]) -> str:
    run = summary.get("run", {})
    metrics = summary.get("metrics", {})
    title = run.get("run_name") or run.get("model") or "GoBench Run"
    lines = [
        f"# GoBench Run: {title}",
        "",
        f"- Status: {'complete' if summary.get('completed') else 'incomplete'}",
        f"- Model: {run.get('model', 'unknown')}",
        f"- Reasoning effort: {run.get('reasoning_effort') or 'none'}",
        f"- Suite: {run.get('suite', 'unknown')}",
        f"- Suite visibility: {run.get('suite_visibility') or 'unknown'}",
        f"- Scorer: {run.get('scorer', 'unknown')}",
        f"- Primary metric: {run.get('primary_metric') or 'mean_point_loss'}",
        f"- Created at: {run.get('created_at', 'unknown')}",
        f"- Prompt hash: `{run.get('prompt_sha256', 'unknown')}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| GoBench Score | {format_metric_number(metrics.get('gobench_score'))} / 100 |",
        f"| Mean Point Loss | {format_metric_number(metrics.get('mean_point_loss'))} |",
        f"| Legal Move Rate | {format_percent(metrics.get('legal_move_rate'))} |",
        f"| Top-1 Match | {format_percent(metrics.get('top1_match_rate'))} |",
        f"| Top-3 Match | {format_percent(metrics.get('top3_match_rate'))} |",
        f"| Top-10 Match | {format_percent(metrics.get('top10_match_rate'))} |",
        f"| Blunder Rate | {format_percent(metrics.get('blunder_rate'))} |",
        f"| Catastrophic Blunder Rate | {format_percent(metrics.get('catastrophic_blunder_rate'))} |",
        f"| Pass Rate | {format_percent(metrics.get('pass_rate'))} |",
        f"| Positions Scored | {metrics.get('count', 0)} |",
        "",
    ]

    phase_mpl = metrics.get("phase_mpl") or {}
    if phase_mpl:
        lines.extend(["## Phase MPL", "", "| Phase | MPL |", "|---|---:|"])
        for phase, mpl in sorted(phase_mpl.items()):
            lines.append(f"| {phase} | {format_metric_number(mpl)} |")
        lines.append("")

    if run.get("response_count") is not None:
        lines.extend(
            [
                "## Run Telemetry",
                "",
                "| Field | Value |",
                "|---|---:|",
                f"| Run elapsed | {run.get('run_elapsed_human') or format_number(run.get('run_elapsed_seconds'))} |",
                f"| Responses | {run.get('response_count', 0)} |",
                f"| Completed responses | {run.get('response_completed_count', 0)} |",
                f"| Incomplete responses | {run.get('response_incomplete_count', 0)} |",
                f"| Response errors | {run.get('response_error_count', 0)} |",
                f"| Total latency seconds | {format_number(run.get('total_latency_seconds'))} |",
                f"| Average latency seconds | {format_number(run.get('avg_latency_seconds'))} |",
                f"| Input tokens | {format_integer(run.get('input_tokens'))} |",
                f"| Output tokens | {format_integer(run.get('output_tokens'))} |",
                f"| Reasoning tokens | {format_integer(run.get('reasoning_tokens'))} |",
                f"| Total tokens | {format_integer(run.get('total_tokens'))} |",
                "",
            ]
        )

    if summary.get("error"):
        lines.extend(["## Error", "", f"```text\n{summary['error']}\n```", ""])

    return "\n".join(lines)


def load_run_summaries(runs_dir: Path) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for metrics_path in sorted(runs_dir.glob("*/metrics.json")):
        try:
            summary = json.loads(metrics_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        metrics = summary.get("metrics")
        if (
            isinstance(metrics, dict)
            and "gobench_score" not in metrics
            and isinstance(metrics.get("mean_point_loss"), (int, float))
        ):
            metrics["gobench_score"] = gobench_score(metrics["mean_point_loss"])
        summary.setdefault("out", str(metrics_path.parent))
        summaries.append(summary)
    return summaries


def filter_run_summaries(
    summaries: list[dict[str, Any]],
    suite: str | None = None,
    min_count: int | None = None,
    name_contains: str | None = None,
    completed_only: bool = False,
) -> list[dict[str, Any]]:
    filtered = []
    for summary in summaries:
        run = summary.get("run", {})
        metrics = summary.get("metrics", {})
        run_name = str(run.get("run_name") or Path(summary.get("out", "")).name)
        if suite and run.get("suite") != suite:
            continue
        if min_count is not None and int(metrics.get("count") or 0) < min_count:
            continue
        if name_contains and name_contains not in run_name:
            continue
        if completed_only and not summary.get("completed"):
            continue
        filtered.append(summary)
    return filtered


def render_leaderboard(summaries: list[dict[str, Any]]) -> str:
    ranked = sorted(
        summaries,
        key=lambda summary: (
            sortable_metric(summary.get("metrics", {}).get("mean_point_loss")),
            summary.get("run", {}).get("model", ""),
        ),
    )
    lines = [
        "| Rank | Run | Model | Suite | Score | MPL | Legal | Top-3 | Blunder | Count | Tokens | Avg s |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for index, summary in enumerate(ranked, start=1):
        run = summary.get("run", {})
        metrics = summary.get("metrics", {})
        run_name = run.get("run_name") or Path(summary.get("out", "")).name
        lines.append(
            "| {rank} | {run_name} | {model} | {suite} | {score} | {mpl} | {legal} | {top3} | {blunder} | {count} | {tokens} | {avg_latency} |".format(
                rank=index,
                run_name=run_name,
                model=run.get("model", "unknown"),
                suite=run.get("suite", "unknown"),
                score=format_metric_number(metrics.get("gobench_score")),
                mpl=format_metric_number(metrics.get("mean_point_loss")),
                legal=format_percent(metrics.get("legal_move_rate")),
                top3=format_percent(metrics.get("top3_match_rate")),
                blunder=format_percent(metrics.get("blunder_rate")),
                count=metrics.get("count", 0),
                tokens=format_integer(run.get("total_tokens")),
                avg_latency=format_number(run.get("avg_latency_seconds")),
            )
        )
    return "\n".join(lines)


def format_number(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return "n/a"


def format_metric_number(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return "n/a"


def format_percent(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value * 100:.1f}%"
    return "n/a"


def format_integer(value: Any) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value))
    return "n/a"


def sortable_metric(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return float("inf")
