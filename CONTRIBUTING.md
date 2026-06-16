# Contributing

GoBench v0.1 is intentionally small: 19x19 static next-move prediction,
Chinese rules, pure-text prompts, and KataGo point-loss scoring.

Before opening a pull request:

- Run `python -m pytest -q`.
- Run `python -m gobench.cli release-check`.
- Keep public-dev data open and official suite data private.
- Do not commit `.env.local`, `data/runs`, `analysis_logs`, `private`, or
  `data/official_v0_1`.
- Add tests for behavior changes in parsing, legality, scoring, profiles, or
  visualization.

For benchmark protocol changes, update `BENCHMARK.md` in the same pull request.
