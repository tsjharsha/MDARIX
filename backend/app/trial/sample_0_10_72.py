"""Release 0.10.72's sample corrections for trials made before it (scripts/refresh_trial_story.py), idempotent.

- SAMPLE-RV-11's problem code SPO2_READING_HIGH gets its IMDRF Annex A term (A0908, "Incorrect, Inadequate or
  Imprecise Result or Readings"), the way the sample's other codes are mapped (sample_imports.SAMPLE_IMDRF_LINKS).
- The sample guide's example under question 2c read "Your examples: Sample examples: …": the text no longer starts
  with "Sample examples:". The guide version is signed: its content fingerprint is computed again and its approval
  record re-recorded on the new fingerprint (the sample approver's, at the same time), as RV-09 was in 0.10.70.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.db.models.guides_communications import DecisionGuideVersion
from backend.app.db.models.regulatory_reference import ImdrfCodeMapping
from backend.app.trial.sample_data import SAMPLE_SOURCE
from backend.app.trial.sample_guides import INJURY_EXAMPLES
from backend.app.trial.sample_imports import (
    PROBLEM_CODES,
    SAMPLE_ACTOR,
    SAMPLE_IMDRF_LINKS,
    SAMPLE_IMDRF_RELEASE,
    SAMPLE_REVIEWER,
    has_sample_import,
)

FLAGSHIP_CODE = "SPO2_READING_HIGH"
OLD_EXAMPLES_PREFIX = "Sample examples: "


def _missing_links(db: Session, tenant_id) -> list[tuple[str, str]]:
    if not has_sample_import(db, tenant_id):
        return []
    have = {
        (row.customer_code, row.imdrf_code)
        for row in db.query(ImdrfCodeMapping.customer_code, ImdrfCodeMapping.imdrf_code).filter(
            ImdrfCodeMapping.tenant_id == tenant_id,
            ImdrfCodeMapping.customer_system == PROBLEM_CODES,
            ImdrfCodeMapping.customer_code == FLAGSHIP_CODE,
        )
    }
    return [(FLAGSHIP_CODE, code) for code in SAMPLE_IMDRF_LINKS[FLAGSHIP_CODE] if (FLAGSHIP_CODE, code) not in have]


def _old_guides(db: Session, tenant_id) -> list[DecisionGuideVersion]:
    rows = db.query(DecisionGuideVersion).filter(
        DecisionGuideVersion.tenant_id == tenant_id, DecisionGuideVersion.source_system == SAMPLE_SOURCE
    )
    return [
        row
        for row in rows
        if any(str(item.get("examples") or "").startswith(OLD_EXAMPLES_PREFIX) for item in row.questions or [])
    ]


def refresh(db: Session, tenant_id, apply: bool, now: datetime | None = None) -> int:
    """How many sample records 0.10.72 corrects; with ``apply`` they are corrected (the caller commits)."""
    links, guides = _missing_links(db, tenant_id), _old_guides(db, tenant_id)
    if not apply:
        return len(links) + len(guides)
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
                review_note="Sample mapping.",
            )
        )
    for row in guides:
        _reword(db, row)
    db.flush()
    return len(links) + len(guides)


def _reword(db: Session, row: DecisionGuideVersion) -> None:
    from backend.app.db.models.foundation import SignedApprovalRecord
    from backend.app.decision_guides.router import _fingerprint
    from backend.app.human_decision.rules import signature_hash

    row.questions = [
        {**item, "examples": INJURY_EXAMPLES}
        if str(item.get("examples") or "").startswith(OLD_EXAMPLES_PREFIX)
        else item
        for item in row.questions
    ]
    if row.content_fingerprint is None:
        return  # a draft: nothing signed
    row.content_fingerprint = _fingerprint(row.market, row.code, row.questions, row.test_cases or [])
    record = db.get(SignedApprovalRecord, row.signed_record_id) if row.signed_record_id else None
    if record is not None:
        record.content_fingerprint = row.content_fingerprint
        record.signature_hash = signature_hash(row.content_fingerprint, record.signer_user_id, row.code)
