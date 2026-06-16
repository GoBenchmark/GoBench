# Metrics

GoBench's primary ranking metric is `mean_point_loss` (MPL): the average point
loss of the submitted move relative to KataGo's best root candidate.

The display score is:

```text
GoBench Score = 100 * exp(-mean_point_loss / 2)
```

Higher GoBench Score is better. Lower MPL is better.

Other reported metrics:

- `legal_move_rate`: fraction of submitted moves accepted as legal.
- `top1_match_rate`: fraction matching KataGo's top move.
- `top3_match_rate`: fraction appearing in KataGo's top 3.
- `top10_match_rate`: fraction appearing in KataGo's top 10.
- `blunder_rate`: fraction above the configured blunder point-loss threshold.
- `catastrophic_blunder_rate`: fraction above the catastrophic threshold.
- `phase_mpl`: MPL split by opening, early-middle, late-middle, and endgame.
