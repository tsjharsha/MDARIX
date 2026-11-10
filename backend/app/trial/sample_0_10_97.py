"""Release 0.10.97's sample correction for trials made before it (scripts/refresh_trial_story.py), idempotent.

B7 checks that the customer was told before a complaint closes (closure check CUSTOMER_TOLD). A new trial's
SAMPLE-RT-03 disposition records it (sample_dispositions.py); one signed before 0.10.97 does not, so the check would
show open on day 0. The signed record is never edited: the sample gets the reply the distributor gave, in the
communications log (Sent, Response, at the disposition's signed time, by its signer), to the complaint's reporter. The
caller commits.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.trial.sample_data import SAMPLE_SOURCE

COMPLAINT = "SAMPLE-RT-03"
REPORTER = "Reporter of SAMPLE-RT-03 (hospital biomedical engineer, fictional)"
NOTE = "Sample: the distributor told the hospital the cause and the fix."


def _owed(db: Session, tenant_id):
    """(complaint, its signed disposition) when RT-03's customer told is neither signed nor in the log, else None."""
    from backend.app.db.models.complaint_disposition import ComplaintDisposition
    from backend.app.db.models.foundation import Complaint
    from backend.app.oversight.closure import responses

    complaint = (
        db.query(Complaint)
        .filter(
            Complaint.tenant_id == tenant_id,
            Complaint.complaint_identifier == COMPLAINT,
            Complaint.source_system == SAMPLE_SOURCE,
        )
        .one_or_none()
    )
    if complaint is None:
        return None
    signed = (
        db.query(ComplaintDisposition)
        .filter(
            ComplaintDisposition.tenant_id == tenant_id,
            ComplaintDisposition.complaint_id == complaint.id,
            ComplaintDisposition.signed_at.isnot(None),
        )
        .order_by(ComplaintDisposition.version.desc())
        .first()
    )
    if signed is None or (signed.service_record or {}).get("customer_told"):
        return None
    if responses(db, tenant_id, [complaint.id]).get(complaint.id):
        return None
    return complaint, signed


def refresh(db: Session, tenant_id, apply: bool, now: datetime | None = None) -> int:
    """1 when RT-03 still needs its sample reply in the communications log; with ``apply`` it gets it (flushed)."""
    from backend.app.communications import rules, service
    from backend.app.db.models.guides_communications import ExternalParty
    from backend.app.trial.sample_guides import _party

    owed = _owed(db, tenant_id)
    if owed is None:
        return 0
    if not apply:
        return 1
    complaint, signed = owed
    at, by = signed.signed_at, signed.signed_by
    reporter = (
        db.query(ExternalParty)
        .filter(
            ExternalParty.tenant_id == tenant_id,
            ExternalParty.complaint_id == complaint.id,
            ExternalParty.party_type == rules.REPORTER,
        )
        .order_by(ExternalParty.created_at)
        .first()
    ) or _party(db, tenant_id, rules.REPORTER, REPORTER, by, at, complaint)
    service.record(
        db,
        tenant_id,
        complaint=complaint,
        party=reporter,
        direction=rules.SENT,
        purpose=rules.RESPONSE,
        subject=f"Resolution of {COMPLAINT}",
        note=NOTE,
        channel="OTHER",  # through the distributor (resolve.TOLD_CHANNELS)
        occurred_at=at,
        actor=by,
        now=at,
        source_system=SAMPLE_SOURCE,
    )
    return 1
