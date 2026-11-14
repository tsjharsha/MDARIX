"""0.10.93 (B2 step 8, spec 9.2): the Cases backfill lists what it would change and writes nothing."""

from __future__ import annotations

import importlib.util
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cases_0_10_93.py"


def _script():
    spec = importlib.util.spec_from_file_location("cases_0_10_93", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check(classification=None, signed=True, review=None):
    return SimpleNamespace(
        classification=classification, signed_at=datetime.now(timezone.utc) if signed else None, review_outcome=review
    )


@pytest.mark.unit
def test_the_state_is_read_from_the_latest_check():
    state = _script().state_for
    assert state(None, False) == "OPEN"
    assert state(_check("COMPLAINT", signed=False), True) == "OPEN"
    assert state(_check("PENDING"), False) == "PENDING"
    assert state(_check("PENDING_CONFIRM"), False) == "PENDING"
    assert state(_check("SERVICE_ONLY"), False) == "IN_REVIEW"
    assert state(_check("INQUIRY", review="AGREED"), False) == "CLOSED"
    assert state(_check("BOTH"), True) == "ESCALATED"
    assert state(_check("SERVICE_ONLY", review="RECLASSIFIED"), True) == "ESCALATED"
    # OD-3: a signed complaint with no complaint is escalated by the upgrade (None: no state of its own).
    assert state(_check("COMPLAINT"), False) is None
    assert state(_check("COMPLAINT"), False, voided=True) == "VOIDED"


@pytest.mark.unit
def test_a_country_becomes_its_code_or_is_kept_to_confirm():
    change = _script().country_change
    assert change("United States") == ("US", None)
    assert change("de") == ("DE", None)
    assert change("US") is None
    assert change("") is None
    assert change("Atlantis") == (None, "Atlantis")


@pytest.mark.unit
def test_counts_mode_prints_counts_only(capsys):
    """For the read-only production run: numbered trials and counts per kind of change, never a trial's key or
    name, a Case reference, the person who logged it or the country text someone typed."""
    script = _script()
    change = script.Change
    lines = [
        change(
            'CALL-0007: channel -> PHONE ("Phone", was kind CONTACT)', "Case channel set to PHONE from its old kind"
        ),
        change("CALL-0007: country 'Lakeside, near the clinic' kept as text", "Case country kept as text"),
        change("CALL-0007: owner -> person@example.org (who logged it)", "Case owner set to who logged it"),
        change("3 CUSTOMER_UPLOAD complaint(s): record owner -> EXTERNAL", "complaint record owner set", 3),
    ]
    found = [("acme-medical", "Acme Medical Devices Pvt Ltd", lines), ("other-org", "Other Org", [])]
    script.print_counts(found)
    out = capsys.readouterr().out
    for private in ("CALL-0007", "person@example.org", "Lakeside", "acme-medical", "Acme Medical", "Other Org"):
        assert private not in out
    assert "Trial 1 of 2: records to change" in out
    assert "Trial 2 of 2: no change" in out
    assert "     3  complaint record owner set" in out
    assert "     1  Case owner set to who logged it" in out


@pytest.mark.db
def test_the_list_names_the_changes_and_writes_nothing():
    from backend.app.db.models.intake import IntakeEvent
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.trial.retention import purge_trial
    from tests.test_free_trial import _approved_trial_client

    _user, approval, _email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        # The sample's calls as a 0.10.92 trial holds them: tr19's defaults, nothing backfilled.
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            for event in db.query(IntakeEvent).filter(IntakeEvent.tenant_id == tenant_id):
                event.status, event.channel, event.owner_id, event.complaint_id = "OPEN", None, None, None
            db.commit()
            before = {
                row.reference: (row.status, row.channel, row.owner_id, row.complaint_id, row.country)
                for row in db.query(IntakeEvent).filter(IntakeEvent.tenant_id == tenant_id)
            }
            lines = _script().plan_tenant(db, tenant_id)
            db.rollback()
        text = "\n".join(lines)
        assert "SAMPLE-CALL-01: channel -> PHONE" in text
        assert "SAMPLE-CALL-01: state OPEN -> IN_REVIEW" in text
        assert "SAMPLE-CALL-02: country 'Germany' -> DE" in text
        assert "SAMPLE-CASE-11: owner -> " in text  # unsigned, still open: the person who logged it
        assert "SAMPLE-CASE-11: state" not in text  # unsigned stays OPEN
        assert "SAMPLE-CALL-02: signed complaint, no complaint: left for a person to escalate" in text
        assert "ESCALATED by the upgrade" not in text  # the sample is never escalated here
        # --counts: the same changes as counts, with no Case reference or person in the kinds.
        found = _script().counts(lines)
        assert found["Case channel set to PHONE from its old kind"] >= 1
        assert found["Case country set to its code"] >= 1
        assert sum(found.values()) >= len(lines)
        assert not any("SAMPLE-" in kind or "@" in kind for kind in found)
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            after = {
                row.reference: (row.status, row.channel, row.owner_id, row.complaint_id, row.country)
                for row in db.query(IntakeEvent).filter(IntakeEvent.tenant_id == tenant_id)
            }
        assert after == before
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:cases-0-10-93-cleanup")
