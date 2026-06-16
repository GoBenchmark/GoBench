from __future__ import annotations

import os

from gobench.core.scoring import ScorerProtocol
from gobench.katago.analysis_client import KataGoAnalysisClient
from gobench.katago.mock_client import MockKataGoClient


def create_scorer() -> ScorerProtocol:
    if os.getenv("GOBENCH_SCORER", "mock").lower() == "katago":
        return KataGoAnalysisClient()
    return MockKataGoClient()
