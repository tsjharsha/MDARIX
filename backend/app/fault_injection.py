"""Non-production fault injection for live dependency-failure validation.

Setting ``MDARIX_SIMULATE_DEPENDENCY_FAILURE=1`` on the API server makes the
analysis dependencies behind Ask MDARIX retrieval, the challenger, failure
chains and scenario intelligence fail *after* authorization has succeeded, so
operators can verify the controlled 503 response and its audit event.

The switch is server-configured only (never client-triggered), off by default
and honoured only in local development and test runs (never in staging or production, which refuse to start
with it set). It replaces the former
per-day flags (DAY27/DAY30/DAY31/DAY32/DAY34_LIVE_DEPENDENCY_FAILURE).
"""

import os
from backend.app.runtime_env import is_local

SIMULATE_DEPENDENCY_FAILURE_FLAG = "MDARIX_SIMULATE_DEPENDENCY_FAILURE"


def dependency_failure_simulated() -> bool:
    return os.environ.get(SIMULATE_DEPENDENCY_FAILURE_FLAG) == "1" and is_local()
