"""Release 0.10.96's sample correction for trials made before it (scripts/refresh_trial_story.py), idempotent.

SAMPLE-RV-09's US report becomes FDA-valid, as a new trial's is (sample_reports.py): a practice report number, the
IMDRF codes with their FDA codes, the sample's US manufacturer with its e-mail (held in memory, never stored),
and B4 and G8 as Send for approval fills them. Its approved snapshot is frozen again at the same moment, now with its
eMDR file (XML, eSubmitter-layout PDF, official form), and the sample approver's record is re-recorded on the new
fingerprint, as 0.10.72 did for the sample guide. A report that still cannot carry a file (the IMDRF release or FDA's
mapping not loaded) is left exactly as it was. The caller commits.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.trial.sample_data import SAMPLE_SOURCE

# Typed before 0.10.96 (filled from the record or at Send now), and the problem code, confirmed again as suggested.
TYPED = ("MFR_REPORT", "B4", "D3", "G1", "G8", "H6_PROBLEM")


def _owed(db: Session, tenant_id) -> list[tuple]:
    """(report, its approved snapshot) for each sample US report approved without an eMDR file."""
    from backend.app.db.models.authority_reports import ReportObligation, ReportSnapshot

    out = []
    for obligation in db.query(ReportObligation).filter(
        ReportObligation.tenant_id == tenant_id,
        ReportObligation.source_system == SAMPLE_SOURCE,
        ReportObligation.form_code == "FDA_3500A",
    ):
        snapshot = (
            db.query(ReportSnapshot)
            .filter(
                ReportSnapshot.tenant_id == tenant_id,
                ReportSnapshot.obligation_id == obligation.id,
                ReportSnapshot.state == "APPROVED",
            )
            .order_by(ReportSnapshot.version.desc())
            .first()
        )
        if snapshot is not None and "emdr_xml" not in (snapshot.fields or {}):
            out.append((obligation, snapshot))
    return out


def refresh(db: Session, tenant_id, apply: bool, now: datetime | None = None, control_db: Session | None = None) -> int:
    """How many sample reports 0.10.96 gives an eMDR file; with ``apply`` they get it (the caller commits)."""
    from backend.app.authority_reports import forms, router, worksheet
    from backend.app.db.models.foundation import SignedApprovalRecord
    from backend.app.human_decision.rules import signature_hash
    from backend.app.trial.sample_reports import US_ENTRIES, _coded, _entries, _freeze_us

    owed = _owed(db, tenant_id)
    if not apply:
        return len(owed)
    control_db = control_db or db
    done = 0
    for obligation, snapshot in owed:
        before, updated = obligation.entries, obligation.updated_at
        author, at = obligation.created_by, snapshot.requested_at
        kept = {key: value for key, value in (before or {}).items() if key not in TYPED}
        number = _entries({"MFR_REPORT": US_ENTRIES["MFR_REPORT"]}, author, at - timedelta(hours=1))
        obligation.entries = {**kept, **number, **_coded(db, control_db, obligation, author, at)}
        obligation.entries = worksheet.confirm_suggestions(
            forms.FDA_3500A, router._context(db, control_db, obligation), obligation.entries, author, at.isoformat()
        )
        fresh = _freeze_us(db, control_db, obligation, author, at)
        if "emdr_xml" in fresh.fields:
            snapshot.fields, snapshot.content_fingerprint = fresh.fields, fresh.content_fingerprint
            record = db.get(SignedApprovalRecord, snapshot.signed_record_id) if snapshot.signed_record_id else None
            if record is not None:
                record.content_fingerprint = snapshot.content_fingerprint
                record.signature_hash = signature_hash(
                    snapshot.content_fingerprint, record.signer_user_id, str(snapshot.version)
                )
            done += 1
        else:
            obligation.entries = before  # no file can be made here: the report stays exactly as it was
        db.delete(fresh)
        obligation.updated_at = updated
        db.flush()
    return done
