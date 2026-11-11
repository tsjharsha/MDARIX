"""Reading the reportability watch (rules.py decides; this module only reads).

It reads the organization's data plane, so it works the same on the shared database and on a dedicated one. It never
changes a complaint and never submits anything.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app.complaint_review import rules as review_rules
from backend.app.complaint_review.service import people
from backend.app.db.models.complaint_review import ComplaintSecondLook
from backend.app.db.models.foundation import Complaint, Investigation, InvestigationComplaint, Product, ProductVersion
from backend.app.db.models.reportability import ComplaintReportability, ReportabilitySettings
from backend.app.db.models.reviews import CaseReview
from backend.app.reportability import assessments, deadlines, facts, markets, rules

# When the organization became aware, for the database's first filter (rules then take the earliest of the three).
AWARE_AT = func.coalesce(Complaint.awareness_timestamp, Complaint.complaint_timestamp, Complaint.recorded_timestamp)
READ_LIMIT = 20000
SHOWS = ("open", "overdue", "due_soon", "follow_up", "decided", "all")


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _day(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc).date()
    return value


def settings_of(db: Session, tenant_id: uuid.UUID, control_db: Session | None = None) -> dict:
    """The organization's reporting windows (none until someone enters them), with the templates to start from."""
    row = db.query(ReportabilitySettings).filter(ReportabilitySettings.tenant_id == tenant_id).first()
    windows = [rules.clean_window(item) for item in (row.windows if row else None) or []]
    editor = row.updated_by if row else None
    names = people(control_db, tenant_id, [editor]) if editor and control_db is not None else {}
    return {
        "windows": windows,
        "lookback_days": row.lookback_days if row else rules.LOOKBACK_DEFAULT,
        "configured": bool(windows),
        "templates": [rules.clean_window(item) for item in rules.TEMPLATES],
        "triggers": [{"code": code, "label": rules.TRIGGER_LABELS[code]} for code in rules.TRIGGERS],
        "version": row.version if row else 0,
        "updated_by": editor,
        "updated_by_name": (names.get(editor) or "A colleague") if editor else None,
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        # B9: the organization's role per market (absent: Manufacturer) and the roles it may choose.
        "reporting_roles": effective_roles(row.reporting_roles if row else None),
        "roles_offered": roles_offered(),
        # tr30 (B9-D9 / B8-D9): patient and reporter details at Send for approval; off unless a Customer Admin set it.
        "report_personal_data": bool(row.report_personal_data) if row else False,
    }


# B9 (B9-D8): the roles an organization may hold per market besides Manufacturer, each behind its part's switch.
ROLES = {
    ("US", "IMPORTER"): "MDARIX_B9_US_IMPORTER",
    ("US", "USER_FACILITY"): "MDARIX_B9_US_USER_FACILITY",
    ("IN", "IMPORTER"): "MDARIX_B9_INDIA",
    ("CA", "IMPORTER"): "MDARIX_B9_CANADA",
}


def roles_offered() -> dict[str, list[str]]:
    """Market -> the roles offered now (Manufacturer always first)."""
    from backend.app import feature_set

    found: dict[str, list[str]] = {}
    for (market, role), switch in ROLES.items():
        if feature_set.switched_on(switch):
            found.setdefault(market, ["MANUFACTURER"]).append(role)
    return found


def effective_roles(stored: dict | None) -> dict[str, str]:
    """The stored roles that are offered now: a role whose switch is off reads as Manufacturer (spec 6.4)."""
    offered = roles_offered()
    return {market: role for market, role in (stored or {}).items() if role in offered.get(market, ())}


def personal_data_on(db: Session, tenant_id: uuid.UUID) -> bool:
    """Whether the organization lets patient and reporter details be typed at Send for approval (default off)."""
    row = (
        db.query(ReportabilitySettings.report_personal_data)
        .filter(ReportabilitySettings.tenant_id == tenant_id)
        .first()
    )
    return bool(row and row[0])


def reporting_roles(db: Session, tenant_id: uuid.UUID) -> dict[str, str]:
    row = db.query(ReportabilitySettings.reporting_roles).filter(ReportabilitySettings.tenant_id == tenant_id).first()
    return effective_roles(row[0] if row else None)


def _moment(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)


def awareness(complaint: Complaint, linked: datetime | None = None) -> tuple[datetime | None, str | None]:
    """When the organization became aware: the earliest of the awareness, received and recorded times (as the case's
    regulatory review reads it; the earliest only ever makes a due date earlier), and which of them it is. ``linked``:
    the earliest awareness among the sources a person linked to this complaint (G20, intake/service.py), which then
    counts too. The market's counting rule takes its day in each time zone (deadlines.py). With neither an awareness
    nor a received date, the event date counts too (``EVENT_DATE``, 0.10.81: the earliest the record has, never
    called "received"); the clock is then provisional until the awareness date is entered (facts.py)."""
    unknown = complaint.awareness_timestamp is None and complaint.complaint_timestamp is None
    moments = [
        (_moment(complaint.awareness_timestamp), "AWARENESS_DATE"),
        (_moment(complaint.complaint_timestamp), "RECEIVED_DATE"),
        (_moment(complaint.event_timestamp) if unknown else None, "EVENT_DATE"),
        (_moment(complaint.recorded_timestamp), "RECORDED_DATE"),
        (_moment(linked), "LINKED_SOURCE"),
    ]
    known = [(moment, source) for moment, source in moments if moment is not None]
    if not known:
        return None, None
    return min(known, key=lambda item: item[0])


def _record(complaint: Complaint, product_name, version) -> dict:
    return {
        "id": str(complaint.id),
        "business_id": complaint.business_id,
        "complaint_identifier": complaint.complaint_identifier,
        "product_id": str(complaint.product_id) if complaint.product_id else None,
        "product_name": product_name,
        "version": version,
        "status": complaint.status,
        "complaint_type": complaint.complaint_type,
        "description": complaint.description,
        "country": complaint.country,
        "severity": complaint.severity,
        "problem_code": complaint.problem_code,
        "received_date": _day(complaint.complaint_timestamp).isoformat() if complaint.complaint_timestamp else None,
        "patient_involved": complaint.patient_involved,
        "serious_injury": complaint.serious_injury,
        "death": complaint.death,
        "malfunction": complaint.malfunction,
    }


def _case_reviews(db: Session, tenant_id: uuid.UUID, complaint_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """For each complaint in a case, the case and the latest regulatory review of it (if any)."""
    found: dict[uuid.UUID, dict] = {}
    if not complaint_ids:
        return found
    links = (
        db.query(InvestigationComplaint.complaint_id, Investigation.id, Investigation.business_id)
        .join(
            Investigation,
            (Investigation.tenant_id == InvestigationComplaint.tenant_id)
            & (Investigation.id == InvestigationComplaint.investigation_id),
        )
        .filter(InvestigationComplaint.tenant_id == tenant_id, InvestigationComplaint.complaint_id.in_(complaint_ids))
        .all()
    )
    case_ids = {case_id for _, case_id, _ in links}
    reviews: dict[uuid.UUID, CaseReview] = {}
    if case_ids:
        for review in (
            db.query(CaseReview)
            .filter(
                CaseReview.tenant_id == tenant_id,
                CaseReview.investigation_id.in_(case_ids),
                CaseReview.review_type == "REGULATORY",
                CaseReview.status.in_(["REQUESTED", "IN_PROGRESS", "COMPLETED"]),
            )
            .order_by(CaseReview.created_at)
            .all()
        ):
            reviews[review.investigation_id] = review  # the latest one wins
    for complaint_id, case_id, case_business_id in links:
        review = reviews.get(case_id)
        entry = {
            "case": {"id": str(case_id), "business_id": case_business_id},
            "review": (
                {
                    "id": str(review.id),
                    "business_id": review.business_id,
                    "status": review.status,
                    "outcome": review.outcome,
                    "completed_at": review.completed_at.isoformat() if review.completed_at else None,
                }
                if review is not None
                else None
            ),
        }
        current = found.get(complaint_id)
        # A complaint in several cases: a case with a review is more telling than one without.
        if current is None or (current["review"] is None and entry["review"] is not None):
            found[complaint_id] = entry
    return found


def decision_view(row: ComplaintReportability | None, names: dict[str, str]) -> dict | None:
    """An earlier single decision on the complaint (before per-market assessment, tr01): kept and shown as it was."""
    if row is None:
        return None
    decided_on = row.reported_on if row.decision == rules.REPORTED else _day(row.decided_at)
    return {
        "single_decision": True,
        "decision": row.decision,
        "rationale": row.rationale,
        "report_reference": row.report_reference,
        "reported_on": row.reported_on.isoformat() if row.reported_on else None,
        "window": row.window_name,
        "due_on": row.due_on.isoformat() if row.due_on else None,
        "on_time": rules.on_time(decided_on, row.due_on),
        "decided_by": names.get(row.decided_by) or "A colleague",
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
    }


def assess(
    complaint: Complaint,
    record: dict,
    windows: list[dict],
    case: dict | None,
    today: datetime | date,
    linked: datetime | None = None,
    org_zone: str | None = None,
    ivd: bool | None = None,
) -> dict:
    """What the watch shows for one complaint (without the person's decision). ``today``: now (a day in older
    callers); ``org_zone``: the organization's time zone (deadlines.py); ``ivd``: the product is an in-vitro diagnostic
    (``markets.product_is_ivd``; None: read from the product name alone)."""
    aware, source = awareness(complaint, linked)
    given = complaint.awareness_timestamp is not None or complaint.complaint_timestamp is not None
    needs = facts.needed(record, given or linked is not None)
    if any(item["fact"] == facts.COUNTRY for item in needs):
        # No country, or none MDARIX knows (F3): every enabled market's clocks, the shortest binding, provisional
        # until the country is entered (as triage counts a record with no country).
        clock_list = sorted(
            (
                # Not that market's clock: the complaint has none yet (no "Great Britain" on its page, 0.10.81).
                replace(clock, market=None)
                for market in markets.enabled_markets(windows)
                for clock in rules.clocks(
                    {**record, "country": markets.MARKET_COUNTRIES[market][0]}, windows, aware, today, org_zone
                )
            ),
            key=lambda clock: (clock.due_at or "", clock.name),
        )
    else:
        clock_list = rules.clocks(record, windows, aware, today, org_zone)
    if markets.is_ivd(record.get("product_name")) if ivd is None else ivd:
        # An in-vitro diagnostic's EU clocks cite the IVDR (starter), not the MDR.
        clock_list = [
            replace(clock, basis=tuple("IVDR_82" if item == "MDR_87" else item for item in clock.basis))
            for clock in clock_list
        ]
    review = (case or {}).get("review")
    settled = bool(review and review["status"] == "COMPLETED" and review["outcome"] in rules.SETTLING_OUTCOMES)
    in_review = bool(review and review["status"] in ("REQUESTED", "IN_PROGRESS"))
    return {
        "aware_date": aware.date().isoformat() if aware else None,
        "aware_at": aware.isoformat() if aware else None,
        "aware_source": source,
        "days_since_aware": (deadlines.day_of(today) - aware.date()).days if aware else None,
        "triggers": rules.triggers_of(record),
        "clocks": [clock.as_dict() for clock in clock_list],
        "binding": clock_list[0].as_dict() if clock_list else None,
        "follow_ups": rules.follow_ups(record, windows, complaint.awareness_timestamp is not None),
        # The facts a reporting step needs and the record does not give (facts.py): the clocks are provisional, and
        # no market conclusion is signed, until they are entered.
        "needs": needs,
        "provisional": bool(needs),
        "case": case,
        "settled_by_case": settled,
        "in_review": in_review,
    }


def _rows(db: Session, tenant_id: uuid.UUID, since: date, product_id: uuid.UUID | None, complaint_ids=None):
    query = (
        db.query(Complaint, Product, ProductVersion.version_identifier, ComplaintSecondLook.decision)
        .outerjoin(Product, (Product.tenant_id == Complaint.tenant_id) & (Product.id == Complaint.product_id))
        .outerjoin(
            ProductVersion,
            (ProductVersion.tenant_id == Complaint.tenant_id) & (ProductVersion.id == Complaint.product_version_id),
        )
        .outerjoin(
            ComplaintSecondLook,
            (ComplaintSecondLook.tenant_id == Complaint.tenant_id) & (ComplaintSecondLook.complaint_id == Complaint.id),
        )
    )
    followed = [
        Complaint.tenant_id == tenant_id,
        or_(
            Complaint.death.is_(True),
            Complaint.serious_injury.is_(True),
            Complaint.malfunction.is_(True),
            Complaint.patient_involved.is_(True),
        ),
        or_(AWARE_AT.is_(None), AWARE_AT >= datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc)),
    ]
    if product_id:
        followed.append(Complaint.product_id == product_id)
    query = query.filter(*followed)
    if complaint_ids is not None:
        # B6a: the asked complaints, within the same READ_LIMIT cut the whole read makes, so both always agree.
        cut = select(Complaint.id).where(*followed).order_by(AWARE_AT.asc(), Complaint.id).limit(READ_LIMIT)
        query = query.filter(
            Complaint.id.in_([uuid.UUID(str(value)) for value in complaint_ids]), Complaint.id.in_(cut)
        )
    return query.order_by(AWARE_AT.asc(), Complaint.id).limit(READ_LIMIT + 1).all()


def _linked(db: Session, tenant_id: uuid.UUID, complaint_ids) -> dict:
    from backend.app.intake.service import linked_awareness

    return linked_awareness(db, tenant_id, complaint_ids)


def counts_as_complaint(status, complaint_type, second_look: str | None) -> bool:
    """A record the watch follows: not dismissed on the second look, and not a cancelled record or inquiry unless a
    person confirmed it is a complaint (until then it waits on the second look). A closed complaint is followed: closing
    it does not settle whether it had to be reported."""
    if second_look == "DISMISSED":
        return False
    if second_look == "CONFIRMED":
        return True
    return not review_rules.is_cancelled(status) and not review_rules.is_inquiry(status, complaint_type)


def watch(
    db: Session,
    control_db: Session | None,
    tenant_id: uuid.UUID,
    *,
    show: str = "open",
    product_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 25,
    today: datetime | date | None = None,
    complaint_ids=None,
) -> dict:
    """The complaints whose reportability needs a person's decision, most urgent first, with a summary. ``today``:
    now (a day in older callers). ``complaint_ids`` (B6a): these complaints only, each item exactly as the whole
    organization's read gives it (tests/test_b6a_scoped_watch.py); the summary then counts only them."""
    today = deadlines.as_moment(today)
    org_zone = deadlines.org_zone(db, tenant_id)
    settings = settings_of(db, tenant_id)
    windows = settings["windows"]
    since = deadlines.day_of(today) - timedelta(days=settings["lookback_days"])
    rows = _rows(db, tenant_id, since, product_id, complaint_ids)
    truncated = len(rows) > READ_LIMIT
    candidates = []
    held_on_second_look = 0
    linked = _linked(db, tenant_id, [row[0].id for row in rows[:READ_LIMIT]])
    ivd: dict = {}
    for complaint, product, version, second_look in rows[:READ_LIMIT]:
        record = _record(complaint, product.name if product else None, version)
        ivd[complaint.id] = markets.product_is_ivd(product)
        if not rules.watched(record):
            continue
        aware, _ = awareness(complaint, linked.get(complaint.id))
        if aware is not None and aware.date() < since:
            continue
        if not counts_as_complaint(complaint.status, complaint.complaint_type, second_look):
            if second_look is None and rules.triggers_of(record):
                held_on_second_look += 1
            continue
        candidates.append((complaint, record))
    ids = [complaint.id for complaint, _ in candidates]
    cases = _case_reviews(db, tenant_id, ids)
    decisions = {
        row.complaint_id: row
        for row in (
            db.query(ComplaintReportability)
            .filter(ComplaintReportability.tenant_id == tenant_id, ComplaintReportability.complaint_id.in_(ids))
            .all()
            if ids
            else []
        )
    }
    names = people(control_db, tenant_id, (row.decided_by for row in decisions.values()))
    assessed = assessments.rows_by_complaint(db, tenant_id, ids)
    roles = reporting_roles(db, tenant_id)
    backlog = imported_backlog(db, tenant_id, today, ids if complaint_ids is not None else None) if ids else {}
    from backend.app.reportability import other_countries

    # Read with the switch off too: a report still open must not let the complaint read as settled.
    others = other_countries.open_lines(db, tenant_id, ids, today)
    items = []
    shortest = None
    for complaint, record in candidates:
        seen = assess(
            complaint,
            record,
            windows,
            cases.get(complaint.id),
            today,
            linked.get(complaint.id),
            org_zone,
            ivd=ivd[complaint.id],
        )
        decided = decisions.get(complaint.id)
        aware = datetime.fromisoformat(seen["aware_at"]) if seen["aware_at"] else None
        seen["markets"] = assessments.markets_summary(
            record, windows, assessed.get(complaint.id, {}), aware, today, org_zone, roles
        )
        seen["binding"] = binding_of(seen["binding"], seen["markets"])
        if seen["needs"] and seen["binding"]:
            # Waiting for its country or awareness date, the clock is the shortest possible: the earliest of the
            # per-market deadlines the triage table shows, one calculation for every screen (0.10.82).
            if shortest is None:
                shortest = triage_shortest(db, control_db, tenant_id, today, complaint_ids)
            seen["binding"] = shortest_binding(seen["binding"], shortest.get(str(complaint.id)))
        if str(complaint.id) in backlog:
            seen["binding"] = backlog_binding(seen["binding"], backlog[str(complaint.id)], today)
        # Settled by an earlier single decision, by its case's completed regulatory review, or by every market's
        # signed conclusion (reportable ones with their filing recorded).
        # B9b (run-2 decision Q4): a country outside the five markets, unsigned or with its report still open, keeps
        # the complaint open on its own line; it never changes the five markets' "settled".
        lines = others.get(complaint.id, [])
        is_decided = (
            decided is not None or seen["settled_by_case"] or assessments.settled(seen["markets"])
        ) and not lines
        state = rules.watch_state(
            other_countries.most_urgent(seen["binding"]["state"] if seen["binding"] else None, lines),
            is_decided,
            seen["in_review"],
            bool(seen["triggers"]),
        )
        items.append(
            {
                **record,
                **seen,
                "state": state,
                "decision": decision_view(decided, names),
                "other_countries": lines,
            }
        )

    def urgency(item: dict):
        binding = item["binding"]
        return (
            rules.STATE_ORDER.get(item["state"], 9),
            binding["due_at"] if binding else "9999-12-31",
            item["aware_date"] or "9999-12-31",
            item["business_id"] or "",
        )

    items.sort(key=urgency)
    undecided = [item for item in items if item["state"] != rules.DECIDED]
    decided_items = [item for item in items if item["state"] == rules.DECIDED]
    decided_rows = [item["decision"] for item in decided_items if item["decision"]]
    summary = {
        "configured": settings["configured"],
        "windows": len(windows),
        "lookback_days": settings["lookback_days"],
        "open": len(undecided),
        "overdue": sum(1 for item in undecided if item["state"] == rules.OVERDUE),
        "due_soon": sum(1 for item in undecided if item["state"] == rules.DUE_SOON),
        "running": sum(1 for item in undecided if item["binding"]),
        "in_review": sum(1 for item in undecided if item["in_review"]),
        "follow_up": sum(1 for item in undecided if item["follow_ups"]),
        "no_window": sum(1 for item in undecided if item["state"] == rules.NO_WINDOW),
        "needs_facts": sum(1 for item in undecided if item["needs"]),
        "decided": len(decided_items),
        "decided_in_window": sum(1 for row in decided_rows if row["on_time"] is True),
        "decided_late": sum(1 for row in decided_rows if row["on_time"] is False),
        "held_on_second_look": held_on_second_look,
    }
    chosen = {
        "open": undecided,
        "overdue": [item for item in undecided if item["state"] == rules.OVERDUE],
        "due_soon": [item for item in undecided if item["state"] == rules.DUE_SOON],
        "follow_up": [item for item in undecided if item["follow_ups"]],
        "decided": sorted(
            decided_items, key=lambda item: (item["decision"] or {}).get("decided_at") or "", reverse=True
        ),
        "all": items,
    }[show if show in SHOWS else "open"]
    start = (page - 1) * page_size
    return {
        "summary": summary,
        "show": show if show in SHOWS else "open",
        "total": len(chosen),
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-len(chosen) // page_size)),
        "truncated": truncated,
        "items": chosen[start : start + page_size],
    }


def one(db: Session, tenant_id: uuid.UUID, complaint_id: uuid.UUID, today: datetime | date | None = None):
    """``(complaint, record, assessment, second-look decision)`` for one complaint, or None when it does not exist."""
    today = deadlines.as_moment(today)
    row = (
        db.query(Complaint, Product, ProductVersion.version_identifier, ComplaintSecondLook.decision)
        .outerjoin(Product, (Product.tenant_id == Complaint.tenant_id) & (Product.id == Complaint.product_id))
        .outerjoin(
            ProductVersion,
            (ProductVersion.tenant_id == Complaint.tenant_id) & (ProductVersion.id == Complaint.product_version_id),
        )
        .outerjoin(
            ComplaintSecondLook,
            (ComplaintSecondLook.tenant_id == Complaint.tenant_id) & (ComplaintSecondLook.complaint_id == Complaint.id),
        )
        .filter(Complaint.tenant_id == tenant_id, Complaint.id == complaint_id)
        .first()
    )
    if row is None:
        return None
    complaint, product, version, second_look = row
    record = _record(complaint, product.name if product else None, version)
    windows = settings_of(db, tenant_id)["windows"]
    case = _case_reviews(db, tenant_id, [complaint.id]).get(complaint.id)
    org_zone = deadlines.org_zone(db, tenant_id)
    seen = assess(
        complaint,
        record,
        windows,
        case,
        today,
        _linked(db, tenant_id, [complaint.id]).get(complaint.id),
        org_zone,
        ivd=markets.product_is_ivd(product),
    )
    seen["org_zone"] = org_zone
    seen["roles"] = reporting_roles(db, tenant_id)
    return complaint, record, seen, second_look


def clocks_for(
    db: Session, tenant_id: uuid.UUID, complaints: list[Complaint], today: datetime | date | None = None
) -> list[dict]:
    """The reporting clock of each complaint (for a case's regulatory review): its binding window and due date, its
    state, and the person's decision if any. Only complaints the watch follows are listed."""
    today = deadlines.as_moment(today)
    org_zone = deadlines.org_zone(db, tenant_id)
    windows = settings_of(db, tenant_id)["windows"]
    roles = reporting_roles(db, tenant_id)
    ids = [row.id for row in complaints]
    decisions = {
        row.complaint_id: row
        for row in (
            db.query(ComplaintReportability)
            .filter(ComplaintReportability.tenant_id == tenant_id, ComplaintReportability.complaint_id.in_(ids))
            .all()
            if ids
            else []
        )
    }
    found = []
    linked = _linked(db, tenant_id, ids)
    product_ids = {row.product_id for row in complaints if row.product_id}
    products = (
        {row.id: row for row in db.query(Product).filter(Product.tenant_id == tenant_id, Product.id.in_(product_ids))}
        if product_ids
        else {}
    )
    for complaint in complaints:
        record = _record(complaint, None, None)
        if not rules.watched(record):
            continue
        ivd = markets.product_is_ivd(products.get(complaint.product_id))
        seen = assess(complaint, record, windows, None, today, linked.get(complaint.id), org_zone, ivd=ivd)
        aware = datetime.fromisoformat(seen["aware_at"]) if seen["aware_at"] else None
        assessed = assessments.rows_by_complaint(db, tenant_id, [complaint.id]).get(complaint.id, {})
        binding = binding_of(
            seen["binding"], assessments.markets_summary(record, windows, assessed, aware, today, org_zone, roles)
        )
        decided = decisions.get(complaint.id)
        found.append(
            {
                "complaint": {"id": str(complaint.id), "business_id": complaint.business_id},
                "state": rules.watch_state(
                    binding["state"] if binding else None, decided is not None, False, bool(seen["triggers"])
                ),
                "binding": binding,
                "aware_date": seen["aware_date"],
                "follow_ups": seen["follow_ups"],
                "decision": decided.decision if decided is not None else None,
            }
        )
    order = {state: index for state, index in rules.STATE_ORDER.items()}
    return sorted(found, key=lambda item: (order.get(item["state"], 9), (item["binding"] or {}).get("due_at") or ""))


def triage_shortest(db: Session, control_db, tenant_id: uuid.UUID, now, complaint_ids=None) -> dict[str, dict]:
    """Each complaint's earliest per-market deadline as triage counts it (intake/rules.py provisional_deadlines, each
    market's conservative category), by the complaint's id: what "shortest possible" means on every screen
    (``complaint_ids``: only these complaints' events, B6a; the whole list otherwise)."""
    from backend.app.intake import service as intake

    found: dict[str, dict] = {}
    moment = deadlines.as_moment(now)
    for item in intake.triage(db, control_db, tenant_id, "all", moment, complaint_ids=complaint_ids)["items"]:
        dated = [deadline for deadline in item["deadlines"] if deadline.get("due_at")]
        if not dated:
            continue
        # Once the incident country is known, its market's deadline is the clock (0.10.84, H3): the other markets
        # apply "only if also reportable", as the triage table says; the earliest of all only while no country is.
        own = [deadline for deadline in dated if deadline.get("own")]
        first = own[0] if own else min(dated, key=lambda deadline: deadline["due_at"])
        for key in item["members"]:
            kind, record_id = key.split(":", 1)
            if kind == intake.COMPLAINT:
                found[record_id] = first
    return found


def imported_backlog(db: Session, tenant_id: uuid.UUID, now, complaint_ids=None) -> dict[str, dict]:
    """The Imported backlog's complaints (intake.service.imported_backlog), by id (``complaint_ids``: these only)."""
    from backend.app.intake import service as intake

    found = intake.imported_backlog(db, tenant_id, page_size=intake.BACKLOG_READ, now=now, complaint_ids=complaint_ids)[
        "items"
    ]
    return {item["id"]: item for item in found}


def backlog_binding(binding: dict | None, held: dict, now) -> dict:
    """OD-12 + 3a (owner, 10 Nov): an old imported complaint in the Imported backlog: its regulatory clock ran in the
    customer's QMS, so the clock shown is the backlog target, with the note; never overdue against a market window."""
    from backend.app.intake.service import BACKLOG_NOTE

    due = datetime.fromisoformat(held["due_at"])
    return {
        **(binding or {"days": None, "day_basis": None, "market": None, "triggers": [], "basis": []}),
        "window": BACKLOG_NOTE,
        "due_date": due.date().isoformat(),
        "due_at": held["due_at"],
        "due_zone": None,
        "due_label": None,
        "days_left": (due.date() - deadlines.day_of(now)).days,
        "state": rules.OVERDUE if held["overdue"] else rules.RUNNING,
        "backlog": True,
    }


def shortest_binding(binding: dict, triage_first: dict | None) -> dict:
    """A provisional binding clock read as triage's earliest deadline (its day, time, zone and state), the rest kept;
    as it was when triage has no deadline for the complaint."""
    if not triage_first:
        return binding
    keys = ("due_date", "due_at", "due_zone", "due_label", "days_left", "state")
    return {
        **binding,
        **{key: triage_first[key] for key in keys if key in triage_first},
        "window": triage_first["basis"],
    }


def binding_of(window_clock: dict | None, market_items: list[dict]) -> dict | None:
    """The binding clock: always the earliest of the windows' clock and every market's own clock (J14: a signed shorter
    category, such as an EU 2-day serious public health threat, binds even while a 15-day window runs)."""
    found = [window_clock] if window_clock else []
    found += [
        {**item["clock"], "triggers": [], "basis": [], "market": item["market"]}
        for item in market_items
        if item.get("clock")
    ]
    return min(found, key=lambda clock: clock["due_at"]) if found else None
