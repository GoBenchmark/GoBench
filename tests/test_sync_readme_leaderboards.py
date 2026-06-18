from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sync_readme_leaderboards.py"
SPEC = importlib.util.spec_from_file_location("sync_readme_leaderboards", SCRIPT_PATH)
assert SPEC and SPEC.loader
sync_readme = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync_readme)


def test_extract_snapshot_includes_last_updated_and_first_table(tmp_path):
    board = tmp_path / "public-dev.md"
    board.write_text(
        """# Public

Last updated: `now`

| Rank | Model |
|---:|---|
| 1 | test |

extra text
""",
        encoding="utf-8",
    )

    assert sync_readme.extract_snapshot(board) == "Last updated: `now`\n\n| Rank | Model |\n| ---: | --- |\n| 1 | test |"


def test_extract_snapshot_limits_readme_table_to_top_10(tmp_path):
    board = tmp_path / "public-dev.md"
    rows = "\n".join(f"| {index} | model-{index} |" for index in range(1, 12))
    board.write_text(
        f"""# Public

| Rank | Model |
|---:|---|
{rows}
""",
        encoding="utf-8",
    )

    snapshot = sync_readme.extract_snapshot(board)

    assert "model-10" in snapshot
    assert "model-11" not in snapshot


def test_extract_snapshot_compacts_full_leaderboard_columns(tmp_path):
    board = tmp_path / "public-dev.md"
    board.write_text(
        """# Public

| Rank | Model | Provider | Score | MPL | Legal | Top-10 | Blunder | Count | Submitter | Issue |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|---|
| 1 | model-a | provider-a | 88.2 | 0.3 | 100% | 90% | 0% | 10 | @alice | #1 |
""",
        encoding="utf-8",
    )

    snapshot = sync_readme.extract_snapshot(board)

    assert "| Rank | Model | Provider | Score | MPL | Top-10 | Submitter |" in snapshot
    assert "| 1 | model-a | provider-a | 88.2 | 0.3 | 90% | @alice |" in snapshot
    assert "Legal" not in snapshot
    assert "Blunder" not in snapshot
    assert "Count" not in snapshot
    assert "Issue" not in snapshot


def test_extract_snapshot_keeps_official_review_column(tmp_path):
    board = tmp_path / "official.md"
    board.write_text(
        """# Official

| Rank | Model | Provider | Score | MPL | Legal | Top-10 | Blunder | Count | Review |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | model-a | provider-a | 88.2 | 0.3 | 100% | 90% | 0% | 50 | approved |
""",
        encoding="utf-8",
    )

    snapshot = sync_readme.extract_snapshot(board)

    assert "| Rank | Model | Provider | Score | MPL | Top-10 | Review |" in snapshot
    assert "| 1 | model-a | provider-a | 88.2 | 0.3 | 90% | approved |" in snapshot


def test_render_block_labels_snapshots_as_top_10(tmp_path):
    public = tmp_path / "public.md"
    official = tmp_path / "official.md"
    table = """| Rank | Model |
|---:|---|
| - | none |
"""
    public.write_text(table, encoding="utf-8")
    official.write_text(table, encoding="utf-8")

    rendered = sync_readme.render_block(public, official)

    assert "### Public-Dev Top 10" in rendered
    assert "### Official Top 10" in rendered


def test_update_between_markers_replaces_generated_block(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        f"before\n{sync_readme.START}\nold\n{sync_readme.END}\nafter\n",
        encoding="utf-8",
    )

    sync_readme.update_between_markers(readme, f"{sync_readme.START}\nnew\n{sync_readme.END}")

    assert readme.read_text(encoding="utf-8") == f"before\n{sync_readme.START}\nnew\n{sync_readme.END}\nafter\n"
