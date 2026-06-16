from __future__ import annotations

import html
import json
import webbrowser
from pathlib import Path
from typing import Any

from gobench.api.schemas import CandidateEval, Position, ScoreResult
from gobench.core.coordinates import BOARD_COLUMNS, coord_to_point, is_pass
from gobench.core.scorer_factory import create_scorer
from gobench.datasets.loader import load_positions, read_jsonl_model, write_jsonl
from gobench.profiles import SuiteProfile, apply_suite_environment, load_suite_profile


def write_run_visualization(
    run_dir: Path,
    suite: SuiteProfile,
    top_k: int = 5,
    open_browser: bool = False,
    refresh_candidates: bool = False,
) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    out_dir = run_dir / "visualization"
    out_dir.mkdir(parents=True, exist_ok=True)

    run = load_json(run_dir / "run.json") if (run_dir / "run.json").exists() else {}
    metrics_summary = load_json(run_dir / "metrics.json") if (run_dir / "metrics.json").exists() else {}
    metrics = metrics_summary.get("metrics", {})
    positions = {position.position_id: position for position in load_positions(suite.positions)}
    results = read_jsonl_model(run_dir / "results.jsonl", ScoreResult)
    raw_by_id = load_raw_response_map(run_dir / "raw_responses.jsonl")
    result_positions = {
        result.position_id: positions[result.position_id] for result in results if result.position_id in positions
    }
    candidate_rows = load_or_create_candidate_rows(run_dir, suite, result_positions, refresh_candidates)
    candidates_by_id = {
        row["position_id"]: [CandidateEval.model_validate(candidate) for candidate in row.get("candidates", [])]
        for row in candidate_rows
    }

    rows = []
    for result in results:
        position = positions.get(result.position_id)
        if position is None:
            continue
        raw = raw_by_id.get(result.position_id, {})
        candidates = candidates_by_id.get(result.position_id, [])[:top_k]
        rows.append(
            {
                "position": position.model_dump(),
                "result": result.model_dump(),
                "raw": raw,
                "candidates": [candidate.model_dump() for candidate in candidates],
                "board_svg": render_board_svg(position, result, candidates),
            }
        )

    html_path = out_dir / "index.html"
    html_path.write_text(render_visualization_html(run, metrics, rows, top_k), encoding="utf-8")
    if open_browser:
        webbrowser.open(html_path.resolve().as_uri())
    return html_path


def load_or_create_candidate_rows(
    run_dir: Path,
    suite: SuiteProfile,
    positions: dict[str, Position],
    refresh: bool,
) -> list[dict[str, Any]]:
    candidates_path = run_dir / "katago_candidates.jsonl"
    existing_rows = load_jsonl_dicts(candidates_path) if candidates_path.exists() else []
    rows_by_id = {str(row.get("position_id")): row for row in existing_rows if row.get("position_id")}
    needed_ids = set(positions)
    if candidates_path.exists() and not refresh and needed_ids.issubset(rows_by_id):
        return [rows_by_id[position_id] for position_id in sorted(needed_ids)]

    apply_suite_environment(suite)
    scorer = create_scorer()
    if refresh:
        rows_by_id = {position_id: row for position_id, row in rows_by_id.items() if position_id not in needed_ids}
    try:
        for position_id in sorted(positions):
            if position_id in rows_by_id:
                continue
            position = positions[position_id]
            print(json.dumps({"stage": "analyze", "position_id": position_id}), flush=True)
            candidates = scorer.analyze_position(position)
            rows_by_id[position_id] = {
                "position_id": position_id,
                "candidates": [candidate.model_dump() for candidate in candidates],
            }
            write_jsonl(candidates_path, [rows_by_id[key] for key in sorted(rows_by_id)])
    finally:
        close = getattr(scorer, "close", None)
        if close:
            close()
    return [rows_by_id[position_id] for position_id in sorted(needed_ids) if position_id in rows_by_id]


def render_board_svg(position: Position, result: ScoreResult, candidates: list[CandidateEval]) -> str:
    board_size = position.board_size
    cell = 30
    margin = 36
    size = margin * 2 + cell * (board_size - 1)
    star_points = star_point_coords(board_size)
    candidate_moves = [candidate.move for candidate in candidates]
    model_move = result.submitted_move

    parts = [
        f'<svg class="board-svg" viewBox="0 0 {size} {size}" role="img" aria-label="{html.escape(position.position_id)} board">',
        f'<rect x="0" y="0" width="{size}" height="{size}" rx="8" fill="#d9aa5f"/>',
    ]

    for index in range(board_size):
        pos = margin + index * cell
        parts.append(f'<line x1="{margin}" y1="{pos}" x2="{size - margin}" y2="{pos}" stroke="#4f351b" stroke-width="1"/>')
        parts.append(f'<line x1="{pos}" y1="{margin}" x2="{pos}" y2="{size - margin}" stroke="#4f351b" stroke-width="1"/>')

    for row, col in star_points:
        x, y = point_xy(row, col, cell, margin)
        parts.append(f'<circle cx="{x}" cy="{y}" r="3.3" fill="#4f351b"/>')

    for row_index, label in enumerate(reversed(range(1, board_size + 1))):
        y = margin + row_index * cell + 4
        parts.append(f'<text x="10" y="{y}" class="coord-label">{label}</text>')
        parts.append(f'<text x="{size - 20}" y="{y}" class="coord-label">{label}</text>')
    for col, label in enumerate(BOARD_COLUMNS[:board_size]):
        x = margin + col * cell
        parts.append(f'<text x="{x}" y="22" class="coord-label center">{label}</text>')
        parts.append(f'<text x="{x}" y="{size - 10}" class="coord-label center">{label}</text>')

    for move in position.black:
        parts.append(render_stone(move, board_size, cell, margin, "black-stone"))
    for move in position.white:
        parts.append(render_stone(move, board_size, cell, margin, "white-stone"))

    for rank, candidate in enumerate(candidates, start=1):
        if is_pass(candidate.move) or candidate.move == model_move:
            continue
        try:
            x, y = move_xy(candidate.move, board_size, cell, margin)
        except ValueError:
            continue
        opacity = max(0.4, 1.0 - (rank - 1) * 0.1)
        parts.append(
            f'<g class="candidate-marker" style="opacity:{opacity:.2f}">'
            f'<circle cx="{x}" cy="{y}" r="11" fill="#f7c948" stroke="#6d4b00" stroke-width="2"/>'
            f'<text x="{x}" y="{y + 4}" class="candidate-rank">{rank}</text>'
            "</g>"
        )

    if not is_pass(model_move):
        try:
            x, y = move_xy(model_move, board_size, cell, margin)
        except ValueError:
            x, y = None, None
        if x is not None and y is not None:
            top_rank = candidate_moves.index(model_move) + 1 if model_move in candidate_moves else None
            label = "M" if top_rank is None else f"M{top_rank}"
            parts.append(
                f'<g class="model-marker">'
                f'<circle cx="{x}" cy="{y}" r="15" fill="none" stroke="#0f62fe" stroke-width="4"/>'
                f'<circle cx="{x}" cy="{y}" r="9" fill="#ffffff" stroke="#0f62fe" stroke-width="2"/>'
                f'<text x="{x}" y="{y + 4}" class="model-label">{html.escape(label)}</text>'
                "</g>"
            )

    parts.append("</svg>")
    return "".join(parts)


def render_stone(move: str, board_size: int, cell: int, margin: int, class_name: str) -> str:
    x, y = move_xy(move, board_size, cell, margin)
    return f'<circle cx="{x}" cy="{y}" r="13.2" class="{class_name}"/>'


def move_xy(move: str, board_size: int, cell: int, margin: int) -> tuple[int, int]:
    row, col = coord_to_point(move, board_size)
    return point_xy(row, col, cell, margin)


def point_xy(row: int, col: int, cell: int, margin: int) -> tuple[int, int]:
    return margin + col * cell, margin + row * cell


def star_point_coords(board_size: int) -> list[tuple[int, int]]:
    if board_size == 19:
        points = [3, 9, 15]
        return [(row, col) for row in points for col in points]
    if board_size >= 13:
        low, mid, high = 3, board_size // 2, board_size - 4
        return [(row, col) for row in (low, mid, high) for col in (low, mid, high)]
    return []


def render_visualization_html(run: dict[str, Any], metrics: dict[str, Any], rows: list[dict[str, Any]], top_k: int) -> str:
    payload = json.dumps(rows, ensure_ascii=False)
    safe_payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    run_name = run.get("run_name") or "GoBench Run"
    model = run.get("model") or "unknown"
    suite = run.get("suite") or "unknown"
    completion = scoring_completion(run, metrics, rows)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>GoBench Visualization - {html.escape(str(run_name))}</title>
  <style>
    :root {{
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #121418;
      --muted: #626a76;
      --border: #d8dde6;
      --accent: #0f62fe;
      --good: #15803d;
      --warn: #a16207;
      --bad: #b91c1c;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); }}
    header {{ padding: 22px 28px 16px; border-bottom: 1px solid var(--border); background: #fff; position: sticky; top: 0; z-index: 10; }}
    h1 {{ margin: 0 0 10px; font-size: 22px; line-height: 1.2; font-weight: 720; letter-spacing: 0; }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 10px; color: var(--muted); font-size: 13px; }}
    .metric-strip {{ display: grid; grid-template-columns: repeat(8, minmax(105px, 1fr)); gap: 10px; padding: 14px 28px; background: #fff; border-bottom: 1px solid var(--border); }}
    .metric {{ border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; background: #fbfcfe; }}
    .metric span {{ display: block; font-size: 12px; color: var(--muted); }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 20px; }}
    main {{ padding: 20px 28px 36px; }}
    .toolbar {{ display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-bottom: 16px; }}
    .toolbar input, .toolbar select {{ height: 34px; border: 1px solid var(--border); border-radius: 6px; padding: 0 10px; background: #fff; font-size: 13px; }}
    .legend {{ margin-left: auto; display: flex; flex-wrap: wrap; gap: 12px; color: var(--muted); font-size: 12px; }}
    .legend-item {{ display: inline-flex; align-items: center; gap: 6px; }}
    .dot {{ width: 12px; height: 12px; border-radius: 999px; display: inline-block; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(430px, 1fr)); gap: 16px; align-items: start; }}
    .card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }}
    .card-head {{ padding: 12px 14px; border-bottom: 1px solid var(--border); display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: start; }}
    .title {{ font-weight: 700; font-size: 15px; }}
    .subtitle {{ color: var(--muted); font-size: 12px; margin-top: 3px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }}
    .status-badge {{ display: inline-flex; align-items: center; height: 20px; border-radius: 999px; padding: 0 8px; font-size: 11px; font-weight: 750; border: 1px solid transparent; }}
    .status-completed {{ color: #166534; background: #dcfce7; border-color: #86efac; }}
    .status-error {{ color: #991b1b; background: #fee2e2; border-color: #fca5a5; }}
    .status-incomplete {{ color: #854d0e; background: #fef3c7; border-color: #facc15; }}
    .status-missing {{ color: #475569; background: #e2e8f0; border-color: #cbd5e1; }}
    .completion-badge {{ display: inline-flex; align-items: center; height: 22px; border-radius: 999px; padding: 0 9px; font-size: 12px; font-weight: 750; border: 1px solid transparent; }}
    .completion-complete {{ color: #166534; background: #dcfce7; border-color: #86efac; }}
    .completion-incomplete {{ color: #991b1b; background: #fee2e2; border-color: #fca5a5; }}
    .loss {{ font-weight: 750; font-size: 18px; text-align: right; }}
    .loss.good {{ color: var(--good); }}
    .loss.warn {{ color: var(--warn); }}
    .loss.bad {{ color: var(--bad); }}
    .board-wrap {{ padding: 12px; background: #eef1f5; }}
    .board-svg {{ width: 100%; height: auto; display: block; max-height: 640px; }}
    .black-stone {{ fill: #111; stroke: #000; stroke-width: 1; }}
    .white-stone {{ fill: #f7f7f7; stroke: #111; stroke-width: 1.5; }}
    .coord-label {{ font-size: 10px; fill: #4f351b; font-weight: 600; }}
    .center {{ text-anchor: middle; }}
    .candidate-rank, .model-label {{ text-anchor: middle; font-size: 11px; font-weight: 800; fill: #111; }}
    .details {{ padding: 12px 14px 14px; display: grid; gap: 10px; }}
    .facts {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }}
    .fact {{ border: 1px solid var(--border); border-radius: 6px; padding: 7px 8px; font-size: 12px; }}
    .fact span {{ display: block; color: var(--muted); margin-bottom: 2px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ padding: 6px 5px; border-bottom: 1px solid #edf0f4; text-align: right; }}
    th:first-child, td:first-child {{ text-align: left; }}
    th {{ color: var(--muted); font-weight: 650; }}
    .raw {{ color: var(--muted); font-size: 12px; }}
    @media (max-width: 760px) {{
      header, main {{ padding-left: 14px; padding-right: 14px; }}
      .metric-strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); padding-left: 14px; padding-right: 14px; }}
      .grid {{ grid-template-columns: 1fr; }}
      .facts {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .legend {{ margin-left: 0; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(str(run_name))}</h1>
    <div class="meta">
      <span>Model: {html.escape(str(model))}</span>
	      <span>Suite: {html.escape(str(suite))}</span>
	      <span>Scorer: {html.escape(str(run.get("scorer", "unknown")))}</span>
	      <span>Top picks shown: {top_k}</span>
	      <span class="completion-badge {completion["class_name"]}">{html.escape(completion["label"])}</span>
	    </div>
  </header>
  <section class="metric-strip">
    {metric_box("Score", fmt(metrics.get("gobench_score")))}
    {metric_box("MPL", fmt(metrics.get("mean_point_loss")))}
    {metric_box("Legal", pct(metrics.get("legal_move_rate")))}
	    {metric_box("Top-3", pct(metrics.get("top3_match_rate")))}
	    {metric_box("Blunder", pct(metrics.get("blunder_rate")))}
	    {metric_box("Scored", completion["fraction"])}
	    {metric_box("Count", str(metrics.get("count", len(rows))))}
    {metric_box("Elapsed", run_elapsed_display(run))}
  </section>
  <main>
    <div class="toolbar">
      <input id="search" type="search" placeholder="Filter by id, move, phase" />
      <select id="phase"><option value="">All phases</option></select>
      <select id="sort">
        <option value="order">Original order</option>
        <option value="loss-desc">Highest point loss</option>
        <option value="loss-asc">Lowest point loss</option>
      </select>
      <div class="legend">
        <span class="legend-item"><span class="dot" style="background:#111"></span>Black</span>
        <span class="legend-item"><span class="dot" style="background:#fff;border:1px solid #111"></span>White</span>
        <span class="legend-item"><span class="dot" style="background:#f7c948;border:1px solid #6d4b00"></span>KataGo rank</span>
        <span class="legend-item"><span class="dot" style="border:3px solid #0f62fe"></span>Model move</span>
      </div>
    </div>
    <div id="grid" class="grid"></div>
  </main>
  <script type="application/json" id="payload">{safe_payload}</script>
  <script>
    const rows = JSON.parse(document.getElementById('payload').textContent);
    const grid = document.getElementById('grid');
    const search = document.getElementById('search');
    const phase = document.getElementById('phase');
    const sort = document.getElementById('sort');

    [...new Set(rows.map(row => row.position.phase).filter(Boolean))].sort().forEach(value => {{
      const option = document.createElement('option');
      option.value = value;
      option.textContent = value;
      phase.appendChild(option);
    }});

    function lossClass(loss) {{
      if (loss <= 1) return 'good';
      if (loss <= 5) return 'warn';
      return 'bad';
    }}

    function render() {{
      const query = search.value.trim().toLowerCase();
      const phaseValue = phase.value;
      let visible = rows.filter(row => {{
        const haystack = [row.position.position_id, row.result.submitted_move, row.position.phase || '', row.raw.status || ''].join(' ').toLowerCase();
        return (!query || haystack.includes(query)) && (!phaseValue || row.position.phase === phaseValue);
      }});
      if (sort.value === 'loss-desc') visible = visible.slice().sort((a, b) => b.result.point_loss - a.result.point_loss);
      if (sort.value === 'loss-asc') visible = visible.slice().sort((a, b) => a.result.point_loss - b.result.point_loss);
      grid.innerHTML = visible.map((row, index) => card(row, index)).join('');
    }}

    function card(row) {{
      const r = row.result;
      const p = row.position;
      return `<article class="card">
        <div class="card-head">
          <div>
            <div class="title">${{escapeHtml(p.position_id)}} · ${{escapeHtml(p.to_move)}} to move</div>
            <div class="subtitle">
              <span>${{escapeHtml(p.phase || 'unlabeled')}}</span>
              <span>model: ${{escapeHtml(r.submitted_move)}}</span>
              ${{statusBadge(row.raw)}}
            </div>
          </div>
          <div class="loss ${{lossClass(r.point_loss)}}">${{formatNumber(r.point_loss)}} pts</div>
        </div>
        <div class="board-wrap">${{row.board_svg}}</div>
        <div class="details">
          <div class="facts">
            ${{fact('Legal', r.legal ? 'yes' : 'no')}}
            ${{fact('Top-1', r.top1_match ? 'yes' : 'no')}}
            ${{fact('Top-3', r.top3_match ? 'yes' : 'no')}}
            ${{fact('Top-10', r.top10_match ? 'yes' : 'no')}}
          </div>
          <table>
            <thead><tr><th>KataGo move</th><th>Lead</th><th>Winrate</th><th>Visits</th></tr></thead>
            <tbody>${{row.candidates.map((candidate, i) => `<tr><td>#${{i + 1}} ${{escapeHtml(candidate.move)}}</td><td>${{formatNumber(candidate.score_lead)}}</td><td>${{candidate.winrate == null ? 'n/a' : formatPercent(candidate.winrate)}}</td><td>${{candidate.visits ?? 'n/a'}}</td></tr>`).join('')}}</tbody>
          </table>
          <div class="raw">Raw output: ${{escapeHtml(row.raw.raw_text || '')}}</div>
        </div>
      </article>`;
    }}

    function fact(label, value) {{
      return `<div class="fact"><span>${{label}}</span>${{escapeHtml(value)}}</div>`;
    }}
    function statusBadge(raw) {{
      const status = responseStatus(raw);
      return `<span class="status-badge ${{status.className}}" title="${{escapeHtml(status.detail)}}">${{escapeHtml(status.label)}}</span>`;
    }}
    function responseStatus(raw) {{
      if (!raw || Object.keys(raw).length === 0) {{
        return {{ label: 'missing response', className: 'status-missing', detail: 'No raw response row was found for this position.' }};
      }}
      if (raw.error) {{
        return {{ label: 'error', className: 'status-error', detail: raw.error }};
      }}
      const value = raw.status || 'missing';
      if (value === 'completed') {{
        return {{ label: 'completed', className: 'status-completed', detail: 'Model response completed.' }};
      }}
      if (value === 'incomplete' || value === 'cancelled' || value === 'failed') {{
        return {{ label: value, className: 'status-error', detail: raw.raw_text || value }};
      }}
      return {{ label: value, className: 'status-incomplete', detail: raw.raw_text || value }};
    }}
    function formatNumber(value) {{
      if (typeof value !== 'number') return 'n/a';
      return Number(value.toFixed(3)).toString();
    }}
    function formatPercent(value) {{
      if (typeof value !== 'number') return 'n/a';
      return `${{(value * 100).toFixed(1)}}%`;
    }}
    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, char => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[char]));
    }}
    [search, phase, sort].forEach(control => control.addEventListener('input', render));
    render();
  </script>
</body>
</html>"""


def metric_box(label: str, value: str) -> str:
    return f'<div class="metric"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>'


def scoring_completion(run: dict[str, Any], metrics: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, str]:
    scored = int_value(run.get("positions_scored"), metrics.get("count"), len(rows))
    requested = int_value(run.get("positions_requested"), run.get("positions_available"), scored)
    if requested <= 0:
        requested = scored
    complete = requested > 0 and scored >= requested
    fraction = f"{scored}/{requested}"
    return {
        "fraction": fraction,
        "label": f"Scoring complete {fraction}" if complete else f"Scoring incomplete {fraction}",
        "class_name": "completion-complete" if complete else "completion-incomplete",
    }


def int_value(*values: Any) -> int:
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return max(0, value)
        if isinstance(value, float):
            return max(0, int(value))
        if isinstance(value, str):
            try:
                return max(0, int(value))
            except ValueError:
                continue
    return 0


def fmt(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return "n/a"


def pct(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value * 100:.1f}%"
    return "n/a"


def run_elapsed_display(run: dict[str, Any]) -> str:
    if run.get("run_elapsed_human"):
        return str(run["run_elapsed_human"])
    value = run.get("run_elapsed_seconds")
    if isinstance(value, (int, float)):
        total = max(0, int(round(value)))
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return "n/a"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl_dicts(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_raw_response_map(path: Path) -> dict[str, dict[str, Any]]:
    return {row["position_id"]: row for row in load_jsonl_dicts(path) if "position_id" in row}


def suite_from_run(run_dir: Path, suite_path: str | None) -> SuiteProfile:
    if suite_path:
        return load_suite_profile(suite_path)
    run_path = run_dir / "run.json"
    if run_path.exists():
        run = load_json(run_path)
        if run.get("suite_path"):
            return load_suite_profile(str(run["suite_path"]))
    return load_suite_profile("suites/public_dev.yaml")
