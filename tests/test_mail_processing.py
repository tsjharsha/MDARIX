"""B7b step 9: what the worker does with a received e-mail (EM-02-09, 11, 13, 17). Messages are built here as .eml
bytes and kept through the receiver's own store(); no SMTP, no real mail."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import pytest

from backend.app.db.models.foundation import Product
from backend.app.db.models.intake import CaseAttachment, InboundMessage
from backend.app.db.models.oversight import DueAlert, OversightSettings
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.mail_in import processing, receiver
from tests.test_free_trial import _approved_trial_client
from tests.test_intake_triage_api import INTAKE, _ok

# B6b B3: scenarios this file verifies (its register row names it, or it is the group's own test file).
pytestmark = [pytest.mark.db, pytest.mark.requirement("EM-01", "EM-02", "EM-05", "EM-07", "EM-08", "EM-17", "EM-18")]


@pytest.fixture(scope="module")
def org():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:mail-processing-cleanup")


@pytest.fixture(autouse=True)
def storage(monkeypatch, tmp_path):
    monkeypatch.setenv("MDARIX_OBJECT_STORAGE_ROOT", str(tmp_path))
    for name in ("MDARIX_CLAMD_HOST", "MDARIX_MALWARE_SCANNER_COMMAND"):
        monkeypatch.delenv(name, raising=False)  # the built-in check: an executable or a script is refused


def eml(
    body: str,
    subject: str = "Pump alarm",
    attachments=(),
    sender: str = "Ward Nurse <nurse@hospital.example>",
    **headers,
) -> bytes:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "cases-test@intake.mdarix.com"
    message["Subject"] = subject
    message["Message-ID"] = f"<{uuid.uuid4().hex}@hospital.example>"
    for name, value in headers.items():
        message[name.replace("_", "-")] = value
    message.set_content(body)
    for name, content, maintype, subtype in attachments:
        message.add_attachment(content, maintype=maintype, subtype=subtype, filename=name)
    return message.as_bytes()


def received(org, content: bytes, sender: str = "nurse@hospital.example") -> InboundMessage:
    row_id = receiver.store(org["tenant_id"], content, sender, datetime.now(timezone.utc))
    with SessionLocal() as control:
        bind_system(control, "test:mail-processing")
        processing.process(control, {"tenant_id": str(org["tenant_id"]), "message_id": str(row_id)})
        control.commit()
    with SessionLocal() as db:
        bind_system(db, "test:mail-processing")
        return db.get(InboundMessage, row_id)


def _files(row) -> list[CaseAttachment]:
    with SessionLocal() as db:
        bind_system(db, "test:mail-processing")
        return db.query(CaseAttachment).filter(CaseAttachment.inbound_message_id == row.id).all()


def test_em02_a_normal_mail_becomes_a_masked_draft_received_at_server_time(org):
    with SessionLocal() as db:
        bind_system(db, "test:mail-processing")
        product = db.query(Product).filter(Product.tenant_id == org["tenant_id"]).first()
    name = product.name if product else "PulseWatch"
    row = received(
        org,
        eml(
            f"Our {name} stopped during a check. Serial number: SN-44812. UDI (01)00812345678906. "
            "Call me on +91 98765 43210.\n-- \nWard Nurse, City Hospital",
            subject="Pump stopped, call +91 98765 43210",
        ),
    )
    assert row.state == "NEW" and row.flags["checked"] is True
    assert row.from_domain == "hospital.example"
    assert "98765" not in (row.subject_masked or "") and "98765" not in row.draft["words"]
    assert "City Hospital" not in row.draft["words"]  # the signature block is cut
    ids = row.draft["identifiers"]
    assert ids["serial"]["text"] == "SN-44812" and ids["udi"]["text"] == "(01)00812345678906"
    assert all(value["status"] == "UNCONFIRMED" and value["source"] == "EMAIL" for value in ids.values())
    if product:
        assert ids["product"]["id"] == str(product.id)
    assert row.flags["fault_words"] and not row.flags["harm_words"]


def test_em06_the_same_words_again_show_a_possible_duplicate(org):
    first = received(org, eml("The display froze twice during the night shift on ward 4."))
    second = received(org, eml("The display froze twice during the night shift on ward 4."))
    assert second.flags["possible_duplicate"]["id"] == str(first.id)


def test_em07_em08_an_infected_file_is_never_stored_others_refused_with_the_reason(org, monkeypatch):
    from backend.app import stage3_workflow_router

    monkeypatch.setattr(stage3_workflow_router, "MAX_ATTACHMENT_BYTES", 40)
    row = received(
        org,
        eml(
            "Photos and the log attached.",
            attachments=[
                ("log.txt", b"Error 42 at 09:40", "text", "plain"),
                ("run.txt", b"#!/bin/sh\nrm -rf /", "text", "plain"),
                ("archive.zip", b"PK\x03\x04", "application", "zip"),
                ("big.txt", b"x" * 100, "text", "plain"),
            ],
        ),
    )
    files = {item.filename_masked: item for item in _files(row)}
    assert files["log.txt"].usable and files["log.txt"].object_key
    assert files["run.txt"].unusable_reason == "Refused: virus found" and files["run.txt"].object_key is None
    assert files["archive.zip"].unusable_reason == "Refused: this type of file is not accepted"
    assert files["big.txt"].unusable_reason == "Refused: larger than 10 MB"
    from object_storage.service import ObjectStorageService

    raw = ObjectStorageService().get(str(org["tenant_id"]), row.raw_object_key)
    assert b"rm -rf" not in raw and b"virus found" in raw and row.raw_object_key.endswith("-clean")
    assert {item["file_name"] for item in row.attachments} == set(files)


def test_em09_an_auto_reply_goes_to_not_a_case_kept_30_days(org):
    row = received(org, eml("I am out of the office until Monday.", Auto_Submitted="auto-replied"))
    assert row.state == "NOT_A_CASE" and row.reason == "AUTO_REPLY"
    assert row.purge_after - row.received_at == timedelta(days=30)
    bounce = received(org, eml("Delivery failed."), sender="")
    assert bounce.state == "NOT_A_CASE"


def test_em04_a_reply_to_a_case_is_offered_as_an_addendum(org):
    case = _ok(org["user"].post(INTAKE, json={"kind": "CONTACT", "reporter_words": "Display flickered on start"}))
    by_subject = received(org, eml("One more photo.", subject=f"Re: {case['reference']} display"))
    assert by_subject.flags["add_to_case"]["reference"] == case["reference"]
    with SessionLocal() as db:
        bind_system(db, "test:mail-processing")
        db.query(InboundMessage).filter(InboundMessage.id == by_subject.id).update(
            {"intake_event_id": uuid.UUID(case["id"]), "state": "ADDED_TO_CASE"}
        )
        db.commit()
    reply = received(org, eml("It happened again today.", subject="Re: hello", In_Reply_To=by_subject.message_id))
    assert reply.flags["add_to_case"]["id"] == case["id"] and reply.state == "NEW"


def test_em11_death_words_raise_the_alert_at_once(org):
    with SessionLocal() as db:
        bind_system(db, "test:mail-processing")
        settings = db.query(OversightSettings).filter(OversightSettings.tenant_id == org["tenant_id"]).first()
        if settings is None:
            settings = OversightSettings(tenant_id=org["tenant_id"])
            db.add(settings)
        settings.urgent_email = True
        db.commit()
    row = received(org, eml("The patient died after the pump stopped."))
    assert row.flags["harm_words"]
    with SessionLocal() as db:
        bind_system(db, "test:mail-processing")
        alerts = db.query(DueAlert).filter(
            DueAlert.tenant_id == org["tenant_id"], DueAlert.item_key == f"mail:{row.id}"
        )
        assert alerts.count() >= 1
        queued = db.query(OutboxEvent).filter(
            OutboxEvent.event_name == "URGENT_CASE_ALERT", OutboxEvent.aggregate_id == row.id
        )
        assert queued.count() >= 1


def test_em13_em17_non_english_flagged_and_a_forwarded_earlier_date_offered(org):
    row = received(
        org,
        eml(
            "---------- Forwarded message ---------\nDate: Mon, 2 Nov 2026 09:00:00 +0000\n"
            "Die Pumpe hat gestern zweimal ohne Grund angehalten und einen Alarm gegeben."
        ),
    )
    assert row.flags["may_not_be_english"] is True
    assert row.header_dates == ["2026-11-02T09:00:00+00:00"]


def test_a_known_site_of_the_sender_domain_is_only_suggested(org):
    from backend.app.db.models.guides_communications import ExternalParty

    words = "The display froze twice during the morning round."
    domain, other = f"site-{uuid.uuid4().hex[:8]}.example", f"lab-{uuid.uuid4().hex[:8]}.example"
    assert received(org, eml(words, sender=f"Desk <desk@{domain}>")).draft["site"] is None  # nothing known yet
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_system(db, "test:mail-processing")
        db.add(
            ExternalParty(
                tenant_id=org["tenant_id"],
                party_type="HOSPITAL",
                name="Northgate Clinic (SAMPLE)",
                contact_email=f"Biomed@{domain.upper()}",
                created_by="test",
                created_at=now,
                updated_by="test",
                updated_at=now,
            )
        )
        db.commit()
    known = received(org, eml(words + " Again.", sender=f"Desk <desk@{domain}>"))
    assert known.draft["site"] == {
        "text": "Northgate Clinic (SAMPLE)",
        "status": "UNCONFIRMED",
        "source": "EMAIL_DOMAIN",
    }
    # A site typed on an earlier Case made from an e-mail of the same domain.
    case = _ok(
        org["user"].post(
            INTAKE, json={"kind": "CONTACT", "reporter_words": "Screen went dark", "reporter_site": "Eastside Lab"}
        )
    )
    first = received(org, eml("Screen went dark on the analyser.", sender=f"Lab <lab@{other}>"))
    with SessionLocal() as db:
        bind_system(db, "test:mail-processing")
        db.query(InboundMessage).filter(InboundMessage.id == first.id).update(
            {"intake_event_id": uuid.UUID(case["id"]), "state": "MADE_CASE"}
        )
        db.commit()
    assert received(org, eml("It went dark again.", sender=f"Lab <lab@{other}>")).draft["site"]["text"] == (
        "Eastside Lab"
    )
    # A personal mail provider's domain is many unrelated senders: no suggestion.
    assert received(org, eml("Alarm again tonight.", sender="Someone <someone@gmail.com>")).draft["site"] is None


def test_an_encrypted_mail_cannot_be_read(org):
    row = received(org, eml("-----BEGIN PGP MESSAGE-----\nhQEMA\n-----END PGP MESSAGE-----"))
    assert row.flags["encrypted"] is True and row.draft["note"] == "Cannot be read: encrypted"
