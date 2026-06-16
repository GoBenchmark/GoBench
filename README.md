# GoBench

GoBench v0.1 is a static next-move benchmark prototype for 19x19 Go. Models receive board positions and submit one legal move. The primary score is mean KataGo point-loss regret relative to KataGo's best move.

This prototype is intentionally small. It does not implement full-game play, Elo, image input, explanation grading, tool-assisted tracks, other board sizes, handicap games, or human expert review.

For the benchmark governance model, official scorer settings, and anti-contamination policy, see `BENCHMARK.md`.

## Install

```bash
git clone https://github.com/richren/GoBench.git
cd GoBench/gobench
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## Test

```bash
pytest
```

## Profile-Based Benchmark Workflow

GoBench supports benchmark-style model and suite profiles:

- `models/gpt-5.5-xhigh.yaml`
- `suites/public_dev.yaml`

The public dev suite uses 10 open KataGo self-play positions generated from
independent game prefixes. It is configured with:

```yaml
visibility: public_dev_open
max_positions: 10
scorer: katago-1.16.4
primary_metric: mean_point_loss
katago_max_visits: 2048
```

List available profiles:

```bash
python -m gobench.cli list-models
python -m gobench.cli list-suites
```

Check local setup:

```bash
python -m gobench.cli doctor \
  --model-profile models/gpt-5.5-xhigh.yaml \
  --suite suites/public_dev.yaml
```

Run generate + score + report in one command:

```bash
python -m gobench.cli run \
  --model-profile models/gpt-5.5-xhigh.yaml \
  --suite suites/public_dev.yaml \
  --out data/runs/gpt-5.5-xhigh-public-dev \
  --open
```

`--open` generates `visualization/index.html` after scoring and opens it in the
browser. Use `--visualize` instead if you want the HTML file written without
opening a browser. The final JSON prints both `visualization` and
`visualization_url` so the HTML can be reopened later. `--visualize-top-k`
controls how many KataGo candidate moves are shown.

During `run` and `run-openai`, GoBench shows a compact live elapsed timer on
stderr. In an interactive terminal it updates one inline status line every
second; when stderr is captured it prints a sparse line every 60 seconds. Set
`GOBENCH_TIMER_INTERVAL_SECONDS=0` or `GOBENCH_TIMER_STYLE=off` to disable the
timer. Use `GOBENCH_TIMER_STYLE=lines` to force line output, or
`GOBENCH_PROGRESS_FORMAT=json` if you want machine-readable progress logs.
Completed runs store `run_elapsed_seconds` and `run_elapsed_human`; the
visualization page shows the elapsed runtime. OpenAI requests time out after 90
seconds by default; set `OPENAI_TIMEOUT_SECONDS=60` to cut off bad connections
sooner, or raise it for very slow high-effort models.

For longer runs, resume generation without discarding completed predictions:

```bash
python -m gobench.cli run \
  --model-profile models/gpt-5.5-xhigh.yaml \
  --suite suites/public_dev.yaml \
  --out data/runs/gpt-5.5-xhigh-public-dev \
  --continue-existing
```

When resuming, GoBench reuses only compatible checkpoints from the same model
profile, prompt, suite, and requested position count. The run summary reports
`existing`, `generated_new`, and `pending` so you can distinguish old saved
predictions from new model calls made in the current invocation. By default,
`--continue-existing` retries pending positions that previously failed. Use
`--no-retry-errors` when you want to inspect a run without spending another
request on prior connection, quota, or API errors.

Generate and score can also be run separately:

```bash
python -m gobench.cli generate \
  --model-profile models/gpt-5.5-xhigh.yaml \
  --suite suites/public_dev.yaml \
  --out data/runs/gpt-5.5-xhigh-public-dev

python -m gobench.cli score \
  --suite suites/public_dev.yaml \
  --run-dir data/runs/gpt-5.5-xhigh-public-dev
```

Score custom predictions:

```bash
python -m gobench.cli score \
  --suite suites/public_dev.yaml \
  --predictions path/to/predictions.jsonl \
  --out data/runs/custom-model-public-dev
```

Build a leaderboard from saved runs:

```bash
python -m gobench.cli leaderboard data/runs
```

Open a browser visualization for a saved run:

```bash
python -m gobench.cli visualize data/runs/gpt-5.5-low-public-dev-selfplay-v1 --open
```

This writes `visualization/index.html` inside the run directory and prints a
`file://` URL for reopening it later. The first visualization run also writes
`katago_candidates.jsonl`, which caches KataGo top picks for each position. If
no candidate cache exists, `visualize` needs the same `KATAGO_BIN`,
`KATAGO_MODEL`, and `KATAGO_CONFIG` environment as normal KataGo scoring.

## Public Dev Data

`data/public_dev` is the open debugging suite. The current public-dev positions
are 10 evenly sampled positions from independent KataGo self-play game prefixes,
not from the synthetic toy generator. The directory contains:

- `data/public_dev/positions.jsonl`
- `data/public_dev/example_predictions.jsonl`
- `data/public_dev/labels.jsonl`
- `data/public_dev/selfplay_manifest.json`

To regenerate it, use:

```bash
python -m gobench.cli make-katago-selfplay-data \
  --out data/public_dev \
  --n 10 \
  --visits 128 \
  --top-k 5 \
  --policy-temperature 0.5 \
  --seed 42
```

This starts a fresh KataGo-guided game for each target depth and stops at the
same full-game targets from move 5 through move 199. It writes the same
`positions.jsonl` and `example_predictions.jsonl` files plus
`selfplay_manifest.json`, which records the generation parameters including
`top_k=5`, `policy_temperature=0.5`, `seed=42`, and generation visits. By
default, `labels.jsonl` uses the fast mock scorer for smoke testing; add
`--label-scorer katago --label-visits 2048` if you want the example labels
precomputed with real KataGo. Keep generation visits modest: 10 independent
prefixes through 199 moves require about 1,000 KataGo root queries before any
labeling. During generation, progress is printed to stderr at position start,
every 10 played moves, and position completion.

## Official v0.1 Hidden Suite

The public repository declares the official v0.1 protocol in
`suites/official_v0_1.yaml`, but the actual positions are closed and ignored by
Git. Generate them privately with:

```bash
python -m gobench.cli make-katago-selfplay-data \
  --out data/official_v0_1 \
  --n 50 \
  --visits 128 \
  --analysis-pv-len 8 \
  --top-k 5 \
  --policy-temperature 0.5 \
  --min-target-moves 5 \
  --max-target-moves 300 \
  --seed 42 \
  --label-scorer none
```

This creates 50 independent KataGo-guided game prefixes, evenly distributed
from move 5 through move 300. Keep `data/official_v0_1` private; official
leaderboard results should report only aggregate metrics and run artifacts.

For quick CI/dev smoke tests without KataGo, keep using synthetic toy data in a
separate directory:

```bash
python -m gobench.cli make-toy-data --out data/toy_dev --n 20
```

## Local File Evaluation

```bash
python -m gobench.cli eval-file \
  --positions data/public_dev/positions.jsonl \
  --predictions data/public_dev/example_predictions.jsonl \
  --labels data/public_dev/labels.jsonl
```

The command prints aggregate JSON metrics, including mean point loss, GoBench Score, legal move rate, top-k match rates, blunder rates, pass rate, and phase MPL.

GoBench Score is a headline 0-100 display score derived from MPL:

```text
GoBench Score = 100 * exp(-mean_point_loss / 2)
```

Higher is better. The official ranking metric remains MPL because it directly measures points lost against KataGo.

## Private Evaluation Server

Start the server:

```bash
python -m gobench.cli serve
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Create a run:

```bash
curl -X POST http://127.0.0.1:8000/runs \
  -H 'content-type: application/json' \
  -d '{"model_name":"example-model","model_version":"2026-06-12","track":"pure_llm","notes":"temperature=0"}'
```

Get the next hidden position:

```bash
curl http://127.0.0.1:8000/runs/{run_id}/next
```

Submit one move:

```bash
curl -X POST http://127.0.0.1:8000/runs/{run_id}/submit \
  -H 'content-type: application/json' \
  -d '{"position_id":"dev_000001","move":"R14"}'
```

For private runs, the submit endpoint returns only:

```json
{"accepted":true}
```

Get aggregate metrics:

```bash
curl http://127.0.0.1:8000/runs/{run_id}/report
```

## Legacy OpenAI Smoke Run

The profile-based `run` command is preferred. The older direct OpenAI command is still available:

```bash
python -m gobench.cli run-model \
  --positions data/public_dev/positions.jsonl \
  --model gpt-5.5 \
  --reasoning-effort xhigh \
  --temperature 0 \
  --limit 5 \
  --max-output-tokens 2000 \
  --out data/runs/gpt-5.5-xhigh-smoke
```

`run-openai` is kept as a compatibility alias for `run-model`.

Each run directory contains:

- `run.json` — model, prompt, scorer, and environment metadata.
- `predictions.jsonl` — parsed model moves.
- `raw_responses.jsonl` — raw model response text, status, token usage when available, and latency.
- `results.jsonl` — per-position score results.
- `metrics.json` — aggregate metrics plus metadata.
- `report.md` — human-readable run report.

By default this uses the configured scorer. If `GOBENCH_SCORER=katago` is set, the run is scored with real KataGo; otherwise it uses the deterministic mock scorer.

Generate a local leaderboard from saved run directories:

```bash
python -m gobench.cli leaderboard data/runs
```

## Real KataGo Scoring

Mock scoring is the default and is not real benchmark scoring. It exists so the API, CLI, metrics, and tests run without KataGo installed.

Real KataGo mode uses KataGo's JSON analysis engine:

```bash
KATAGO_BIN=/path/to/katago
KATAGO_MODEL=/path/to/model.bin.gz
KATAGO_CONFIG=configs/katago_gobench_official.cfg
GOBENCH_SCORER=katago
KATAGO_MAX_VISITS=2048
KATAGO_ANALYSIS_PV_LEN=12
KATAGO_REPORT_ANALYSIS_AS=SIDETOMOVE
GOBENCH_DB=./data/gobench.sqlite
```

Then run, for example:

```bash
GOBENCH_SCORER=katago python -m gobench.cli precompute-labels \
  --positions data/public_dev/positions.jsonl \
  --out data/labels/public_katago_labels.jsonl

GOBENCH_SCORER=katago python -m gobench.cli eval-file \
  --positions data/public_dev/positions.jsonl \
  --predictions data/public_dev/example_predictions.jsonl
```

`KataGoAnalysisClient` launches:

```bash
katago analysis -config "$KATAGO_CONFIG" -model "$KATAGO_MODEL"
```

It sends static board positions as `initialStones`, sets `initialPlayer` from `to_move`, requests `reportAnalysisWinratesAs=SIDETOMOVE`, and scores submitted moves from KataGo `scoreLead`. If a legal submitted move is absent from the root candidate list, the client runs a forced root query with `allowMoves` for that move.

For full hidden-test quality, use a tuned `analysis.cfg`, a strong model, and enough visits for stable point-loss estimates. Current v0.1 still treats ko history conservatively: positions are sent as static stones plus side to move, not reconstructed from full move history.

For leaderboard-style local scoring, prefer `configs/katago_gobench_official.cfg`. It disables neural-net board-orientation randomization, uses fixed visits and PV length, and removes wide-root noise. The Homebrew `analysis_example.cfg` is useful for exploration but has `nnRandomize = true`, so it is not the best default for official benchmark claims.

## Credibility Checklist

Before treating a run as a benchmark result:

- Run `python -m gobench.cli doctor --model-profile ... --suite ...`.
- Use a versioned suite profile such as `suites/public_dev.yaml`.
- Use real KataGo scoring, not the mock scorer.
- Prefer `configs/katago_gobench_official.cfg` for reproducibility.
- Keep `run.json`, `predictions.jsonl`, `raw_responses.jsonl`, `results.jsonl`, `metrics.json`, and `report.md`.
- Report whether the suite is public-dev or official-hidden.
- Treat public-dev scores as smoke/debug results, not final leaderboard claims.
