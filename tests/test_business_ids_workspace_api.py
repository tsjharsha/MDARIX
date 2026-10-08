"""The investigation workspace returns each record's MDARIX ID (business_id, md26) and the IDs of the records it shows.

Complaints, investigations, evidence, decisions, signatures, briefs, scenarios, supplier evidence requests and
evaluation runs carry their own ``business_id``; a displayed reference carries ``<role>_business_id``. AI results get
their IDs only in the API response: the grounding context and the stored AI output never change (the first tests).
"""

import re
import uuid
from datetime import datetime, timezone

import pytest

import backend.app.evaluation_router as evaluation_router
from backend.app.db.models.foundation import Decision, Evidence, Investigation, Tenant
from backend.app.db.session import SessionLocal
from hypothesis_engine.schemas import Hypothesis
from investigation_workspace.schemas import InvestigationWorkspaceResponse
from investigation_workspace.service import with_business_ids
from investigator.business_ids import with_evidence_business_ids, with_hypothesis_business_ids
from investigator.schemas import SourceReference
from tests import reports_seed
from tests.conftest import with_signing_plan
from tests.reports_seed import PASSWORD, role_client
from tests.test_business_permissions import _client_with_role
from tests.test_manage_investigation import _open_case
from tests.test_supplier_evidence_requests import PATH as EVIDENCE_REQUESTS, _body, own_supplier

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _matches(pattern: str, value) -> bool:
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


# --- AI results: IDs only in the response, never in the AI context or the stored output (no database needed) ---


class RecordingSession:
    """Stands in for a session: answers each statement with the rows registered for the table it reads."""

    def __init__(self, rows_by_table):
        self.rows_by_table = rows_by_table
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        table = statement.get_final_froms()[0].name
        self._rows = self.rows_by_table.get(table, [])
        return self

    def all(self):
        return self._rows


def _hypothesis(hypothesis_id, statement, references=()):
    return Hypothesis(
        hypothesis_id=hypothesis_id,
        investigation_id=uuid.uuid4(),
        statement=statement,
        scope="Version B",
        status="PROPOSED",
        temporal_consistency={},
        source_references=list(references),
        context_snapshot={},
        provenance={},
        created_at=NOW,
        updated_at=NOW,
    )


def test_empty_ids_leave_the_serialized_ai_result_unchanged():
    reference = SourceReference(reference_type="EVIDENCE", evidence_id=str(uuid.uuid4()), evidence_identifier="EV-1")
    dumped = _hypothesis(uuid.uuid4(), "Seal wear", [reference]).model_dump(mode="json")
    assert "business_id" not in dumped and "evidence_business_id" not in dumped["source_references"][0]
    reference.evidence_business_id = "EVD000001"
    assert reference.model_dump(mode="json")["evidence_business_id"] == "EVD000001"


def test_ids_reach_the_api_response():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from hypothesis_engine.schemas import HypothesisSet, HypothesisSetResponse

    application = FastAPI()
    hypothesis = _hypothesis(uuid.uuid4(), "Seal wear")
    hypothesis.business_id = "HYP000007"

    @application.get("/set", response_model=HypothesisSetResponse)
    def hypothesis_set():
        return HypothesisSetResponse(
            hypothesis_set=HypothesisSet(
                hypothesis_set_id=uuid.uuid4(),
                investigation_id=hypothesis.investigation_id,
                source_analysis_id=uuid.uuid4(),
                context_snapshot_id="snapshot",
                context_snapshot_version="v1",
                status="MIXED_EVIDENCE",
                hypotheses=[hypothesis, _hypothesis(uuid.uuid4(), "Not recorded")],
                validation_summary={},
                guardrails={},
                provenance={},
                created_at=NOW,
            ),
            persisted=True,
        )

    items = TestClient(application).get("/set").json()["hypothesis_set"]["hypotheses"]
    assert items[0]["business_id"] == "HYP000007" and "business_id" not in items[1]


def test_evidence_references_get_their_ids_in_one_query():
    evidence_id = uuid.uuid4()
    known = SourceReference(reference_type="EVIDENCE", evidence_id=str(evidence_id))
    unknown = SourceReference(reference_type="EVIDENCE", evidence_id=str(uuid.uuid4()))
    context = SourceReference(reference_type="DETERMINISTIC_CONTEXT", evidence_business_id="EVD999999")
    result = _hypothesis(uuid.uuid4(), "Seal wear", [known, unknown, context])
    db = RecordingSession({"evidence": [(evidence_id, "EVD000003")]})
    with_evidence_business_ids(db, result)
    assert known.evidence_business_id == "EVD000003"
    assert unknown.evidence_business_id is None
    assert context.evidence_business_id is None  # only MDARIX sets it, never the model
    assert len(db.statements) == 1


def test_hypotheses_are_matched_to_their_records_by_id_then_statement():
    from hypothesis_engine.schemas import HypothesisSet, HypothesisSetResponse

    same_id, regenerated, new = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    response = HypothesisSetResponse(
        hypothesis_set=HypothesisSet(
            hypothesis_set_id=uuid.uuid4(),
            investigation_id=uuid.uuid4(),
            source_analysis_id=uuid.uuid4(),
            context_snapshot_id="snapshot",
            context_snapshot_version="v1",
            status="MIXED_EVIDENCE",
            hypotheses=[
                _hypothesis(same_id, "Seal wear"),
                _hypothesis(regenerated, "Firmware timing"),
                _hypothesis(new, "Not saved"),
            ],
            validation_summary={},
            guardrails={},
            provenance={},
            created_at=NOW,
        ),
        persisted=True,
    )
    db = RecordingSession(
        {"hypotheses": [(same_id, "Seal wear", "HYP000001"), (uuid.uuid4(), "Firmware timing", "HYP000002")]}
    )
    with_hypothesis_business_ids(db, uuid.uuid4(), response)
    assert [item.business_id for item in response.hypothesis_set.hypotheses] == ["HYP000001", "HYP000002", None]


def test_workspace_ids_are_added_to_a_copy_for_the_response():
    investigation_id, product_id, evidence_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    workspace = InvestigationWorkspaceResponse(
        investigation={"id": str(investigation_id), "product_id": str(product_id), "investigation_identifier": "I-1"},
        product_context={},
        temporal_context={},
        relationship_context={},
        evidence_context=[{"id": str(evidence_id), "evidence_identifier": "EV-1"}],
        retrieval_context=None,
        limitations=[],
        guardrails={},
        metadata={},
    )
    db = RecordingSession(
        {
            "investigations": [(investigation_id, "INV000004")],
            "products": [(product_id, "PROD000002")],
            "evidence": [(evidence_id, "EVD000009")],
        }
    )
    shown = with_business_ids(db, workspace)
    assert (
        shown.investigation["business_id"] == "INV000004" and shown.investigation["product_business_id"] == "PROD000002"
    )
    assert list(shown.evidence_context[0])[:2] == ["id", "business_id"]
    assert shown.evidence_context[0]["business_id"] == "EVD000009"
    assert "business_id" not in workspace.investigation and "business_id" not in workspace.evidence_context[0]


# --- API (database) ---


@pytest.fixture(scope="module")
def seed():
    case = reports_seed.seed_case()
    # Signing and Ask need the plan every real organization has (on a fresh database nothing has given it yet).
    with SessionLocal() as db:
        with_signing_plan(db, db.query(Tenant).filter(Tenant.id == uuid.UUID(case["tenant_id"])).one())
        db.commit()
    yield case
    reports_seed.cleanup(case)


def test_complaint_list_carries_business_ids_and_finds_them():
    viewer = _client_with_role("VIEWER")
    body = viewer.get("/api/v1/complaints", params={"page_size": 5}).json()
    item = body["items"][0]
    assert _matches(r"CMP\d{6}", item["business_id"]) and _matches(r"PROD\d{6}", item["product_business_id"])
    found = viewer.get("/api/v1/complaints", params={"q": item["business_id"].lower()}).json()
    assert [row["id"] for row in found["items"]] == [item["id"]]


def test_opening_and_managing_an_investigation_return_its_business_id():
    lead = _client_with_role("INVESTIGATOR")
    case = _open_case(lead)
    with SessionLocal() as db:
        expected = db.query(Investigation.business_id).filter(Investigation.id == case).scalar()
    assert _matches(r"INV\d{6}", expected)
    edited = lead.patch(
        f"/api/v1/investigations/{case}",
        json={"reason": "Reason recorded for the audit trail", "investigation_question": "Why do alarms rise now?"},
    )
    assert edited.status_code == 200 and edited.json()["business_id"] == expected
    assignees = lead.get("/api/v1/investigation-assignees").json()
    assert all(_matches(r"USR\d{6}", person["business_id"]) for person in assignees)


def test_opening_returns_the_new_case_and_product_ids():
    lead = _client_with_role("INVESTIGATOR")
    product = lead.get("/api/v1/complaints", params={"page_size": 1}).json()["items"][0]
    made = lead.post(
        "/api/v1/investigations",
        json={"product_id": product["product_id"], "investigation_question": "Why do alarms rise after release B?"},
    )
    assert made.status_code == 201, made.text
    assert _matches(r"INV\d{6}", made.json()["business_id"])
    assert made.json()["product_business_id"] == product["product_business_id"]


def test_workspace_and_decision_context_carry_business_ids(seed):
    client = role_client("INVESTIGATOR")[0]
    case = seed["investigation_id"]
    workspace = client.get(f"/api/v1/investigations/{case}/workspace", params={"include_retrieval": False})
    assert workspace.status_code == 200, workspace.text
    header = workspace.json()["investigation"]
    assert _matches(r"INV\d{6}", header["business_id"]) and _matches(r"PROD\d{6}", header["product_business_id"])
    evidence = workspace.json()["evidence_context"]
    assert evidence and all(_matches(r"EVD\d{6}", item["business_id"]) for item in evidence)
    context = client.get(f"/api/v1/investigations/{case}/decision-context").json()
    assert context["investigation"]["business_id"] == header["business_id"]
    assert context["product_context"]["product_business_id"] == header["product_business_id"]
    assert all(_matches(r"EVD\d{6}", item["business_id"]) for item in context["evidence"])


def test_decisions_carry_their_and_their_investigations_business_ids(seed):
    client = role_client("INVESTIGATOR")[0]
    case = seed["investigation_id"]
    with SessionLocal() as db:
        case_id = db.query(Investigation.business_id).filter(Investigation.id == case).scalar()
    listed = client.get(f"/api/v1/investigations/{case}/decisions").json()
    assert listed and all(_matches(r"DEC\d{6}", item["business_id"]) for item in listed)
    assert all(item["investigation_business_id"] == case_id for item in listed)
    one = client.get(f"/api/v1/investigations/decisions/{listed[0]['id']}").json()
    assert one["business_id"] == listed[0]["business_id"] and one["investigation_business_id"] == case_id
    created = client.post(
        f"/api/v1/investigations/{case}/decisions",
        json={
            "selected_action": "NO_DECISION_YET",
            "rationale": "More evidence is needed.",
            "temporal_mode": "current",
        },
    )
    assert created.status_code == 200, created.text
    assert (
        _matches(r"DEC\d{6}", created.json()["business_id"]) and created.json()["investigation_business_id"] == case_id
    )


def test_signatures_carry_their_and_their_decisions_business_ids(seed):
    approver = role_client("APPROVER")[0]
    signed_decision = next(
        decision_id
        for decision_id in seed["decision_ids"]
        if approver.get(f"/api/v1/governance/decisions/{decision_id}/signature-history").json()
    )
    with SessionLocal() as db:
        decision_business_id = db.query(Decision.business_id).filter(Decision.id == signed_decision).scalar()
    report = approver.get(f"/api/v1/governance/decisions/{signed_decision}/signature-verification").json()
    assert report["decision_business_id"] == decision_business_id
    assert report["signatures"] and all(_matches(r"ESIG\d{6}", item["business_id"]) for item in report["signatures"])
    history = approver.get(f"/api/v1/governance/decisions/{signed_decision}/signature-history").json()
    assert {item["business_id"] for item in history} == {item["business_id"] for item in report["signatures"]}


def test_signing_returns_the_signature_and_decision_business_ids(seed):
    with SessionLocal() as db:
        decision = Decision(
            id=uuid.uuid4(),
            tenant_id=uuid.UUID(seed["tenant_id"]),
            investigation_id=uuid.UUID(seed["investigation_id"]),
            decision_identifier=f"DEC-BIZID-{uuid.uuid4().hex[:8]}",
            decision_type="INVESTIGATION_REVIEW",
            disposition="REQUIRES_REVIEW",
            rationale="Signed by the business identifier test",
            decision_status="REQUIRES_REVIEW",
            authorized_by_ref=f"creator-{uuid.uuid4().hex[:8]}@example.invalid",
            decision_timestamp=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(decision)
        db.commit()
        version, expected = decision.updated_at.isoformat(), decision.business_id
    approver = role_client("APPROVER")[0]
    signed = approver.post(
        f"/api/v1/governance/decisions/{decision.id}/sign",
        json={"decision": "APPROVE", "remarks": "Reviewed", "password": PASSWORD, "object_version": version},
    )
    assert signed.status_code == 200, signed.text
    assert _matches(r"ESIG\d{6}", signed.json()["business_id"]) and signed.json()["decision_business_id"] == expected


def test_analytics_lists_and_story_carry_business_ids(seed):
    client = role_client("INVESTIGATOR")[0]
    investigations = client.get("/api/v1/analytics/investigations").json()["investigations"]
    assert investigations and all(_matches(r"INV\d{6}", row["business_id"]) for row in investigations)
    evidence = client.get("/api/v1/analytics/evidence").json()["evidence"]
    assert evidence and all(_matches(r"EVD\d{6}", row["business_id"]) for row in evidence)
    signals = client.get("/api/v1/analytics/signals").json()["signals"]
    assert signals and all(_matches(r"CMP\d{6}", row["business_id"]) for row in signals)
    detail = client.get(f"/api/v1/signals/{signals[0]['business_id'].lower()}").json()
    assert detail["status"] == "READY_FOR_REVIEW" and detail["signal"]["business_id"] == signals[0]["business_id"]
    assert _matches(r"PROD\d{6}", detail["signal"]["product_business_id"])
    assert all(_matches(r"INV\d{6}", row["business_id"]) for row in detail["related_investigations"])
    story = client.get(f"/api/v1/story/{seed['investigation_id']}").json()
    assert _matches(r"INV\d{6}", story["investigation_business_id"])
    version_story = client.get(f"/api/v1/products/{seed['product_id']}/versions/{seed['version_id']}/story").json()
    assert _matches(r"PV\d{6}", version_story["version"]["business_id"])
    assert _matches(r"PROD\d{6}", version_story["version"]["product_business_id"])
    for section, pattern in (("complaints", r"CMP\d{6}"), ("investigations", r"INV\d{6}"), ("evidence", r"EVD\d{6}")):
        assert all(_matches(pattern, row["business_id"]) for row in version_story[section]), section


def test_evidence_list_and_detail_carry_business_ids():
    client = role_client("INVESTIGATOR")[0]
    listed = client.get("/api/v1/evidence", params={"limit": 5}).json()
    assert listed and all(_matches(r"EVD\d{6}", row["business_id"]) for row in listed)
    detail = client.get(f"/api/v1/evidence/{listed[0]['id']}").json()
    assert detail["evidence"]["business_id"] == listed[0]["business_id"]
    assert all(_matches(r"AIEX\d{6}", row["business_id"]) for row in detail["ai_provenance"])


def test_supplier_evidence_requests_carry_their_supplier_and_case_ids(seed):
    client = role_client("INVESTIGATOR")[0]
    supplier = own_supplier(client)
    made = client.post(EVIDENCE_REQUESTS, json=_body(supplier, investigation_id=seed["investigation_id"]))
    assert made.status_code == 200, made.text
    assert _matches(r"EVR\d{6}", made.json()["business_id"])
    listed = next(item for item in client.get(EVIDENCE_REQUESTS).json() if item["id"] == made.json()["id"])
    assert listed["business_id"] == made.json()["business_id"]
    assert _matches(r"SUP\d{6}", listed["supplier_business_id"])
    assert _matches(r"INV\d{6}", listed["investigation_business_id"])
    reply = client.post(f"{EVIDENCE_REQUESTS}/{made.json()['id']}/reply", json={"note": "Certificate received"})
    assert reply.status_code == 200 and reply.json()["business_id"] == made.json()["business_id"]


def test_ai_results_carry_record_and_evidence_ids(seed):
    client = role_client("INVESTIGATOR")[0]
    case = seed["investigation_id"]
    made = client.post(f"/api/v1/investigations/{case}/hypotheses", json={"investigation_id": case})
    assert made.status_code == 200, made.text
    hypotheses = made.json()["hypothesis_set"]["hypotheses"]
    assert hypotheses and all(_matches(r"HYP\d{6}", item["business_id"]) for item in hypotheses)
    latest = client.get(f"/api/v1/investigations/{case}/hypotheses").json()["hypothesis_set"]["hypotheses"]
    assert [item["business_id"] for item in latest] == [item["business_id"] for item in hypotheses]
    analysis = client.get(f"/api/v1/investigations/{case}/analysis/latest").json()["analysis"]
    references = [ref for ref in analysis["source_references"] if ref.get("evidence_id")]
    with SessionLocal() as db:
        known = {str(row.id) for row in db.query(Evidence.id).filter(Evidence.tenant_id == seed["tenant_id"])}
    for reference in references:
        if reference["evidence_id"] in known:
            assert _matches(r"EVD\d{6}", reference["evidence_business_id"])
    unknowns = client.post(f"/api/v1/investigations/{case}/unknowns", json={"investigation_id": case})
    assert unknowns.status_code == 200, unknowns.text
    for item in unknowns.json()["unknown_set"]["unknowns"]:
        assert "business_id" not in item or _matches(r"UNK\d{6}", item["business_id"])


def test_briefs_scenarios_and_counterfactuals_carry_business_ids(seed):
    client = role_client("INVESTIGATOR")[0]
    case = seed["investigation_id"]
    with SessionLocal() as db:
        case_id = db.query(Investigation.business_id).filter(Investigation.id == case).scalar()
    brief = client.post(f"/api/v1/investigations/{case}/briefs", json={"temporal_mode": "current"})
    assert brief.status_code == 200, brief.text
    assert _matches(r"DBR\d{6}", brief.json()["business_id"]) and brief.json()["investigation_business_id"] == case_id
    listed = client.get(f"/api/v1/investigations/{case}/briefs").json()["briefs"]
    assert all(item["investigation_business_id"] == case_id for item in listed)
    scenario = client.post(
        f"/api/v1/investigations/{case}/scenarios",
        json={
            "scenario_type": "EXCLUDE_RELATIONSHIP",
            "question": "What changes if the occlusion sensor bench test is excluded?",
            # The target must be part of the case (reports_seed: "Bench test of occlusion sensor").
            "target": "occlusion sensor",
            "persist": True,
        },
    )
    assert scenario.status_code == 200, scenario.text
    assert _matches(r"SCN\d{6}", scenario.json()["business_id"])
    explored = client.post(
        f"/api/v1/investigations/{case}/scenarios",
        json={"scenario_type": "EXCLUDE_RELATIONSHIP", "question": "And without saving?", "target": "occlusion sensor"},
    )
    assert explored.status_code == 200 and explored.json()["business_id"] is None
    counterfactual = client.post(
        f"/api/v1/investigations/{case}/counterfactuals",
        json={
            "intervention_type": "REMOVE_CHANGE",
            "intervention_target": "occlusion sensor",
            "intervention_description": "Remove the candidate change from the explanation.",
        },
    )
    assert counterfactual.status_code == 200, counterfactual.text
    assert _matches(r"SCN\d{6}", counterfactual.json()["business_id"])
    listed = client.get(f"/api/v1/investigations/{case}/counterfactuals").json()
    assert all(_matches(r"SCN\d{6}", item["business_id"]) for item in listed)


def test_evaluation_runs_carry_their_business_id(monkeypatch):
    monkeypatch.setattr(
        evaluation_router,
        "run_golden_evaluation",
        lambda scenario_ids: {"evaluation_version": "TEST", "passed": 1, "total": 1, "results": []},
    )
    client = role_client("INVESTIGATOR")[0]
    started = client.post("/api/v1/evaluations/runs", json={})
    assert started.status_code == 202, started.text
    assert _matches(r"EVAL\d{6}", started.json()["business_id"])
    run = client.get(f"/api/v1/evaluations/runs/{started.json()['evaluation_run_id']}").json()
    assert run["business_id"] == started.json()["business_id"]


def test_ask_intelligence_carries_business_ids(seed):
    client = role_client("INVESTIGATOR")[0]
    answer = client.post(
        "/api/v1/ask/", json={"question": "What do we know?", "investigation_id": seed["investigation_id"]}
    )
    assert answer.status_code == 200, answer.text
    intelligence = answer.json()["intelligence"]
    assert all(_matches(r"HYP\d{6}", item["business_id"]) for item in intelligence["hypotheses"])
    assert all(_matches(r"UNK\d{6}", item["business_id"]) for item in intelligence["unknowns"])
    for link in intelligence["provenance"]:
        assert _matches(r"EVD\d{6}", link["evidence_business_id"])
        assert _matches(r"HYP\d{6}", link["hypothesis_business_id"])
