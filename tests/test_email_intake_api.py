"""B7b step 10: "E-mail to check", Make it a case / Add to case / Not a case, the raw view, the purge, the address
settings and the switch (EM-03, EM-12, EM-15, purge after 30 days, B7-D9 sample, off by default)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.models.foundation import AuditEvent
from backend.app.db.models.intake import CaseAttachment, InboundMessage, IntakeEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.mail_in import processing, receiver
from backend.app.mail_in import router as mail_router
from tests.test_free_trial import _approved_trial_client
from tests.test_intake_triage_api import INTAKE, _ok
from tests.test_mail_processing import eml

# B6b B3: scenarios this file verifies (its register row names it, or it is the group's own test file).
pytestmark = [pytest.mark.db, pytest.mark.requirement("EM-01", "EM-02", "EM-05", "EM-07", "EM-08", "EM-17", "EM-18")]
API = "/api/v1/email-intake"


@pytest.fixture(scope="module")
def org():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:email-intake-cleanup")


@pytest.fixture(autouse=True)
def switched_on(monkeypatch, tmp_path):
    monkeypatch.setenv("MDARIX_EMAIL_INTAKE", "on")
    monkeypatch.setenv("MDARIX_OBJECT_STORAGE_ROOT", str(tmp_path))
    for name in ("MDARIX_CLAMD_HOST", "MDARIX_MALWARE_SCANNER_COMMAND"):
        monkeypatch.delenv(name, raising=False)


def _received(org, content: bytes) -> str:
    row_id = receiver.store(org["tenant_id"], content, "nurse@hospital.example", datetime.now(timezone.utc))
    with SessionLocal() as control:
        bind_system(control, "test:email-intake")
        processing.process(control, {"tenant_id": str(org["tenant_id"]), "message_id": str(row_id)})
        control.commit()
    return str(row_id)


def _audits(tenant_id, entity_id) -> list[str]:
    with SessionLocal() as db:
        bind_system(db, "test:email-intake")
        return [
            row.action
            for row in db.query(AuditEvent).filter(
                AuditEvent.tenant_id == tenant_id, AuditEvent.entity_id == uuid.UUID(entity_id)
            )
        ]


def test_switched_off_no_route_and_no_screen(org, monkeypatch):
    monkeypatch.delenv("MDARIX_EMAIL_INTAKE", raising=False)
    assert org["user"].get(f"{API}/messages").status_code == 404
    assert org["user"].get(f"{API}/settings").status_code == 404
    from backend.app import mail_in

    assert mail_in.enabled() is False


def test_a_trial_sees_the_sample_email_and_no_real_address(org):
    items = _ok(org["user"].get(f"{API}/messages"))["items"]
    sample = next(item for item in items if item["sample"])
    assert sample["from_domain"] == "citycare-hospital.example" and sample["sender_verified"] is False
    assert sample["identifiers"]["serial"]["text"] == "PW-20931" and sample["fault_words"]
    assert "CityCare Hospital (SAMPLE" not in sample["words"]  # signature cut
    again = _ok(org["user"].get(f"{API}/messages"))["items"]
    assert sum(1 for item in again if item["sample"]) == 1
    settings = org["user"].get(f"{API}/settings")
    if settings.status_code == 200:
        assert settings.json()["trial"] is True and settings.json()["address"] is None
        refused = org["user"].put(f"{API}/settings", json={"on": True})
        assert refused.status_code == 409 and refused.json()["detail"]["code"] == "TRIAL_NO_ADDRESS"
    else:
        assert settings.status_code == 403


def test_em03_make_it_a_case_carries_channel_message_id_receipt_time_and_files(org):
    message_id = _received(
        org,
        eml("The PulseWatch alarm failed during a check.", attachments=[("log.txt", b"E42 09:40", "text", "plain")]),
    )
    with SessionLocal() as db:
        bind_system(db, "test:email-intake")
        message = db.get(InboundMessage, uuid.UUID(message_id))
        received_at, raw_id = message.received_at, message.message_id
    case = _ok(
        org["user"].post(
            INTAKE,
            json={
                "kind": "CONTACT",
                "reporter_words": "The PulseWatch alarm failed during a check.",
                "inbound_message_id": message_id,
                "channel": "PHONE",
                "received_at": "2020-01-01T10:00",
            },
        )
    )
    with SessionLocal() as db:
        bind_system(db, "test:email-intake")
        event = db.get(IntakeEvent, uuid.UUID(case["id"]))
        assert event.channel == "EMAIL" and event.channel_ref == raw_id and event.received_at == received_at
        message = db.get(InboundMessage, uuid.UUID(message_id))
        assert message.state == "MADE_CASE" and message.intake_event_id == event.id and message.purge_after is None
        files = db.query(CaseAttachment).filter(CaseAttachment.intake_event_id == event.id).all()
        assert [item.filename_masked for item in files] == ["log.txt"]
    twice = org["user"].post(
        INTAKE, json={"kind": "CONTACT", "reporter_words": "Second try at the same", "inbound_message_id": message_id}
    )
    assert twice.status_code == 409


def test_add_to_case_makes_an_email_addendum(org):
    case = _ok(org["user"].post(INTAKE, json={"kind": "CONTACT", "reporter_words": "Display flickered on start"}))
    message_id = _received(org, eml("A photo of the screen is attached now.", subject=f"Re: {case['reference']}"))
    listed = {item["id"]: item for item in _ok(org["user"].get(f"{API}/messages"))["items"]}
    assert listed[message_id]["add_to_case"]["id"] == case["id"]
    detail = _ok(org["user"].post(f"{API}/messages/{message_id}/add-to-case", json={"case_id": case["id"]}))
    assert any(item.get("kind") == "EMAIL" for item in detail.get("addenda", [])), detail.get("addenda")
    assert "EMAIL_ADDED_TO_CASE" in _audits(org["tenant_id"], message_id)


def test_em12_not_a_case_on_a_fault_word_needs_a_quality_reviewer(org, monkeypatch):
    message_id = _received(org, eml("The pump stopped and gave an error alarm twice."))
    monkeypatch.setattr(mail_router, "effective_permissions", lambda *args: {"case.log"})
    refused = org["user"].post(f"{API}/messages/{message_id}/not-a-case", json={"reason": "SPAM"})
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "QUALITY_REVIEWER_NEEDED"
    assert "EMAIL_NOT_A_CASE_REFUSED" in _audits(org["tenant_id"], message_id)
    monkeypatch.setattr(mail_router, "effective_permissions", lambda *args: {"quality.review"})
    done = _ok(org["user"].post(f"{API}/messages/{message_id}/not-a-case", json={"reason": "DUPLICATE"}))
    assert done["state"] == "NOT_A_CASE" and done["reason"] == "DUPLICATE"


def test_em12_the_reviewer_who_opened_it_does_not_dismiss_it_outside_a_trial(org, monkeypatch):
    from backend.app.signer_training import router as training

    message_id = _received(org, eml("The pump stopped and gave an error alarm twice."))
    _ok(org["user"].get(f"{API}/messages"))  # the first to see it is the one who opened it
    with SessionLocal() as db:
        bind_system(db, "test:email-intake")
        assert db.get(InboundMessage, uuid.UUID(message_id)).flags["opened_by"]
    monkeypatch.setattr(mail_router, "effective_permissions", lambda *args: {"quality.review"})
    real = training.is_trial
    monkeypatch.setattr(training, "is_trial", lambda *args: False)
    refused = org["user"].post(f"{API}/messages/{message_id}/not-a-case", json={"reason": "SPAM"})
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "SAME_PERSON"
    assert "EMAIL_NOT_A_CASE_REFUSED" in _audits(org["tenant_id"], message_id)
    monkeypatch.setattr(training, "is_trial", real)  # in a trial the one reviewer may decide (spec 4.4 step 6)
    done = _ok(org["user"].post(f"{API}/messages/{message_id}/not-a-case", json={"reason": "SPAM"}))
    assert done["state"] == "NOT_A_CASE"


def test_em15_the_raw_view_is_need_to_know_and_audited(org, monkeypatch):
    from backend.app.access import permissions

    message_id = _received(org, eml("Please call me back about the monitor."))
    monkeypatch.setattr(permissions, "effective_roles", lambda *args: ["EXECUTIVE"])
    assert org["user"].get(f"{API}/messages/{message_id}/raw").status_code == 403
    monkeypatch.setattr(permissions, "effective_roles", lambda *args: ["SERVICE_DESK"])
    opened = org["user"].get(f"{API}/messages/{message_id}/raw")
    assert opened.status_code == 200 and b"Please call me back" in opened.content
    actions = _audits(org["tenant_id"], message_id)
    assert "EMAIL_RAW_REFUSED" in actions and "EMAIL_RAW_OPENED" in actions


def test_not_a_case_is_purged_after_30_days(org):
    message_id = _received(
        org, eml("Out of office.", Auto_Submitted="auto-replied", attachments=[("a.txt", b"note", "text", "plain")])
    )
    with SessionLocal() as db:
        bind_system(db, "test:email-intake")
        row = db.get(InboundMessage, uuid.UUID(message_id))
        assert row.state == "NOT_A_CASE"
        assert mail_router.purge_expired(db, org["tenant_id"], datetime.now(timezone.utc)) == 0 or row.state != "PURGED"
        row.purge_after = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.flush()
        assert mail_router.purge_expired(db, org["tenant_id"], datetime.now(timezone.utc)) >= 1
        db.commit()
        row = db.get(InboundMessage, uuid.UUID(message_id))
        assert row.state == "PURGED" and row.raw_object_key is None
        assert db.query(CaseAttachment).filter(CaseAttachment.inbound_message_id == row.id).count() == 0
