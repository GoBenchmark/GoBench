from __future__ import annotations

import os

from gobench.profiles import apply_suite_environment, load_model_profile, load_suite_profile


def test_default_model_profile_loads_openai_settings():
    profile = load_model_profile("gpt-5.5-xhigh")

    assert profile.name == "gpt-5.5-xhigh"
    assert profile.provider == "openai"
    assert profile.model == "gpt-5.5"
    assert profile.reasoning_effort == "xhigh"
    assert profile.temperature is None
    assert profile.prompt_template == "prompts/pure_llm_json_v1.txt"


def test_public_dev_suite_uses_katago_version_and_10_positions():
    suite = load_suite_profile("public_dev")

    assert suite.name == "public_dev"
    assert suite.max_positions == 10
    assert suite.scorer == "katago-1.16.4"
    assert suite.katago_max_visits == 2048
    assert suite.visibility == "public_dev_open"
    assert suite.primary_metric == "mean_point_loss"
    assert suite.canary and "gobench-public-dev-canary" in suite.canary


def test_official_v0_1_suite_declares_hidden_50_position_protocol():
    suite = load_suite_profile("official_v0_1")

    assert suite.name == "official_v0_1"
    assert suite.max_positions == 50
    assert suite.scorer == "katago-1.16.4"
    assert suite.visibility == "official_hidden"
    assert suite.primary_metric == "mean_point_loss"


def test_suite_environment_maps_versioned_katago_to_scorer(monkeypatch):
    suite = load_suite_profile("public_dev")
    monkeypatch.setenv("GOBENCH_SCORER", "mock")
    monkeypatch.setenv("KATAGO_MAX_VISITS", "1")
    monkeypatch.setenv("KATAGO_ANALYSIS_PV_LEN", "1")

    apply_suite_environment(suite)

    assert os.environ["GOBENCH_SCORER"] == "katago"
    assert os.environ["KATAGO_MAX_VISITS"] == "2048"
    assert os.environ["KATAGO_ANALYSIS_PV_LEN"] == "12"
