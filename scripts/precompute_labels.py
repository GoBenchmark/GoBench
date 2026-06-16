from __future__ import annotations

from gobench.cli import cmd_precompute_labels


if __name__ == "__main__":
    cmd_precompute_labels("data/private_test/positions.jsonl", "data/labels/private_labels.jsonl")
