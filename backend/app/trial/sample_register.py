"""W1d (D08): the sample evidence register. One page that answers "where did this number come from?" for the
flagship story (OrbitCare 300 Rev B, SAMPLE-INV-001), read from the trial's own sample records:

the product and its versions; the supplier and component change; the lots with their units and pressure-alarm
complaints; the complaint counts and the monthly rates **from the trend check** (the same computation Home and the
flagship's step 1 read: ``signals.insight.trend_board``, before -> after = the expected and recent counts over the
trend's window, x 30 days); the inspection changes; the evidence for, against and missing, with each record's date
and source; the synthetic follow-up (labelled); and the exact limits of the sample dataset. Read only. None when the
sample is not there.
"""

from __future__ import annotations

import uuid
from datetime import date, timezone

from sqlalchemy.orm import Session

from backend.app.trial import sample_follow_up
from backend.app.trial.sample_source import SAMPLE_SOURCE

PRODUCT = "SAMPLE-ORBIT-300"
CASE = "SAMPLE-INV-001"
CHANGE = "SAMPLE-CHG-014"
SENSOR = f"{PRODUCT}-C1"
PROBLEM = "PRESSURE_ALARM"
# Incoming inspection of the pressure sensor, as the change record and the CAPA state it (sources named).
INSPECTION = (
    {"when": "Rev A, Precision Sensors Ltd", "units_per_lot": 32, "source": CHANGE},
    {"when": "Rev B, NovaSense Components", "units_per_lot": 13, "source": CHANGE},
    {"when": "After SAMPLE-CAPA-02 (synthetic follow-up)", "units_per_lot": 32, "source": sample_follow_up.EVIDENCE},
)
LIMITS = (
    "Every record here is sample data made for the free trial: OrbitCare 300 is not a real device.",
    "One product with its versions and lots, one supplier change and one investigation: real files are larger and "
    "less tidy.",
    "Complaint dates move with your trial day (the sample clock) until you work on the sample; their spacing stays.",
    "The trend check compares the last 30 days with the expected count from earlier days per unit in the field; it is "
    "an observed comparison, not proof of a cause.",
    "The evidence shows a time and lot association after the supplier and inspection changes. The cause is not "
    "confirmed: the bench test of returned pumps is not in the sample.",
    "The follow-up after SAMPLE-CAPA-02 is synthetic. It is never shown as real history and never counted in trends.",
)


def _day(value) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).date().isoformat() if hasattr(value, "astimezone") else value.isoformat()


def monthly(row: dict) -> dict | None:
    """Complaints a month before -> after from a trend row, as the screens compute it (signalAi.ts monthlyRates)."""
    days = row.get("recent_days") or 0
    if days <= 0 or not isinstance(row.get("expected"), (int, float)):
        return None
    return {"before": round(row["expected"] / days * 30, 1), "after": round(row["recent"] / days * 30, 1)}


def register(db: Session, tenant_id: uuid.UUID, today: date) -> dict | None:
    from backend.app.capa_effectiveness.service import current_checks
    from backend.app.db.models.foundation import (
        Capa,
        Change,
        Complaint,
        Component,
        ComponentSupplier,
        Evidence,
        Hypothesis,
        HypothesisEvidence,
        Investigation,
        InvestigationComplaint,
        LotBatch,
        Product,
        ProductVersion,
        Supplier,
        Unknown,
    )
    from backend.app.signals import insight

    product = (
        db.query(Product)
        .filter(
            Product.tenant_id == tenant_id,
            Product.product_identifier == PRODUCT,
            Product.source_system == SAMPLE_SOURCE,
        )
        .first()
    )
    if product is None:
        return None
    versions = (
        db.query(ProductVersion)
        .filter(ProductVersion.tenant_id == tenant_id, ProductVersion.product_id == product.id)
        .order_by(ProductVersion.release_timestamp)
        .all()
    )
    version_names = {row.id: row.version_identifier for row in versions}
    change = (
        db.query(Change)
        .filter(
            Change.tenant_id == tenant_id, Change.change_identifier == CHANGE, Change.source_system == SAMPLE_SOURCE
        )
        .first()
    )
    suppliers = (
        db.query(Component.revision, Supplier.name, ComponentSupplier.effective_timestamp)
        .join(
            ComponentSupplier,
            (ComponentSupplier.tenant_id == Component.tenant_id) & (ComponentSupplier.component_id == Component.id),
        )
        .join(
            Supplier,
            (Supplier.tenant_id == ComponentSupplier.tenant_id) & (Supplier.id == ComponentSupplier.supplier_id),
        )
        .filter(Component.tenant_id == tenant_id, Component.component_identifier == SENSOR)
        .order_by(ComponentSupplier.effective_timestamp)
        .all()
    )
    case = (
        db.query(Investigation)
        .filter(
            Investigation.tenant_id == tenant_id,
            Investigation.investigation_identifier == CASE,
            Investigation.source_system == SAMPLE_SOURCE,
        )
        .first()
    )
    in_case = set()
    if case is not None:
        in_case = {
            complaint_id
            for (complaint_id,) in db.query(InvestigationComplaint.complaint_id).filter(
                InvestigationComplaint.tenant_id == tenant_id, InvestigationComplaint.investigation_id == case.id
            )
        }
    complaints = (
        db.query(Complaint.id, Complaint.lot_batch_id, Complaint.problem_code)
        .filter(Complaint.tenant_id == tenant_id, Complaint.product_id == product.id)
        .all()
    )
    lots = (
        db.query(LotBatch)
        .filter(LotBatch.tenant_id == tenant_id, LotBatch.product_version_id.in_(list(version_names)))
        .order_by(LotBatch.lot_identifier)
        .all()
    )
    alarms = [row for row in complaints if row.problem_code == PROBLEM]
    trend = insight.trend_board(db, tenant_id, grouping="version", product_id=product.id)
    trend_rows = [
        {
            "version": (item.get("product_version") or {}).get("version_identifier"),
            "recent": item["recent"],
            "recent_days": item["recent_days"],
            "expected": item["expected"],
            "ratio": item["ratio"],
            "label": item["label"],
            "monthly": monthly(item),
        }
        for item in trend.get("items", [])
    ]
    evidence = []
    links = []
    unknowns = []
    if case is not None:
        evidence = (
            db.query(Evidence)
            .filter(Evidence.tenant_id == tenant_id, Evidence.investigation_id == case.id)
            .order_by(Evidence.evidence_identifier)
            .all()
        )
        links = (
            db.query(
                HypothesisEvidence.relation_type,
                HypothesisEvidence.rationale,
                Hypothesis.statement,
                Evidence.evidence_identifier,
            )
            .join(
                Hypothesis,
                (Hypothesis.tenant_id == HypothesisEvidence.tenant_id)
                & (Hypothesis.id == HypothesisEvidence.hypothesis_id),
            )
            .join(
                Evidence,
                (Evidence.tenant_id == HypothesisEvidence.tenant_id) & (Evidence.id == HypothesisEvidence.evidence_id),
            )
            .filter(
                HypothesisEvidence.tenant_id == tenant_id,
                Hypothesis.investigation_id == case.id,
                HypothesisEvidence.retracted_at.is_(None),
            )
            .order_by(Evidence.evidence_identifier, Hypothesis.statement)
            .all()
        )
        unknowns = (
            db.query(Unknown.description, Unknown.evidence_needed, Unknown.status)
            .filter(Unknown.tenant_id == tenant_id, Unknown.investigation_id == case.id)
            .order_by(Unknown.description)
            .all()
        )
    follow_record = (
        db.query(Evidence)
        .filter(
            Evidence.tenant_id == tenant_id,
            Evidence.evidence_identifier == sample_follow_up.EVIDENCE,
            Evidence.source_system == SAMPLE_SOURCE,
        )
        .first()
    )
    capa = (
        db.query(Capa.id, Capa.capa_identifier, Capa.title)
        .filter(
            Capa.tenant_id == tenant_id,
            Capa.capa_identifier == sample_follow_up.CAPA,
            Capa.source_system == SAMPLE_SOURCE,
        )
        .first()
    )
    check = current_checks(db, tenant_id, [capa.id]).get(capa.id) if capa is not None else None

    def link(kind: str) -> list[dict]:
        return [
            {"evidence": row.evidence_identifier, "hypothesis": row.statement, "why": row.rationale}
            for row in links
            if row.relation_type == kind
        ]

    return {
        "title": "Sample evidence register",
        "sample": True,
        "product": {
            "id": str(product.id),
            "ref": product.product_identifier,
            "name": product.name,
            "versions": [
                {
                    "version": row.version_identifier,
                    "released": _day(row.release_timestamp),
                    "description": row.description,
                }
                for row in versions
            ],
        },
        "change": (
            {"ref": change.change_identifier, "description": change.description, "on": _day(change.event_timestamp)}
            if change
            else None
        ),
        "component": {
            "ref": SENSOR,
            "suppliers": [
                {"revision": revision, "supplier": name, "from": _day(since)} for revision, name, since in suppliers
            ],
        },
        "lots": [
            {
                "ref": lot.lot_identifier,
                "version": version_names.get(lot.product_version_id),
                "built": _day(lot.effective_timestamp),
                "units": lot.quantity,
                "complaints": sum(1 for row in complaints if row.lot_batch_id == lot.id),
                "pressure_alarm": sum(1 for row in alarms if row.lot_batch_id == lot.id),
                "in_case": any(row.lot_batch_id == lot.id and row.id in in_case for row in complaints),
            }
            for lot in lots
        ],
        "complaints": {
            "on_product": len(complaints),
            "pressure_alarm": len(alarms),
            "in_case": len(in_case),
            "trend": trend_rows,
            "trend_source": "The trend check (Trends and Home read the same computation)",
        },
        "inspection": list(INSPECTION),
        "case": {"id": str(case.id), "ref": CASE, "question": case.investigation_question} if case else None,
        "evidence": {
            "records": [
                {
                    "ref": row.evidence_identifier,
                    "title": row.title,
                    "recorded": _day(row.created_at),
                    "source": row.source_reference,
                    "fact_type": row.fact_type,
                    "content": row.content,
                }
                for row in evidence
            ],
            "for": link("support"),
            "against": link("contradict"),
            "missing": [
                {"what": row.description, "needed": row.evidence_needed, "status": row.status} for row in unknowns
            ],
        },
        "follow_up": {
            "label": sample_follow_up.LABEL,
            "notice": sample_follow_up.NOTICE,
            "record": (
                {
                    "ref": follow_record.evidence_identifier,
                    "title": follow_record.title,
                    "recorded": _day(follow_record.created_at),
                }
                if follow_record
                else None
            ),
            "capa": {"id": str(capa.id), "ref": capa.capa_identifier, "title": capa.title} if capa else None,
            "check": check.status if check is not None else None,
            "after": sample_follow_up.after(),
        },
        "limits": list(LIMITS),
        "as_of": today.isoformat(),
    }
