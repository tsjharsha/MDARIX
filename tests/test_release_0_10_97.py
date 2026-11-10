"""0.10.97 (B7a): a trial made before it gets SAMPLE-RT-03's reply in the communications log once, so the
customer-told closure check is met on day 0 (backend/app/trial/sample_0_10_97.py); the signed disposition stays as
signed."""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.models.complaint_disposition import ComplaintDisposition
from backend.app.db.models.foundation import Complaint
from backend.app.db.models.guides_communications import CommunicationEntry
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db


def _told(db, complaint) -> str:
    from backend.app.oversight import closure

    items = closure.checklist(closure.facts(db, complaint.tenant_id, complaint))
    return next(item["result"] for item in items if item["code"] == "CUSTOMER_TOLD")


def test_a_trial_made_before_0_10_97_gets_rt03_s_reply_once():
    from backend.app.oversight import closure
    from backend.app.trial import sample_0_10_97
    from backend.app.trial.retention import purge_trial

    _, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            rt03 = db.query(Complaint).filter_by(complaint_identifier="SAMPLE-RT-03").one()
            assert sample_0_10_97.refresh(db, tenant_id, apply=False) == 0  # a new trial signs it with the record
            assert _told(db, rt03) != closure.BLOCKED
            # As a trial made before 0.10.97 had it: the disposition signed without customer told, nothing in the log.
            signed = db.query(ComplaintDisposition).filter_by(complaint_id=rt03.id).one()
            record = {key: value for key, value in signed.service_record.items() if key != "customer_told"}
            signed.service_record = record
            db.commit()
            assert _told(db, rt03) == closure.BLOCKED
            assert sample_0_10_97.refresh(db, tenant_id, apply=False) == 1
            assert db.query(CommunicationEntry).filter_by(complaint_id=rt03.id).count() == 0  # the dry run adds none
            assert sample_0_10_97.refresh(db, tenant_id, apply=True) == 1
            db.commit()
            assert sample_0_10_97.refresh(db, tenant_id, apply=True) == 0  # idempotent
            reply = db.query(CommunicationEntry).filter_by(complaint_id=rt03.id).one()
            assert (reply.direction, reply.purpose, reply.status) == ("SENT", "RESPONSE", "CLOSED")
            assert reply.occurred_at == signed.signed_at and reply.logged_by == signed.signed_by
            assert _told(db, rt03) != closure.BLOCKED
            db.refresh(signed)
            assert signed.service_record == record  # the signed record is never edited
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:0.10.97-cleanup")
