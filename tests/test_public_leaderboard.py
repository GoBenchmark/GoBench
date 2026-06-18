from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update_public_leaderboard.py"
SPEC = importlib.util.spec_from_file_location("update_public_leaderboard", SCRIPT_PATH)
assert SPEC and SPEC.loader
leaderboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(leaderboard)


def make_issue(number: int, model: str, score: float, mpl: float) -> dict:
    return {
        "number": number,
        "html_url": f"https://github.com/GoBenchmark/GoBench/issues/{number}",
        "title": f"Public-Dev Result: {model}",
        "user": {"login": "tester"},
        "updated_at": "2026-06-19T00:00:00Z",
        "body": f"""### Model name

{model}

### Provider or API gateway

Example Provider

### Suite

public_dev

### Aggregate metrics

GoBench Score: {score}
Mean Point Loss: {mpl}
Legal Move Rate: 100%
Top-3 Match: 20%
Blunder Rate: 10%
Positions Scored: 10
""",
    }


def test_parse_submission_extracts_public_dev_metrics():
    issue = make_issue(7, "example/model", 42.35, 3.21)

    submission = leaderboard.parse_submission(issue)

    assert submission["model"] == "example/model"
    assert submission["provider"] == "Example Provider"
    assert submission["gobench_score"] == 42.35
    assert submission["mean_point_loss"] == 3.21
    assert submission["legal_move_rate"] == 1.0
    assert submission["top3_match_rate"] == 0.2
    assert submission["positions_scored"] == 10


def test_render_public_leaderboard_sorts_by_score_then_mpl():
    low = leaderboard.parse_submission(make_issue(1, "low-score", 10, 1))
    best = leaderboard.parse_submission(make_issue(2, "best", 90, 2))
    tie = leaderboard.parse_submission(make_issue(3, "tie-better-mpl", 90, 1))

    rendered = leaderboard.render_public_leaderboard([low, best, tie], "2026-06-19T00:00:00+00:00")

    best_index = rendered.index("tie-better-mpl")
    second_index = rendered.index("| 2 | best")
    low_index = rendered.index("low-score")
    assert best_index < second_index < low_index
    assert "Valid open issues are ranked automatically" in rendered


def test_script_writes_leaderboard_from_issue_json(tmp_path):
    issues_path = tmp_path / "issues.json"
    out_path = tmp_path / "public-dev.md"
    issues_path.write_text(json.dumps([make_issue(4, "example/model", 55.678, 2.345)]), encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--issues-json",
            str(issues_path),
            "--out",
            str(out_path),
            "--generated-at",
            "2026-06-19T00:00:00+00:00",
        ],
        check=True,
    )

    rendered = out_path.read_text(encoding="utf-8")
    assert "| 1 | example/model | Example Provider | 55.68 | 2.35 |" in rendered
