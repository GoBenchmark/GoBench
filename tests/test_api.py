from pathlib import Path

from fastapi.testclient import TestClient

from gobench.api.main import create_app
from gobench.api.routes import get_private_positions
from gobench.datasets.loader import write_jsonl
from gobench.datasets.sample_data import make_toy_positions
from gobench.storage.db import create_session_factory, get_session


def make_client(tmp_path: Path) -> TestClient:
    session_factory = create_session_factory(str(tmp_path / "test.sqlite"))
    positions = make_toy_positions(2)
    write_jsonl(tmp_path / "positions.jsonl", positions)

    def override_session():
        with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_private_positions] = lambda: positions
    return TestClient(app)


def test_health(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_private_run_flow_does_not_leak_submit_scores(tmp_path):
    client = make_client(tmp_path)
    run_response = client.post(
        "/runs",
        json={
            "model_name": "example-model",
            "model_version": "2026-06-12",
            "track": "pure_llm",
            "notes": "temperature=0",
        },
    )
    run_id = run_response.json()["run_id"]

    next_response = client.get(f"/runs/{run_id}/next")
    position = next_response.json()
    assert "black" in position

    submit_response = client.post(
        f"/runs/{run_id}/submit",
        json={"position_id": position["position_id"], "move": "R14"},
    )
    assert submit_response.status_code == 200
    assert submit_response.json() == {"accepted": True}
    assert set(submit_response.json()) == {"accepted"}

    duplicate_response = client.post(
        f"/runs/{run_id}/submit",
        json={"position_id": position["position_id"], "move": "Q16"},
    )
    assert duplicate_response.status_code == 409

    report = client.get(f"/runs/{run_id}/report").json()
    assert report["count"] == 1
    assert "mean_point_loss" in report
    assert "gobench_score" in report
    assert report["gobench_score_tau"] == 2.0
