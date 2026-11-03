"""Release 0.10.79's sample correction for trials made before it (scripts/refresh_trial_story.py), idempotent.

The sample's two problem codes that had no IMDRF link get one, the most specific Annex A term of IMDRF's Release 2026
workbook that says what the complaint says (sample_imports.SAMPLE_IMDRF_LINKS): FLOW_ZERO_READING (SAMPLE-RV-07)
A090808 "Low Readings" and SPO2_DROPOUT_HARM (SAMPLE-RV-01) A090811 "Unable to Obtain Readings", approved by the
sample reviewer as the other sample links are. A code that already has a link, the trial user's own included, is
left as it is.

The caller commits.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.db.models.regulatory_reference import ImdrfCodeMapping
from backend.app.trial.sample_imports import (
    PROBLEM_CODES,
    SAMPLE_ACTOR,
    SAMPLE_IMDRF_LINKS,
    SAMPLE_IMDRF_RELEASE,
    SAMPLE_REVIEWER,
    has_sample_import,
)

NEW_CODES = ("FLOW_ZERO_READING", "SPO2_DROPOUT_HARM")


def _missing_links(db: Session, tenant_id) -> list[tuple[str, str]]:
    if not has_sample_import(db, tenant_id):
        return []
    linked = {
        code
        for (code,) in db.query(ImdrfCodeMapping.customer_code).filter(
            ImdrfCodeMapping.tenant_id == tenant_id,
            ImdrfCodeMapping.customer_system == PROBLEM_CODES,
            ImdrfCodeMapping.customer_code.in_(NEW_CODES),
        )
    }
    return [(code, imdrf) for code in NEW_CODES if code not in linked for imdrf in SAMPLE_IMDRF_LINKS[code]]


def refresh(db: Session, tenant_id, apply: bool, now: datetime | None = None) -> int:
    """How many sample links 0.10.79 adds; with ``apply`` they are added (the caller commits)."""
    links = _missing_links(db, tenant_id)
    if not apply:
        return len(links)
    now = now or datetime.now(timezone.utc)
    for code, imdrf_code in links:
        db.add(
            ImdrfCodeMapping(
                tenant_id=tenant_id,
                customer_system=PROBLEM_CODES,
                customer_code=code,
                customer_term=code.replace("_", " ").capitalize(),
                release=SAMPLE_IMDRF_RELEASE,
                annex="A",
                imdrf_code=imdrf_code,
                status="APPROVED",
                proposed_by=SAMPLE_ACTOR,
                proposed_at=now,
                reviewed_by=SAMPLE_REVIEWER,
                reviewed_at=now,
                review_note="Sample mapping, checked against IMDRF Release 2026 (0.10.79).",
            )
        )
    db.flush()
    return len(links)
