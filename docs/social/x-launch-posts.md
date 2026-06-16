# GoBench X Launch Kit

Repo: https://github.com/GoBenchmark/GoBench

## Main Announcement Thread

1. GoBench is live.

   Can today's AI models actually reason about Go?

   Pure-text 19x19 board positions. No engines. No tools. One legal next move, scored by KataGo point-loss regret.

   https://github.com/GoBenchmark/GoBench

2. Why Go?

   The rules are simple, but the strategy is brutal: tactics, global influence, endgame value, sacrifice, sente, shape.

   A move can look plausible in text and still lose by many points.

3. GoBench tests two things at once:

   Generalization: can the model handle unfamiliar positions?

   Reasoning: can it choose a strong move without calling a Go engine, search tool, or external assistant?

4. Official submissions are API-only.

   Accepted: documented model APIs or compatible API gateways.

   Not accepted: codex_exec, private Codex runners, shell agents, browser/computer-use automation, tool-assisted runs, mock scoring, or leaked hidden data.

## Short Single-Post Version

GoBench is live: a pure-text 19x19 Go benchmark for AI models.

No Go engine. No tools. One legal next move. KataGo point-loss scoring.

It tests generalization and reasoning: can a model play strong Go from its own judgment?

https://github.com/GoBenchmark/GoBench

## Official Submission Post

GoBench rule: official submissions are API-only.

Use documented model APIs or compatible API gateways. Do not submit codex_exec, private Codex runners, shell agents, browser/computer-use automation, tool-assisted runs, or mock-scored results as official claims.

## Suggested Image Pairing

- Attach `gobench-x-poster-1.png` to post 1 or the single-post version for the ASI/sci-fi launch hook.
- Attach `gobench-x-poster-2.png` to post 3 for the clean benchmark explainer.
