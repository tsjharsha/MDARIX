"""Release 0.10.77's sample corrections for trials made before it (scripts/refresh_trial_story.py), idempotent.

- **The sample's IMDRF links**, checked against IMDRF's own Release 2026 workbook (data/code_lists): each sample
  problem code now links to the most specific Annex A term that says what the complaint says, of release 2026
  (sample_imports.SAMPLE_IMDRF_LINKS; before, the level-1 headings A14 and A16 and, for SPO2_READING_HIGH, A0908, of
  release 2025). The link rows are re-recorded in place, still approved by the sample reviewer.
- **The sample's prepared reports keep the codes they were approved with.** From 0.10.77 a mapped code is a suggestion
  the regulatory manager confirms; a sample report frozen before the upgrade (SAMPLE-RV-09's 3500A, accepted) gets
  its code fields recorded as confirmed by the sample author, with the value its approved snapshot holds, so the
  report reads as it was filed. Its health effect codes, needed on an initial 3500A from 0.10.77, read as the sample
  author entered them in eSubmitter (as its conclusion code does).

The caller commits.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.trial.sample_data import SAMPLE_SOURCE
from backend.app.trial.sample_imports import (
    EARLIER_IMDRF_LINKS,
    PROBLEM_CODES,
    SAMPLE_ACTOR,
    SAMPLE_IMDRF_RELEASE,
)
from backend.app.trial.sample_reports import US_ENTRIES

US_SAMPLE_HEALTH_EFFECTS = {key: US_ENTRIES[key] for key in ("H6_CLINICAL", "H6_IMPACT")}


def _old_links(db: Session, tenant_id) -> list:
    from backend.app.db.models.regulatory_reference import ImdrfCodeMapping

    rows = db.query(ImdrfCodeMapping).filter(
        ImdrfCodeMapping.tenant_id == tenant_id,
        ImdrfCodeMapping.customer_system == PROBLEM_CODES,
        ImdrfCodeMapping.proposed_by == SAMPLE_ACTOR,
    )
    return [row for row in rows if (row.customer_code, row.imdrf_code) in EARLIER_IMDRF_LINKS]


def _frozen_codes(db: Session, tenant_id) -> list[tuple]:
    """(obligation, field id, entry) for each code field of a sample report frozen before 0.10.77 that has no entry."""
    from backend.app.authority_reports import forms
    from backend.app.db.models.authority_reports import ReportObligation, ReportSnapshot

    out = []
    for obligation in db.query(ReportObligation).filter(
        ReportObligation.tenant_id == tenant_id, ReportObligation.source_system == SAMPLE_SOURCE
    ):
        snapshot = (
            db.query(ReportSnapshot)
            .filter(ReportSnapshot.tenant_id == tenant_id, ReportSnapshot.obligation_id == obligation.id)
            .order_by(ReportSnapshot.version.desc())
            .first()
        )
        if snapshot is None:
            continue
        entries = obligation.entries or {}
        frozen = {
            item["id"]: item for section in (snapshot.fields or {}).get("sections", []) for item in section["fields"]
        }
        at = snapshot.requested_at.isoformat()
        for field in forms.FORMS[obligation.form_code].fields():
            if not (field.source or "").startswith("imdrf_") or (entries.get(field.id) or {}).get("value"):
                continue
            held = (frozen.get(field.id) or {}).get("value")
            if held:
                entry = {"value": held, "code_state": "CONFIRMED", "suggested": held}
            elif obligation.form_code == "FDA_3500A" and field.id in US_SAMPLE_HEALTH_EFFECTS:
                entry = {"value": US_SAMPLE_HEALTH_EFFECTS[field.id]}
            else:
                continue
            out.append((obligation, field.id, {**entry, "by": obligation.created_by, "at": at}))
    return out


def refresh(db: Session, tenant_id, apply: bool, now: datetime | None = None) -> int:
    """How many sample records 0.10.77 corrects; with ``apply`` they are corrected (the caller commits)."""
    from backend.app.db.models.regulatory_reference import ImdrfCodeMapping

    links, codes = _old_links(db, tenant_id), _frozen_codes(db, tenant_id)
    if not apply:
        return len(links) + len(codes)
    now = now or datetime.now(timezone.utc)
    for row in links:
        target = EARLIER_IMDRF_LINKS[(row.customer_code, row.imdrf_code)]
        twin = (
            db.query(ImdrfCodeMapping.id)
            .filter(
                ImdrfCodeMapping.tenant_id == tenant_id,
                ImdrfCodeMapping.customer_system == row.customer_system,
                ImdrfCodeMapping.customer_code == row.customer_code,
                ImdrfCodeMapping.release == SAMPLE_IMDRF_RELEASE,
                ImdrfCodeMapping.annex == row.annex,
                ImdrfCodeMapping.imdrf_code == target,
            )
            .first()
        )
        if twin:
            db.delete(row)  # the new link is there already (a sample row only)
            continue
        row.release, row.imdrf_code, row.reviewed_at = SAMPLE_IMDRF_RELEASE, target, now
        row.review_note = "Sample mapping, checked against IMDRF Release 2026 (0.10.77)."
    for obligation, field_id, entry in codes:
        obligation.entries = {**(obligation.entries or {}), field_id: entry}
    db.flush()
    return len(links) + len(codes)
