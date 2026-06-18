# GoBench: Testing LLMs on Strategic Go Reasoning

![GoBench ASI launch poster](docs/social/gobench-x-poster-1.png)

Can today's AI models actually reason about Go, or are they just fluent about Go?

GoBench is a compact benchmark for evaluating both the **generalization** and
**reasoning** abilities of AI models on 19x19 Go. A model receives a board
position in text, with no Go engine and no external tools, and must return one
legal next move. GoBench then scores the move by its point-loss regret relative
to KataGo's best move.

Go is an unusually sharp testbed for intelligence: the rules are simple, the
state space is enormous, local tactics interact with global judgment, and a
plausible-looking move can still lose the game by many points. A genuinely
superintelligent model should eventually be able to play Go from its own
reasoning, without calling tools, on par with systems such as KataGo. GoBench is
a small open step toward measuring that gap.

GoBench v0.1 is intentionally focused: static next-move prediction, pure text
input, legal move parsing, and KataGo-based point-loss scoring. It is designed
to be easy to run locally, hard to hand-wave, and honest about what is and is
not being measured.

![GoBench visualization preview](docs/gobench-visualization.png)

> [!IMPORTANT]
> **Official benchmark submissions are API-only.** Public-dev means the open
> `suites/public_dev.yaml` / `data/public_dev` development suite; public-dev
> runs are for debugging, not leaderboard claims. Official GoBench results must
> use the closed `official_v0_1` suite, real KataGo scoring, preserved run
> artifacts, and documented model API or API-gateway calls. `codex_exec`,
> private Codex runners, shell agents, browser/computer-use automation,
> tool-assisted runs, mock scoring, and leaked hidden data are not accepted. See
> [Official Benchmark Submissions](#official-benchmark-submissions).

## 🔍 Reading the Preview

- **GoBench Score:** a 0-100 display score derived from mean point loss. Higher
  is better.
- **Mean Point Loss / MPL:** average points lost by the model's move compared
  with KataGo's preferred move. Lower is better.
- **Legal Moves:** fraction of model outputs that parse as legal Go moves.
- **Top-3 Match:** fraction of model moves that appear in KataGo's top three
  candidate moves for the position.
- **Blunder Rate:** fraction of moves whose point loss crosses the configured
  blunder threshold.
- **KataGo rank:** yellow numbered markers show KataGo's highest-ranked
  candidate moves on the board.
- **Model move:** the blue ring marks the move submitted by the evaluated
  model.
- **Black / White:** existing stones on the board before the model's move.
- **Public-dev:** the open development suite for debugging prompts, formatting,
  legality, scoring, and visualization. It is not an official leaderboard
  claim.

## 🎯 What GoBench Measures

- **Board understanding:** can the model parse and reason from a raw 19x19
  position?
- **Legal move discipline:** can it reliably produce valid Go coordinates?
- **Strategic judgment:** how many points does its move lose relative to
  KataGo's preferred move?
- **Robustness across phases:** opening, middle-game, and endgame positions are
  reported separately.
- **Benchmark hygiene:** public-dev data is open for debugging, while official
  leaderboard-style evaluation should use hidden positions and fixed scorer
  settings.

This prototype is intentionally small. It does not implement full-game play, Elo, image input, explanation grading, tool-assisted tracks, other board sizes, handicap games, or human expert review.

For the benchmark governance model, official scorer settings, and anti-contamination policy, see `BENCHMARK.md`.

## ⚡ Quick Start

Install GoBench in an isolated environment:

```bash
git clone https://github.com/GoBenchmark/GoBench.git
cd GoBench
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run the test suite:

```bash
python -m pytest
```

Run a no-network smoke test against the bundled public-dev examples:

```bash
python -m gobench.cli eval-file \
  --positions data/public_dev/positions.jsonl \
  --predictions data/public_dev/example_predictions.jsonl \
  --labels data/public_dev/labels.jsonl
```

That command uses the checked-in example predictions and labels, so it works
without a provider API key or KataGo install. It is the fastest way to confirm
that the CLI, parser, legality checks, and metrics pipeline are working.

List the model and suite profiles:

```bash
python -m gobench.cli list-models
python -m gobench.cli list-suites
```

Diagnose your local setup:

```bash
python -m gobench.cli doctor
```

`doctor` reports whether your API key, output directory, and KataGo settings are
ready. It exits nonzero when required real-scoring pieces are missing. Missing
KataGo is fine for the no-network smoke test above; real benchmark claims
should use KataGo scoring.

## 📊 Leaderboards

GoBench has two tracks:

- **Public-dev leaderboard:** an open community board for `public_dev` runs.
  It is easy to try, needs no approval, and valid open GitHub issues are ranked
  automatically. Submit with the
  [Public-Dev Result issue form](https://github.com/GoBenchmark/GoBench/issues/new?template=public-dev-result.yml)
  and view the board in [`leaderboards/public-dev.md`](leaderboards/public-dev.md).
- **Official hidden-suite leaderboard:** the serious benchmark board for the
  closed `official_v0_1` suite. It requires authorized hidden-suite access,
  real KataGo scoring, preserved artifacts, and maintainer review. View the
  board in [`leaderboards/official.md`](leaderboards/official.md).

<!-- GOBENCH_LEADERBOARDS_START -->

### Public-Dev Snapshot

[Open full public-dev leaderboard](leaderboards/public-dev.md)

Last updated: `2026-06-18T20:08:13+00:00`

| Rank | Model | Provider | Score | MPL | Legal | Top-3 | Blunder | Count | Submitter | Issue |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|---|
| - | No public-dev submissions yet | - | - | - | - | - | - | - | - | - |

### Official Snapshot

[Open full official leaderboard](leaderboards/official.md)

| Rank | Model | Provider | Score | MPL | Legal | Top-3 | Blunder | Count | Review |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| - | No approved official submissions yet | - | - | - | - | - | - | - | - |

<!-- GOBENCH_LEADERBOARDS_END -->

## 🤖 Run a Model

Official leaderboard submissions are API-only. Use direct provider APIs or
compatible API gateways through GoBench model profiles; `codex_exec`, private
Codex runners, shell-based agent loops, browser/computer-use automation, and
other tool-using runtimes are not accepted as official results.

Configure your local model profile and API key once, for example:

```bash
python -m gobench.cli configure \
  --model gpt-5.5 \
  --reasoning-effort xhigh \
  --api-key "$OPENAI_API_KEY"
```

Or start from a built-in provider preset:

```bash
python -m gobench.cli list-presets

# OpenAI Responses API
python -m gobench.cli configure --preset openai --api-key "$OPENAI_API_KEY"

# Anthropic Messages API
python -m gobench.cli configure --preset claude-opus --api-key "$ANTHROPIC_API_KEY"

# OpenAI-compatible chat APIs
python -m gobench.cli configure --preset deepseek --api-key "$DEEPSEEK_API_KEY"
python -m gobench.cli configure --preset gemini --api-key "$GEMINI_API_KEY"

# MiniMax and broad model catalogs through OpenRouter
python -m gobench.cli configure --preset minimax --api-key "$OPENROUTER_API_KEY"
python -m gobench.cli configure --preset openrouter \
  --model anthropic/claude-opus-4.8 \
  --api-key "$OPENROUTER_API_KEY"
```

Presets are intentionally thin: they fill in `provider`, `model`,
`api_key_env`, and when needed `api_base`. You can still override the model id
with `--model` or use any OpenAI-compatible endpoint:

```bash
python -m gobench.cli configure \
  --provider openai-chat \
  --model provider/model-id \
  --api-base https://provider.example.com/v1 \
  --api-key-env PROVIDER_API_KEY \
  --api-key "$PROVIDER_API_KEY"
```

This writes two local files that are ignored by Git:

- `.gobench/model.yaml`: your default model profile.
- `.env.local`: your API/scorer environment settings.

After that, GoBench automatically uses `.gobench/model.yaml` when
`--model-profile` is omitted.

If you only want to test model calling and save predictions before configuring
KataGo, run generation by itself:

```bash
python -m gobench.cli generate \
  --suite suites/public_dev.yaml \
  --out data/runs/my-model-public-dev
```

For benchmark-style scored results, configure KataGo too. The example below
uses an OpenAI profile, but the same scorer flags work with other provider
presets:

```bash
python -m gobench.cli configure --force \
  --model gpt-5.5 \
  --reasoning-effort xhigh \
  --api-key "$OPENAI_API_KEY" \
  --scorer katago \
  --katago-bin /path/to/katago \
  --katago-model /path/to/model.bin.gz \
  --katago-config configs/katago_gobench_official.cfg
```

Then check your setup:

```bash
python -m gobench.cli doctor
```

Run generate + score + report in one command:

```bash
python -m gobench.cli run \
  --suite suites/public_dev.yaml \
  --out data/runs/my-model-public-dev
```

After a successful `run`, GoBench writes `visualization/index.html` and opens it
in your browser by default. Use `--no-open` to write the HTML without opening a
browser, or `--no-visualize` to skip visualization entirely.

Build a local leaderboard from saved runs:

```bash
python -m gobench.cli leaderboard data/runs
```

<a id="official-benchmark-submissions"></a>

## 🏁 Official Benchmark Submissions

Public-dev means the open `suites/public_dev.yaml` / `data/public_dev`
development suite. Public-dev runs are welcome for debugging prompts, API
setup, legality, and visualization, but they are not official leaderboard
claims. An official GoBench v0.1 submission must use the closed
`official_v0_1` suite held by the benchmark maintainer.

Official submissions must:

- Generate moves through a documented model API or compatible API gateway
  configured in a GoBench model profile.
- Use a fixed model id, provider, API transport, reasoning/effort setting,
  prompt template, and prompt SHA-256.
- Use real KataGo scoring with the published official config or a documented
  successor, not the mock scorer.
- Preserve `run.json`, `predictions.jsonl`, `raw_responses.jsonl`,
  `results.jsonl`, `metrics.json`, and `report.md`.
- Report aggregate metrics, model identity, prompt hash, scorer/KataGo
  settings, token counts, latency, run date, and whether the suite is
  `public_dev` or `official_v0_1`.

To submit an official hidden-suite result:

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

4. Run the official suite and create a submission bundle:

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
   scorer settings, and archive SHA-256.
6. Do not attach the `*-submission.tar.gz` archive publicly; the maintainer
   will coordinate private archive transfer/review in the GitHub issue.

Public-dev/community results use a separate, fully public path. No approval is
needed for the public board:

- **Public-dev/community result:** open the
  [Public-Dev Result issue form](https://github.com/GoBenchmark/GoBench/issues/new?template=public-dev-result.yml).
  Paste the command and aggregate metrics. Valid open public-dev issues are
  ranked automatically in [`leaderboards/public-dev.md`](leaderboards/public-dev.md).
  Public-dev issues are for debugging and comparison, not official leaderboard
  claims.

Do not publish hidden-suite positions, labels, prompts containing hidden
positions, visualization artifacts, or raw hidden-suite run artifacts.

The following are not accepted as official leaderboard submissions:
`codex_exec`, `codex exec`, private Codex runners, shell-based agent loops,
browser/computer-use automation, tool-assisted model runs, public-dev scores,
mock-scored runs, or runs that expose hidden positions or labels.

For the full submission checklist, see `docs/submission.md`. For the protocol,
hidden-suite outline, and anti-contamination policy, see the
[Official v0.1 Hidden Suite](#official-v0-1-hidden-suite) section and
`BENCHMARK.md`.

For quick CI/dev smoke tests without KataGo, keep using synthetic toy data in a
separate directory:

```bash
python -m gobench.cli make-toy-data --out data/toy_dev --n 20
```

## 🧭 Profile-Based Workflow

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

The final JSON prints both `visualization` and
`visualization_url` so the HTML can be reopened later. `--visualize-top-k`
controls how many KataGo candidate moves are shown.

During profile-based `run` and the legacy `run-openai` command, GoBench shows a
compact live elapsed timer on stderr. In an interactive terminal it updates one
inline status line every second; when stderr is captured it prints a sparse
line every 60 seconds. Set `GOBENCH_TIMER_INTERVAL_SECONDS=0` or
`GOBENCH_TIMER_STYLE=off` to disable the timer. Use
`GOBENCH_TIMER_STYLE=lines` to force line output, or
`GOBENCH_PROGRESS_FORMAT=json` if you want machine-readable progress logs.
Completed runs store `run_elapsed_seconds` and `run_elapsed_human`; the
visualization page shows the elapsed runtime. Provider API requests time out
after 90 seconds by default. Set `GOBENCH_API_TIMEOUT_SECONDS=60` to cut off
bad connections sooner, or raise it for very slow high-effort models.
`OPENAI_TIMEOUT_SECONDS` is still accepted as a backward-compatible fallback.

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

## 🧪 Public Dev Data

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

<a id="official-v0-1-hidden-suite"></a>

## 🔒 Official v0.1 Hidden Suite

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

## 📄 Local File Evaluation

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

## 🖥️ Private Evaluation Server

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

## 🧪 Legacy OpenAI Smoke Run

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

## ⚖️ Real KataGo Scoring

Mock scoring is the default and is not real benchmark scoring. It exists so the
API, CLI, metrics, and tests run without KataGo installed.

For real scoring, install KataGo separately, download or locate a KataGo model,
then point GoBench at the binary, model, and fixed analysis config. On
macOS/Homebrew, `KATAGO_BIN` is often `/opt/homebrew/bin/katago`; the model is
usually under Homebrew's KataGo share directory.

```bash
export GOBENCH_SCORER=katago
export KATAGO_BIN=/path/to/katago
export KATAGO_MODEL=/path/to/model.bin.gz
export KATAGO_CONFIG=configs/katago_gobench_official.cfg
export KATAGO_MAX_VISITS=2048
export KATAGO_ANALYSIS_PV_LEN=12
export KATAGO_REPORT_ANALYSIS_AS=SIDETOMOVE
export GOBENCH_DB=./data/gobench.sqlite
```

You can also put those values in `.env.local`; profile-based commands load that
file automatically.

Verify the setup:

```bash
python -m gobench.cli doctor \
  --model-profile models/gpt-5.5-xhigh.yaml \
  --suite suites/public_dev.yaml
```

Then run the public-dev suite with real KataGo scoring:

```bash
python -m gobench.cli run \
  --model-profile models/gpt-5.5-xhigh.yaml \
  --suite suites/public_dev.yaml \
  --out data/runs/gpt-5.5-xhigh-public-dev-katago
```

Or precompute labels and evaluate a predictions file:

```bash
python -m gobench.cli precompute-labels \
  --positions data/public_dev/positions.jsonl \
  --out data/labels/public_katago_labels.jsonl

python -m gobench.cli eval-file \
  --positions data/public_dev/positions.jsonl \
  --predictions data/public_dev/example_predictions.jsonl \
  --labels data/labels/public_katago_labels.jsonl
```

`KataGoAnalysisClient` launches:

```bash
katago analysis -config "$KATAGO_CONFIG" -model "$KATAGO_MODEL"
```

It sends static board positions as `initialStones`, sets `initialPlayer` from `to_move`, requests `reportAnalysisWinratesAs=SIDETOMOVE`, and scores submitted moves from KataGo `scoreLead`. If a legal submitted move is absent from the root candidate list, the client runs a forced root query with `allowMoves` for that move.

For full hidden-test quality, use a tuned `analysis.cfg`, a strong model, and enough visits for stable point-loss estimates. Current v0.1 still treats ko history conservatively: positions are sent as static stones plus side to move, not reconstructed from full move history.

For leaderboard-style local scoring, prefer `configs/katago_gobench_official.cfg`. It disables neural-net board-orientation randomization, uses fixed visits and PV length, and removes wide-root noise. The Homebrew `analysis_example.cfg` is useful for exploration but has `nnRandomize = true`, so it is not the best default for official benchmark claims.

## ✅ Credibility Checklist

Before treating a run as a benchmark result:

- Run `python -m gobench.cli doctor --model-profile ... --suite ...`.
- Generate moves through a documented model API profile, not `codex_exec`,
  private Codex runners, shell agents, or tool-using automation.
- Use a versioned suite profile such as `suites/public_dev.yaml`.
- Use real KataGo scoring, not the mock scorer.
- Prefer `configs/katago_gobench_official.cfg` for reproducibility.
- Keep `run.json`, `predictions.jsonl`, `raw_responses.jsonl`, `results.jsonl`, `metrics.json`, and `report.md`.
- Report whether the suite is public-dev or official-hidden.
- Treat public-dev scores as smoke/debug results, not final leaderboard claims.
- For official leaderboard claims, follow the
  `Official Benchmark Submissions` section above and `docs/submission.md`.
