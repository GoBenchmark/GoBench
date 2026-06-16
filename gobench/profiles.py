from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ModelProfile:
    path: Path
    name: str
    provider: str
    model: str
    reasoning_effort: str | None
    temperature: float | None
    max_output_tokens: int
    prompt_template: str
    api_key_env: str | None = None
    api_base: str | None = None


@dataclass(frozen=True)
class SuiteProfile:
    path: Path
    name: str
    positions: str
    max_positions: int | None
    scorer: str
    katago_max_visits: int | None
    katago_analysis_pv_len: int | None
    description: str | None = None
    visibility: str | None = None
    canary: str | None = None
    primary_metric: str | None = None


def load_model_profile(value: str) -> ModelProfile:
    path = resolve_profile_path(value, Path("models"))
    data = load_yaml(path)
    return ModelProfile(
        path=path,
        name=str(data.get("name") or path.stem),
        provider=str(data.get("provider", "openai")),
        model=str(data["model"]),
        reasoning_effort=data.get("reasoning_effort"),
        temperature=data.get("temperature"),
        max_output_tokens=int(data.get("max_output_tokens", 2000)),
        prompt_template=str(data.get("prompt_template", "prompts/pure_llm_json_v1.txt")),
        api_key_env=data.get("api_key_env"),
        api_base=data.get("api_base"),
    )


def load_suite_profile(value: str) -> SuiteProfile:
    path = resolve_profile_path(value, Path("suites"))
    data = load_yaml(path)
    return SuiteProfile(
        path=path,
        name=str(data.get("name") or path.stem),
        positions=str(data["positions"]),
        max_positions=int(data["max_positions"]) if data.get("max_positions") is not None else None,
        scorer=str(data.get("scorer", "mock")),
        katago_max_visits=int(data["katago_max_visits"]) if data.get("katago_max_visits") is not None else None,
        katago_analysis_pv_len=int(data["katago_analysis_pv_len"])
        if data.get("katago_analysis_pv_len") is not None
        else None,
        description=data.get("description"),
        visibility=data.get("visibility"),
        canary=data.get("canary"),
        primary_metric=data.get("primary_metric"),
    )


def resolve_profile_path(value: str, directory: Path) -> Path:
    candidate = Path(value)
    if candidate.exists():
        return candidate
    if candidate.suffix not in {".yaml", ".yml"}:
        candidate = directory / f"{value}.yaml"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"profile not found: {value}")


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def list_profiles(directory: str) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(Path(directory).glob("*.y*ml")):
        try:
            data = load_yaml(path)
        except Exception as exc:
            rows.append({"path": str(path), "error": str(exc)})
            continue
        rows.append({"path": str(path), "name": data.get("name", path.stem), **data})
    return rows


def apply_suite_environment(suite: SuiteProfile) -> None:
    if suite.scorer.startswith("katago"):
        os.environ["GOBENCH_SCORER"] = "katago"
    else:
        os.environ["GOBENCH_SCORER"] = suite.scorer
    if suite.katago_max_visits is not None:
        os.environ["KATAGO_MAX_VISITS"] = str(suite.katago_max_visits)
    if suite.katago_analysis_pv_len is not None:
        os.environ["KATAGO_ANALYSIS_PV_LEN"] = str(suite.katago_analysis_pv_len)
