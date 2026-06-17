# Submissions

Public-dev scores are for debugging. Official v0.1 leaderboard results should
use the closed `official_v0_1` suite generated and held by the benchmark
maintainer.

Official submissions must use direct model APIs or compatible API gateways
configured through GoBench model profiles. `codex_exec`, `codex exec`, private
Codex runners, shell-based agent loops, browser/computer-use automation, and
other tool-using runtimes are development experiments only and are not accepted
as official leaderboard results.

## Choose a Submission Type

- **Official hidden-suite result:** use the
  [Official Submission Request issue form](https://github.com/GoBenchmark/GoBench/issues/new?template=official-submission.yml).
  This starts the review publicly on GitHub, but the hidden-suite archive stays
  private. Paste only aggregate metrics and metadata into the issue.
- **Public-dev/community result:** use the
  [Public-Dev Result issue form](https://github.com/GoBenchmark/GoBench/issues/new?template=public-dev-result.yml).
  These results are public debugging/comparison reports, not leaderboard
  claims.

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

sha256sum "$RUN_DIR-submission.tar.gz" 2>/dev/null || shasum -a 256 "$RUN_DIR-submission.tar.gz"
```

All submissions start on GitHub:

- **Official hidden-suite result:** open the
  [Official Submission Request issue form](https://github.com/GoBenchmark/GoBench/issues/new?template=official-submission.yml).
  Fill in the aggregate metrics, prompt hash, scorer settings, and archive
  SHA-256. Do not attach the `*-submission.tar.gz` archive publicly; the
  maintainer will coordinate private upload instructions in the GitHub issue.
- **Public-dev/community result:** open the
  [Public-Dev Result issue form](https://github.com/GoBenchmark/GoBench/issues/new?template=public-dev-result.yml).
  Paste the command and aggregate metrics. Public-dev issues are for debugging
  and comparison, not official leaderboard claims.

Do not publish hidden-suite positions, labels, prompts containing hidden
positions, visualization artifacts, or raw hidden-suite run artifacts.

For each run, keep:

- `run.json`
- `predictions.jsonl`
- `raw_responses.jsonl`
- `results.jsonl`
- `metrics.json`
- `report.md`

Report aggregate metrics, model identity, prompt hash, scorer version, KataGo
settings, token counts, latency, and run date.
