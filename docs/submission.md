# Submissions

Public-dev scores are for debugging. Official v0.1 leaderboard results should
use the closed `official_v0_1` suite generated and held by the benchmark
maintainer.

Official submissions must use direct model APIs or compatible API gateways
configured through GoBench model profiles. `codex_exec`, `codex exec`, private
Codex runners, shell-based agent loops, browser/computer-use automation, and
other tool-using runtimes are development experiments only and are not accepted
as official leaderboard results.

## Command Template

After receiving authorized access to the official hidden suite, create a
submission bundle with real KataGo scoring:

```bash
export GOBENCH_SCORER=katago
export KATAGO_BIN=/path/to/katago
export KATAGO_MODEL=/path/to/model.bin.gz
export KATAGO_CONFIG=configs/katago_gobench_official.cfg
export KATAGO_MAX_VISITS=2048
export KATAGO_ANALYSIS_PV_LEN=12

RUN_DIR=data/runs/your-model-official-v0-1

python -m gobench.cli run \
  --model-profile .gobench/model.yaml \
  --suite suites/official_v0_1.yaml \
  --out "$RUN_DIR" \
  --no-visualize

python -m gobench.cli bundle-submission "$RUN_DIR"
```

`bundle-submission` validates the required files and writes
`data/runs/your-model-official-v0-1-submission.tar.gz`. Submit the archive
through the maintainer-approved submission channel. Do not publish hidden-suite
positions, labels, prompts containing hidden positions, or visualization
artifacts for official runs.

For each run, keep:

- `run.json`
- `predictions.jsonl`
- `raw_responses.jsonl`
- `results.jsonl`
- `metrics.json`
- `report.md`

Report aggregate metrics, model identity, prompt hash, scorer version, KataGo
settings, token counts, latency, and run date.
