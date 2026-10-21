"""The human decision end to end: the decision maker's queue and dashboard, the decision screen, signing a decision on
an approved Decision Brief version (the decision, its context snapshot, signature, follow-ups and their tasks, the
case and the decision task), verification (VALID, and INVALID once the signed remarks or the snapshot change), the
refusals (wrong password, an author, an administrator, a stale or changed brief), superseding a signed decision, a
rejection, returning the brief without a signature, and legacy signing and verification left as they were.

Everything runs in a fresh organization of its own (on the shared plane), deleted at the end.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from tests.conftest import with_signing_plan

from backend.app.db.models.decision_outcomes import DecisionFollowUp
from backend.app.db.models.foundation import AuditEvent, Decision, SignedApprovalRecord
from backend.app.db.models.reviews import BriefReviewAction, DecisionBriefVersion
from backend.app.db.models.stage3 import ContextSnapshot
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_decision_brief import PASSWORD, _base, _case_row, _client, _code, _row, _submitted, _tasks

RATIONALE = "The bench test reproduces the sensor drift of release B; the conclusion holds"
CONDITIONS = "Retest lot 7 within 30 days and report the result to quality"
SUPERSEDE_REASON = "The decision is corrected: no further action is needed after all"
RETURN_COMMENT = "The bench test of lot 7 must be in the brief before I decide"


@pytest.fixture(scope="module")
def org():
    """A fresh organization with an investigator (who writes briefs), a quality reviewer, three approvers, a leader,
    a customer administrator and a viewer."""
    from backend.app.customer_lifecycle import build_customer_tenant
    from backend.app.trial.retention import purge_trial

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db,
            tenant_key=f"DECIDE_{uuid.uuid4().hex[:8].upper()}",
            name="Human decision",
            status="ACTIVE",
            now=now,
        )
        db.add(customer)
        db.add(tenant)
        db.commit()  # registers the organization on the shared plane (migration md20)
        with_signing_plan(db, tenant)  # the plan and decision rules every organization has
        tenant_id = tenant.id
    people = {
        name: _client(tenant_id, role, name.title())
        for name, role in (
            ("investigator", "INVESTIGATOR"),
            ("reviewer", "REVIEWER"),
            ("reviewer2", "REVIEWER"),
            ("approver", "APPROVER"),
            ("approver2", "APPROVER"),
            ("approver3", "APPROVER"),
            ("leader", "LEADER"),
            ("admin", "CUSTOMER_ADMIN"),
            ("viewer", "VIEWER"),
        )
    }
    try:
        yield {"tenant_id": tenant_id, **people}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:human-decision-cleanup")


def _approved(org, author: str = "investigator") -> tuple[dict, dict]:
    """A ready case whose brief version 1 ``author`` wrote and submitted and a quality reviewer approved for decision:
    ``(case, approved version)``."""
    case, _ = _submitted(org, author)
    reviewer, _ = org["reviewer"]
    accepted = reviewer.post(_base(case["id"]) + "/versions/1/review", json={"action": "ACCEPT_FOR_DECISION"})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "APPROVED_FOR_DECISION"
    return case, accepted.json()


def _path(case_id) -> str:
    return f"/api/v1/investigations/{case_id}/decision"


def _body(brief: dict, **changes) -> dict:
    body = {
        "brief_version_id": brief["id"],
        "brief_content_hash": brief["content_hash"],
        "outcome": "ACCEPT_CONCLUSION",
        "rationale": RATIONALE,
        "password": PASSWORD,
    }
    body.update(changes)
    return body


def _audit(tenant_id, entity_id) -> list[str]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return [
            row[0]
            for row in db.query(AuditEvent.action)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.entity_id == uuid.UUID(str(entity_id)))
            .order_by(AuditEvent.created_at)
        ]


def _readiness(client, case_id) -> dict:
    body = client.get(f"/api/v1/investigations/{case_id}/readiness").json()
    return {
        "checks": {item["key"]: item["result"] for item in body["checks"]},
        "steps": {item["key"]: item["status"] for item in body["steps"]},
    }


def _signature(tenant_id, decision_id) -> SignedApprovalRecord:
    return _row(tenant_id, SignedApprovalRecord, object_id=uuid.UUID(str(decision_id)), decision_type="CASE_DECISION")


def _change(tenant_id, model, row_id, **values) -> dict:
    """Set ``values`` on one row (as a tamperer with database access would) and return what they were."""
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = db.query(model).filter(model.id == uuid.UUID(str(row_id))).one()
        before = {key: getattr(row, key) for key in values}
        for key, value in values.items():
            setattr(row, key, value)
        db.commit()
        return before


def _governance_status(client, decision_id) -> str:
    response = client.get(f"/api/v1/governance/decisions/{decision_id}/signature-verification")
    assert response.status_code == 200, response.text
    return response.json()["verification_status"]


# ------------------------------------------------------------------------------------------- queue and screen


def test_the_queue_the_dashboard_and_the_decision_screen(org):
    approver, _ = org["approver"]
    investigator, _ = org["investigator"]
    viewer, _ = org["viewer"]
    case, brief = _approved(org)

    queue = approver.get("/api/v1/decisions/queue")
    assert queue.status_code == 200, queue.text
    items = [item for item in queue.json()["items"] if item["investigation"]["id"] == case["id"]]
    assert len(items) == 1 and queue.json()["total"] >= 1
    item = items[0]
    assert item["brief"]["id"] == brief["id"] and item["brief"]["business_id"].startswith("DBV")
    assert item["brief"]["content_hash"] == brief["content_hash"] and item["brief"]["version"] == 1
    assert item["brief"]["quality_reviewer_name"] == "Reviewer Brief"
    assert item["investigation"]["business_id"] == case["business_id"]
    assert item["investigation"]["product"]["name"].startswith("Brief Pump")
    assert item["critical"] is False and item["awaiting_since"]
    assert {review["review_type"] for review in item["required_reviews"]} == {"RISK", "REGULATORY"}
    assert item["actions"] == {"can_decide": True, "reason": None}
    for refused in (investigator.get("/api/v1/decisions/queue"), viewer.get("/api/v1/decisions/summary")):
        assert refused.status_code == 403 and _code(refused) == "PERMISSION_DENIED"

    summary = approver.get("/api/v1/decisions/summary")
    assert summary.status_code == 200, summary.text
    counts = summary.json()["counts"]
    assert counts["awaiting_signature"] >= 1
    assert set(counts) == {
        "awaiting_signature",
        "critical",
        "due_soon",
        "overdue",
        "signed_30d",
        "returned_30d",
        "follow_ups_open",
        "follow_ups_overdue",
        "impact_assessments_open",
    }
    assert any(entry["investigation"]["id"] == case["id"] for entry in summary.json()["awaiting"])

    screen = approver.get(_path(case["id"]))
    assert screen.status_code == 200, screen.text
    body = screen.json()
    assert body["investigation"]["business_id"] == case["business_id"]
    assert body["brief"]["id"] == brief["id"] and body["brief"]["status"] == "APPROVED_FOR_DECISION"
    assert body["brief"]["hash_verified"] is True
    assert body["brief"]["narrative"]["proposed_conclusion"].startswith("Sensor drift")
    assert body["brief"]["established_facts"] and body["brief"]["unknowns"]["open"] == []
    assert body["brief"]["risk_review"]["state"] == "COMPLETED"
    assert body["brief"]["ai_assistance"]["executions"]
    assert body["brief"]["readiness"]
    kinds = [item["kind"] for item in body["reviewers"]]
    assert "QUALITY" in kinds and "RISK" in kinds and "REGULATORY" in kinds
    accepted = [item for item in body["reviewers"] if item["action"] == "ACCEPT_FOR_DECISION"]
    assert accepted and accepted[0]["name"] == "Reviewer Brief" and accepted[0]["at"]
    assert body["decisions"] == [] and body["current_decision"] is None and body["legacy_decision_count"] == 0
    assert [item["code"] for item in body["outcomes"]] == [
        "ACCEPT_CONCLUSION",
        "ACCEPT_WITH_CONDITIONS",
        "REJECT_CONCLUSION",
        "CLOSE_NO_FURTHER_ACTION",
    ]
    assert len(body["follow_up_options"]) == 5
    # The exact words signed, naming the person who would sign and the role they sign under.
    assert body["outcomes"][0]["signature_meaning"] == (
        f"I, Approver Brief, Authorized Decision Maker, have reviewed Decision Brief {brief['business_id']} version 1 "
        "and decide: Accept the conclusion"
    )
    assert item["investigation"]["product"]["id"] and (
        item["investigation"]["product"]["id"] == body["investigation"]["product"]["id"]
    )
    assert body["actions"]["can_sign"] is True and body["actions"]["can_return"] is True
    assert body["actions"]["reason"] is None and body["actions"]["supersede_required"] is False

    # The author reads the same screen but is offered nothing; so is a viewer.
    for client in (investigator, viewer):
        actions = client.get(_path(case["id"])).json()["actions"]
        assert actions["can_sign"] is False and actions["can_return"] is False and actions["reason"]
    missing = approver.get(_path(uuid.uuid4()))
    assert missing.status_code == 404


# ------------------------------------------------------------------------------------------------------ signing


def test_signing_a_decision_records_everything_and_verifies(org):
    tenant_id = org["tenant_id"]
    approver, approver_id = org["approver"]
    investigator, investigator_id = org["investigator"]
    case, brief = _approved(org)

    signed = approver.post(
        _path(case["id"]) + "/sign",
        json=_body(
            brief,
            outcome="ACCEPT_WITH_CONDITIONS",
            conditions=CONDITIONS,
            follow_ups=[
                {"action_type": "CAPA_REQUIRED"},
                {"action_type": "RISK_REASSESSMENT_REQUIRED", "assigned_role": "RISK_REVIEWER", "title": "Reassess"},
            ],
        ),
    )
    assert signed.status_code == 200, signed.text
    record = signed.json()
    decision = record["decision"]
    assert decision["business_id"] and decision["decision_kind"] == "BRIEF"
    assert decision["decision_identifier"].endswith("-D1")
    assert decision["outcome"] == "ACCEPT_WITH_CONDITIONS" and decision["decision_status"] == "SIGNED"
    assert decision["conditions"] == CONDITIONS and decision["rationale"] == RATIONALE
    assert decision["decided_by_user_id"] == approver_id and decision["decided_by_name"] == "Approver Brief"
    assert decision["decided_under_role"] == "APPROVER" and decision["approval_authority_id"]
    assert decision["brief_version_id"] == brief["id"] and decision["brief_business_id"] == brief["business_id"]
    assert decision["brief_content_hash"] == brief["content_hash"]
    assert decision["evidence_set_hash"] == brief["content"]["context"]["evidence_set_hash"]
    assert decision["ai_execution_refs"] == [case["_execution"]]
    assert [item["action_type"] for item in decision["follow_up_actions"]] == [
        "CAPA_REQUIRED",
        "RISK_REASSESSMENT_REQUIRED",
    ]
    assert decision["investigation_business_id"] == case["business_id"]
    assert record["brief"]["hash_verified"] is True
    verification = approver.get(f"/api/v1/governance/decisions/{decision['id']}/signature-verification").json()
    assert [(item["kind"], item["decision_id"]) for item in verification["signatures"]] == [
        ("CASE_DECISION", decision["id"])
    ]
    # The report names the signer, for the signer too (DEV-024), and for a colleague who reads it.
    assert verification["signatures"][0]["signer_name"] == "Approver Brief"
    viewer, _ = org["viewer"]
    read_by_colleague = viewer.get(f"/api/v1/governance/decisions/{decision['id']}/signature-verification")
    assert read_by_colleague.status_code == 200, read_by_colleague.text
    assert read_by_colleague.json()["signatures"][0]["signer_name"] == "Approver Brief"
    signature = record["signature"]
    assert signature["business_id"] and signature["status"] == "SIGNED"
    assert signature["signer_name"] == "Approver Brief"
    assert signature["signature_meaning"] == (
        f"I, Approver Brief, Authorized Decision Maker, have reviewed Decision Brief {brief['business_id']} version 1 "
        "and decide: Accept with conditions"
    )
    # The rules enforced at signing are read back on the record: approval authority and segregation of duties.
    checks = {item["key"]: item for item in record["verification"]["checks"]}
    assert checks["authority"]["ok"] and checks["authority"]["detail"] == (
        "The signer held approval authority as Authorized Decision Maker when signing"
    )
    assert checks["separation"]["ok"] and checks["separation"]["label"] == "Segregation of duties"
    assert len(signature["fingerprint_full"]) == 64 and "…" in signature["fingerprint"]
    assert record["verification"]["status"] == "VALID"
    assert {item["key"]: item["ok"] for item in record["verification"]["checks"]} == {
        "fingerprint": True,
        "signature": True,
        "brief_hash": True,
        "snapshot": True,
        "authority": True,
        "separation": True,
    }
    assert record["snapshot"]["evidence_set_hash"] == decision["evidence_set_hash"]
    assert record["snapshot"]["scope_version"] == 1
    assert record["supersedes"] is None and record["superseded_by"] is None

    # The follow-ups: the CAPA goes to the case owner (the investigator), the reassessment to the role named.
    follow_ups = {item["action_type"]: item for item in record["follow_ups"]}
    capa, risk = follow_ups["CAPA_REQUIRED"], follow_ups["RISK_REASSESSMENT_REQUIRED"]
    assert capa["business_id"].startswith("FUP") and capa["status"] == "OPEN"
    assert capa["assignee_user_id"] == investigator_id and capa["title"] == f"CAPA required for {case['business_id']}"
    assert capa["due_at"] and capa["task_id"]
    assert risk["assigned_role"] == "RISK_REVIEWER" and risk["assignee_user_id"] is None and risk["title"] == "Reassess"
    tasks = {str(task.id): task for task in _tasks(tenant_id, case["id"], "FOLLOW_UP")}
    for item in (capa, risk):
        task = tasks[item["task_id"]]
        assert task.source_entity_type == "DecisionFollowUp" and str(task.source_entity_id) == item["id"]
        assert task.details["follow_up_id"] == item["id"]
        assert task.details["follow_up_business_id"] == item["business_id"]
        assert task.details["action_type"] == item["action_type"]
    assert str(tasks[capa["task_id"]].assigned_user_id) == investigator_id
    assert tasks[risk["task_id"]].assigned_role == "RISK_REVIEWER"
    # My Work shows the follow-up's business id as the task's source.
    mine = investigator.get("/api/v1/tasks", params={"view": "assigned"}).json()["items"]
    shown = [item for item in mine if item["id"] == capa["task_id"]]
    assert shown and shown[0]["source"]["business_id"] == capa["business_id"]
    assert shown[0]["source"]["label"] == f"Decision follow-up {capa['business_id']}"

    # The case is decided, the decision task completed, the readiness passes, the snapshot is stored.
    assert _case_row(tenant_id, case["id"]).workflow_state == "DECIDED"
    approvals = _tasks(tenant_id, case["id"], "DECISION_APPROVAL")
    assert approvals and all(task.status == "COMPLETED" for task in approvals)
    assert approvals[-1].completion_outcome == "ACCEPT_WITH_CONDITIONS"
    readiness = _readiness(approver, case["id"])
    assert readiness["checks"]["decision"] == "PASS" and readiness["steps"]["human_review"] == "DONE"
    snapshot = _row(tenant_id, ContextSnapshot, decision_id=uuid.UUID(decision["id"]))
    assert snapshot.decision_version == brief["content_hash"]
    assert snapshot.snapshot["brief"]["business_id"] == brief["business_id"]
    assert snapshot.snapshot["signer"] == {"id": approver_id, "role": "APPROVER"}
    stored = _signature(tenant_id, decision["id"])
    assert stored.decision == "ACCEPT_COND" and stored.object_version == brief["content_hash"]
    assert stored.signer_role.upper() == "APPROVER" and stored.remarks == RATIONALE
    assert "CASE_DECISION_SIGNED" in _audit(tenant_id, decision["id"])

    # The governance verification checks the extended material too.
    assert _governance_status(approver, decision["id"]) == "VALID"
    # Changed remarks on the signature: INVALID (both checks), then restored.
    before = _change(tenant_id, SignedApprovalRecord, stored.id, remarks=RATIONALE + " (edited)")
    tampered = approver.get(f"/api/v1/decisions/{decision['id']}/record").json()["verification"]
    assert tampered["status"] == "INVALID"
    assert {item["key"]: item["ok"] for item in tampered["checks"]}["fingerprint"] is False
    assert _governance_status(approver, decision["id"]) == "INVALID"
    _change(tenant_id, SignedApprovalRecord, stored.id, **before)
    # A changed context snapshot: INVALID, then restored.
    before = _change(tenant_id, ContextSnapshot, snapshot.id, snapshot={**snapshot.snapshot, "outcome": "X"})
    tampered = approver.get(f"/api/v1/decisions/{decision['id']}/record").json()["verification"]
    assert tampered["status"] == "INVALID"
    assert {item["key"]: item["ok"] for item in tampered["checks"]}["snapshot"] is False
    assert _governance_status(approver, decision["id"]) == "INVALID"
    _change(tenant_id, ContextSnapshot, snapshot.id, **before)
    assert approver.get(f"/api/v1/decisions/{decision['id']}/record").json()["verification"]["status"] == "VALID"

    # The screen now shows the decision; anyone in the organization reads its record, another organization does not.
    screen = investigator.get(_path(case["id"])).json()
    assert screen["current_decision"]["id"] == decision["id"] and len(screen["decisions"]) == 1
    assert screen["actions"]["supersede_required"] is True
    assert org["viewer"][0].get(f"/api/v1/decisions/{decision['id']}/record").status_code == 200
    assert approver.get(f"/api/v1/decisions/{uuid.uuid4()}/record").status_code == 404
    # A decision on a brief is never signed, reviewed or changed through the legacy endpoints.
    legacy = approver.post(
        f"/api/v1/governance/decisions/{decision['id']}/sign",
        json={"decision": "APPROVE", "remarks": "x", "password": PASSWORD, "object_version": "x"},
    )
    assert legacy.status_code == 409 and _code(legacy) == "DECISION_SIGNED_ON_BRIEF"
    changed = approver.post(
        f"/api/v1/governance/decisions/{decision['id']}/material-change",
        json={"change_summary": "x", "expected_updated_at": "x"},
    )
    assert changed.status_code == 409 and _code(changed) == "DECISION_SIGNED_ON_BRIEF"
    listed = approver.get(f"/api/v1/investigations/{case['id']}/decisions").json()
    assert [item["actions"]["can_sign"] for item in listed if str(item["id"]) == decision["id"]] == [False]


def test_signing_refusals_are_audited(org):
    tenant_id = org["tenant_id"]
    approver3, _ = org["approver3"]
    admin, _ = org["admin"]
    leader, _ = org["leader"]
    investigator, _ = org["investigator"]
    case, brief = _approved(org)
    path = _path(case["id"]) + "/sign"

    wrong = approver3.post(path, json=_body(brief, password="Not the password 1"))
    assert wrong.status_code == 403 and _code(wrong) == "INVALID_REAUTHENTICATION"
    assert "SIGNATURE_REAUTHENTICATION_FAILED" in _audit(tenant_id, case["id"])
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        details = [
            row[0]
            for row in db.query(AuditEvent.details).filter(
                AuditEvent.tenant_id == tenant_id, AuditEvent.entity_id == uuid.UUID(case["id"])
            )
        ]
    assert not any("Not the password" in str(item) for item in details)

    administrator = admin.post(path, json=_body(brief))
    assert administrator.status_code == 403 and _code(administrator) == "ADMINISTRATOR_CANNOT_SIGN"
    assert "ADMINISTRATOR_CANNOT_SIGN" in _audit(tenant_id, case["id"])
    not_authorized = investigator.post(path, json=_body(brief))
    assert not_authorized.status_code == 403 and _code(not_authorized) == "APPROVAL_AUTHORITY_DENIED"

    stale = approver3.post(path, json=_body(brief, brief_content_hash="0" * 64))
    assert stale.status_code == 409 and _code(stale) == "STALE_BRIEF"
    assert "STALE_BRIEF" in _audit(tenant_id, case["id"])
    unknown = approver3.post(path, json=_body(brief, brief_version_id=str(uuid.uuid4())))
    assert unknown.status_code == 404 and _code(unknown) == "BRIEF_VERSION_NOT_FOUND"
    before = _change(tenant_id, DecisionBriefVersion, brief["id"], title="Changed title")  # not in the hash
    assert approver3.get(_path(case["id"])).json()["brief"]["hash_verified"] is True
    _change(tenant_id, DecisionBriefVersion, brief["id"], **before)
    row = _row(tenant_id, DecisionBriefVersion, id=uuid.UUID(brief["id"]))
    before = _change(tenant_id, DecisionBriefVersion, brief["id"], narrative={**row.narrative, "author_notes": "x"})
    tampered = approver3.post(path, json=_body(brief))
    assert tampered.status_code == 409 and _code(tampered) == "BRIEF_TAMPERED"
    assert approver3.get(_path(case["id"])).json()["actions"]["can_sign"] is False
    _change(tenant_id, DecisionBriefVersion, brief["id"], **before)

    invalid = approver3.post(path, json=_body(brief, outcome="CLOSE_NO_FURTHER_ACTION", conditions=CONDITIONS))
    assert invalid.status_code == 422 and _code(invalid) == "DECISION_INVALID"
    assert PASSWORD not in invalid.text  # a refusal never echoes the password
    rejecting = approver3.post(
        path, json=_body(brief, outcome="REJECT_CONCLUSION", follow_ups=[{"action_type": "CAPA_REQUIRED"}])
    )
    assert rejecting.status_code == 422 and _code(rejecting) == "DECISION_INVALID"
    supersede = approver3.post(
        path, json=_body(brief, supersedes_decision_id=str(uuid.uuid4()), supersede_reason=SUPERSEDE_REASON)
    )
    assert supersede.status_code == 409 and _code(supersede) == "SUPERSEDE_NOT_ALLOWED"
    # Nothing was signed.
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        assert db.query(Decision).filter(Decision.investigation_id == uuid.UUID(case["id"])).count() == 0
    assert _case_row(tenant_id, case["id"]).workflow_state == "READY_FOR_DECISION"

    # Whoever wrote the brief never decides on it, even with approval authority.
    own_case, own_brief = _approved(org, "leader")
    own = leader.post(_path(own_case["id"]) + "/sign", json=_body(own_brief))
    assert own.status_code == 403 and _code(own) == "SOD_DENIED"
    assert "SOD_DENIED" in _audit(tenant_id, own_case["id"])
    assert leader.get(_path(own_case["id"])).json()["actions"]["can_sign"] is False


# --------------------------------------------------------------------------------------------------- superseding


def test_a_new_decision_supersedes_the_current_one(org):
    tenant_id = org["tenant_id"]
    approver, _ = org["approver"]
    approver2, _ = org["approver2"]
    case, brief = _approved(org)
    path = _path(case["id"]) + "/sign"
    first = approver.post(path, json=_body(brief))
    assert first.status_code == 200, first.text
    first_id = first.json()["decision"]["id"]

    required = approver2.post(path, json=_body(brief, outcome="CLOSE_NO_FURTHER_ACTION"))
    assert required.status_code == 409 and _code(required) == "SUPERSEDE_REQUIRED"
    wrong = approver2.post(
        path,
        json=_body(
            brief,
            outcome="CLOSE_NO_FURTHER_ACTION",
            supersedes_decision_id=str(uuid.uuid4()),
            supersede_reason=SUPERSEDE_REASON,
        ),
    )
    assert wrong.status_code == 409 and _code(wrong) == "SUPERSEDE_REQUIRED"
    second = approver2.post(
        path,
        json=_body(
            brief, outcome="CLOSE_NO_FURTHER_ACTION", supersedes_decision_id=first_id, supersede_reason=SUPERSEDE_REASON
        ),
    )
    assert second.status_code == 200, second.text
    new = second.json()
    assert new["decision"]["supersedes_decision_id"] == first_id
    assert new["decision"]["decision_identifier"].endswith("-D2")
    assert new["supersedes"]["id"] == first_id and new["supersedes"]["business_id"]
    assert new["verification"]["status"] == "VALID"

    old = _row(tenant_id, Decision, id=uuid.UUID(first_id))
    assert old.decision_status == "SUPERSEDED" and str(old.superseded_by_decision_id) == new["decision"]["id"]
    assert old.supersede_reason == SUPERSEDE_REASON and old.superseded_at is not None
    assert old.outcome == "ACCEPT_CONCLUSION" and old.rationale == RATIONALE  # nothing else changed
    old_record = approver.get(f"/api/v1/decisions/{first_id}/record").json()
    assert old_record["decision"]["decision_status"] == "SUPERSEDED"
    assert old_record["superseded_by"]["id"] == new["decision"]["id"]
    assert old_record["verification"]["status"] == "VALID"  # superseding never breaks the earlier signature
    assert "CASE_DECISION_SUPERSEDED" in _audit(tenant_id, first_id)
    # The case timeline names who superseded it: the signer of the new decision.
    timeline = approver.get(f"/api/v1/investigations/{case['id']}/trust/timeline", params={"page_size": 200})
    assert timeline.status_code == 200, timeline.text
    superseded = next(item for item in timeline.json()["items"] if item["event"] == "CASE_DECISION_SUPERSEDED")
    assert superseded["actor"] is not None and superseded["actor"]["name"] == "Approver2 Brief"

    screen = approver.get(_path(case["id"])).json()
    assert screen["current_decision"]["id"] == new["decision"]["id"]
    assert [item["id"] for item in screen["decisions"]] == [new["decision"]["id"], first_id]
    latest, earlier = screen["decisions"]
    assert (
        latest["status"] == "SIGNED" and latest["supersedes"]["id"] == first_id and latest["supersedes"]["business_id"]
    )
    assert latest["signer_name"] == "Approver2 Brief" and latest["signer_role"] == "APPROVER"
    assert earlier["status"] == "SUPERSEDED" and earlier["superseded_by"]["id"] == new["decision"]["id"]
    assert _case_row(tenant_id, case["id"]).workflow_state == "DECIDED"
    assert _readiness(approver, case["id"])["checks"]["decision"] == "PASS"


# -------------------------------------------------------------------------------------- rejecting and returning


def test_a_rejection_sends_the_brief_back(org):
    tenant_id = org["tenant_id"]
    approver, _ = org["approver"]
    _, investigator_id = org["investigator"]
    case, brief = _approved(org)
    rejected = approver.post(_path(case["id"]) + "/sign", json=_body(brief, outcome="REJECT_CONCLUSION"))
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["decision"]["outcome"] == "REJECT_CONCLUSION"
    assert rejected.json()["follow_ups"] == []
    assert _case_row(tenant_id, case["id"]).workflow_state == "IN_PROGRESS"
    assert _row(tenant_id, DecisionBriefVersion, id=uuid.UUID(brief["id"])).status == "RETURNED"
    returns = [task for task in _tasks(tenant_id, case["id"], "FOLLOW_UP") if task.is_return]
    assert returns and str(returns[-1].assigned_user_id) == investigator_id
    assert returns[-1].source_entity_type == "DecisionBriefVersion" and returns[-1].details["comment"] == RATIONALE
    approvals = _tasks(tenant_id, case["id"], "DECISION_APPROVAL")
    assert approvals[-1].status == "COMPLETED" and approvals[-1].completion_outcome == "REJECT_CONCLUSION"
    readiness = _readiness(approver, case["id"])
    assert readiness["checks"]["decision"] == "PENDING" and readiness["steps"]["human_review"] == "IN_PROGRESS"


def test_returning_the_brief_without_a_signature(org):
    tenant_id = org["tenant_id"]
    approver, _ = org["approver"]
    investigator, investigator_id = org["investigator"]
    case, brief = _approved(org)
    path = _path(case["id"]) + "/return"
    body = {"brief_version_id": brief["id"], "comment": RETURN_COMMENT}

    refused = investigator.post(path, json=body)
    assert refused.status_code == 403 and _code(refused) == "PERMISSION_DENIED"
    assert approver.post(path, json={**body, "comment": "short"}).status_code == 422
    returned = approver.post(path, json=body)
    assert returned.status_code == 200, returned.text
    assert returned.json()["brief"]["status"] == "RETURNED"
    assert returned.json()["actions"]["can_sign"] is False

    assert _row(tenant_id, DecisionBriefVersion, id=uuid.UUID(brief["id"])).status == "RETURNED"
    action = _row(tenant_id, BriefReviewAction, brief_version_id=uuid.UUID(brief["id"]), action="RETURN_FOR_ANALYSIS")
    assert action.comment == "Returned by the decision maker: " + RETURN_COMMENT
    assert _case_row(tenant_id, case["id"]).workflow_state == "IN_PROGRESS"
    returns = [task for task in _tasks(tenant_id, case["id"], "FOLLOW_UP") if task.is_return]
    assert returns and str(returns[-1].assigned_user_id) == investigator_id
    approvals = _tasks(tenant_id, case["id"], "DECISION_APPROVAL")
    assert approvals[-1].status == "COMPLETED" and approvals[-1].completion_outcome == "RETURNED"
    assert "CASE_DECISION_RETURNED" in _audit(tenant_id, case["id"])
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        assert db.query(Decision).filter(Decision.investigation_id == uuid.UUID(case["id"])).count() == 0
        assert (
            db.query(DecisionFollowUp).filter(DecisionFollowUp.investigation_id == uuid.UUID(case["id"])).count() == 0
        )
    again = approver.post(path, json=body)
    assert again.status_code == 409 and _code(again) == "STALE_BRIEF"


# ----------------------------------------------------------------------------------------------------- legacy


def test_legacy_signing_and_verification_are_unchanged(org):
    tenant_id = org["tenant_id"]
    approver, _ = org["approver"]
    case, _ = _approved(org)
    now = datetime.now(timezone.utc)
    legacy = Decision(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        investigation_id=uuid.UUID(case["id"]),
        decision_identifier=f"LEGACY-{uuid.uuid4().hex[:8]}",
        decision_type="INVESTIGATION_REVIEW",
        disposition="REQUIRES_REVIEW",
        rationale="Legacy decision",
        decision_status="REQUIRES_REVIEW",
        authorized_by_ref=f"creator-{uuid.uuid4().hex[:8]}@example.com",
        updated_at=now,
        decision_timestamp=now,
        created_at=now,
    )
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.add(legacy)
        db.commit()
        legacy_id = str(legacy.id)
        version = legacy.updated_at.isoformat()
    assert _row(tenant_id, Decision, id=uuid.UUID(legacy_id)).decision_kind == "LEGACY"
    signed = approver.post(
        f"/api/v1/governance/decisions/{legacy_id}/sign",
        json={"decision": "APPROVE", "remarks": "Reviewed", "password": PASSWORD, "object_version": version},
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["status"] == "APPROVED"
    record = _row(tenant_id, SignedApprovalRecord, object_id=uuid.UUID(legacy_id))
    assert record.decision_type == "INVESTIGATION_REVIEW" and record.decision == "APPROVE"
    assert _governance_status(approver, legacy_id) == "VALID"
    before = _change(tenant_id, SignedApprovalRecord, record.id, remarks="Changed")
    assert _governance_status(approver, legacy_id) == "INVALID"
    _change(tenant_id, SignedApprovalRecord, record.id, **before)
    assert _governance_status(approver, legacy_id) == "VALID"
    # A legacy decision has no record on the human decision screen; it is counted there.
    assert approver.get(f"/api/v1/decisions/{legacy_id}/record").status_code == 404
    assert approver.get(_path(case["id"])).json()["legacy_decision_count"] == 1
