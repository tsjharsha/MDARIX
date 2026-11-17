"""Reading CAPA effectiveness checks (rules.py decides; this module only reads).

It reads the organization's data plane, so it works the same on the shared database and on a dedicated one.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.capa_effectiveness import rules
from backend.app.complaint_review.service import people
from backend.app.db.models.capa_effectiveness import CapaEffectivenessCheck
from backend.app.db.models.foundation import Capa, Complaint, Investigation, InvestigationComplaint, Product

# When a complaint was received (as the backlog board reads it).
RECEIVED_AT = func.coalesce(Complaint.complaint_timestamp, Complaint.event_timestamp, Complaint.created_at)
READ_LIMIT = 5000
SHOWS = ("attention", "scheduled", "done", "all")


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _day(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc).date()
    return value


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def current_checks(db: Session, tenant_id: uuid.UUID, capa_ids) -> dict[uuid.UUID, CapaEffectivenessCheck]:
    """The latest round of each CAPA's check."""
    ids = list(capa_ids)
    if not ids:
        return {}
    found: dict[uuid.UUID, CapaEffectivenessCheck] = {}
    for row in (
        db.query(CapaEffectivenessCheck)
        .filter(CapaEffectivenessCheck.tenant_id == tenant_id, CapaEffectivenessCheck.capa_id.in_(ids))
        .order_by(CapaEffectivenessCheck.round)
        .all()
    ):
        found[row.capa_id] = row
    return found


def check_view(row: CapaEffectivenessCheck | None, names: dict[str, str]) -> dict | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "round": row.round,
        "status": row.status,
        "criteria": row.criteria,
        "planned_on": _iso(row.planned_on),
        "measured_from": _iso(row.measured_from),
        "plan_version": row.plan_version,
        "planned_by": names.get(row.planned_by) or "A colleague",
        "planned_at": _iso(row.planned_at),
        "result_summary": row.result_summary,
        "evidence": row.evidence or {},
        "signed_by": (names.get(row.signed_by) or "A colleague") if row.signed_by else None,
        "signer_role": row.signer_role,
        "signed_at": _iso(row.signed_at),
        "content_fingerprint": row.content_fingerprint,
    }


def item_of(capa: Capa, product_name, case_business_id, check: CapaEffectivenessCheck | None, names, today) -> dict:
    """One CAPA as the effectiveness list shows it."""
    if check is not None:
        planned_on, source = check.planned_on, rules.MDARIX
        state = rules.state_of(check.status, planned_on, today)
    else:
        planned_on = _day(capa.effectiveness_check_at)
        source = rules.SOURCE_SYSTEM if planned_on else None
        state = rules.state_of(None, planned_on, today)
    return {
        "capa": {
            "id": str(capa.id),
            "business_id": capa.business_id,
            "capa_identifier": capa.capa_identifier,
            "qms_reference": capa.qms_reference,
            "title": capa.title,
            "status": capa.status,
            "action_type": capa.action_type,
            "source_system": capa.source_system,
            "opened_on": _iso(_day(capa.opened_at)),
            "due_on": _iso(_day(capa.due_at)),
            "closed": rules.is_closed(capa.status),
            "product_id": str(capa.product_id) if capa.product_id else None,
            "product_name": product_name,
            "investigation": (
                {"id": str(capa.investigation_id), "business_id": case_business_id} if capa.investigation_id else None
            ),
        },
        "state": state,
        "planned_on": _iso(planned_on),
        "plan_source": source,
        "days_left": (planned_on - today).days if planned_on and state not in rules.RESULTS else None,
        "closed_without_check": rules.is_closed(capa.status) and state == rules.NOT_PLANNED,
        "check": check_view(check, names),
    }


def _capas(db: Session, tenant_id: uuid.UUID):
    return (
        db.query(Capa, Product.name, Investigation.business_id)
        .outerjoin(Product, (Product.tenant_id == Capa.tenant_id) & (Product.id == Capa.product_id))
        .outerjoin(
            Investigation,
            (Investigation.tenant_id == Capa.tenant_id) & (Investigation.id == Capa.investigation_id),
        )
        .filter(Capa.tenant_id == tenant_id)
    )


def _names_for(control_db, tenant_id, checks) -> dict[str, str]:
    refs = [ref for row in checks for ref in (row.planned_by, row.signed_by) if ref]
    return people(control_db, tenant_id, refs)


def board(
    db: Session,
    control_db: Session | None,
    tenant_id: uuid.UUID,
    *,
    show: str = "attention",
    page: int = 1,
    page_size: int = 25,
    today: date | None = None,
) -> dict:
    """Every CAPA that needs an effectiveness check (cancelled and rejected ones are left out), most urgent first."""
    today = today or today_utc()
    rows = _capas(db, tenant_id).order_by(Capa.opened_at.desc().nullslast(), Capa.id).limit(READ_LIMIT + 1).all()
    truncated = len(rows) > READ_LIMIT
    rows = [row for row in rows[:READ_LIMIT] if not rules.is_excluded(row[0].status)]
    checks = current_checks(db, tenant_id, (capa.id for capa, _, _ in rows))
    names = _names_for(control_db, tenant_id, checks.values())
    items = [item_of(capa, product, case, checks.get(capa.id), names, today) for capa, product, case in rows]
    items.sort(
        key=lambda item: (
            rules.STATE_ORDER.get(item["state"], 9),
            # Among CAPAs without a plan, the closed ones first: closed without verifying is the finding.
            not item["closed_without_check"],
            item["planned_on"] or "9999-12-31",
            item["capa"]["business_id"] or "",
        )
    )
    states = [item["state"] for item in items]
    summary = {
        "capas": len(items),
        "not_planned": states.count(rules.NOT_PLANNED),
        "closed_without_check": sum(1 for item in items if item["closed_without_check"]),
        "overdue": states.count(rules.OVERDUE),
        "due_soon": states.count(rules.DUE_SOON),
        "scheduled": states.count(rules.SCHEDULED),
        "effective": states.count(rules.EFFECTIVE),
        "not_effective": states.count(rules.NOT_EFFECTIVE),
        "inconclusive": states.count(rules.INCONCLUSIVE),
        "date_from_source": sum(1 for item in items if item["plan_source"] == rules.SOURCE_SYSTEM),
    }
    chosen = {
        "attention": [
            item
            for item in items
            if item["state"]
            in (rules.OVERDUE, rules.DUE_SOON, rules.NOT_PLANNED, rules.NOT_EFFECTIVE, rules.INCONCLUSIVE)
        ],
        "scheduled": [item for item in items if item["state"] == rules.SCHEDULED],
        "done": [item for item in items if item["state"] in rules.RESULTS],
        "all": items,
    }[show if show in SHOWS else "attention"]
    start = (page - 1) * page_size
    return {
        "summary": summary,
        "show": show if show in SHOWS else "attention",
        "total": len(chosen),
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-len(chosen) // page_size)),
        "truncated": truncated,
        "items": chosen[start : start + page_size],
    }


def load_capa(db: Session, tenant_id: uuid.UUID, capa_id: uuid.UUID, lock: bool = False):
    query = db.query(Capa).filter(Capa.tenant_id == tenant_id, Capa.id == capa_id)
    return query.with_for_update().first() if lock else query.first()


def rounds_of(db: Session, tenant_id: uuid.UUID, capa_id: uuid.UUID) -> list[CapaEffectivenessCheck]:
    return (
        db.query(CapaEffectivenessCheck)
        .filter(CapaEffectivenessCheck.tenant_id == tenant_id, CapaEffectivenessCheck.capa_id == capa_id)
        .order_by(CapaEffectivenessCheck.round)
        .all()
    )


def problem_codes(db: Session, capa: Capa) -> list[str]:
    """The problem codes of the complaints of the CAPA's case, most frequent first."""
    if capa.investigation_id is None:
        return []
    rows = (
        db.query(Complaint.problem_code, func.count())
        .join(
            InvestigationComplaint,
            (InvestigationComplaint.tenant_id == Complaint.tenant_id)
            & (InvestigationComplaint.complaint_id == Complaint.id),
        )
        .filter(
            InvestigationComplaint.tenant_id == capa.tenant_id,
            InvestigationComplaint.investigation_id == capa.investigation_id,
            Complaint.problem_code.isnot(None),
        )
        .group_by(Complaint.problem_code)
        .order_by(func.count().desc(), Complaint.problem_code)
        .all()
    )
    return [code for code, _ in rows if str(code or "").strip()]


def _count(db: Session, capa: Capa, codes: list[str], start: date, end: date) -> int:
    """Complaints on the CAPA's product (with one of ``codes`` when there are any) received in [start, end)."""
    begin = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    finish = datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc)
    query = db.query(func.count(Complaint.id)).filter(
        Complaint.tenant_id == capa.tenant_id,
        Complaint.product_id == capa.product_id,
        RECEIVED_AT >= begin,
        RECEIVED_AT < finish,
    )
    if codes:
        query = query.filter(Complaint.problem_code.in_(codes))
    return int(query.scalar() or 0)


def measure(db: Session, capa: Capa, measured_from: date, today: date) -> dict:
    """The complaint recurrence on the CAPA's product and its case's problem codes, before and since
    ``measured_from`` (equal periods, 30 to 365 days), or why it cannot be measured."""
    codes = problem_codes(db, capa)
    scope = {"product_id": str(capa.product_id) if capa.product_id else None, "problem_codes": codes}
    if capa.product_id is None:
        return {"available": False, "reason": "This CAPA names no product, so recurrence cannot be counted", **scope}
    if measured_from > today:
        return {"available": False, "reason": "The measurement has not started yet", **scope}
    after_days = (today - measured_from).days + 1  # today included
    before_days = rules.baseline_days(after_days)
    before = _count(db, capa, codes, measured_from - timedelta(days=before_days), measured_from)
    after = _count(db, capa, codes, measured_from, today + timedelta(days=1))
    return {
        "available": True,
        **scope,
        "measured_from": measured_from.isoformat(),
        "measured_to": today.isoformat(),
        **rules.recurrence(before, before_days, after, after_days),
    }


def suggested_start(capa: Capa, today: date) -> date:
    """Where a new plan's measurement starts by default: the CAPA's due day (the action in place), else its opening."""
    for value in (capa.due_at, capa.opened_at):
        day = _day(value)
        if day is not None and day <= today:
            return day
    return today


def detail(db: Session, control_db: Session | None, tenant_id: uuid.UUID, capa_id: uuid.UUID, today=None):
    """One CAPA's check: the list item, every round, the measured recurrence and a suggested plan. None if missing."""
    today = today or today_utc()
    row = _capas(db, tenant_id).filter(Capa.id == capa_id).first()
    if row is None:
        return None
    capa, product_name, case_business_id = row
    rounds = rounds_of(db, tenant_id, capa_id)
    names = _names_for(control_db, tenant_id, rounds)
    current = rounds[-1] if rounds else None
    item = item_of(capa, product_name, case_business_id, current, names, today)
    codes = problem_codes(db, capa)
    start = current.measured_from if current is not None else suggested_start(capa, today)
    planned = _day(capa.effectiveness_check_at)
    from backend.app.trial import sample_follow_up

    return {
        **item,
        "excluded": rules.is_excluded(capa.status),
        "rounds": [check_view(check, names) for check in rounds],
        "recurrence": measure(db, capa, start, today),
        "suggestion": {
            "criteria": rules.default_criteria(product_name, codes),
            "planned_on": max(planned or today + timedelta(days=90), start).isoformat(),
            "measured_from": start.isoformat(),
        },
        "can_plan": not rules.is_excluded(capa.status) and (current is None or current.status != rules.EFFECTIVE),
        "can_sign": current is not None and current.status == rules.PLANNED,
        # W1d (D04): the sample CAPA's labelled synthetic follow-up, once its check is planned (None elsewhere).
        "synthetic_follow_up": sample_follow_up.for_check(db, capa, current, today),
    }
