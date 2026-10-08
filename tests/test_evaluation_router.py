"""POST /evaluations/runs stores only what the real pipeline computed: never a pass that was not earned."""

import uuid
from datetime import datetime, timezone

import pytest

import backend.app.evaluation_router as evaluation_router
from backend.app.db.models.foundation import EvaluationRun, ReleaseAssuranceResult
from backend.app.db.session import SessionLocal
from tests.reports_seed import golden_tenant_id, role_client

RUNS = "/api/v1/evaluations/runs"


def _report(passed, total=12):
    return {
        "evaluation_version": "TEST",
        "model": "MDARIX rules (no language model configured)",
        "passed": passed,
        "total": total,
        "thresholds": {"match": 0.75},
        "results": [
            {"scenario_id": f"VS{i:03d}", "status": "PASS" if i <= passed else "FAIL"} for i in range(1, total + 1)
        ],
    }


def _start(client, **body):
    response = client.post(RUNS, json=body)
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "RUNNING"
    return response.json()["evaluation_run_id"]


def _assurance(run_id):
    with SessionLocal() as db:
        return db.query(ReleaseAssuranceResult).filter(ReleaseAssuranceResult.evaluation_run_id == run_id).one()


@pytest.mark.parametrize("passed, outcome", [(12, "PASS"), (11, "FAIL")])
def test_the_stored_status_is_the_computed_one(monkeypatch, passed, outcome):
    monkeypatch.setattr(evaluation_router, "run_golden_evaluation", lambda scenario_ids: _report(passed))
    client = role_client("INVESTIGATOR")[0]
    run_id = _start(client)
    body = client.get(f"{RUNS}/{run_id}").json()
    assert body["status"] == outcome and body["results"]["passed"] == passed and body["completed_at"]
    assert _assurance(run_id).status == ("PASS" if outcome == "PASS" else "BLOCKED")


def test_a_run_that_fails_to_complete_is_an_error_never_a_pass(monkeypatch):
    def broken(scenario_ids):
        raise RuntimeError("embedding model missing")

    monkeypatch.setattr(evaluation_router, "run_golden_evaluation", broken)
    client = role_client("INVESTIGATOR")[0]
    run_id = _start(client)
    body = client.get(f"{RUNS}/{run_id}").json()
    assert body["status"] == "ERROR" and body["results"]["error"] == "RuntimeError"
    assert _assurance(run_id).status == "BLOCKED"


def test_no_scenario_evaluated_is_not_a_pass(monkeypatch):
    monkeypatch.setattr(evaluation_router, "run_golden_evaluation", lambda scenario_ids: _report(0, total=0))
    client = role_client("INVESTIGATOR")[0]
    assert client.get(f"{RUNS}/{_start(client)}").json()["status"] == "FAIL"


def test_the_real_pipeline_is_scored_on_one_scenario():
    client = role_client("INVESTIGATOR")[0]
    run_id = _start(client, scenario_ids=["VS001"])
    body = client.get(f"{RUNS}/{run_id}").json()
    assert body["status"] in {"PASS", "FAIL"}, body
    [result] = body["results"]["results"]
    assert result["scenario_id"] == "VS001" and result["analysis_author"] == "RULES"
    assert {check["check"] for check in result["checks"]} >= {"CITATIONS_VALID", "NO_PROHIBITED", "GROUNDED"}
    assert body["status"] == ("PASS" if result["status"] == "PASS" else "FAIL")


def test_one_run_at_a_time_and_requests_are_validated(monkeypatch):
    client = role_client("INVESTIGATOR")[0]
    assert client.post(RUNS, json={"scenario_ids": ["VS999"]}).status_code == 422
    assert role_client("VIEWER")[0].post(RUNS, json={}).status_code == 403
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        row = EvaluationRun(
            id=uuid.uuid4(),
            tenant_id=golden_tenant_id(),
            suite_version="TEST",
            dataset_version="TEST",
            release_version="TEST",
            configuration_hash="0" * 64,
            status="RUNNING",
            results={},
            started_at=now,
            created_at=now,
        )
        db.add(row)
        db.commit()
        try:
            busy = client.post(RUNS, json={})
            assert busy.status_code == 409 and busy.json()["detail"]["code"] == "EVALUATION_ALREADY_RUNNING"
        finally:
            row.status = "ERROR"
            db.commit()


def test_all_fifteen_golden_scenarios_can_be_requested(monkeypatch):
    from evaluation.harness import SCENARIO_IDS, load_scenarios

    assert SCENARIO_IDS == [item["scenario_id"] for item in load_scenarios()] and len(SCENARIO_IDS) == 15
    requested = []
    monkeypatch.setattr(
        evaluation_router, "run_golden_evaluation", lambda scenario_ids: requested.append(scenario_ids) or _report(3, 3)
    )
    client = role_client("INVESTIGATOR")[0]
    run_id = _start(client, scenario_ids=["VS013", "vs014", "VS015"])
    assert requested == [{"VS013", "VS014", "VS015"}]
    assert client.get(f"{RUNS}/{run_id}").json()["status"] == "PASS"
    assert client.post(RUNS, json={"scenario_ids": SCENARIO_IDS + ["VS001"]}).status_code == 422  # over 15
