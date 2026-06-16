from gobench.api.schemas import ScoreResult
from gobench.core.metrics import aggregate_metrics, gobench_score


def test_metric_aggregation():
    results = [
        ScoreResult(
            position_id="a",
            submitted_move="D4",
            legal=True,
            point_loss=0.0,
            top1_match=True,
            top3_match=True,
            top10_match=True,
            blunder=False,
            catastrophic_blunder=False,
            phase="opening",
        ),
        ScoreResult(
            position_id="b",
            submitted_move="pass",
            legal=False,
            point_loss=50.0,
            top1_match=False,
            top3_match=False,
            top10_match=False,
            blunder=True,
            catastrophic_blunder=True,
            phase="endgame",
        ),
    ]
    metrics = aggregate_metrics(results)
    assert metrics["count"] == 2
    assert metrics["mean_point_loss"] == 25.0
    assert metrics["gobench_score"] == gobench_score(25.0)
    assert metrics["gobench_score_tau"] == 2.0
    assert metrics["legal_move_rate"] == 0.5
    assert metrics["pass_rate"] == 0.5
    assert metrics["phase_mpl"]["opening"] == 0.0


def test_gobench_score_uses_tau_2():
    assert gobench_score(0.0) == 100.0
    assert round(gobench_score(2.0), 3) == 36.788
    assert round(gobench_score(5.0), 3) == 8.208


def test_empty_metrics_do_not_claim_perfect_score():
    metrics = aggregate_metrics([])
    assert metrics["count"] == 0
    assert metrics["mean_point_loss"] is None
    assert metrics["gobench_score"] is None
