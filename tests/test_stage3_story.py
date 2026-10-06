"""The story view's stage statuses and the AI assurance metrics are computed from the case's real records."""

import pytest

from tests.reports_seed import bare_case, cleanup, role_client, seed_case


@pytest.fixture(scope="module")
def cases():
    full, bare = seed_case(), bare_case()
    yield full, bare
    cleanup(full)
    cleanup(bare)


def _stages(client, investigation_id):
    body = client.get(f"/api/v1/story/{investigation_id}").json()
    assert body["status"] == "READY_FOR_REVIEW", body
    return {stage["key"]: stage for stage in body["stages"]}


def test_a_case_with_evidence_analysis_and_a_signed_decision(cases):
    full, _ = cases
    stages = _stages(role_client("VIEWER")[0], full["investigation_id"])
    assert stages["evidence"]["status"] == "AVAILABLE" and stages["evidence"]["count"] == 2
    assert stages["analysis"]["status"] == "AVAILABLE"
    assert stages["decision"]["status"] == "COMPLETE"
    assert stages["hypotheses"]["status"] == "AVAILABLE" and stages["unknowns"]["status"] == "AVAILABLE"
    assert stages["signal"]["count"] == 1 and stages["product_version"]["status"] == "AVAILABLE"
    assert stages["assurance"]["status"] == "AVAILABLE" and stages["audit"]["status"] == "AVAILABLE"
    assert stages["scenario"]["status"] == "PENDING" and stages["failure_chain"]["status"] == "PENDING"


def test_a_bare_case_is_pending_where_nothing_is_recorded(cases):
    _, bare = cases
    stages = _stages(role_client("VIEWER")[0], bare["investigation_id"])
    assert stages["product"]["status"] == "AVAILABLE" and stages["investigation"]["status"] == "AVAILABLE"
    for key in ("evidence", "analysis", "decision", "signal", "hypotheses"):
        assert stages[key]["status"] == "PENDING", key


def test_unknown_or_malformed_ids_are_not_found():
    client = role_client("VIEWER")[0]
    assert client.get("/api/v1/story/not-a-uuid").json()["status"] == "NOT_FOUND"
    assert client.get("/api/v1/story/00000000-0000-0000-0000-000000000000").json()["status"] == "NOT_FOUND"


def test_assurance_metrics_count_real_executions(cases):
    metrics = role_client("VIEWER")[0].get("/api/v1/ai/assurance/summary").json()["metrics"]
    assert metrics["total_executions"] >= 1 and metrics["pass"] >= 1
    assert metrics["assessed"] >= metrics["pass"] + metrics["pass_with_limitations"] + metrics["blocked"]
