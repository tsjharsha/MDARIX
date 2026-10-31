"""The trial's read-only preview of the distributor and authorised-representative views (T-G37P), with the sample
parties and the fixed sample product set (trial/sample_dispositions.py). The rows come from service.py, which G37 calls
with a mandate's product set; nothing here writes."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from backend.app.db.models.foundation import Complaint, LotBatch, Product, ProductVersion
from backend.app.party_views import service
from backend.app.trial import sample_dispositions as sample
from backend.app.trial.sample_data import SAMPLE_SOURCE

BANNER = (
    "Preview with sample data. In a pilot, your distributor or authorised representative signs in separately, with "
    "MFA and an access end date (from MDARIX 1.0.1)."
)
PRRC_NOTE = "The authorised representative is not your PRRC. It has its own PRRC (MDR Art. 11 and 15(6))."
NO_SAMPLE = "The sample data was removed, so there is nothing to preview."


def _frame(page: str, **body) -> dict:
    return {"page": page, "banner": BANNER, "read_only": True, **body}


def _sample_complaints(db: Session, tenant_id: uuid.UUID, identifiers) -> list[Complaint]:
    return (
        db.query(Complaint)
        .filter(
            Complaint.tenant_id == tenant_id,
            Complaint.source_system == SAMPLE_SOURCE,
            Complaint.complaint_identifier.in_(list(identifiers)),
        )
        .order_by(Complaint.complaint_identifier)
        .all()
    )


def intake(db: Session, tenant_id: uuid.UUID) -> dict:
    """The distributor's intake form, filled with the submission that became SAMPLE-RT-01. It cannot be sent."""
    identifier, reference = next(iter(sample.DISTRIBUTOR_SUBMISSIONS.items()))
    row = (
        db.query(Complaint, Product.name, ProductVersion.version_identifier, LotBatch.lot_identifier)
        .outerjoin(Product, (Product.tenant_id == Complaint.tenant_id) & (Product.id == Complaint.product_id))
        .outerjoin(
            ProductVersion,
            (ProductVersion.tenant_id == Complaint.tenant_id) & (ProductVersion.id == Complaint.product_version_id),
        )
        .outerjoin(LotBatch, (LotBatch.tenant_id == Complaint.tenant_id) & (LotBatch.id == Complaint.lot_batch_id))
        .filter(
            Complaint.tenant_id == tenant_id,
            Complaint.source_system == SAMPLE_SOURCE,
            Complaint.complaint_identifier == identifier,
        )
        .first()
    )
    if row is None:
        return _frame("INTAKE", party=sample.SAMPLE_DISTRIBUTOR, submission=None, empty=NO_SAMPLE)
    complaint, product, version, lot = row
    # The therapist called the distributor's service desk on the day of the event: its first knowledge.
    known = complaint.event_timestamp or complaint.awareness_timestamp
    return _frame(
        "INTAKE",
        party=sample.SAMPLE_DISTRIBUTOR,
        submission={
            "reference": reference,
            "product": " ".join(part for part in (product, version) if part),
            "lot": lot,
            "first_knowledge": known.date().isoformat() if known else None,
            "words": sample.DISTRIBUTOR_WORDS[identifier],
            "becomes": identifier,
        },
    )


def distributor_status(db: Session, tenant_id: uuid.UUID) -> dict:
    """The sample distributor's own complaints only: reporter type Distributor and filed by it."""
    complaints = [
        row
        for row in _sample_complaints(db, tenant_id, sample.DISTRIBUTOR_SUBMISSIONS)
        if (row.reporter_type or "").strip().lower() == "distributor"
    ]
    statuses = service.submitter_status(db, tenant_id, complaints)
    items = []
    for complaint in complaints:
        status = statuses[complaint.id]
        note = sample.RELEASED_CLOSING_NOTES.get(complaint.complaint_identifier)
        items.append(
            {
                "reference": sample.DISTRIBUTOR_SUBMISSIONS[complaint.complaint_identifier],
                "complaint": complaint.complaint_identifier,
                "status": status["status"],
                "status_label": status["label"],
                "received": service.received_day(complaint),
                "last_change": status["last_change"],
                "closing_note": note if status["status"] == service.CLOSED else None,
            }
        )
    return _frame(
        "DISTRIBUTOR_STATUS",
        party=sample.SAMPLE_DISTRIBUTOR,
        statuses=[{"code": code, "label": label} for code, label in service.STATUS_LABELS.items()],
        items=items,
        empty=None if items else NO_SAMPLE,
    )


def authorised_representative(db: Session, tenant_id: uuid.UUID) -> dict:
    """The sample authorised representative's portfolio (OrbitCare 300 and VentraLink 250), with both panels."""
    products = (
        db.query(Product.id, Product.name)
        .filter(
            Product.tenant_id == tenant_id,
            Product.source_system == SAMPLE_SOURCE,
            Product.product_identifier.in_(sample.AUTHORISED_REPRESENTATIVE_PRODUCTS),
        )
        .order_by(Product.name)
        .all()
    )
    ids = [row.id for row in products]
    found = service.portfolio(db, tenant_id, ids)
    return _frame(
        "AUTHORISED_REPRESENTATIVE",
        party=sample.SAMPLE_AUTHORISED_REPRESENTATIVE,
        prrc_note=PRRC_NOTE,
        products=[row.name for row in products],
        complaints=found["complaints"],
        high_risk=found["high_risk"],
        recurring=service.recurring_issues(db, tenant_id, ids),
        empty=None if products else NO_SAMPLE,
    )
