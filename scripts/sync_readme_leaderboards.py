#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


START = "<!-- GOBENCH_LEADERBOARDS_START -->"
END = "<!-- GOBENCH_LEADERBOARDS_END -->"


def main() -> None:
    parser = argparse.ArgumentParser(description="Render leaderboard snapshots into README.md.")
    parser.add_argument("--readme", default="README.md")
    parser.add_argument("--public", default="leaderboards/public-dev.md")
    parser.add_argument("--official", default="leaderboards/official.md")
    args = parser.parse_args()

    readme = Path(args.readme)
    rendered = render_block(Path(args.public), Path(args.official))
    update_between_markers(readme, rendered)
    print(f"synced {readme}")


def render_block(public_path: Path, official_path: Path) -> str:
    public = extract_snapshot(public_path)
    official = extract_snapshot(official_path)
    return "\n".join(
        [
            START,
            "",
            "### Public-Dev Snapshot",
            "",
            f"[Open full public-dev leaderboard]({public_path.as_posix()})",
            "",
            public,
            "",
            "### Official Snapshot",
            "",
            f"[Open full official leaderboard]({official_path.as_posix()})",
            "",
            official,
            "",
            END,
        ]
    )


def extract_snapshot(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    updated = extract_last_updated(text)
    table = extract_first_table(text)
    if updated:
        return f"{updated}\n\n{table}"
    return table


def extract_last_updated(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("Last updated:"):
            return line
    return None


def extract_first_table(text: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        table = []
        for table_line in lines[index:]:
            if not table_line.startswith("|"):
                break
            table.append(table_line)
        if len(table) >= 2:
            return "\n".join(table)
    raise ValueError("no markdown table found")


def update_between_markers(path: Path, block: str) -> None:
    text = path.read_text(encoding="utf-8")
    if START in text and END in text:
        pattern = re.compile(f"{re.escape(START)}.*?{re.escape(END)}", re.DOTALL)
        updated = pattern.sub(block, text)
    else:
        heading = "## 🤖 Run a Model"
        if heading not in text:
            raise ValueError(f"{path} does not contain {heading!r}")
        updated = text.replace(heading, f"{block}\n\n{heading}", 1)
    path.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
