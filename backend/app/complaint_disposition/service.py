"""Reading complaint dispositions (rules.py and triggers.py decide; this module reads and shapes).

- ``facts_of`` and ``screen``: what the disposition screen shows for one complaint: the triggers met with their facts,
  the open cases that make it a known issue, whether the routine path is offered (T-U13), the classification to
  confirm (T-G39) and the versions signed so far.
- ``board``: open complaints still waiting for a disposition (not in a case), newest first.
- ``trend``: service-level and known-issue resolutions by product, problem code and lot, beside the complaint counts,
  grouped and filtered by use environment, user type and root-cause attribution (T-G36R).
- ``recurring``, ``waiting_past_target``, ``to_review`` and ``escalations``: what Readiness lists.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import exists, func
from sqlalchemy.orm import Session

from backend.app.complaint_classification import rules as coding
from backend.app.complaint_disposition import rules, triggers
from backend.app.complaint_review import rules as review_rules
from backend.app.db.models.complaint_disposition import ComplaintDisposition
from backend.app.db.models.complaint_review import ComplaintSecondLook
from backend.app.db.models.foundation import (
    Complaint,
    Investigation,
    InvestigationComplaint,
    LotBatch,
    Product,
    ProductVersion,
)
from backend.app.db.models.market_assessment import ComplaintClassification, ComplaintMarketAssessment
from backend.app.db.models.reportability import ComplaintReportability
from backend.app.reportability import markets
from backend.app.reportability import rules as reporting_rules
from backend.app.business_ids import complaint_ref

READ_LIMIT = 5000
RECEIVED_AT = func.coalesce(Complaint.complaint_timestamp, Complaint.event_timestamp, Complaint.created_at)


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def ref_of(complaint: Complaint) -> str:
    return complaint_ref(complaint)


def versions_of(db: Session, tenant_id: uuid.UUID, complaint_id, lock: bool = False) -> list[ComplaintDisposition]:
    query = db.query(ComplaintDisposition).filter(
        ComplaintDisposition.tenant_id == tenant_id, ComplaintDisposition.complaint_id == complaint_id
    )
    if lock:
        query = query.with_for_update()
    return query.order_by(ComplaintDisposition.version).all()


def current_by_complaint(db: Session, tenant_id: uuid.UUID, complaint_ids=None) -> dict:
    """``{complaint id: current disposition}``."""
    query = db.query(ComplaintDisposition).filter(
        ComplaintDisposition.tenant_id == tenant_id, ComplaintDisposition.superseded_by.is_(None)
    )
    if complaint_ids is not None:
        ids = list(complaint_ids)
        if not ids:
            return {}
        query = query.filter(ComplaintDisposition.complaint_id.in_(ids))
    return {row.complaint_id: row for row in query}


def classifications_of(db: Session, tenant_id: uuid.UUID, complaint_id) -> list[ComplaintClassification]:
    return (
        db.query(ComplaintClassification)
        .filter(ComplaintClassification.tenant_id == tenant_id, ComplaintClassification.complaint_id == complaint_id)
        .order_by(ComplaintClassification.version)
        .all()
    )


def classification_view(row: ComplaintClassification | None, names: dict[str, str]) -> dict:
    """The classification as the screen shows it: Unknown (never a guess) when none is proposed, the source values
    beside the coded ones."""
    if row is None:
        return {
            "id": None,
            "version": 0,
            "use_environment": coding.UNKNOWN,
            "use_environment_text": None,
            "user_type": coding.UNKNOWN,
            "user_type_text": None,
            "source_values": {},
            "state": "PROPOSED",
            "coding_criteria_version": coding.CODING_CRITERIA_VERSION,
            "confirmed_by": None,
            "confirmed_at": None,
            "change_reason": None,
            "sample": False,
        }
    return {
        "id": str(row.id),
        "version": row.version,
        "use_environment": row.use_environment,
        "use_environment_text": row.use_environment_text,
        "user_type": row.user_type,
        "user_type_text": row.user_type_text,
        "source_values": row.source_values or {},
        "state": row.state,
        "coding_criteria_version": row.coding_criteria_version,
        "confirmed_by": (names.get(row.confirmed_by) or "A colleague") if row.confirmed_by else None,
        "confirmed_at": _iso(row.confirmed_at),
        "change_reason": row.change_reason,
        "sample": row.source_system is not None,
    }


def disposition_view(row: ComplaintDisposition, names: dict[str, str], case_refs: dict[str, str]) -> dict:
    return {
        "id": str(row.id),
        "version": row.version,
        "branch": row.branch,
        "branch_label": rules.BRANCH_LABELS[row.branch],
        "triggers": row.triggers or [],
        "answers": row.answers or {},
        "service_record": row.service_record,
        "attribution": row.attribution,
        "attribution_label": rules.ATTRIBUTION_LABELS.get(row.attribution or ""),
        "attribution_reason": row.attribution_reason,
        "investigation_id": str(row.investigation_id) if row.investigation_id else None,
        "investigation_ref": case_refs.get(str(row.investigation_id)) if row.investigation_id else None,
        "routine_path": row.routine_path,
        "hands_on_seconds": row.hands_on_seconds,
        "change_reason": row.change_reason,
        "signed_record_id": str(row.signed_record_id),
        "content_fingerprint": row.content_fingerprint,
        "signed_by": names.get(row.signed_by) or "A colleague",
        "signed_at": _iso(row.signed_at),
        "superseded": row.superseded_by is not None,
        "sample": row.source_system is not None,
    }


def case_refs(db: Session, tenant_id: uuid.UUID, ids) -> dict[str, str]:
    wanted = [item for item in {*ids} if item]
    if not wanted:
        return {}
    return {
        str(row.id): row.business_id or row.investigation_identifier
        for row in db.query(Investigation.id, Investigation.business_id, Investigation.investigation_identifier).filter(
            Investigation.tenant_id == tenant_id, Investigation.id.in_(wanted)
        )
    }


def complaint_row(db: Session, tenant_id: uuid.UUID, complaint_id):
    """``(complaint, product name, version, lot)`` or None."""
    return (
        db.query(Complaint, Product.name, ProductVersion.version_identifier, LotBatch.lot_identifier)
        .outerjoin(Product, (Product.tenant_id == Complaint.tenant_id) & (Product.id == Complaint.product_id))
        .outerjoin(
            ProductVersion,
            (ProductVersion.tenant_id == Complaint.tenant_id) & (ProductVersion.id == Complaint.product_version_id),
        )
        .outerjoin(LotBatch, (LotBatch.tenant_id == Complaint.tenant_id) & (LotBatch.id == Complaint.lot_batch_id))
        .filter(Complaint.tenant_id == tenant_id, Complaint.id == complaint_id)
        .first()
    )


def facts_of(db: Session, tenant_id: uuid.UUID, complaint: Complaint, product_name, enabled: list[str]):
    assessments = (
        db.query(ComplaintMarketAssessment)
        .filter(
            ComplaintMarketAssessment.tenant_id == tenant_id, ComplaintMarketAssessment.complaint_id == complaint.id
        )
        .order_by(ComplaintMarketAssessment.version)
        .all()
    )
    legacy = (
        db.query(ComplaintReportability)
        .filter(ComplaintReportability.tenant_id == tenant_id, ComplaintReportability.complaint_id == complaint.id)
        .first()
    )
    return triggers.Facts(complaint, ref_of(complaint), product_name, enabled, assessments, legacy)


def known_issue_cases(db: Session, tenant_id: uuid.UUID, complaint: Complaint) -> list[dict]:
    """The open cases whose scope holds another complaint with the same product and problem code, or the same lot."""
    if complaint.product_id is None:
        return []
    code = (complaint.problem_code or "").strip().upper()
    rows = (
        db.query(Investigation, Complaint.problem_code, Complaint.lot_batch_id)
        .join(
            InvestigationComplaint,
            (InvestigationComplaint.tenant_id == Investigation.tenant_id)
            & (InvestigationComplaint.investigation_id == Investigation.id),
        )
        .join(
            Complaint,
            (Complaint.tenant_id == InvestigationComplaint.tenant_id)
            & (Complaint.id == InvestigationComplaint.complaint_id),
        )
        .filter(
            Investigation.tenant_id == tenant_id,
            triggers.OPEN_CASE,
            Investigation.product_id == complaint.product_id,
            Complaint.id != complaint.id,
        )
        .all()
    )
    found: dict[uuid.UUID, dict] = {}
    for case, problem_code, lot_id in rows:
        reasons = []
        if code and (problem_code or "").strip().upper() == code:
            reasons.append("same product and problem code")
        if complaint.lot_batch_id is not None and lot_id == complaint.lot_batch_id:
            reasons.append("same lot")
        if not reasons:
            continue
        item = found.setdefault(
            case.id,
            {
                "id": str(case.id),
                "ref": case.business_id or case.investigation_identifier,
                "identifier": case.investigation_identifier,
                "question": case.investigation_question,
                "match": [],
                "in_scope": False,
            },
        )
        item["match"] = sorted({*item["match"], *reasons})
    linked = {
        row[0]
        for row in db.query(InvestigationComplaint.investigation_id).filter(
            InvestigationComplaint.tenant_id == tenant_id, InvestigationComplaint.complaint_id == complaint.id
        )
    }
    for case_id, item in found.items():
        item["in_scope"] = case_id in linked
    return sorted(found.values(), key=lambda item: item["ref"])


def second_look_open(db: Session, tenant_id: uuid.UUID, complaint_id) -> dict | None:
    """The complaint's second-look flag when it is open or confirmed (the routine path is then not offered)."""
    from backend.app.complaint_review.service import assess

    _, flag = assess(db, tenant_id, complaint_id)
    if flag is None:
        return None
    decision = (
        db.query(ComplaintSecondLook.decision)
        .filter(ComplaintSecondLook.tenant_id == tenant_id, ComplaintSecondLook.complaint_id == complaint_id)
        .scalar()
    )
    if decision == "DISMISSED":
        return None
    return {"decision": decision, "reasons": [reason.get("label") for reason in flag.as_dict().get("reasons", [])]}


def watch_record(complaint: Complaint) -> dict:
    return {
        "death": complaint.death,
        "serious_injury": complaint.serious_injury,
        "malfunction": complaint.malfunction,
        "patient_involved": complaint.patient_involved,
        "country": complaint.country,
    }


def routine_offer(on_watch: bool, second_look: dict | None, met: list[dict]) -> dict:
    """Whether the routine path is offered (T-U13): not on the reportability watch, no open or confirmed second-look
    flag, no escalation trigger. Each condition that fails is said."""
    blocked = []
    if on_watch:
        blocked.append(
            "On the reportability watch: a death, serious injury or malfunction is recorded, or a patient's "
            "outcome is unknown"
        )
    if second_look is not None:
        blocked.append("The second look flags this record")
    if met:
        blocked.append("An escalation trigger is met")
    return {"offered": not blocked, "blocked": blocked, "basis": rules.ROUTINE_BASIS}


def screen_facts(db: Session, tenant_id: uuid.UUID, complaint_id, today: date) -> dict | None:
    """Everything the decision depends on, read now: the screen and the signing both use it."""
    from backend.app.reportability.service import settings_of

    row = complaint_row(db, tenant_id, complaint_id)
    if row is None:
        return None
    complaint, product_name, version, lot = row
    enabled = markets.enabled_markets(settings_of(db, tenant_id)["windows"])
    facts = facts_of(db, tenant_id, complaint, product_name, enabled)
    met = triggers.evaluate(db, tenant_id, facts, today)
    on_watch = reporting_rules.watched(watch_record(complaint))
    second_look = second_look_open(db, tenant_id, complaint.id)
    return {
        "complaint": complaint,
        "product_name": product_name,
        "version": version,
        "lot": lot,
        "enabled": enabled,
        "facts": facts,
        "triggers": met,
        "on_watch": on_watch,
        "second_look": second_look,
        "routine": routine_offer(on_watch, second_look, met),
        "candidates": known_issue_cases(db, tenant_id, complaint),
    }


def summary_of(complaint: Complaint, product_name, version, lot) -> dict:
    received = complaint.complaint_timestamp or complaint.event_timestamp or complaint.created_at
    return {
        "id": str(complaint.id),
        "ref": ref_of(complaint),
        "complaint_identifier": complaint.complaint_identifier,
        "product_id": str(complaint.product_id) if complaint.product_id else None,
        "product_name": product_name,
        "version": version,
        "lot": lot,
        "description": complaint.description,
        "source": complaint.reporter_type,
        "reporter_type": complaint.reporter_type,
        "problem_code": complaint.problem_code,
        "country": complaint.country,
        "status": complaint.status,
        "received_date": _iso(received.date()) if received else None,
        "awareness_date": _iso(complaint.awareness_timestamp.date()) if complaint.awareness_timestamp else None,
        "patient_involved": complaint.patient_involved,
        "serious_injury": complaint.serious_injury,
        "death": complaint.death,
        "malfunction": complaint.malfunction,
        "sample": complaint.source_system == "MDARIX_SAMPLE",
    }


# ------------------------------------------------------------------------------------------------------- the board

SHOWS = ("waiting", "signed")


def _open_unlinked(db: Session, tenant_id: uuid.UUID):
    in_case = exists().where(
        InvestigationComplaint.tenant_id == Complaint.tenant_id, InvestigationComplaint.complaint_id == Complaint.id
    )
    has_disposition = exists().where(
        ComplaintDisposition.tenant_id == Complaint.tenant_id,
        ComplaintDisposition.complaint_id == Complaint.id,
        ComplaintDisposition.superseded_by.is_(None),
    )
    return (
        db.query(Complaint.id, Complaint.status, Complaint.complaint_type, ComplaintSecondLook.decision, RECEIVED_AT)
        .outerjoin(
            ComplaintSecondLook,
            (ComplaintSecondLook.tenant_id == Complaint.tenant_id) & (ComplaintSecondLook.complaint_id == Complaint.id),
        )
        .filter(Complaint.tenant_id == tenant_id, ~in_case, ~has_disposition)
    )


def waiting_ids(db: Session, tenant_id: uuid.UUID) -> list[tuple[uuid.UUID, date | None]]:
    """Open complaints with no current disposition and in no case (a case decides those), newest first."""
    rows = _open_unlinked(db, tenant_id).order_by(RECEIVED_AT.desc(), Complaint.id).limit(READ_LIMIT).all()
    found = []
    for complaint_id, status, complaint_type, decision, received in rows:
        if review_rules.counts_as_open(status, complaint_type, decision):
            found.append((complaint_id, received.date() if isinstance(received, datetime) else received))
    return found


def board(db: Session, tenant_id: uuid.UUID, *, show: str = "waiting", page: int = 1, page_size: int = 25) -> dict:
    """The complaints waiting for a disposition (each with whether the routine path is offered), or the signed
    dispositions, newest first."""
    today = today_utc()
    waiting = waiting_ids(db, tenant_id)
    signed_rows = (
        db.query(ComplaintDisposition)
        .filter(ComplaintDisposition.tenant_id == tenant_id, ComplaintDisposition.superseded_by.is_(None))
        .order_by(ComplaintDisposition.signed_at.desc())
        .limit(READ_LIMIT)
        .all()
    )
    counts = Counter(row.branch for row in signed_rows)
    summary = {
        "waiting": len(waiting),
        "signed": len(signed_rows),
        "by_branch": {branch: counts.get(branch, 0) for branch in rules.BRANCHES},
        "routine_target_seconds": rules.ROUTINE_TARGET_SECONDS,
    }
    start = (page - 1) * page_size
    if show == "signed":
        chosen = signed_rows[start : start + page_size]
        ids = [row.complaint_id for row in chosen]
        total = len(signed_rows)
    else:
        show = "waiting"
        ids = [complaint_id for complaint_id, _ in waiting[start : start + page_size]]
        total = len(waiting)
        chosen = []
    items = []
    for complaint_id in ids:
        facts = screen_facts(db, tenant_id, complaint_id, today)
        if facts is None:
            continue
        item = summary_of(facts["complaint"], facts["product_name"], facts["version"], facts["lot"])
        item.update(
            {
                "on_watch": facts["on_watch"],
                "routine_offered": facts["routine"]["offered"],
                "triggers": triggers.codes(facts["triggers"]),
                "known_issue": [case["ref"] for case in facts["candidates"]],
            }
        )
        items.append(item)
    if show == "signed":
        refs = case_refs(db, tenant_id, [row.investigation_id for row in chosen])
        by_id = {row.complaint_id: row for row in chosen}
        for item in items:
            row = by_id[uuid.UUID(item["id"])]
            item["disposition"] = {**disposition_view(row, {}, refs), "signed_by_ref": row.signed_by}
    return {
        "summary": summary,
        "show": show,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
        "items": items,
    }


def waiting_past_target(db: Session, tenant_id: uuid.UUID, today: date, target_days: int) -> list:
    """Complaints waiting for a disposition past the backlog target: ``[(id, age)]``, oldest first."""
    found = []
    for complaint_id, received in waiting_ids(db, tenant_id):
        age = review_rules.age_days(received, today)
        if age is not None and age > target_days:
            found.append((complaint_id, age))
    return sorted(found, key=lambda item: -item[1])


# ---------------------------------------------------------------------------------------------- after signing


def to_review(db: Session, tenant_id: uuid.UUID, today: date) -> list[dict]:
    """Service-level and known-issue dispositions whose complaint now meets a trigger it did not meet at signing:
    "disposition to review: trigger met after signing". The trial does not reopen them by itself."""
    from backend.app.reportability.service import settings_of

    rows = (
        db.query(ComplaintDisposition, Complaint, Product.name)
        .join(
            Complaint,
            (Complaint.tenant_id == ComplaintDisposition.tenant_id)
            & (Complaint.id == ComplaintDisposition.complaint_id),
        )
        .outerjoin(Product, (Product.tenant_id == Complaint.tenant_id) & (Product.id == Complaint.product_id))
        .filter(
            ComplaintDisposition.tenant_id == tenant_id,
            ComplaintDisposition.superseded_by.is_(None),
            ComplaintDisposition.branch.in_(rules.RESOLVED),
        )
        .limit(READ_LIMIT)
        .all()
    )
    if not rows:
        return []
    enabled = markets.enabled_markets(settings_of(db, tenant_id)["windows"])
    found = []
    for disposition, complaint, product_name in rows:
        met = triggers.evaluate(db, tenant_id, facts_of(db, tenant_id, complaint, product_name, enabled), today)
        signed = {item.get("code") for item in disposition.triggers or []}
        new = [item for item in met if item["code"] not in signed]
        if new:
            found.append({"id": str(complaint.id), "ref": ref_of(complaint), "triggers": triggers.codes(new)})
    return found


def escalations(db: Session, tenant_id: uuid.UUID, since: datetime) -> list[ComplaintDisposition]:
    return (
        db.query(ComplaintDisposition)
        .filter(
            ComplaintDisposition.tenant_id == tenant_id,
            ComplaintDisposition.superseded_by.is_(None),
            ComplaintDisposition.branch.in_(rules.ESCALATED),
            ComplaintDisposition.signed_at >= since,
        )
        .order_by(ComplaintDisposition.signed_at.desc())
        .all()
    )


def recurring(db: Session, tenant_id: uuid.UUID, today: date) -> list[dict]:
    """Recurring service-level matters: RECURRING_COUNT or more service-level resolutions on one product and problem
    code within RECURRING_DAYS that no open case covers."""
    since = datetime.combine(today - timedelta(days=triggers.RECURRING_DAYS), datetime.min.time(), tzinfo=timezone.utc)
    rows = (
        db.query(
            Complaint.product_id,
            Product.name,
            func.upper(Complaint.problem_code),
            Complaint.business_id,
            Complaint.complaint_identifier,
        )
        .join(
            ComplaintDisposition,
            (ComplaintDisposition.tenant_id == Complaint.tenant_id)
            & (ComplaintDisposition.complaint_id == Complaint.id),
        )
        .outerjoin(Product, (Product.tenant_id == Complaint.tenant_id) & (Product.id == Complaint.product_id))
        .filter(
            ComplaintDisposition.tenant_id == tenant_id,
            ComplaintDisposition.superseded_by.is_(None),
            ComplaintDisposition.branch == rules.SERVICE_LEVEL,
            ComplaintDisposition.signed_at >= since,
            Complaint.product_id.isnot(None),
            Complaint.problem_code.isnot(None),
        )
        .all()
    )
    groups: dict[tuple, list] = defaultdict(list)
    names = {}
    for product_id, name, code, business_id, identifier in rows:
        groups[(product_id, code)].append(business_id or identifier)
        names[product_id] = name
    found = []
    for (product_id, code), refs in groups.items():
        if len(refs) >= triggers.RECURRING_COUNT and not triggers.covering_cases(db, tenant_id, product_id, code):
            found.append(
                {
                    "product_id": str(product_id),
                    "product_name": names[product_id],
                    "problem_code": code,
                    "count": len(refs),
                    "complaints": sorted(refs),
                }
            )
    return sorted(found, key=lambda item: (-item["count"], item["product_name"] or ""))


# ------------------------------------------------------------------------------------------------------- the trend

GROUPINGS = ("product", "problem", "lot", "use_environment", "user_type", "attribution")


def trend(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    group: str = "problem",
    use_environment: str | None = None,
    user_type: str | None = None,
    attribution: str | None = None,
) -> dict:
    """Service-level and known-issue resolutions (current dispositions) beside the complaint counts, by product and
    problem code (or lot, use environment, user type, attribution), filtered by the classification and attribution.
    Unknown is its own group; the classification is the latest version of each complaint's."""
    group = group if group in GROUPINGS else "problem"
    classified = {}
    for row in (
        db.query(ComplaintClassification)
        .filter(ComplaintClassification.tenant_id == tenant_id, ComplaintClassification.superseded_by.is_(None))
        .all()
    ):
        current = classified.get(row.complaint_id)
        if current is None or row.version > current.version:
            classified[row.complaint_id] = row
    dispositions = current_by_complaint(db, tenant_id)
    rows = (
        db.query(
            Complaint.id,
            Complaint.product_id,
            Product.name,
            Complaint.problem_code,
            LotBatch.lot_identifier,
        )
        .outerjoin(Product, (Product.tenant_id == Complaint.tenant_id) & (Product.id == Complaint.product_id))
        .outerjoin(LotBatch, (LotBatch.tenant_id == Complaint.tenant_id) & (LotBatch.id == Complaint.lot_batch_id))
        .filter(Complaint.tenant_id == tenant_id)
        .limit(READ_LIMIT * 4)
        .all()
    )
    groups: dict[tuple, dict] = {}
    totals = Counter()
    for complaint_id, product_id, product_name, problem_code, lot in rows:
        row = classified.get(complaint_id)
        environment = row.use_environment if row else coding.UNKNOWN
        user = row.user_type if row else coding.UNKNOWN
        disposition = dispositions.get(complaint_id)
        cause = disposition.attribution if disposition is not None and disposition.attribution else "NONE"
        if use_environment and environment != use_environment:
            continue
        if user_type and user != user_type:
            continue
        if attribution and cause != attribution:
            continue
        product_label = product_name or "No product"
        code = (problem_code or "").strip().upper() or "NO_CODE"
        key = {
            "product": (product_label,),
            "problem": (product_label, code),
            "lot": (product_label, lot or "No lot"),
            "use_environment": (coding.USE_ENVIRONMENT_LABELS.get(environment, environment),),
            "user_type": (coding.USER_TYPE_LABELS.get(user, user),),
            "attribution": (rules.ATTRIBUTION_LABELS.get(cause, "No attribution"),),
        }[group]
        item = groups.setdefault(
            key, {"key": list(key), "complaints": 0, "service_level": 0, "known_issue": 0, "escalated": 0}
        )
        item["complaints"] += 1
        totals["complaints"] += 1
        if disposition is not None:
            bucket = {
                rules.SERVICE_LEVEL: "service_level",
                rules.KNOWN_ISSUE: "known_issue",
            }.get(disposition.branch, "escalated")
            item[bucket] += 1
            totals[bucket] += 1
    items = sorted(
        groups.values(),
        key=lambda item: (-(item["service_level"] + item["known_issue"]), -item["complaints"], item["key"]),
    )
    return {
        "group": group,
        "groupings": list(GROUPINGS),
        "filters": {"use_environment": use_environment, "user_type": user_type, "attribution": attribution},
        "totals": {key: totals.get(key, 0) for key in ("complaints", "service_level", "known_issue", "escalated")},
        "items": items,
        "use_environments": coding.USE_ENVIRONMENT_LABELS,
        "user_types": coding.USER_TYPE_LABELS,
        "attributions": rules.ATTRIBUTION_LABELS,
        "recurring": recurring(db, tenant_id, today_utc()),
        "recurring_rule": f"{triggers.RECURRING_COUNT} or more service-level resolutions on one product and problem "
        f"code within {triggers.RECURRING_DAYS} days that no open case covers (starter threshold)",
    }


def counts_by_branch(db: Session, tenant_id: uuid.UUID, begin: datetime, end: datetime) -> dict:
    """Current dispositions signed in a period, by branch, and the escalations by trigger (the management review)."""
    rows = (
        db.query(ComplaintDisposition)
        .filter(
            ComplaintDisposition.tenant_id == tenant_id,
            ComplaintDisposition.superseded_by.is_(None),
            ComplaintDisposition.signed_at >= begin,
            ComplaintDisposition.signed_at < end,
        )
        .all()
    )
    by_branch = Counter(row.branch for row in rows)
    by_trigger = Counter(
        code for row in rows if row.branch == rules.ESCALATED_BY_TRIGGER for code in triggers.codes(row.triggers or [])
    )
    return {
        "signed": len(rows),
        "by_branch": {branch: by_branch.get(branch, 0) for branch in rules.BRANCHES},
        "by_trigger": {code: by_trigger.get(code, 0) for code in triggers.CODES},
        "routine": sum(1 for row in rows if row.routine_path),
    }
