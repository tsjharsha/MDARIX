"""B7 step 3: Resolve and close through the API on the trial's routine sample complaint (RT-08, 10, 25, 26, 27; B7-D1,
D4, D5, D6): one signature, two signed records; customer told and the problem code required; the event owner taken
over only when ticked; a new failure mode answered as known behaviour; Complete closes and reopens with a reason;
Connect never closes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from backend.app.db.models.complaint_disposition import ComplaintDisposition
from backend.app.db.models.foundation import AuditEvent, Complaint, SignedApprovalRecord
from backend.app.db.models.oversight import EventClosure
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from tests.test_complaint_disposition_api import _acknowledge
from tests.test_free_trial import PASSWORD, _approved_trial_client

pytestmark = pytest.mark.db

RECORD = {
    "troubleshooting": "Alarm check and filter inspection over the phone with the therapist.",
    "correction_type": "USER_INSTRUCTED",
    "correction": "User instructed to re-seat the filter in its housing.",
    "result": "Alarm cleared, device in use.",
    "service_ticket": "",
    "no_investigation_reason": "USE_RELATED_INSTRUCTED",
    "device_returned": "NOT_NEEDED",
}


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        rt01 = (
            db.query(Complaint.id)
            .filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == "SAMPLE-RT-01")
            .scalar()
        )
    try:
        yield {"user": user, "tenant_id": tenant_id, "rt01": str(rt01)}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:resolve-cleanup")


def _url(complaint_id: str, tail: str = "/resolve-and-close") -> str:
    return f"/api/v1/complaints/{complaint_id}{tail}"


def _body(view: dict, **extra) -> dict:
    disposition = view["disposition"]
    classification = disposition["classification"]
    body = {
        "problem_code": view["prefill"]["problem_code"] or "B7_NEW_MODE",
        "service_record": RECORD,
        "attribution": "USE_RELATED",
        "classification": {
            key: classification[key]
            for key in ("use_environment", "use_environment_text", "user_type", "user_type_text")
        },
        "customer_told": {"how": "PHONE", "note": "Told the therapist the alarm cause and the fix."},
        "seen_triggers": disposition["trigger_codes"],
        "seen_version": disposition["version"],
        "opened_at": disposition["opened_at"],
        "password": PASSWORD,
    }
    body.update(extra)
    return body


def _actions(tenant_id, *actions) -> list:
    with SessionLocal() as db:
        bind_system(db, "test: the audit trail")
        return [
            (row.action, row.details)
            for row in db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action.in_(actions))
            .order_by(AuditEvent.created_at)
        ]


def _closure(tenant_id, complaint_id) -> EventClosure | None:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return db.query(EventClosure).filter(EventClosure.complaint_id == uuid.UUID(complaint_id)).one_or_none()


def test_rt08_one_signature_writes_two_records_and_closes_in_complete(trial):
    user, rt01, tenant_id = trial["user"], trial["rt01"], trial["tenant_id"]
    view = user.get(_url(rt01)).json()
    assert view["mode"] == "COMPLETE" and view["button"] == "Resolve and close"
    assert view["offer"]["full"] is True, view["offer"]
    assert view["prefill"]["correction_type"] in ("USER_INSTRUCTED", "PART_REPLACED", "SETTING_CORRECTED")
    assert "NO_FAULT_FOUND" in view["disposition"]["corrections"]
    _acknowledge(user)

    # Customer told and the problem code are never skipped (spec 2.2 rule 8; RT-08).
    untold = user.post(_url(rt01), json=_body(view, customer_told={}))
    assert untold.status_code == 422 and untold.json()["detail"]["code"] == "CUSTOMER_TOLD_REQUIRED"
    uncoded = user.post(_url(rt01), json=_body(view, problem_code=""))
    assert uncoded.status_code == 422 and uncoded.json()["detail"]["code"] == "PROBLEM_CODE_REQUIRED"

    # A new problem code on the product is a new failure mode: refused until seen, then answered as known behaviour.
    fresh = user.post(_url(rt01), json=_body(view, problem_code="B7_NEW_MODE"))
    assert fresh.status_code == 409 and fresh.json()["detail"]["code"] == "TRIGGER_MET_SINCE_OPENED"
    seen = [*view["disposition"]["trigger_codes"], "NEW_FAILURE_MODE"]
    escalates = user.post(_url(rt01), json=_body(view, problem_code="B7_NEW_MODE", seen_triggers=seen))
    assert escalates.status_code == 422, escalates.text

    # Someone else owns the event: signing asks to take it over first.
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.add(
            EventClosure(
                tenant_id=tenant_id,
                complaint_id=uuid.UUID(rt01),
                owner_id="someone-else",
                version=0,
                updated_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    owned = user.post(_url(rt01), json=_body(view, problem_code="B7_NEW_MODE", seen_triggers=seen))
    assert owned.status_code == 409 and owned.json()["detail"]["code"] == "OWNER_TAKE_OVER"

    signed = user.post(
        _url(rt01),
        json=_body(
            view,
            problem_code="B7_NEW_MODE",
            seen_triggers=seen,
            known_behaviour_ref="IFU-PW-12 section 7.3",
            take_over=True,
        ),
    )
    assert signed.status_code == 200, signed.text
    after = signed.json()
    assert after["closed"] is True and after["owner"]["is_me"] is True

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        complaint = db.get(Complaint, uuid.UUID(rt01))
        assert complaint.status == "closed" and complaint.problem_code == "B7_NEW_MODE"
        disposition = (
            db.query(ComplaintDisposition)
            .filter(ComplaintDisposition.complaint_id == complaint.id, ComplaintDisposition.superseded_by.is_(None))
            .one()
        )
        assert disposition.branch == "SERVICE_LEVEL" and disposition.service_record["customer_told"]["how"] == "PHONE"
        assert disposition.answers["TRIGGER"]["known_behaviour"] == "IFU-PW-12 section 7.3"
        row = db.query(EventClosure).filter(EventClosure.complaint_id == complaint.id).one()
        assert row.ready_state == "READY" and row.closed_by == row.signed_by and row.closed_at is not None
        told = next(item for item in row.checklist if item["code"] == "CUSTOMER_TOLD")
        assert told["result"] == "PASS"
        bind_system(db, "test: the two signed records")
        records = {
            record.decision_type: record
            for record in db.query(SignedApprovalRecord).filter(
                SignedApprovalRecord.id.in_([disposition.signed_record_id, row.signed_record_id])
            )
        }
    assert set(records) == {"COMPLAINT_DISPOSITION", "EVENT_READY_TO_CLOSE"}
    assert "close the complaint in MDARIX" in records["EVENT_READY_TO_CLOSE"].signature_meaning
    assert records["COMPLAINT_DISPOSITION"].signer_user_id == records["EVENT_READY_TO_CLOSE"].signer_user_id
    actions = [
        action for action, _ in _actions(tenant_id, "PROBLEM_CODE_SET", "EVENT_OWNER_TAKEN_OVER", "COMPLAINT_CLOSED")
    ]
    assert actions == ["PROBLEM_CODE_SET", "EVENT_OWNER_TAKEN_OVER", "COMPLAINT_CLOSED"]

    again = user.post(_url(rt01), json=_body(after))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "ALREADY_CLOSED"


def test_rt26_reopen_needs_a_reason_and_supersedes_the_closure(trial):
    user, rt01, tenant_id = trial["user"], trial["rt01"], trial["tenant_id"]
    short = user.post(_url(rt01, "/reopen"), json={"reason": "new info"})
    assert short.status_code == 422
    reopened = user.post(_url(rt01, "/reopen"), json={"reason": "The reporter called back: the alarm returned twice."})
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["closed"] is False
    row = _closure(tenant_id, rt01)
    assert row.closed_at is None and row.ready_state is None and row.reopen_reason.startswith("The reporter")
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        assert db.get(Complaint, uuid.UUID(rt01)).status == "open"
    assert [action for action, _ in _actions(tenant_id, "COMPLAINT_REOPENED")] == ["COMPLAINT_REOPENED"]
    twice = user.post(_url(rt01, "/reopen"), json={"reason": "The reporter called back: the alarm returned twice."})
    assert twice.status_code == 409


def test_rt25_connect_marks_ready_to_close_and_never_closes(trial):
    user, rt01, tenant_id = trial["user"], trial["rt01"], trial["tenant_id"]
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.get(Complaint, uuid.UUID(rt01)).record_owner = "EXTERNAL"
        db.commit()
    view = user.get(_url(rt01)).json()
    assert view["mode"] == "CONNECT" and view["button"] == "Resolve and mark ready to close in your QMS"
    assert view["problem_code_read_only"] is True
    body = _body(
        view,
        problem_code="SOMETHING_ELSE",
        customer_told={"qms_letter_id": "QMS-LTR-0042"},
        known_behaviour_ref="IFU-PW-12 section 7.3",
        change_reason="Reopened after the reporter called back; resolved again.",
    )
    signed = user.post(_url(rt01), json=body)
    assert signed.status_code == 200, signed.text
    assert signed.json()["closed"] is False
    row = _closure(tenant_id, rt01)
    assert row.ready_state == "READY" and row.closed_at is None
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        complaint = db.get(Complaint, uuid.UUID(rt01))
        assert complaint.status == "open" and complaint.problem_code == "B7_NEW_MODE"  # read only in Connect
    assert (
        user.post(_url(rt01, "/reopen"), json={"reason": "The QMS owns it; it reopens there, not here."}).status_code
        == 409
    )


def test_rt27_not_possible_needs_the_reason(trial):
    user, rt01 = trial["user"], trial["rt01"]
    view = user.get(_url(rt01)).json()
    refused = user.post(_url(rt01), json=_body(view, customer_told={"how": "NOT_POSSIBLE"}))
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "CUSTOMER_TOLD_REQUIRED"
