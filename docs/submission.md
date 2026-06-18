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

- **Public-dev/community result:** use the
  [Public-Dev Result issue form](https://github.com/GoBenchmark/GoBench/issues/new?template=public-dev-result.yml).
  This is the easiest path. It needs no maintainer approval; valid open issues
  are ranked automatically in
  [`leaderboards/public-dev.md`](../leaderboards/public-dev.md).
- **Official hidden-suite result:** use the
  [Official Submission Request issue form](https://github.com/GoBenchmark/GoBench/issues/new?template=official-submission.yml).
  This starts the review publicly on GitHub, but the hidden-suite archive stays
  private. Paste only aggregate metrics and metadata into the issue.

## Public-Dev Steps

1. Run the public development suite locally:

```bash
python -m gobench.cli run \
  --suite suites/public_dev.yaml \
  --out data/runs/your-model-public-dev
```

2. Open the
   [Public-Dev Result issue form](https://github.com/GoBenchmark/GoBench/issues/new?template=public-dev-result.yml).
3. Paste the command you ran and aggregate metrics from `report.md` or
   `metrics.json`.
4. Leave the issue open. If the issue has valid Score and MPL fields, it will
   be ranked automatically in the public-dev leaderboard.

Public-dev results are public debugging/comparison reports, not official
leaderboard claims.

## Official Hidden-Suite Steps

1. Open the
   [Official Submission Request issue form](https://github.com/GoBenchmark/GoBench/issues/new?template=official-submission.yml).
2. Wait for maintainer approval. If approved, the maintainer grants your GitHub
   account read access to the private
   [`GoBenchmark/gobench-official-suite`](https://github.com/GoBenchmark/gobench-official-suite)
   repository. The link may show `404` until access is granted.
3. Clone the private suite repo and copy the hidden positions into your local
   public GoBench checkout:

```bash
mkdir -p data/official_v0_1
cp /path/to/gobench-official-suite/data/official_v0_1/positions.jsonl \
  data/official_v0_1/positions.jsonl
```

Do not publish, attach, mirror, train on, or redistribute hidden-suite files.

4. Create a submission bundle with real KataGo scoring:

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

5. Return to the GitHub issue and paste only aggregate metrics, prompt hash,
   scorer settings, run metadata, and archive SHA-256.
6. Do not attach the `*-submission.tar.gz` archive publicly; the maintainer
   will coordinate private archive transfer/review in the GitHub issue.

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
