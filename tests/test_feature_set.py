"""MDARIX_FEATURE_SET (backend/app/feature_set.py): ``full`` serves every route, as built; ``mvp`` refuses exactly the
routes of the parked areas, before any handler runs, and keeps every route a kept screen calls."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import feature_set as sets
from backend.app.decision_router import router as legacy_decision_router
from backend.app.main import app
from backend.app.regulatory_router import router as regulatory_router
from backend.app.risk_router import router as risk_router
from counterfactual.router import router as counterfactual_router
from scenario_intelligence.router import router as scenario_router

# Routes the MVP keeps that sit next to parked ones: the current decision, the decision queue, the Decision Brief,
# and the unknowns and failure-chain steps the investigation panel still calls.
KEPT = (
    "/api/v1/investigations/{investigation_id}/decision",
    "/api/v1/decisions/queue",
    "/api/v1/investigations/{investigation_id}/decision-brief",
    "/api/v1/investigations/{investigation_id}/unknowns",
    "/api/v1/investigations/{investigation_id}/failure-chains",
    # The automatic trust check's policy replaces the static agent catalog on the AI guardrails screen.
    "/api/v1/ai/trust-policy",
    "/api/v1/ai/release-gate",
)
# The static agent catalog (fixed text describing "agents"), parked on its own (Phase 6).
AGENT_CATALOG = "/api/v1/ai/agents/catalog"
# The public demo request: the website offers none, and it mailed a typed name to any address (SEC-04, 0.10.35). The
# Platform Admin list of earlier requests stays.
PUBLIC_DEMO_REQUEST = "/api/v1/public/demo-requests"


def _paths() -> list[str]:
    return list(app.openapi()["paths"])


def _router_paths(*routers) -> set[str]:
    return {route.path for router in routers for route in router.routes}


@pytest.fixture
def mvp(monkeypatch):
    monkeypatch.setenv("MDARIX_FEATURE_SET", "mvp")


def test_full_is_the_default_and_serves_every_route(monkeypatch):
    monkeypatch.delenv("MDARIX_FEATURE_SET", raising=False)
    assert sets.feature_set() == sets.FULL and not sets.is_mvp()
    assert all(sets.serves_path(path) for path in _paths())
    monkeypatch.setenv("MDARIX_FEATURE_SET", " FULL ")
    assert sets.feature_set() == sets.FULL


def test_mvp_parks_exactly_the_routes_of_the_parked_areas(mvp):
    parked = {path for path in _paths() if not sets.serves_path(path)}
    expected = _router_paths(
        regulatory_router, risk_router, counterfactual_router, scenario_router, legacy_decision_router
    ) | {AGENT_CATALOG, PUBLIC_DEMO_REQUEST}
    assert parked == expected
    assert sets.serves_path("/api/v1/platform-admin/demo-requests")
    assert len(parked) >= 15
    for path in KEPT:
        assert path in _paths(), path
        assert sets.serves_path(path), path


def test_a_parked_route_answers_404_before_any_handler(monkeypatch):
    anonymous = TestClient(app)
    parked, kept = "/api/v1/regulatory/documents", "/api/v1/decisions/queue"

    monkeypatch.setenv("MDARIX_FEATURE_SET", "full")
    assert anonymous.get(parked).status_code == 401
    assert anonymous.get(kept).status_code == 401

    monkeypatch.setenv("MDARIX_FEATURE_SET", "mvp")
    refused = anonymous.get(parked)
    assert refused.status_code == 404
    assert refused.json()["detail"]["code"] == "NOT_IN_THIS_FEATURE_SET"
    assert anonymous.get(kept).status_code == 401
    assert anonymous.get("/health/live").status_code == 200


@pytest.mark.db
def test_the_session_context_names_the_feature_set_for_the_interface(monkeypatch):
    from tests.conftest import authenticated_client

    client = authenticated_client()
    monkeypatch.delenv("MDARIX_FEATURE_SET", raising=False)
    assert client.get("/api/v1/session/context").json()["feature_set"] == "full"
    monkeypatch.setenv("MDARIX_FEATURE_SET", "mvp")
    assert client.get("/api/v1/session/context").json()["feature_set"] == "mvp"


def test_an_unknown_feature_set_is_refused_and_reported(monkeypatch):
    from backend.app.config_check import _feature_set_problem

    monkeypatch.setenv("MDARIX_FEATURE_SET", "lite")
    with pytest.raises(RuntimeError, match="MDARIX_FEATURE_SET"):
        sets.feature_set()
    assert "MDARIX_FEATURE_SET must be full or mvp" in (_feature_set_problem() or "")
    for good in ("full", "mvp", ""):
        monkeypatch.setenv("MDARIX_FEATURE_SET", good)
        assert _feature_set_problem() is None
