# Submissions

Public-dev scores are for debugging. Official v0.1 leaderboard results should
use the closed `official_v0_1` suite generated and held by the benchmark
maintainer.

Official submissions must use direct model APIs or compatible API gateways
configured through GoBench model profiles. `codex_exec`, `codex exec`, private
Codex runners, shell-based agent loops, browser/computer-use automation, and
other tool-using runtimes are development experiments only and are not accepted
as official leaderboard results.

For each run, keep:

- `run.json`
- `predictions.jsonl`
- `raw_responses.jsonl`
- `results.jsonl`
- `metrics.json`
- `report.md`

Report aggregate metrics, model identity, prompt hash, scorer version, KataGo
settings, token counts, latency, and run date.
