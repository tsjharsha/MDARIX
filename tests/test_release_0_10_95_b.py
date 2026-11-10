"""Hardening 0.10.95, run 2 (code-audit fixes 13-20) against the database."""

from __future__ import annotations

import uuid

import pytest

from auth import emailer
from backend.app import import_quarantine, notifications
from backend.app.db.models.ingestion import ImportQuarantineRow
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from backend.app.trial import imports
from outbox.worker import OutboxWorker
from tests.test_customer_admin_account_security import _tenant
from tests.test_evidence_workflow import PDF, _case, _internal, _unknown, org  # noqa: F401 (org is a fixture)
from tests.test_notifications_delivery import _user

pytestmark = pytest.mark.db

# Two set-aside rows per template that share the first column and differ in the rest of the record's identity.
SAME_FIRST_COLUMN = {
    "products": [
        {"product_id": "P-1", "product_name": "Pump", "version": "Rev C"},
        {"product_id": "P-1", "product_name": "Pump", "version": "Rev D"},
    ],
    "bom": [
        {"product_id": "P-1", "version": "Rev D", "component_id": "C-1"},
        {"product_id": "P-1", "version": "Rev D", "component_id": "C-2"},
    ],
    "lot_genealogy": [
        {"lot_id": "L-1", "component_id": "C-1", "component_lot_id": "K-1"},
        {"lot_id": "L-1", "component_id": "C-1", "component_lot_id": "K-2"},
    ],
    "distribution": [
        {
            "lot_id": "L-1",
            "consignee": "Lakeside Hospital",
            "country": "IE",
            "quantity": "x",
            "ship_date": "2026-07-28",
        },
        {
            "lot_id": "L-1",
            "consignee": "Lakeside Hospital",
            "country": "IE",
            "quantity": "x",
            "ship_date": "2026-08-02",
        },
    ],
}


@pytest.fixture(scope="module")
def tenant_id():
    with SessionLocal() as db:
        bind_system(db, "test: hardening run 2")
        tenant = _tenant(db, "H95B")
        db.commit()
        return tenant.id


@pytest.mark.parametrize("entity", sorted(SAME_FIRST_COLUMN))
def test_a_later_import_closes_only_the_set_aside_row_of_the_record_it_wrote(tenant_id, entity):  # audit 13
    fixed, other = SAME_FIRST_COLUMN[entity]
    source = imports.WORKSPACE_POLICY.source
    columns = imports.identity_columns(entity)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        ref = uuid.uuid4()
        import_quarantine.store(
            db, tenant_id, ref, entity, source, [(2, fixed, ["x"]), (3, other, ["x"])], imports.stored_value
        )
        db.flush()
        closed = import_quarantine.close_fixed(
            db, tenant_id, entity, columns, {import_quarantine.record_identity(fixed, columns)}, set(), "test", source
        )
        stored = {item.line: item for item in db.query(ImportQuarantineRow).filter_by(import_ref=ref)}
        assert closed == [str(stored[2].id)]
        assert (stored[2].status, stored[3].status) == ("REPROCESSED", "OPEN")
        db.rollback()


def test_a_retry_after_one_refused_address_emails_only_that_address(tenant_id, monkeypatch):  # audit 14
    sent, refuse = [], {"on": True}
    with SessionLocal() as db:
        bind_system(db, "test: one refused address")
        good, bad = _user(db, tenant_id, "APPROVER").username, _user(db, tenant_id, "APPROVER").username
        event_id = notifications.notify_review_pending(db, tenant_id, decision_id=uuid.uuid4()).id
        db.commit()

    def send(recipient, **_):
        if recipient == bad and refuse["on"]:
            raise emailer.EmailDeliveryError("mailbox refused")
        sent.append(recipient)
        return "SENT"

    def publisher(name, payload):
        with SessionLocal() as db:
            bind_system(db, "test: deliver")
            assert notifications.handle_event(db, name, payload)

    monkeypatch.setattr(emailer, "send_review_pending_notice", send)
    worker, stats = OutboxWorker(publisher), {"published": 0, "failed": 0, "dead_lettered": 0}
    with SessionLocal() as db:
        bind_system(db, "test: worker")
        worker._deliver_one(db, event_id, stats)
        row = db.get(OutboxEvent, event_id)
        assert stats["failed"] == 1 and sent == [good]
        assert "@" not in str(row.payload), "the queue never holds an email address"
        row.next_attempt_at, refuse["on"] = None, False  # the retry is due, the mailbox accepts now
        db.commit()
        worker._deliver_one(db, event_id, stats)
        assert stats["published"] == 1 and sent == [good, bad]


def test_an_upload_over_the_storage_quota_is_refused_with_413_not_500(org, monkeypatch):  # noqa: F811 (audit 15)
    requester, colleague = org["investigator"][0], org["colleague"]
    case = _case(org)
    made = _internal(
        case["id"], requester, recipient_user_id=colleague[1], unknown_id=_unknown(org["tenant_id"], case["id"])["id"]
    )
    base = f"/api/v1/evidence-requests/{made.json()['id']}"
    assert colleague[0].post(f"{base}/acknowledge").status_code == 200
    monkeypatch.setenv("MDARIX_OBJECT_STORAGE_TENANT_QUOTA_BYTES", "4")
    refused = colleague[0].post(f"{base}/attachments", files={"file": ("batch-record.pdf", PDF, "application/pdf")})
    assert refused.status_code == 413, refused.text
    assert refused.json()["detail"]["code"] == "TENANT_STORAGE_QUOTA_EXCEEDED"
