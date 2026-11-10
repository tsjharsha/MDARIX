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
    for case_id in ("not-a-uuid", "00000000-0000-0000-0000-000000000000"):
        answer = client.get(f"/api/v1/story/{case_id}")
        assert answer.status_code == 404 and answer.json()["detail"]["code"] == "INVESTIGATION_NOT_FOUND"


def test_assurance_metrics_count_real_executions(cases):
    metrics = role_client("VIEWER")[0].get("/api/v1/ai/assurance/summary").json()["metrics"]
    assert metrics["total_executions"] >= 1 and metrics["pass"] >= 1
    assert metrics["assessed"] >= metrics["pass"] + metrics["pass_with_limitations"] + metrics["blocked"]


def test_version_story_lists_the_cases_linked_to_its_complaints_and_their_evidence(cases):
    full, _ = cases
    client = role_client("INVESTIGATOR")[0]
    body = client.get(f"/api/v1/products/{full['product_id']}/versions/{full['version_id']}/story").json()
    assert body["status"] == "READY_FOR_REVIEW", body
    # The seeded complaint is on this version and linked to the case; the case holds one direct and one linked record.
    assert body["counts"] == {"complaints": 1, "investigations": 1, "evidence": 2}
    assert [row["investigation_identifier"] for row in body["investigations"]] == [f"INV-{full['tag']}"]
    assert sorted(row["evidence_identifier"] for row in body["evidence"]) == [
        f"EV-{full['tag']}-1",
        f"EV-{full['tag']}-2",
    ]


def test_signal_detail_carries_the_recorded_severity(cases):
    full, _ = cases
    detail = role_client("INVESTIGATOR")[0].get(f"/api/v1/signals/C-{full['tag']}").json()
    assert detail["status"] == "READY_FOR_REVIEW", detail
    assert detail["signal"]["severity"] == "high"
