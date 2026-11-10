"""B7 step 11 (spec 5): the opt-in urgent e-mail alert (UA-01..04; UA-05 by a Case escalated with a death)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.intake import service as intake
from backend.app.oversight import urgent_alert
from tests.test_free_trial import _approved_trial_client
from tests.test_intake_triage_api import INTAKE, _all_no, _ok, _sign

pytestmark = pytest.mark.db
SETTINGS = "/api/v1/oversight/settings/alerts-and-files"
WORDS = "The patient died after the pump stopped during the infusion at the ward"


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:urgent-alert-cleanup")


def _events(tenant_id, subject_id, name=urgent_alert.ALERT) -> list[OutboxEvent]:
    with SessionLocal() as db:
        bind_system(db, "test:urgent-alert")
        rows = (
            db.query(OutboxEvent)
            .filter(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.event_name == name,
                OutboxEvent.aggregate_id == uuid.UUID(str(subject_id)),
            )
            .all()
        )
        db.expunge_all()
        return rows


def _urgent(user) -> dict:
    return _ok(user.post(INTAKE, json={"kind": "URGENT", "reporter_words": WORDS}))


def test_opted_out_sends_nothing(trial):  # UA-02
    case = _urgent(trial["user"])
    assert _events(trial["tenant_id"], case["id"]) == []


def test_opted_in_the_email_goes_at_once_with_no_patient_data(trial, monkeypatch):  # UA-01, UA-03
    from auth import emailer

    user, tenant_id = trial["user"], trial["tenant_id"]
    assert _ok(user.put(SETTINGS, json={"urgent_email": True}))["urgent_email"] is True
    case = _urgent(user)
    queued = _events(tenant_id, case["id"])
    assert queued and all(set(event.payload) >= {"user_id", "reference", "received_at"} for event in queued)
    assert WORDS not in str([event.payload for event in queued])  # identifiers only in the outbox
    sent = []
    monkeypatch.setattr(emailer, "_send", lambda recipient, message, **_: sent.append((recipient, message)) or "SENT")
    from backend.app.notifications import NotificationFailed, handle_event

    with SessionLocal() as db:
        bind_system(db, "test:urgent-alert")
        assert handle_event(db, queued[0].event_name, dict(queued[0].payload)) is True
    recipient, message = sent[0]
    assert message.subject == "MDARIX: urgent case received"
    assert case["reference"] in message.paragraphs[0] and "died" not in str(message)
    # UA-03: an SMTP failure is a failed event the worker retries; the same item never queues a second e-mail.

    def broken(*_args, **_kwargs):
        raise emailer.EmailDeliveryError("smtp down")

    monkeypatch.setattr(emailer, "_send", broken)
    with SessionLocal() as db:
        bind_system(db, "test:urgent-alert")
        with pytest.raises(NotificationFailed):
            handle_event(db, queued[0].event_name, {**queued[0].payload, "sent": []})
        assert (
            urgent_alert.queue(
                db,
                db,
                tenant_id,
                reference=case["reference"],
                subject_id=uuid.UUID(case["id"]),
                received_at=None,
                actor="test",
            )
            == 0
        )


def test_an_overdue_acknowledgement_gets_one_reminder(trial):  # UA-04
    user, tenant_id = trial["user"], trial["tenant_id"]
    _ok(user.put(SETTINGS, json={"urgent_email": True}))
    case = _urgent(user)
    later = intake.now_utc() + timedelta(hours=3)
    with SessionLocal() as db:
        bind_system(db, "test:urgent-alert")
        db.info.clear()  # the triage list's memo
        first = urgent_alert.remind_overdue(db, db, tenant_id, later)
        db.commit()
        db.info.clear()
        again = urgent_alert.remind_overdue(db, db, tenant_id, later + timedelta(minutes=5))
        db.commit()
    assert first >= 1 and again == 0
    assert len(_events(tenant_id, case["id"], urgent_alert.REMINDER)) >= 1


def test_a_case_escalated_with_a_death_sends_the_alert(trial):  # spec 5: any death on the fast track
    user, tenant_id = trial["user"], trial["tenant_id"]
    _ok(user.put(SETTINGS, json={"urgent_email": True}))
    event = _ok(
        user.post(
            INTAKE, json={"kind": "CONTACT", "reporter_words": WORDS, "answers": _all_no(Q3="YES", Q4="YES", Q5="YES")}
        )
    )
    _ok(_sign(user, event, "COMPLAINT"))
    assert _events(tenant_id, event["id"])
