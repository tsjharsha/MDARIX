"""The controlled Decision Brief end to end: composing a version from the case's records (sections, leading hypothesis
by people's judgement, AI disclosure, fingerprints), editing and refreshing the draft, the AI draft, the submission
gate (blocked and allowed), freezing a submitted version, segregation of duties in quality review, the return loop
with a new version, acceptance (ready for decision, decision task) and a resubmission superseding it, escalation, a
return for a risk review, the quality dashboard, permissions, other organizations and closed cases.

Everything runs in a fresh organization of its own (on the shared plane), deleted at the end.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from auth.durable import persist_session
from auth.service import _hash
from backend.app.db.models.foundation import (
    AIExecution,
    AuditEvent,
    AuthUser,
    Complaint,
    Evidence,
    Hypothesis,
    HypothesisEvidence,
    Investigation,
    InvestigationBrief,
    InvestigationEvidence,
    Product,
    ProductVersion,
    Tenant,
    TenantMembership,
)
from backend.app.db.models.reviews import CaseReview, DecisionBriefVersion
from backend.app.db.models.stage3 import SupplierEvidenceRequest
from backend.app.db.models.workflow import WorkflowTask
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from backend.app.decision_brief import rules
from backend.app.main import app

PASSWORD = "Decision brief 2026!"
QUESTION = "Why do occlusion alarms rise after release B?"
COMMENT = "The bench test of the returned pumps is still missing"
NARRATIVE = {
    "problem_statement": "Occlusion alarms rose after release B without occlusions",
    "proposed_conclusion": "Sensor drift in release B is the best supported explanation",
    "recommended_actions": ["Replace the occlusion sensor", "Retrain the field service team"],
}


@pytest.fixture(scope="module")
def org():
    """A fresh organization with an investigator, two quality reviewers, a leader (every permission) and a viewer."""
    from backend.app.customer_lifecycle import build_customer_tenant
    from backend.app.trial.retention import purge_trial

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db,
            tenant_key=f"BRIEF_{uuid.uuid4().hex[:8].upper()}",
            name="Decision brief",
            status="ACTIVE",
            now=now,
        )
        db.add(customer)
        db.add(tenant)
        db.commit()  # registers the organization on the shared plane (migration md20)
        tenant_id = tenant.id
    people = {
        name: _client(tenant_id, role, name.title())
        for name, role in (
            ("investigator", "INVESTIGATOR"),
            ("reviewer", "REVIEWER"),
            ("reviewer2", "REVIEWER"),
            ("leader", "LEADER"),
            ("viewer", "VIEWER"),
        )
    }
    try:
        yield {"tenant_id": tenant_id, **people}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:decision-brief-cleanup")


def _client(tenant_id, role: str, name: str) -> tuple[TestClient, str]:
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=f"brief-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name=f"{name} Brief",
            company="Test",
            password_hash=_hash(PASSWORD),
            role=role,
            status="ACTIVE",
            email_verified=True,
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        db.flush()
        db.add(
            TenantMembership(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=user.id,
                status="ACTIVE",
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        token = secrets.token_urlsafe(32)
        persist_session(db, token, user.id, tenant_id)
        user_id = str(user.id)
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    return client, user_id


def _add(tenant_id, *rows) -> None:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.add_all(rows)
        db.commit()


def _product(tenant_id) -> tuple[str, str]:
    """A product with one version and one complaint on it: ``(product id, complaint id)``."""
    now = datetime.now(timezone.utc)
    tag = uuid.uuid4().hex[:8].upper()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_identifier=f"DB-P-{tag}",
            name=f"Brief Pump {tag}",
            created_at=now,
            updated_at=now,
        )
        db.add(product)
        db.flush()
        version = ProductVersion(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_id=product.id,
            version_identifier="Rev B",
            created_at=now,
            updated_at=now,
        )
        db.add(version)
        db.flush()
        complaint = Complaint(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            complaint_identifier=f"DB-C-{uuid.uuid4().hex[:10].upper()}",
            product_id=product.id,
            product_version_id=version.id,
            event_timestamp=now - timedelta(days=5),
            description="Occlusion alarm without an occlusion",
            status="open",
            created_at=now,
            updated_at=now,
        )
        db.add(complaint)
        db.commit()
        return str(product.id), str(complaint.id)


def _evidence(tenant_id, case_id, title: str = "Bench test of the occlusion sensor") -> Evidence:
    now = datetime.now(timezone.utc)
    return Evidence(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        evidence_identifier=f"DB-EV-{uuid.uuid4().hex[:10].upper()}",
        evidence_type="test_report",
        title=title,
        investigation_id=uuid.UUID(str(case_id)),
        created_at=now,
        updated_at=now,
    )


def _case(org, author: str = "investigator", *, ready: bool = True) -> dict:
    """A case opened by ``author`` with one complaint in scope. ``ready``: one accepted supporting piece of evidence,
    a hypothesis a person judged strongly supported (and an AI one nobody judged), an AI run, and completed risk and
    regulatory reviews."""
    tenant_id = org["tenant_id"]
    client, _ = org[author]
    product_id, complaint_id = _product(tenant_id)
    made = client.post(
        "/api/v1/investigations",
        json={
            "product_id": product_id,
            "investigation_question": QUESTION,
            "complaint_ids": [complaint_id],
            "assign_to_me": True,
        },
    )
    assert made.status_code == 201, made.text
    case = made.json()
    if not ready:
        return case
    now = datetime.now(timezone.utc)
    case_uuid = uuid.UUID(case["id"])
    evidence = _evidence(tenant_id, case["id"])
    reviewer_id = uuid.UUID(org["reviewer"][1])
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.add(evidence)
        db.flush()
        db.add(
            InvestigationEvidence(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                investigation_id=case_uuid,
                evidence_id=evidence.id,
                review_status="ACCEPTED",
                relationship="SUPPORTING",
                review_reason="The bench test reproduces the alarm",
                reviewed_by=str(reviewer_id),
                reviewed_at=now,
                linked_by=str(reviewer_id),
                created_at=now,
            )
        )
        judged = Hypothesis(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=case_uuid,
            statement="The occlusion sensor of release B drifts",
            status="mixed_evidence",
            origin="ai",
            human_status="STRONGLY_SUPPORTED",
            status_reason="The bench test reproduces the drift",
            reviewer_disposition="HUMAN_JUDGED",
            created_at=now,
            updated_at=now,
        )
        unjudged = Hypothesis(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=case_uuid,
            statement="Users set the occlusion limit too low",
            status="supported",
            origin="ai",
            created_at=now,
            updated_at=now,
        )
        db.add_all([judged, unjudged])
        db.flush()
        db.add(
            HypothesisEvidence(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                hypothesis_id=judged.id,
                evidence_id=evidence.id,
                relation_type="support",
                rationale="Drift reproduced on the bench",
                created_by_type="human",
                created_by=str(reviewer_id),
                created_at=now,
            )
        )
        execution = AIExecution(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=case_uuid,
            provider="mdarix-controlled-hypothesis-engine",
            model_name="test-model",
            orchestration_version="R1-test",
            validation_status="COMPLETED",
            execution_timestamp=now,
        )
        db.add(execution)
        for review_type, outcome in (
            ("RISK", "NO_CHANGE_REQUIRED"),
            ("REGULATORY", "NO_REPORTABILITY_CONCERN_IDENTIFIED"),
        ):
            db.add(
                CaseReview(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    investigation_id=case_uuid,
                    review_type=review_type,
                    status="COMPLETED",
                    required_by_policy=False,
                    requested_by=str(reviewer_id),
                    reviewer_user_id=reviewer_id,
                    reviewer_role="REVIEWER",
                    outcome=outcome,
                    rationale="Reviewed against the risk file and the reporting rules",
                    scope_version=1,
                    completed_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
        db.commit()
        case["_evidence"] = evidence.business_id
        case["_judged"] = judged.business_id
        case["_unjudged"] = unjudged.business_id
        case["_execution"] = execution.business_id
    return case


def _base(case_id) -> str:
    return f"/api/v1/investigations/{case_id}/decision-brief"


def _code(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


def _submitted(org, author: str = "investigator") -> tuple[dict, dict]:
    """A ready case whose brief version 1 ``author`` composed, wrote and submitted."""
    case = _case(org, author)
    client, _ = org[author]
    assert client.post(_base(case["id"]), json={}).status_code == 201
    assert client.put(_base(case["id"]) + "/draft", json=NARRATIVE).status_code == 200
    submitted = client.post(_base(case["id"]) + "/submit", json={"comment": "Ready for review"})
    assert submitted.status_code == 200, submitted.text
    return case, submitted.json()


def _row(tenant_id, model, **filters):
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        found = db.query(model).filter_by(**filters).one()
        db.expunge(found)
        return found


def _case_row(tenant_id, case_id) -> Investigation:
    return _row(tenant_id, Investigation, id=uuid.UUID(str(case_id)))


def _tasks(tenant_id, case_id, task_type: str) -> list[WorkflowTask]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        rows = (
            db.query(WorkflowTask)
            .filter(WorkflowTask.investigation_id == uuid.UUID(str(case_id)), WorkflowTask.task_type == task_type)
            .order_by(WorkflowTask.created_at)
            .all()
        )
        db.expunge_all()
        return rows


def _audit_actions(tenant_id, entity_id) -> list[str]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return [
            row[0]
            for row in db.query(AuditEvent.action)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.entity_id == uuid.UUID(str(entity_id)))
            .order_by(AuditEvent.created_at)
        ]


def _foreign_case() -> str:
    """A case of another organization (the golden one)."""
    with SessionLocal() as db:
        bind_system(db, "test: a case of another organization")
        golden = db.query(Tenant.id).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").one()[0]
        return str(db.query(Investigation.id).filter(Investigation.tenant_id == golden).first()[0])


def _blocking(response) -> set[str]:
    return {item["key"] for item in response.json()["detail"]["blocking"]}


# ------------------------------------------------------------------------------------------------- composing


def test_composing_editing_and_refreshing_a_draft(org):
    tenant_id = org["tenant_id"]
    client, user_id = org["investigator"]
    viewer, _ = org["viewer"]
    case = _case(org)
    base = _base(case["id"])

    empty = viewer.get(base)  # reading needs only a session
    assert empty.status_code == 200, empty.text
    assert empty.json()["current"] is None and empty.json()["versions"] == []
    assert empty.json()["gate"]["can_submit"] is False and not any(empty.json()["actions"].values())
    refused = viewer.post(base, json={})
    assert refused.status_code == 403 and _code(refused) == "PERMISSION_DENIED"

    made = client.post(base, json={})
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["version"] == 1 and body["status"] == "DRAFT" and body["editable"] is True
    assert body["business_id"].startswith("DBV") and body["title"] == f"Decision brief {case['business_id']} v1"
    assert body["hash_verified"] is True and len(body["content_hash"]) == 64
    content = body["content"]
    assert content["investigation"]["business_id"] == case["business_id"]
    assert content["investigation"]["question"] == QUESTION
    assert content["product"]["business_id"] and content["product"]["name"].startswith("Brief Pump")
    assert content["scope"]["version"] == 1 and content["scope"]["included_count"] == 1
    inventory = content["evidence_inventory"]
    assert inventory["total"] == 1 and inventory["by_review_status"] == {"ACCEPTED": 1}
    assert inventory["items"][0]["business_id"] == case["_evidence"]
    assert any(
        item["kind"] == "EVIDENCE" and item["evidence_business_id"] == case["_evidence"]
        for item in content["established_facts"]
    )
    supporting = {(item["source"], item["evidence_business_id"]) for item in content["supporting_evidence"]}
    # Each piece of evidence once (0.10.72): the link to the leading hypothesis replaces the case's own judgement.
    assert supporting == {("HYPOTHESIS", case["_evidence"])}
    assert content["contradicting_evidence"] == []
    # The leading hypothesis is the one a person judged; the AI's own "supported" never makes one lead.
    assert content["leading_hypothesis"]["business_id"] == case["_judged"]
    assert content["leading_hypothesis"]["human_status"] == "STRONGLY_SUPPORTED"
    alternative = content["alternative_hypotheses"]
    assert [item["business_id"] for item in alternative] == [case["_unjudged"]]
    assert alternative[0]["ai_status"] == "supported" and alternative[0]["human_status"] is None
    assert alternative[0]["kind_label"] == "AI interpretation"
    assert content["unknowns"]["open"] == [] and content["unknowns"]["accepted_limitations"] == []
    for key in ("risk_review", "regulatory_review"):
        assert content[key]["state"] == "COMPLETED" and content[key]["review"]["business_id"].startswith("REV")
    assert content["risk_review"]["review"]["outcome"] == "NO_CHANGE_REQUIRED"
    assert content["risk_review"]["review"]["reviewer_name"] == "Reviewer Brief"
    ai = content["ai_assistance"]
    assert [item["business_id"] for item in ai["executions"]] == [case["_execution"]]
    assert ai["executions"][0]["kind"] == "Hypotheses" and ai["executions"][0]["model"] == "test-model"
    assert ai["statement"].startswith("AI assisted: 1 AI run (Hypotheses)")
    assert ai["statement"].endswith(rules.AI_JUDGEMENT_SENTENCE)
    assert {check["key"] for check in content["readiness"]} >= {"scope_complete", "evidence_reviewed", "risk_review"}
    context = content["context"]
    assert context["scope_version"] == 1 and len(context["evidence_set_hash"]) == 64
    assert content["unavailable"] == []
    # The problem statement starts as the investigation's question, AI off too (0.10.69: nothing typed twice).
    assert body["narrative"]["problem_statement"] == " ".join(QUESTION.split())
    assert body["narrative"]["contributor_names"] == ["Investigator Brief"]

    again = client.post(base, json={})
    assert again.status_code == 409 and _code(again) == "BRIEF_ALREADY_OPEN"

    assert client.put(base + "/draft", json={}).status_code == 422
    edited = client.put(base + "/draft", json={"problem_statement": NARRATIVE["problem_statement"]})
    assert edited.status_code == 200, edited.text
    assert edited.json()["narrative"]["problem_statement"] == NARRATIVE["problem_statement"]
    assert edited.json()["content_hash"] != body["content_hash"] and edited.json()["hash_verified"] is True
    assert edited.json()["content"] == content  # editing the narrative never recomposes the content

    _add(tenant_id, _evidence(tenant_id, case["id"], "Field service report"))
    refreshed = client.post(base + "/draft/refresh")
    assert refreshed.status_code == 200, refreshed.text
    fresh = refreshed.json()
    assert fresh["content"]["evidence_inventory"]["total"] == 2
    assert fresh["content"]["context"]["evidence_set_hash"] != context["evidence_set_hash"]
    assert fresh["narrative"]["problem_statement"] == NARRATIVE["problem_statement"]
    assert fresh["version"] == 1 and fresh["hash_verified"] is True

    page = client.get(base).json()
    assert page["current"]["version"] == 1 and [item["version"] for item in page["versions"]] == [1]
    assert page["actions"]["can_edit"] is True and page["actions"]["can_compose"] is False
    assert page["gate"]["can_submit"] is False and page["actions"]["can_submit"] is False
    assert {"evidence_reviewed", "proposed_conclusion"} <= {item["key"] for item in page["gate"]["blocking"]}

    one = viewer.get(base + "/versions/1")
    assert one.status_code == 200 and one.json()["content_hash"] == fresh["content_hash"]
    missing = viewer.get(base + "/versions/2")
    assert missing.status_code == 404 and _code(missing) == "BRIEF_VERSION_NOT_FOUND"
    actions = _audit_actions(tenant_id, body["id"])
    assert actions[:3] == ["BRIEF_CREATED", "BRIEF_DRAFT_UPDATED", "BRIEF_REFRESHED"]
    assert _row(tenant_id, DecisionBriefVersion, id=uuid.UUID(body["id"])).created_by == user_id


def test_starting_from_the_ai_draft(org):
    tenant_id = org["tenant_id"]
    client, _ = org["investigator"]
    case = _case(org)
    base = _base(case["id"])
    unavailable = client.post(base, json={"use_ai_draft": True})
    assert unavailable.status_code == 409 and _code(unavailable) == "AI_DRAFT_NOT_AVAILABLE"

    now = datetime.now(timezone.utc)
    brief_id = uuid.uuid4()  # kept: the row is expired once its session commits
    brief = InvestigationBrief(
        id=brief_id,
        tenant_id=tenant_id,
        investigation_id=uuid.UUID(case["id"]),
        brief_version=1,
        title="Investigation brief",
        generated_by="test",
        temporal_mode="current",
        content={
            "ai_brief": {
                "headline": "Alarms rose after release B.",
                "sections": {
                    "what_we_know": [{"statement": "One complaint since May", "evidence": []}],
                    "next_steps": [{"statement": "Review the release B change record", "evidence": []}],
                },
            }
        },
        provenance={},
        created_at=now,
        updated_at=now,
    )
    _add(tenant_id, brief)
    made = client.post(base, json={"use_ai_draft": True})
    assert made.status_code == 201, made.text
    narrative = made.json()["narrative"]
    assert narrative["ai_draft_used"] is True and narrative["ai_draft_label"] == rules.AI_DRAFT_LABEL
    assert narrative["ai_draft_text"].startswith("Alarms rose after release B.")
    assert narrative["ai_draft_source"]["brief_version"] == 1
    # The brief writes itself first: the problem statement is the case's question, the recommended actions are the
    # AI's possible next steps; the proposed conclusion is never written for the author.
    assert narrative["problem_statement"] == " ".join(QUESTION.split())
    assert narrative["recommended_actions"] == ["Review the release B change record"]
    assert narrative["proposed_conclusion"] == ""
    assert narrative["ai_draft_source"]["out_of_date"] in (True, False)
    assert made.json()["source_ai_brief_id"] == str(brief_id)
    ai = made.json()["content"]["ai_assistance"]
    assert ai["ai_draft_used"] is True and "the author started the narrative from an AI draft" in ai["statement"]

    dropped = client.put(base + "/draft", json={"ai_draft_used": False})
    assert dropped.status_code == 200 and dropped.json()["narrative"]["ai_draft_text"] is None


# ------------------------------------------------------------------------------------------------ submitting


def test_submission_is_refused_until_the_gate_allows_it(org):
    tenant_id = org["tenant_id"]
    client, user_id = org["investigator"]
    case = _case(org, ready=False)
    base = _base(case["id"])
    assert client.post(base, json={}).status_code == 201

    refused = client.post(base + "/submit", json={})
    assert refused.status_code == 409 and _code(refused) == "BRIEF_NOT_READY"
    assert {"evidence_reviewed", "proposed_conclusion"} <= _blocking(refused)

    now = datetime.now(timezone.utc)
    _add(
        tenant_id,
        SupplierEvidenceRequest(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=uuid.UUID(case["id"]),
            requested_by=user_id,
            title="Bench test results of the returned pumps",
            requested_items={"items": ["Bench test report"]},
            recipient="supplier.quality@example.invalid",  # a request always names who is asked
            status="SENT",
            priority="HIGH",
            created_at=now,
            updated_at=now,
        ),
    )
    assert client.put(base + "/draft", json=NARRATIVE).status_code == 200
    refused = client.post(base + "/submit", json={})
    assert refused.status_code == 409
    blocking = _blocking(refused)
    assert "no_blocking_request" in blocking and "problem_statement" not in blocking

    row = _row(tenant_id, DecisionBriefVersion, investigation_id=uuid.UUID(case["id"]))
    assert row.status == "DRAFT" and row.submitted_at is None
    assert _case_row(tenant_id, case["id"]).workflow_state != "BRIEF_IN_REVIEW"
    assert _tasks(tenant_id, case["id"], "QUALITY_REVIEW") == []


def test_submitting_freezes_the_version_and_queues_its_quality_review(org):
    tenant_id = org["tenant_id"]
    client, _ = org["investigator"]
    reviewer, _ = org["reviewer"]
    case, body = _submitted(org)
    base = _base(case["id"])
    assert body["status"] == "READY_FOR_REVIEW" and body["editable"] is False
    assert body["submitted_by_name"] == "Investigator Brief" and body["submitted_at"]
    assert body["hash_verified"] is True
    assert body["narrative"]["proposed_conclusion"] == NARRATIVE["proposed_conclusion"]
    assert body["readiness"]["checks"]

    row = _case_row(tenant_id, case["id"])
    assert row.workflow_state == "BRIEF_IN_REVIEW" and row.status == "open"
    assert "INVESTIGATION_STATE_CHANGED" in _audit_actions(tenant_id, case["id"])
    assert "BRIEF_SUBMITTED" in _audit_actions(tenant_id, body["id"])
    [task] = _tasks(tenant_id, case["id"], "QUALITY_REVIEW")
    assert task.status == "NEW" and task.assigned_role == "REVIEWER" and task.assigned_user_id is None
    assert task.source_entity_type == "DecisionBriefVersion" and str(task.source_entity_id) == body["id"]
    assert task.title == f"Quality review of {case['business_id']} brief v1"

    queue = reviewer.get("/api/v1/tasks", params={"view": "queue", "q": case["business_id"]}).json()["items"]
    [listed] = [item for item in queue if item["id"] == str(task.id)]
    assert listed["source"]["business_id"] == body["business_id"]
    assert listed["source"]["label"] == f"Decision brief {body['business_id']}"

    for response in (
        client.put(base + "/draft", json={"problem_statement": "Something else entirely"}),
        client.post(base + "/draft/refresh"),
        client.post(base + "/submit", json={}),
    ):
        assert response.status_code == 409 and _code(response) == "BRIEF_NOT_EDITABLE", response.text
    again = client.post(base, json={})
    assert again.status_code == 409 and _code(again) == "BRIEF_ALREADY_OPEN"

    _add(tenant_id, _evidence(tenant_id, case["id"], "Late service report"))
    frozen = client.get(base + "/versions/1").json()
    assert frozen["content"] == body["content"] and frozen["content_hash"] == body["content_hash"]
    assert frozen["hash_verified"] is True


# --------------------------------------------------------------------------------------------- quality review


def test_nobody_reviews_a_version_they_wrote_or_submitted(org):
    investigator, _ = org["investigator"]
    leader, _ = org["leader"]
    reviewer, _ = org["reviewer"]
    case = _case(org)
    base = _base(case["id"])
    assert investigator.post(base, json={}).status_code == 201
    # The leader writes part of the narrative: a contributor never reviews the version either.
    assert leader.put(base + "/draft", json=NARRATIVE).status_code == 200
    assert investigator.post(base + "/submit", json={}).status_code == 200

    for response in (
        leader.post(base + "/versions/1/start-review", json={}),
        leader.post(base + "/versions/1/review", json={"action": "ACCEPT_FOR_DECISION"}),
    ):
        assert response.status_code == 403 and _code(response) == "SOD_DENIED", response.text
    page = leader.get(base).json()
    assert page["actions"]["can_review"] is False and page["actions"]["can_start_review"] is False
    refused = investigator.post(base + "/versions/1/start-review", json={})
    assert refused.status_code == 403 and _code(refused) == "PERMISSION_DENIED"
    assert reviewer.get(base).json()["actions"]["can_start_review"] is True

    own_case, _ = _submitted(org, "leader")
    response = leader.post(_base(own_case["id"]) + "/versions/1/review", json={"action": "ACCEPT_FOR_DECISION"})
    assert response.status_code == 403 and _code(response) == "SOD_DENIED"


def test_a_return_sends_the_brief_back_and_a_new_version_follows(org):
    tenant_id = org["tenant_id"]
    investigator, investigator_id = org["investigator"]
    reviewer, reviewer_id = org["reviewer"]
    reviewer2, _ = org["reviewer2"]
    case, first = _submitted(org)
    base = _base(case["id"])

    started = reviewer.post(base + "/versions/1/start-review", json={})
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "UNDER_REVIEW"
    [action] = started.json()["review_actions"]
    assert action["action"] == "START_REVIEW" and action["actor_name"] == "Reviewer Brief"
    assert action["actor_role"] == "REVIEWER"
    [task] = _tasks(tenant_id, case["id"], "QUALITY_REVIEW")
    assert str(task.assigned_user_id) == reviewer_id and task.status == "ACCEPTED"
    twice = reviewer2.post(base + "/versions/1/start-review", json={})
    assert twice.status_code == 409 and _code(twice) == "BRIEF_STATE_CONFLICT"

    assert reviewer.post(base + "/versions/1/review", json={"action": "RETURN_FOR_EVIDENCE"}).status_code == 422
    returned = reviewer.post(base + "/versions/1/review", json={"action": "RETURN_FOR_EVIDENCE", "comment": COMMENT})
    assert returned.status_code == 200, returned.text
    body = returned.json()
    assert body["status"] == "RETURNED" and body["reviewed_by_name"] == "Reviewer Brief"
    assert body["review_actions"][-1]["comment"] == COMMENT and body["review_request"] is None
    assert body["content_hash"] == first["content_hash"] and body["hash_verified"] is True
    assert _case_row(tenant_id, case["id"]).workflow_state == "IN_PROGRESS"
    [task] = _tasks(tenant_id, case["id"], "QUALITY_REVIEW")
    assert task.status == "COMPLETED" and task.completion_outcome == "RETURN_FOR_EVIDENCE"
    [follow_up] = _tasks(tenant_id, case["id"], "FOLLOW_UP")
    assert follow_up.is_return is True and str(follow_up.assigned_user_id) == investigator_id
    assert follow_up.status == "ASSIGNED" and follow_up.details["comment"] == COMMENT
    assert "BRIEF_RETURN_FOR_EVIDENCE" in _audit_actions(tenant_id, first["id"])
    again = reviewer.post(base + "/versions/1/review", json={"action": "ACCEPT_FOR_DECISION"})
    assert again.status_code == 409 and _code(again) == "BRIEF_STATE_CONFLICT"
    assert investigator.get(base).json()["actions"]["can_compose"] is True

    second = investigator.post(base, json={})
    assert second.status_code == 201, second.text
    assert second.json()["version"] == 2 and second.json()["status"] == "DRAFT"
    assert second.json()["narrative"]["problem_statement"] == NARRATIVE["problem_statement"]
    resubmitted = investigator.post(base + "/submit", json={})
    assert resubmitted.status_code == 200, resubmitted.text
    [follow_up] = _tasks(tenant_id, case["id"], "FOLLOW_UP")
    assert follow_up.status == "COMPLETED" and follow_up.completion_outcome == "RESUBMITTED"
    versions = {item["version"]: item["status"] for item in investigator.get(base).json()["versions"]}
    assert versions == {1: "RETURNED", 2: "READY_FOR_REVIEW"}
    assert _case_row(tenant_id, case["id"]).workflow_state == "BRIEF_IN_REVIEW"

    summary = reviewer.get("/api/v1/decision-briefs/summary").json()
    assert summary["counts"]["resubmitted"] >= 1
    assert any(
        item["investigation_business_id"] == case["business_id"] and item["version"] == 2
        for item in summary["awaiting"]
    )


def test_accepting_makes_the_case_ready_for_decision_and_a_resubmission_supersedes_it(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    reviewer, _ = org["reviewer"]
    case, first = _submitted(org)
    base = _base(case["id"])

    accepted = reviewer.post(base + "/versions/1/review", json={"action": "ACCEPT_FOR_DECISION"})
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["status"] == "APPROVED_FOR_DECISION" and body["reviewed_at"]
    assert [item["action"] for item in body["review_actions"]] == ["START_REVIEW", "ACCEPT_FOR_DECISION"]
    assert _case_row(tenant_id, case["id"]).workflow_state == "READY_FOR_DECISION"
    [review_task] = _tasks(tenant_id, case["id"], "QUALITY_REVIEW")
    assert review_task.status == "COMPLETED" and review_task.completion_outcome == "ACCEPT_FOR_DECISION"
    [decision_task] = _tasks(tenant_id, case["id"], "DECISION_APPROVAL")
    assert decision_task.status == "NEW" and decision_task.assigned_role == "APPROVER"
    assert (
        decision_task.source_entity_type == "DecisionBriefVersion"
        and str(decision_task.source_entity_id) == first["id"]
    )
    assert decision_task.title == f"Decide on {case['business_id']} (brief v1)"
    assert {"BRIEF_START_REVIEW", "BRIEF_ACCEPT_FOR_DECISION"} <= set(_audit_actions(tenant_id, first["id"]))

    assert investigator.get(base).json()["actions"]["can_compose"] is True
    assert investigator.post(base, json={}).status_code == 201
    assert _case_row(tenant_id, case["id"]).workflow_state == "READY_FOR_DECISION"
    resubmitted = investigator.post(base + "/submit", json={})
    assert resubmitted.status_code == 200, resubmitted.text
    versions = {item["version"]: item["status"] for item in investigator.get(base).json()["versions"]}
    assert versions == {1: "SUPERSEDED", 2: "READY_FOR_REVIEW"}
    [decision_task] = _tasks(tenant_id, case["id"], "DECISION_APPROVAL")
    assert decision_task.status == "SUPERSEDED" and decision_task.completion_outcome == "BRIEF_RESUBMITTED"
    assert "BRIEF_SUPERSEDED" in _audit_actions(tenant_id, first["id"])
    assert _case_row(tenant_id, case["id"]).workflow_state == "BRIEF_IN_REVIEW"
    superseded = investigator.get(base + "/versions/1").json()
    assert superseded["content_hash"] == first["content_hash"] and superseded["hash_verified"] is True


def test_escalation_and_a_return_for_a_risk_review(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    reviewer, _ = org["reviewer"]
    case, first = _submitted(org)
    base = _base(case["id"])

    short = reviewer.post(base + "/versions/1/review", json={"action": "ESCALATE", "comment": "Too short"})
    assert short.status_code == 422
    escalated = reviewer.post(base + "/versions/1/review", json={"action": "ESCALATE", "comment": COMMENT})
    assert escalated.status_code == 200, escalated.text
    assert escalated.json()["status"] == "UNDER_REVIEW" and escalated.json()["reviewed_at"] is None
    tasks = _tasks(tenant_id, case["id"], "QUALITY_REVIEW")
    assert {(task.assigned_role, task.status) for task in tasks} == {("REVIEWER", "ACCEPTED"), ("LEADER", "NEW")}

    returned = reviewer.post(base + "/versions/1/review", json={"action": "RETURN_FOR_RISK_REVIEW", "comment": COMMENT})
    assert returned.status_code == 200, returned.text
    body = returned.json()
    assert body["status"] == "RETURNED"
    assert body["review_request"]["review_type"] == "RISK" and body["review_request"]["requested"] is True
    assert {task.status for task in _tasks(tenant_id, case["id"], "QUALITY_REVIEW")} == {"COMPLETED"}
    requested = _row(tenant_id, CaseReview, investigation_id=uuid.UUID(case["id"]), status="REQUESTED")
    assert requested.review_type == "RISK" and str(requested.brief_version_id) == first["id"]

    # The new version cannot go to review while the requested risk review is still open.
    assert investigator.post(base, json={}).status_code == 201
    refused = investigator.post(base + "/submit", json={})
    assert refused.status_code == 409 and "risk_review" in _blocking(refused)


# ------------------------------------------------------------------------------------------ quality dashboard


def test_the_quality_dashboard(org):
    tenant_id = org["tenant_id"]
    investigator, user_id = org["investigator"]
    reviewer, _ = org["reviewer"]
    viewer, _ = org["viewer"]
    case, body = _submitted(org)
    blocked_case = _case(org)
    now = datetime.now(timezone.utc)
    _add(
        tenant_id,
        SupplierEvidenceRequest(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=uuid.UUID(blocked_case["id"]),
            requested_by=user_id,
            title="Bench test results of the returned pumps",
            requested_items={"items": ["Bench test report"]},
            recipient="supplier.quality@example.invalid",  # a request always names who is asked
            status="SENT",
            priority="CRITICAL",
            created_at=now,
            updated_at=now,
        ),
    )

    summary = reviewer.get("/api/v1/decision-briefs/summary")
    assert summary.status_code == 200, summary.text
    data = summary.json()
    assert set(data["counts"]) == {
        "awaiting_review",
        "under_review_by_me",
        "returned_open",
        "resubmitted",
        "blocked_cases",
        "overdue_cases",
    }
    [item] = [item for item in data["awaiting"] if item["business_id"] == body["business_id"]]
    assert item["investigation"]["id"] == case["id"] and item["investigation"]["business_id"] == case["business_id"]
    assert item["investigation"]["question"] == QUESTION and item["investigation"]["product_id"]
    assert item["investigation_business_id"] == case["business_id"] and item["version"] == 1
    assert item["submitted_by_name"] == "Investigator Brief" and item["can_review"] is True
    [blocked] = [
        item for item in data["blocked"] if item["investigation"]["business_id"] == blocked_case["business_id"]
    ]
    assert {"key": "no_blocking_request", "label": "No urgent evidence request is open"} in blocked["blocking"]
    before = data["counts"]["under_review_by_me"]
    assert reviewer.post(_base(case["id"]) + "/versions/1/start-review", json={}).status_code == 200
    assert reviewer.get("/api/v1/decision-briefs/summary").json()["counts"]["under_review_by_me"] == before + 1

    listed = reviewer.get("/api/v1/decision-briefs", params={"status": "UNDER_REVIEW", "page_size": 200})
    assert listed.status_code == 200 and listed.json()["total"] >= 1
    [row] = [item for item in listed.json()["items"] if item["business_id"] == body["business_id"]]
    assert row["investigation"]["business_id"] == case["business_id"] and row["status_label"] == "Under quality review"
    assert all(item["status"] == "UNDER_REVIEW" for item in listed.json()["items"])
    assert reviewer.get("/api/v1/decision-briefs", params={"status": "NOPE"}).status_code == 422
    for client in (investigator, viewer):
        for path in ("/api/v1/decision-briefs/summary", "/api/v1/decision-briefs"):
            refused = client.get(path)
            assert refused.status_code == 403 and _code(refused) == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------------- isolation and closed cases


def test_other_organizations_unknown_cases_and_closed_cases(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    reviewer, _ = org["reviewer"]
    for case_id in (str(uuid.uuid4()), _foreign_case()):
        base = _base(case_id)
        for response in (
            investigator.get(base),
            investigator.get(base + "/versions/1"),
            investigator.post(base, json={}),
            investigator.put(base + "/draft", json=NARRATIVE),
            investigator.post(base + "/submit", json={}),
            reviewer.post(base + "/versions/1/start-review", json={}),
            reviewer.post(base + "/versions/1/review", json={"action": "ACCEPT_FOR_DECISION"}),
        ):
            assert response.status_code == 404 and _code(response) == "INVESTIGATION_NOT_FOUND", response.text
    no_brief = _case(org, ready=False)
    missing = investigator.put(_base(no_brief["id"]) + "/draft", json=NARRATIVE)
    assert missing.status_code == 404 and _code(missing) == "BRIEF_NOT_FOUND"

    case, _ = _submitted(org)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = db.query(Investigation).filter(Investigation.id == uuid.UUID(case["id"])).one()
        row.workflow_state = "CLOSED"
        row.status = "closed"
        db.commit()
    base = _base(case["id"])
    for response in (
        investigator.post(base, json={}),
        reviewer.post(base + "/versions/1/start-review", json={}),
        reviewer.post(base + "/versions/1/review", json={"action": "ACCEPT_FOR_DECISION"}),
    ):
        assert response.status_code == 409 and _code(response) == "CASE_CLOSED", response.text
    page = reviewer.get(base).json()
    assert page["current"]["status"] == "READY_FOR_REVIEW" and not any(page["actions"].values())
