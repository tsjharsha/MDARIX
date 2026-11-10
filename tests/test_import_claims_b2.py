"""0.10.93 (B2) import leftovers: IN-14, a QMS ID two complaints claim is set aside (spec 3.3, step 2 of the merge).

The row is neither merged into one of the claimants nor made a third complaint; it is set aside with "Two complaints
claim QMS ID X: reconcile them", and both claimants stay as they were.
"""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.models.foundation import Complaint
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_free_trial import _approved_trial_client
from tests.test_intake_triage_api import INTAKE, _all_no, _ok, _sign, _upload

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:import-claims-cleanup")


def _escalated(user, words: str) -> dict:
    event = _ok(user.post(INTAKE, json={"kind": "CONTACT", "reporter_words": words, "answers": _all_no(Q3="YES")}))
    return _ok(_sign(user, event, "COMPLAINT"))


def test_a_qms_id_two_complaints_claim_is_set_aside_never_merged_or_duplicated(trial):  # IN-14
    user, tenant_id = trial["user"], trial["tenant_id"]
    from backend.app.db.models.intake import IntakeEvent

    first = _escalated(user, "Caller says the infusion pump stopped mid-dose twice this week.")
    second = _escalated(user, "Caller says the infusion pump alarm sounded with no occlusion present.")
    # One complaint holds the QMS ID; another's Case had it typed (the unique index allows one complaint per ID).
    with SessionLocal() as db:
        bind_system(db, "test:import-claims")
        db.get(Complaint, uuid.UUID(first["complaint_id"])).qms_ref = "QMS-777"
        db.get(IntakeEvent, uuid.UUID(second["id"])).qms_ref = "QMS-777"
        db.commit()
    result = _upload(
        user,
        "complaint_id,product_id,product_name,description\n"
        "QMS-777,CLM-PUMP,Claim Pump,Pump stopped mid-dose\n"
        "QMS-778,CLM-PUMP,Claim Pump,Display flickered once\n",
    )
    assert result["rejected_rows"] == 1
    assert "Two complaints claim QMS ID QMS-777: reconcile them" in str(result), result
    with SessionLocal() as db:
        bind_system(db, "test:import-claims")
        identifiers = {
            row.complaint_identifier
            for row in db.query(Complaint).filter(
                Complaint.tenant_id == tenant_id, Complaint.complaint_identifier.in_(["QMS-777", "QMS-778"])
            )
        }
        assert identifiers == {"QMS-778"}  # the other row imports; no third complaint for QMS-777
        for complaint_id in (first["complaint_id"], second["complaint_id"]):
            kept = db.get(Complaint, uuid.UUID(complaint_id))
            assert kept.last_synced_at is None and kept.record_owner != "EXTERNAL"
            assert kept.description.startswith("Caller says")  # neither claimant was overwritten
