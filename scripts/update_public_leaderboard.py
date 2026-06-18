#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECTION_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the public-dev leaderboard from GitHub issue submissions.")
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY", "GoBenchmark/GoBench"))
    parser.add_argument("--issues-json", help="Read issue JSON from a local file instead of GitHub")
    parser.add_argument("--out", default="leaderboards/public-dev.md")
    parser.add_argument("--generated-at", help="ISO timestamp for deterministic tests")
    args = parser.parse_args()

    issues = load_issues(args.repo, args.issues_json)
    submissions = [submission for issue in issues if (submission := parse_submission(issue))]
    ranked = sorted(
        submissions,
        key=lambda submission: (
            -(submission["gobench_score"] if submission["gobench_score"] is not None else -1),
            submission["mean_point_loss"] if submission["mean_point_loss"] is not None else float("inf"),
            submission["issue_number"],
        ),
    )
    rendered = render_public_leaderboard(ranked, args.generated_at)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(json.dumps({"out": str(out_path), "ranked": len(ranked)}, indent=2))


def load_issues(repo: str, issues_json: str | None) -> list[dict[str, Any]]:
    if issues_json:
        data = json.loads(Path(issues_json).read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise SystemExit(f"{issues_json} must contain a JSON list")
        return data
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN or GH_TOKEN is required when --issues-json is not used")
    return fetch_public_dev_issues(repo, token)


def fetch_public_dev_issues(repo: str, token: str) -> list[dict[str, Any]]:
    gh_issues = fetch_public_dev_issues_with_gh(repo, token)
    if gh_issues is not None:
        return gh_issues
    owner_repo = urllib.parse.quote(repo, safe="/")
    query = urllib.parse.urlencode(
        {"state": "open", "labels": "public-dev,benchmark-submission", "per_page": "100"}
    )
    url = f"https://api.github.com/repos/{owner_repo}/issues?{query}"
    issues: list[dict[str, Any]] = []
    while url:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "gobench-public-leaderboard",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            issues.extend(json.loads(response.read().decode("utf-8")))
            url = next_link(response.headers.get("Link"))
    return [issue for issue in issues if "pull_request" not in issue]


def fetch_public_dev_issues_with_gh(repo: str, token: str) -> list[dict[str, Any]] | None:
    if not shutil.which("gh"):
        return None
    env = os.environ.copy()
    env.setdefault("GH_TOKEN", token)
    env.setdefault("GITHUB_TOKEN", token)
    command = [
        "gh",
        "api",
        "-X",
        "GET",
        "--paginate",
        f"repos/{repo}/issues",
        "-f",
        "state=open",
        "-f",
        "labels=public-dev,benchmark-submission",
        "-f",
        "per_page=100",
        "--jq",
        ".[] | @json",
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, env=env, text=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    issues = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    return [issue for issue in issues if "pull_request" not in issue]


def next_link(header: str | None) -> str | None:
    if not header:
        return None
    for part in header.split(","):
        match = re.match(r'\s*<([^>]+)>;\s*rel="next"', part)
        if match:
            return match.group(1)
    return None


def parse_submission(issue: dict[str, Any]) -> dict[str, Any] | None:
    body = str(issue.get("body") or "")
    sections = parse_issue_sections(body)
    metrics = parse_metrics(sections.get("aggregate metrics", ""))
    score = metrics.get("gobench_score")
    mpl = metrics.get("mean_point_loss")
    count = metrics.get("positions_scored") or metrics.get("count")
    if score is None or mpl is None:
        return None
    suite = clean_cell(sections.get("suite") or "public_dev")
    if "public" not in suite.lower():
        return None
    return {
        "issue_number": int(issue.get("number") or 0),
        "issue_url": str(issue.get("html_url") or ""),
        "submitter": clean_cell(((issue.get("user") or {}).get("login")) or "unknown"),
        "model": clean_cell(sections.get("model name") or issue.get("title") or "unknown"),
        "provider": clean_cell(sections.get("provider or api gateway") or "unknown"),
        "suite": suite,
        "gobench_score": score,
        "mean_point_loss": mpl,
        "legal_move_rate": metrics.get("legal_move_rate"),
        "top3_match_rate": metrics.get("top3_match_rate"),
        "blunder_rate": metrics.get("blunder_rate"),
        "positions_scored": int(count) if isinstance(count, (int, float)) else None,
        "updated_at": str(issue.get("updated_at") or issue.get("created_at") or ""),
    }


def parse_issue_sections(body: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(body))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        name = normalize_label(match.group(1))
        sections[name] = body[start:end].strip()
    return sections


def parse_metrics(text: str) -> dict[str, float]:
    metrics: dict[str, float] = {}
    label_map = {
        "gobench score": "gobench_score",
        "score": "gobench_score",
        "mean point loss": "mean_point_loss",
        "average point loss": "mean_point_loss",
        "mpl": "mean_point_loss",
        "legal move rate": "legal_move_rate",
        "legal moves": "legal_move_rate",
        "legal": "legal_move_rate",
        "top-3 match": "top3_match_rate",
        "top3 match": "top3_match_rate",
        "top-3": "top3_match_rate",
        "blunder rate": "blunder_rate",
        "blunder": "blunder_rate",
        "positions scored": "positions_scored",
        "count": "count",
    }
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("-*").strip()
        if not line or ":" not in line:
            continue
        label, value = line.split(":", 1)
        key = label_map.get(normalize_label(label))
        if not key:
            continue
        number = parse_number(value)
        if number is not None:
            metrics[key] = number
    return metrics


def parse_number(value: str) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
    if not match:
        return None
    number = float(match.group(0))
    if "%" in value:
        number /= 100.0
    return number


def render_public_leaderboard(submissions: list[dict[str, Any]], generated_at: str | None = None) -> str:
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    submissions = sorted(
        submissions,
        key=lambda submission: (
            -(submission["gobench_score"] if submission["gobench_score"] is not None else -1),
            submission["mean_point_loss"] if submission["mean_point_loss"] is not None else float("inf"),
            submission["issue_number"],
        ),
    )
    lines = [
        "# Public-Dev Leaderboard",
        "",
        "This community leaderboard is automatically generated from open GitHub issues labeled `public-dev` and `benchmark-submission`.",
        "It is meant to make GoBench easy to try and compare. It is not the official hidden-suite benchmark.",
        "",
        f"Last updated: `{generated_at}`",
        "",
        "| Rank | Model | Provider | Score | MPL | Legal | Top-3 | Blunder | Count | Submitter | Issue |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    if submissions:
        for rank, submission in enumerate(submissions, start=1):
            lines.append(
                "| {rank} | {model} | {provider} | {score} | {mpl} | {legal} | {top3} | {blunder} | {count} | @{submitter} | [#{issue_number}]({issue_url}) |".format(
                    rank=rank,
                    model=submission["model"],
                    provider=submission["provider"],
                    score=format_metric(submission["gobench_score"]),
                    mpl=format_metric(submission["mean_point_loss"]),
                    legal=format_percent(submission.get("legal_move_rate")),
                    top3=format_percent(submission.get("top3_match_rate")),
                    blunder=format_percent(submission.get("blunder_rate")),
                    count=submission.get("positions_scored") or "n/a",
                    submitter=submission["submitter"],
                    issue_number=submission["issue_number"],
                    issue_url=submission["issue_url"],
                )
            )
    else:
        lines.append("| - | No public-dev submissions yet | - | - | - | - | - | - | - | - | - |")
    lines.extend(
        [
            "",
            "Submit a public-dev result with the [Public-Dev Result issue form](https://github.com/GoBenchmark/GoBench/issues/new?template=public-dev-result.yml).",
            "Valid open issues are ranked automatically; no maintainer approval is required for this public board.",
            "",
        ]
    )
    return "\n".join(lines)


def normalize_label(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def clean_cell(value: Any) -> str:
    text = str(value).strip().replace("\n", " ")
    return text.replace("|", "\\|") or "unknown"


def format_metric(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return "n/a"


def format_percent(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value * 100:.1f}%"
    return "n/a"


if __name__ == "__main__":
    main()
