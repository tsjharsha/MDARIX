"""Non-production fault injection for live dependency-failure validation.

Setting ``MDARIX_SIMULATE_DEPENDENCY_FAILURE=1`` on the API server makes the
analysis dependencies behind Ask MDARIX retrieval, the challenger, failure
chains and scenario intelligence fail *after* authorization has succeeded, so
operators can verify the controlled 503 response and its audit event.

The switch is server-configured only (never client-triggered), off by default
and ignored whenever ``MDARIX_ENV=production``. It replaces the former
per-day flags (DAY27/DAY30/DAY31/DAY32/DAY34_LIVE_DEPENDENCY_FAILURE).
"""
import os

SIMULATE_DEPENDENCY_FAILURE_FLAG = "MDARIX_SIMULATE_DEPENDENCY_FAILURE"


def dependency_failure_simulated() -> bool:
    return (
        os.environ.get(SIMULATE_DEPENDENCY_FAILURE_FLAG) == "1"
        and os.environ.get("MDARIX_ENV", "development").lower() != "production"
    )
