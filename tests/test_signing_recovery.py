"""DEV-07 (0.10.86): signing on a dedicated plane is a recoverable state machine (backend/app/signing_commit.py).

A dedicated plane is simulated with a second session on the test database: the decision and its receipt are in one
transaction, the signature and the control audit trail in another, exactly as with two databases. Failures are
injected at every durable step: the record not saved, a crash after the PENDING signature, a crash after the record
is saved, the last step failing, and a crash after everything committed but before the response. Each ends with one
decision and one valid signature, or with nothing signed, never a signature without its decision or a PENDING one
shown as valid; a retry of the same request returns the same decision. The shared plane is covered, unchanged, by
tests/test_human_decision.py."""

from __future__ import annotations

import pytest
from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app import signing_commit
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import AuditEvent, Decision, SignedApprovalRecord
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from backend.app.main import app
from backend.app.request_context import get_request_context
# org: the fixture of test_human_decision (hence the F811 notes below).
from tests.test_human_decision import _approved, _body, _governance_status, _path, org  # noqa: F401

pytestmark = pytest.mark.db


class Injected(RuntimeError):
    """A failure the test injects."""


@pytest.fixture
def dedicated(monkeypatch):
    """Requests get their business data in a session of their own (a dedicated plane); ``fail`` makes the next
    data-plane commit, or one durable step of signing_commit, fail once."""
    plan = {"commit": False, "step": None, "settle": False}

    class DataPlane(Session):
        def commit(self):
            if plan["commit"]:
                plan["commit"] = False
                raise Injected("the data plane went away")
            super().commit()

    def data_plane(ctx=Depends(get_request_context)):
        db = DataPlane(bind=SessionLocal.kw["bind"], autoflush=SessionLocal.kw.get("autoflush", True))
        bind_tenant(db, ctx.tenant_id)
        try:
            yield db
        finally:
            db.close()

    def reached(step):
        if plan["step"] == step:
            plan["step"] = None
            raise Injected(f"crashed after {step}")

    real_settle = signing_commit.settle

    def settle(control_db, data, signature_id):
        if plan["settle"]:
            plan["settle"] = False
            raise Injected("the control database went away")
        return real_settle(control_db, data, signature_id)

    monkeypatch.setattr(signing_commit, "_reached", reached)
    monkeypatch.setattr(signing_commit, "settle", settle)
    app.dependency_overrides[get_data_plane_db] = data_plane
    try:
        yield plan
    finally:
        app.dependency_overrides.pop(get_data_plane_db, None)


def _state(tenant_id, case_id) -> dict:
    """The case's decisions, their signatures and the signing audit events (actions), as stored."""
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        decisions = db.query(Decision).filter(Decision.tenant_id == tenant_id, Decision.investigation_id == case_id)
        ids = [row.id for row in decisions]
        signatures = (
            db.query(SignedApprovalRecord)
            .filter(SignedApprovalRecord.tenant_id == tenant_id, SignedApprovalRecord.object_id.in_(ids or [None]))
            .all()
        )
        actions = [
            row.action
            for row in db.query(AuditEvent.action).filter(
                AuditEvent.tenant_id == tenant_id,
                AuditEvent.action == "CASE_DECISION_SIGNED",
                AuditEvent.entity_id.in_(ids or [None]),
            )
        ]
        return {"decisions": ids, "signatures": [row.status for row in signatures], "signed_events": actions}


def _abandoned(tenant_id, since_ids: set) -> list[dict]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return [
            row.details
            for row in db.query(AuditEvent).filter(
                AuditEvent.tenant_id == tenant_id, AuditEvent.action == signing_commit.ABANDONED
            )
            if row.id not in since_ids
        ]


def _audit_ids(tenant_id) -> set:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return {row[0] for row in db.query(AuditEvent.id).filter(AuditEvent.tenant_id == tenant_id)}


def _orphans(tenant_id) -> list:
    """Signatures of decisions that do not exist."""
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        decisions = {row[0] for row in db.query(Decision.id).filter(Decision.tenant_id == tenant_id)}
        return [
            row.id
            for row in db.query(SignedApprovalRecord).filter(
                SignedApprovalRecord.tenant_id == tenant_id, SignedApprovalRecord.object_type == "Decision"
            )
            if row.object_id not in decisions
        ]


def _settle_all() -> dict:
    with SessionLocal() as db:
        return signing_commit.settle_pending(db, older_than=signing_commit.timedelta(0))


def test_the_decision_not_saved_leaves_no_signature_and_the_person_signs_again(org, dedicated):  # noqa: F811
    tenant_id = org["tenant_id"]
    approver, _ = org["approver"]
    case, brief = _approved(org)
    before = _audit_ids(tenant_id)
    dedicated["commit"] = True
    with pytest.raises(Injected):
        approver.post(_path(case["id"]) + "/sign", json=_body(brief))
    # Before 0.10.86 the signature (and "decision signed") stayed in the control plane without its decision.
    assert _state(tenant_id, case["id"])["decisions"] == [] and _orphans(tenant_id) == []
    (abandoned,) = _abandoned(tenant_id, before)
    assert abandoned["decision"] and abandoned["fingerprint"]
    again = approver.post(_path(case["id"]) + "/sign", json=_body(brief))
    assert again.status_code == 200, again.text
    state = _state(tenant_id, case["id"])
    assert len(state["decisions"]) == 1 and state["signatures"] == ["SIGNED"]
    assert state["signed_events"] == ["CASE_DECISION_SIGNED"]
    assert _governance_status(approver, again.json()["decision"]["id"]) == "VALID"


def test_a_crash_after_the_pending_signature_is_abandoned_on_recovery(org, dedicated):  # noqa: F811
    tenant_id = org["tenant_id"]
    approver, _ = org["approver"]
    case, brief = _approved(org)
    dedicated["step"] = "pending"
    with pytest.raises(Injected):
        approver.post(_path(case["id"]) + "/sign", json=_body(brief))
    # The process "died": a PENDING signature, no decision. After a restart the settlement job abandons it.
    assert _state(tenant_id, case["id"])["decisions"] == [] and len(_orphans(tenant_id)) == 1
    outcome = _settle_all()
    assert outcome["settled"].get("ABANDONED", 0) >= 1 and outcome["failed"] == []
    assert _orphans(tenant_id) == []
    assert approver.post(_path(case["id"]) + "/sign", json=_body(brief)).status_code == 200
    assert _state(tenant_id, case["id"])["signatures"] == ["SIGNED"]


def test_a_crash_after_the_decision_is_saved_is_completed_on_recovery_never_valid_before(org, dedicated):  # noqa: F811
    tenant_id = org["tenant_id"]
    approver, _ = org["approver"]
    case, brief = _approved(org)
    dedicated["step"] = "saved"
    with pytest.raises(Injected):
        approver.post(_path(case["id"]) + "/sign", json=_body(brief))
    state = _state(tenant_id, case["id"])
    assert len(state["decisions"]) == 1 and state["signatures"] == [signing_commit.PENDING]
    assert state["signed_events"] == []  # nothing says "signed" yet
    decision_id = str(state["decisions"][0])
    assert _governance_status(approver, decision_id) != "VALID"  # a PENDING signature is never shown as valid
    outcome = _settle_all()
    assert outcome["settled"].get("SIGNED", 0) >= 1
    state = _state(tenant_id, case["id"])
    assert state["signatures"] == ["SIGNED"] and state["signed_events"] == ["CASE_DECISION_SIGNED"]
    assert _governance_status(approver, decision_id) == "VALID"
    assert _settle_all()["settled"].get("SIGNED", 0) == 0  # settling again changes nothing


def test_the_last_step_failing_answers_incomplete_and_a_read_or_a_retry_completes_it_once(org, dedicated):  # noqa: F811
    tenant_id = org["tenant_id"]
    approver, _ = org["approver"]
    case, brief = _approved(org)
    dedicated["settle"] = True
    response = approver.post(_path(case["id"]) + "/sign", json=_body(brief))
    assert response.status_code == 503 and response.json()["detail"]["code"] == "SIGNING_INCOMPLETE"
    (decision_id,) = _state(tenant_id, case["id"])["decisions"]
    # Reading the signed record completes it.
    record = approver.get(f"/api/v1/decisions/{decision_id}/record")
    assert record.status_code == 200, record.text
    assert record.json()["verification"]["status"] == "VALID"
    # The person retries the very same request (the answer was lost): the same decision, not a second one.
    again = approver.post(_path(case["id"]) + "/sign", json=_body(brief))
    assert again.status_code == 200 and again.json()["decision"]["id"] == str(decision_id)
    state = _state(tenant_id, case["id"])
    assert len(state["decisions"]) == 1 and state["signatures"] == ["SIGNED"]
    assert state["signed_events"] == ["CASE_DECISION_SIGNED"]


def test_a_crash_after_everything_committed_is_answered_by_a_retry_with_that_decision(org, dedicated):  # noqa: F811
    tenant_id = org["tenant_id"]
    approver, _ = org["approver"]
    case, brief = _approved(org)
    dedicated["step"] = "signed"
    with pytest.raises(Injected):
        approver.post(_path(case["id"]) + "/sign", json=_body(brief))
    (decision_id,) = _state(tenant_id, case["id"])["decisions"]
    again = approver.post(_path(case["id"]) + "/sign", json=_body(brief))
    assert again.status_code == 200 and again.json()["decision"]["id"] == str(decision_id)
    # A retry still proves the person: a wrong password is refused, and does not touch the decision.
    wrong = approver.post(_path(case["id"]) + "/sign", json=_body(brief, password="not-the-password-1"))
    assert wrong.status_code in (401, 403), wrong.text
    # Another request (a different rationale) is not a retry: the case is decided, it is refused as before.
    other = approver.post(_path(case["id"]) + "/sign", json=_body(brief, rationale="Another rationale for the same"))
    assert other.status_code == 409, other.text
    state = _state(tenant_id, case["id"])
    assert len(state["decisions"]) == 1 and state["signatures"] == ["SIGNED"]
    assert state["signed_events"] == ["CASE_DECISION_SIGNED"]


@pytest.mark.unit
def test_the_signing_states_are_documented_where_the_code_is():
    doc = signing_commit.__doc__
    for state in ("PREPARE", "PENDING", "SAVED", "SIGNED", "SIGNATURE_ABANDONED", "signature-settlement"):
        assert state in doc, state


def test_the_settlement_job_is_scheduled():
    from backend.app.scheduler import JOBS

    assert "signature-settlement" in {job.name for job in JOBS}
    with SessionLocal() as db:
        bind_system(db, "test")
        assert signing_commit.settle_pending(db)["failed"] == []
