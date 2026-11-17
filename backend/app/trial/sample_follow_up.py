"""W1d (D04): the synthetic follow-up of SAMPLE-CAPA-02, so a trial can finish the effectiveness journey.

SAMPLE-CAPA-02 restores incoming inspection of the NovaSense pressure sensors to 32 units per lot. Its effect could
only show in lots built after the fix, and the CAPA is due after the trial's today, so no real record can show it.
The sample therefore carries a clearly labelled **synthetic follow-up**: three lots built after the fix (inspection
restored to 32 sensors per lot), their pressure-alarm complaints month by month, and the before/after comparison
against lots 003 and 004 (counted from the sample's own records). It is labelled "Synthetic follow-up (sample)"
everywhere and is never presented as real history:

- it is **not** a lot, a complaint or a trend row: nothing of it reaches the complaint lists, the trend check, the
  reports or a customer's numbers. Its lots are dated in days after the fix, never as calendar history;
- it is kept as one sample evidence record (``SAMPLE-EV-006``, not attached to the case, not searchable), so the
  evidence register can show where it came from, and sample removal, restart and the sample clock take it;
- it shows on the CAPA's effectiveness check **once the check is planned** (the person has decided what to measure),
  and is part of what the person signs; a signed check keeps the follow-up it was signed on;
- a person reads it and signs the result themselves (effective, not effective or inconclusive). Nothing is pre-signed.

``refresh`` stages the record for older trials (dry run first), and never where SAMPLE-CAPA-02's check is signed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.trial.sample_source import SAMPLE_SOURCE

CAPA = "SAMPLE-CAPA-02"
ORBIT = "SAMPLE-ORBIT-300"
EVIDENCE = "SAMPLE-EV-006"
BEFORE_LOTS = (f"{ORBIT}-LOT-003", f"{ORBIT}-LOT-004")
PROBLEM = "PRESSURE_ALARM"
LABEL = "Synthetic follow-up (sample)"
NOTICE = (
    "Synthetic follow-up (sample): simulated lots built after the fix and their complaints, so you can practise the "
    "effectiveness check. It is not real history. None of it is in your complaint lists, trends or reports."
)
ACTION = "Incoming inspection of NovaSense pressure sensors restored to 32 units per lot (SAMPLE-CAPA-02)"
FOLLOW_UP_DAYS = 90
# (lot, built on day N after the fix, units, sensors inspected, sensors out of range, pressure-alarm complaints in
# months 1, 2 and 3 after the fix). A lot has no complaint before it is built.
LOTS = (
    ("FU-LOT-101", 10, 150, 32, 0, (0, 0, 1)),
    ("FU-LOT-102", 40, 150, 32, 1, (0, 0, 0)),
    ("FU-LOT-103", 70, 150, 32, 0, (0, 0, 0)),
)
LIMITS = (
    "Synthetic: the follow-up lots, their inspection results and their complaints are simulated for the sample.",
    "The before figures come from the sample's own records for lots 003 and 004; both are sample data.",
    "Observed counts per 1,000 unit-months, not a statistical test: judge them against the check's criteria.",
    "Three lots and 90 days are a short follow-up; a real check would wait for the planned day.",
)


def _rate(complaints: int, unit_months: float) -> float | None:
    return round(complaints * 1000 / unit_months, 1) if unit_months > 0 else None


def after() -> dict:
    """The synthetic lots after the fix. Pure."""
    months = [sum(lot[5][index] for lot in LOTS) for index in range(3)]
    unit_months = round(sum(units * (FOLLOW_UP_DAYS - built) / 30 for _, built, units, *_ in LOTS), 1)
    complaints = sum(months)
    return {
        "source": LABEL,
        "lots": [
            {
                "lot": lot,
                "built_day_after_fix": built,
                "units": units,
                "sensors_inspected": inspected,
                "sensors_out_of_range": out,
                "complaints": sum(by_month),
            }
            for lot, built, units, inspected, out, by_month in LOTS
        ],
        "months": [{"month": index + 1, "days": 30, "complaints": count} for index, count in enumerate(months)],
        "complaints": complaints,
        "unit_months": unit_months,
        "per_1000_unit_months": _rate(complaints, unit_months),
    }


def content_text() -> str:
    """The evidence record's text, written from the same figures."""
    data = after()
    lots = "; ".join(
        f"{item['lot']} built day {item['built_day_after_fix']} after the fix, {item['units']} units, "
        f"{item['sensors_out_of_range']} of {item['sensors_inspected']} sensors out of range, "
        f"{item['complaints']} pressure-alarm complaints"
        for item in data["lots"]
    )
    return (
        f"{NOTICE} Action: {ACTION}. Follow-up of {FOLLOW_UP_DAYS} days: {lots}. In all {data['complaints']} "
        f"complaint in {data['unit_months']} unit-months ({data['per_1000_unit_months']} per 1,000 unit-months)."
    )


def has_record(db: Session, tenant_id) -> bool:
    from backend.app.db.models.foundation import Evidence

    return (
        db.query(Evidence.id)
        .filter(
            Evidence.tenant_id == tenant_id,
            Evidence.evidence_identifier == EVIDENCE,
            Evidence.source_system == SAMPLE_SOURCE,
        )
        .first()
        is not None
    )


def stage(db: Session, tenant_id, now: datetime) -> int:
    """The follow-up's evidence record, where the sample has SAMPLE-CAPA-02 and the record is missing. Flushes."""
    from backend.app.db.models.foundation import Capa, Evidence

    capa = (
        db.query(Capa.id)
        .filter(Capa.tenant_id == tenant_id, Capa.capa_identifier == CAPA, Capa.source_system == SAMPLE_SOURCE)
        .first()
    )
    if capa is None or has_record(db, tenant_id):
        return 0
    db.add(
        Evidence(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            evidence_identifier=EVIDENCE,
            investigation_id=None,
            evidence_type="synthetic_follow_up",
            title=f"{LABEL}: lots built after {CAPA}",
            source_reference="MDARIX sample dataset (synthetic)",
            document_ref="sample://orbitcare-300/follow-up",
            reliability_status="synthetic",
            fact_type="derived_fact",
            content=content_text(),
            source_system=SAMPLE_SOURCE,
            source_identifier=EVIDENCE,
            source_timestamp=now,
            effective_timestamp=now,
            recorded_timestamp=now,
            ingestion_timestamp=now,
            created_at=now,
            updated_at=now,
        )
    )
    db.flush()
    return 1


def signed_check(db: Session, tenant_id) -> bool:
    """Whether SAMPLE-CAPA-02 has a signed effectiveness check (the refresh never changes what was signed on)."""
    from backend.app.db.models.capa_effectiveness import CapaEffectivenessCheck
    from backend.app.db.models.foundation import Capa

    return (
        db.query(CapaEffectivenessCheck.id)
        .join(Capa, (Capa.tenant_id == CapaEffectivenessCheck.tenant_id) & (Capa.id == CapaEffectivenessCheck.capa_id))
        .filter(
            CapaEffectivenessCheck.tenant_id == tenant_id,
            Capa.capa_identifier == CAPA,
            Capa.source_system == SAMPLE_SOURCE,
            CapaEffectivenessCheck.signed_at.isnot(None),
        )
        .first()
        is not None
    )


def refresh(db: Session, tenant_id, apply: bool, now: datetime | None = None) -> int:
    """1 when an older trial's sample needs the follow-up record (added with ``apply``), else 0. Idempotent."""
    from backend.app.db.models.foundation import Capa

    owed = (
        db.query(Capa.id)
        .filter(Capa.tenant_id == tenant_id, Capa.capa_identifier == CAPA, Capa.source_system == SAMPLE_SOURCE)
        .first()
        is not None
        and not has_record(db, tenant_id)
        and not signed_check(db, tenant_id)
    )
    if owed and apply:
        stage(db, tenant_id, now or datetime.now(timezone.utc))
    return int(owed)


def before(db: Session, tenant_id, product_id, today) -> dict:
    """Lots 003 and 004 (the first NovaSense lots, 13-sensor inspection) from the sample's records: their
    pressure-alarm complaints by 30-day month since the first was built, and per 1,000 unit-months to ``today``."""
    from backend.app.db.models.foundation import Complaint, LotBatch

    lots = (
        db.query(LotBatch.id, LotBatch.lot_identifier, LotBatch.quantity, LotBatch.effective_timestamp)
        .filter(
            LotBatch.tenant_id == tenant_id,
            LotBatch.lot_identifier.in_(BEFORE_LOTS),
            LotBatch.source_system == SAMPLE_SOURCE,
        )
        .all()
    )
    built = {row.id: row.effective_timestamp.astimezone(timezone.utc).date() for row in lots if row.effective_timestamp}
    stamps = [
        moment.astimezone(timezone.utc).date()
        for (moment,) in db.query(Complaint.complaint_timestamp).filter(
            Complaint.tenant_id == tenant_id,
            Complaint.product_id == product_id,
            Complaint.lot_batch_id.in_(list(built)),
            Complaint.problem_code == PROBLEM,
            Complaint.complaint_timestamp.isnot(None),
        )
    ]
    unit_months = round(
        sum((row.quantity or 0) * (today - built[row.id]).days / 30 for row in lots if row.id in built), 1
    )
    months = []
    first = min(built.values()).toordinal() if built else today.toordinal() + 1
    for begin in range(first, today.toordinal() + 1, 30):
        days = min(30, today.toordinal() - begin + 1)
        months.append(
            {
                "month": len(months) + 1,
                "days": days,
                "complaints": sum(1 for day in stamps if begin <= day.toordinal() < begin + days),
            }
        )
    return {
        "source": "Your sample records: lots 003 and 004",
        "lots": sorted(row.lot_identifier for row in lots),
        "units": sum(row.quantity or 0 for row in lots),
        "months": months,
        "complaints": len(stamps),
        "unit_months": unit_months,
        "per_1000_unit_months": _rate(len(stamps), unit_months),
    }


def for_check(db: Session, capa, check, today) -> dict | None:
    """The follow-up the check shows and signs: on SAMPLE-CAPA-02 only, once its check is planned and the record is
    staged; a signed check keeps the follow-up it was signed on (or none). None elsewhere."""
    if check is None or capa.source_system != SAMPLE_SOURCE or capa.capa_identifier != CAPA:
        return None
    if check.status != "PLANNED":
        return (check.evidence or {}).get("synthetic_follow_up")
    if not has_record(db, capa.tenant_id):
        return None
    return {
        "label": LABEL,
        "synthetic": True,
        "notice": NOTICE,
        "action": ACTION,
        "evidence_ref": EVIDENCE,
        "follow_up_days": FOLLOW_UP_DAYS,
        "before": before(db, capa.tenant_id, capa.product_id, today),
        "after": after(),
        "limits": list(LIMITS),
    }
