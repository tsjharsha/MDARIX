"""What a signal's complaints have in common, and the statistical trend check (trend_rules.py) per product version.

- ``trend_board``: the trend check for every product version (or version and problem, or version and complaint type)
  of the organization, most notable first. Every complaint counts whatever its status; only records a person dismissed
  on the second look as not a complaint are left out.
- ``records_summary``: a signal's complaints summarized from their fields (period, harm, lots, markets, recurring
  words, No Fault Found codes); every sentence cites the complaints it rests on. Rules only, always available.
- ``ai_summary``: the same, written by the language model from the complaints' texts, kept only sentence by sentence
  when every cited complaint is one of the signal's and the sentence claims no cause or decision. When AI is off,
  unavailable or over budget, the records summary stands and the reason is given.

Reading only; nothing here changes a complaint or a signal, and nothing raises a signal.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter, defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.complaint_review import rules as review_rules
from backend.app.db.models.complaint_review import ComplaintSecondLook
from backend.app.db.models.foundation import Complaint, LotBatch, Product, ProductVersion
from backend.app.db.models.signals import OPEN_SIGNAL_STATUSES, Signal, SignalComplaint
from backend.app.signals import logic, service, trend_rules

EVENT_AT = func.coalesce(Complaint.event_timestamp, Complaint.complaint_timestamp, Complaint.created_at)
READ_LIMIT = 50000
SUMMARY_COMPLAINTS_MAX = 40
CITED_MAX = 6
STOPWORDS = frozenset(
    """a an and are as at be been but by during for from had has have he her his in into is it its of on or our
    she that the their them they this to was were when which while who with without after before not no after also
    customer patient user reported reports report device unit pump product""".split()
)
WORD = re.compile(r"[a-z][a-z\-]{3,}")
# Recurring words leave out what a complaint says did NOT happen ("no patient injury reported", "without harm"): from a
# negation to the end of its clause. They also leave out clinical outcomes (the sentence on deaths, serious injuries and
# malfunctions above counts them from the complaint's own fields), complaint-handling boilerplate ("returned for
# evaluation") and identifiers (a lot or model number such as SAMPLE-ORBIT-300-LOT-003).
NEGATIONS = frozenset("no not without never none nor neither".split())
CLAUSE = re.compile(r"[.;:!?,()]|\bbut\b")
IDENTIFIER = re.compile(r"\S*\d\S*")
OUTCOME_WORDS = frozenset(
    """death deaths died dead fatal fatality injury injuries injured harm harmed serious malfunction malfunctions
    malfunctioned""".split()
)
FILLER_WORDS = frozenset("evaluation returned".split())


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _day(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc).date()
    return value


def _midnight(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)


def _group_key(grouping: str, row) -> tuple:
    if grouping == "problem":
        return (row.product_id, row.product_version_id, logic.problem_key(row.problem_code, row.complaint_type))
    if grouping == "type":
        kind = " ".join(str(row.complaint_type or "").split()).upper() or logic.UNSPECIFIED_PROBLEM
        return (row.product_id, row.product_version_id, kind[: logic.PROBLEM_KEY_LENGTH])
    return (row.product_id, row.product_version_id, None)


def _counted(db: Session, tenant_id: uuid.UUID, since: date, today: date):
    """Every complaint with a product from ``since`` to ``today`` (S5: a complaint dated in the future is in neither
    window), except those dismissed on the second look."""
    query = (
        db.query(
            Complaint.id,
            Complaint.business_id,
            Complaint.product_id,
            Complaint.product_version_id,
            Complaint.problem_code,
            Complaint.complaint_type,
            EVENT_AT.label("event_at"),
        )
        .outerjoin(
            ComplaintSecondLook,
            (ComplaintSecondLook.tenant_id == Complaint.tenant_id) & (ComplaintSecondLook.complaint_id == Complaint.id),
        )
        .filter(
            Complaint.tenant_id == tenant_id,
            Complaint.product_id.isnot(None),
            EVENT_AT >= _midnight(since),
            EVENT_AT < _midnight(today + timedelta(days=1)),
            (ComplaintSecondLook.decision.is_(None)) | (ComplaintSecondLook.decision != "DISMISSED"),
        )
    )
    return query.limit(READ_LIMIT + 1).all()


def _version_ages(db: Session, tenant_id: uuid.UUID, version_ids, today: date, unknown_of=()) -> dict:
    """Days since each version was released, else since its first complaint (it existed at least that long). PV-1 F12:
    the unknown version's age is per product, keyed ``(None, product id)`` for each product in ``unknown_of``."""
    ids = [item for item in version_ids if item is not None]
    ages: dict = {}
    if ids:
        for version_id, released in (
            db.query(ProductVersion.id, ProductVersion.release_timestamp)
            .filter(ProductVersion.tenant_id == tenant_id, ProductVersion.id.in_(ids))
            .all()
        ):
            if released is not None:
                ages[version_id] = (today - _day(released)).days
    unknown = [item for item in version_ids if item not in ages]
    if unknown:
        known_ids = [item for item in unknown if item is not None]
        query = db.query(Complaint.product_version_id, func.min(EVENT_AT)).filter(Complaint.tenant_id == tenant_id)
        rows = []
        if known_ids:
            rows += (
                query.filter(Complaint.product_version_id.in_(known_ids)).group_by(Complaint.product_version_id).all()
            )
        for version_id, first in rows:
            if first is not None:
                ages[version_id] = (today - _day(first)).days
    products = [item for item in unknown_of if item is not None]
    if products:
        for product_id, first in (
            db.query(Complaint.product_id, func.min(EVENT_AT))
            .filter(
                Complaint.tenant_id == tenant_id,
                Complaint.product_version_id.is_(None),
                Complaint.product_id.in_(products),
            )
            .group_by(Complaint.product_id)
            .all()
        ):
            if first is not None:
                ages[(None, product_id)] = (today - _day(first)).days
    return ages


def _lot_releases(db: Session, tenant_id: uuid.UUID, version_ids) -> dict:
    """``{version id: [(release day, quantity)]}``: each lot of the versions, released on its manufacture date (else
    the day it was recorded), with the devices it released (md43; None when not known)."""
    ids = [item for item in version_ids if item is not None]
    found: dict = defaultdict(list)
    if not ids:
        return found
    for version_id, effective, created, quantity in (
        db.query(LotBatch.product_version_id, LotBatch.effective_timestamp, LotBatch.created_at, LotBatch.quantity)
        .filter(LotBatch.tenant_id == tenant_id, LotBatch.product_version_id.in_(ids))
        .all()
    ):
        found[version_id].append((_day(effective or created), quantity))
    return found


def _previous_versions(db: Session, tenant_id: uuid.UUID, version_ids) -> dict:
    """``{version id: {id, name, released, this_released}}`` for each released version whose product has an earlier
    released version: the one it replaced (the latest released before it)."""
    ids = [item for item in version_ids if item is not None]
    if not ids:
        return {}
    mine = (
        db.query(ProductVersion.id, ProductVersion.product_id, ProductVersion.release_timestamp)
        .filter(ProductVersion.tenant_id == tenant_id, ProductVersion.id.in_(ids))
        .all()
    )
    released_products = {row.product_id for row in mine if row.release_timestamp is not None}
    if not released_products:
        return {}
    siblings = (
        db.query(
            ProductVersion.id,
            ProductVersion.product_id,
            ProductVersion.version_identifier,
            ProductVersion.release_timestamp,
        )
        .filter(
            ProductVersion.tenant_id == tenant_id,
            ProductVersion.product_id.in_(released_products),
            ProductVersion.release_timestamp.isnot(None),
        )
        .all()
    )
    found = {}
    for row in mine:
        if row.release_timestamp is None:
            continue
        released = _day(row.release_timestamp)
        earlier = [
            item
            for item in siblings
            if item.product_id == row.product_id and item.id != row.id and _day(item.release_timestamp) < released
        ]
        if earlier:
            prior = max(earlier, key=lambda item: _day(item.release_timestamp))
            found[row.id] = {
                "id": prior.id,
                "name": prior.version_identifier,
                "released": _day(prior.release_timestamp),
                "this_released": released,
            }
    return found


def _version_rows(db: Session, tenant_id: uuid.UUID, version_id: uuid.UUID, start: date, end: date) -> list:
    """The complaints of one version with events from ``start`` to ``end`` (both included), except those dismissed on
    the second look: the previous version's baseline."""
    return (
        db.query(
            Complaint.id,
            Complaint.business_id,
            Complaint.product_id,
            Complaint.product_version_id,
            Complaint.problem_code,
            Complaint.complaint_type,
            EVENT_AT.label("event_at"),
        )
        .outerjoin(
            ComplaintSecondLook,
            (ComplaintSecondLook.tenant_id == Complaint.tenant_id) & (ComplaintSecondLook.complaint_id == Complaint.id),
        )
        .filter(
            Complaint.tenant_id == tenant_id,
            Complaint.product_version_id == version_id,
            EVENT_AT >= _midnight(start),
            EVENT_AT < _midnight(end + timedelta(days=1)),
            (ComplaintSecondLook.decision.is_(None)) | (ComplaintSecondLook.decision != "DISMISSED"),
        )
        .limit(READ_LIMIT)
        .all()
    )


def version_changes(db: Session, tenant_id: uuid.UUID, version_ids) -> dict[str, list[dict]]:
    """``{version id: changes}``: the changes recorded as affecting a component of each version (a supplier change is
    recorded against the component it affects, as signals/service.py ``_related`` reads it), newest first.
    shortcut: a change linked to the whole product is left out, as it would show on every version; add it if a
    product-level change ever needs to show here."""
    from backend.app.db.models.foundation import Change, ProductComponent, RealityRelationship
    from backend.app.workflow.tasks import shorten

    if not version_ids:
        return {}
    rows = (
        db.query(ProductComponent.product_version_id, Change)
        .join(
            RealityRelationship,
            (RealityRelationship.tenant_id == ProductComponent.tenant_id)
            & (RealityRelationship.target_entity_type == "Component")
            & (RealityRelationship.target_entity_id == ProductComponent.component_id)
            & (RealityRelationship.source_entity_type == "Change"),
        )
        .join(
            Change,
            (Change.tenant_id == RealityRelationship.tenant_id) & (Change.id == RealityRelationship.source_entity_id),
        )
        .filter(
            ProductComponent.tenant_id == tenant_id,
            ProductComponent.product_version_id.in_([uuid.UUID(str(item)) for item in version_ids]),
        )
        .order_by(Change.event_timestamp.desc().nulls_last(), Change.change_identifier)
        .all()
    )
    found: dict[str, list[dict]] = defaultdict(list)
    for version_id, change in rows:
        listed = found[str(version_id)]
        if any(item["id"] == str(change.id) for item in listed):
            continue
        listed.append(
            {
                "id": str(change.id),
                "identifier": change.change_identifier,
                "change_type": change.change_type,
                "title": shorten(change.description, 200),
                "event_at": change.event_timestamp.isoformat() if change.event_timestamp else None,
            }
        )
    return dict(found)


def _scale(recent_units: float | None, baseline_units: float | None) -> float | None:
    """The recent window's unit-days over the baseline's, when both are known."""
    return recent_units / baseline_units if recent_units and baseline_units else None


def _names(db: Session, tenant_id: uuid.UUID, product_ids, version_ids) -> tuple[dict, dict]:
    products = {
        row.id: row
        for row in db.query(
            Product.id,
            Product.business_id,
            Product.product_identifier,
            Product.name,
            Product.product_family,
            Product.gmdn_term,
            Product.description,
            Product.device_category,
            Product.single_use,
            Product.use_period_days,
        )
        .filter(
            Product.tenant_id == tenant_id, Product.id.in_([item for item in product_ids if item] or [uuid.uuid4()])
        )
        .all()
    }
    versions = {
        row.id: row
        for row in db.query(ProductVersion.id, ProductVersion.business_id, ProductVersion.version_identifier)
        .filter(
            ProductVersion.tenant_id == tenant_id,
            ProductVersion.id.in_([item for item in version_ids if item] or [uuid.uuid4()]),
        )
        .all()
    }
    return products, versions


def _open_signals(db: Session, tenant_id: uuid.UUID) -> dict:
    """The open signals by (product, version, problem key), to show next to a matching group."""
    found: dict = defaultdict(list)
    for row in (
        db.query(
            Signal.id,
            Signal.business_id,
            Signal.status,
            Signal.product_id,
            Signal.product_version_id,
            Signal.problem_key,
        )
        .filter(Signal.tenant_id == tenant_id, Signal.status.in_(list(OPEN_SIGNAL_STATUSES)))
        .all()
    ):
        found[(row.product_id, row.product_version_id, row.problem_key)].append(
            {"id": str(row.id), "business_id": row.business_id, "status": row.status}
        )
    return found


# The trend boards already read in one readiness read (``shared_trend_boards``), by organization, grouping, product
# and day; None outside one.
_SHARED_BOARDS: ContextVar[dict | None] = ContextVar("shared_trend_boards", default=None)


@contextmanager
def shared_trend_boards():
    """Within the block, ``trend_board`` reads each board once: Readiness's trend check and its risk file check both
    read the board by problem (backend/app/readiness_home/service.py), and nothing in a readiness read changes a
    record. The callers only read the board they are given."""
    token = _SHARED_BOARDS.set({})
    try:
        yield
    finally:
        _SHARED_BOARDS.reset(token)


def trend_board(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    grouping: str = "version",
    product_id: uuid.UUID | None = None,
    today: date | None = None,
) -> dict:
    """The trend check of every group, most notable first, with what was counted."""
    grouping = grouping if grouping in trend_rules.GROUPINGS else "version"
    today = today or today_utc()
    shared = _SHARED_BOARDS.get()
    if shared is None:
        return _trend_board(db, tenant_id, grouping, product_id, today)
    key = (str(tenant_id), grouping, str(product_id) if product_id else None, today)
    if key not in shared:
        shared[key] = _trend_board(db, tenant_id, grouping, product_id, today)
    return shared[key]


def _trend_board(db: Session, tenant_id: uuid.UUID, grouping: str, product_id: uuid.UUID | None, today: date) -> dict:
    recent_start = today - timedelta(days=trend_rules.RECENT_DAYS - 1)
    since = recent_start - timedelta(days=trend_rules.HISTORY_DAYS)
    # Every group of the organization is checked, whatever the product filter: the adjusted values allow for all the
    # groups tested on the board (S4), so a product's row reads the same filtered or not.
    rows = _counted(db, tenant_id, since, today)
    truncated = len(rows) > READ_LIMIT
    rows = rows[:READ_LIMIT]
    events = service.linked_events(db, tenant_id)
    groups: dict = defaultdict(lambda: {"recent": [], "history": [], "listed": []})
    for row in rows:
        day = _day(row.event_at)
        if day is None:
            continue
        bucket = "recent" if day >= recent_start else "history"
        key = _group_key(grouping, row)
        if bucket == "recent":
            groups[key]["listed"].append(row)
        # S2: an event linked from several records counts once, by its earliest record; the others stay listed.
        if events.get(row.id, row.id) == row.id:
            groups[key][bucket].append(row)
    version_ids = {key[1] for key in groups}
    ages = _version_ages(db, tenant_id, version_ids, today, {key[0] for key in groups if key[1] is None})
    products, versions = _names(db, tenant_id, {key[0] for key in groups}, version_ids)
    signals = _open_signals(db, tenant_id) if grouping == "problem" else {}
    lots = _lot_releases(db, tenant_id, version_ids)
    previous = _previous_versions(db, tenant_id, version_ids)
    baselines: dict = {}
    found = []
    for key, bucket in groups.items():
        product_ref, version_ref, problem = key
        age = ages.get(version_ref if version_ref is not None else (None, product_ref))
        days_of_history = trend_rules.history_days(age)
        # S3: a version younger than the recent window is expected only the days it has existed (release day included).
        recent_days = trend_rules.RECENT_DAYS if age is None else min(trend_rules.RECENT_DAYS, age + 1)
        product = products.get(product_ref)
        version = versions.get(version_ref)
        # J27: a single-use product's units are used up, so the units ever released are not the units in the field.
        disposable, use_days = trend_rules.product_basis(product)
        # With a use period, a single-use product's units in the field are those still within it after release.
        by_units = not disposable or use_days is not None
        recent_units = trend_rules.unit_days(lots.get(version_ref), recent_start, today, use_days) if by_units else None
        counted_by_use = disposable and use_days is not None and recent_units is not None
        note = (
            (trend_rules.use_note(use_days) if counted_by_use else trend_rules.SINGLE_USE_NOTE) if disposable else None
        )
        against_previous = None
        prior = previous.get(version_ref)
        if prior:
            # The version it replaced, over the days before this version's release.
            window = min(trend_rules.HISTORY_DAYS, (prior["this_released"] - prior["released"]).days)
            if window >= trend_rules.MIN_HISTORY_DAYS:
                start = prior["this_released"] - timedelta(days=window)
                end = prior["this_released"] - timedelta(days=1)
                if prior["id"] not in baselines:
                    baselines[prior["id"]] = [
                        row
                        for row in _version_rows(db, tenant_id, prior["id"], start, end)
                        if events.get(row.id, row.id) == row.id
                    ]
                baseline = [row for row in baselines[prior["id"]] if _group_key(grouping, row)[2] == problem]
                against_previous = trend_rules.check(
                    len(bucket["recent"]),
                    len(baseline),
                    window,
                    scale=_scale(recent_units, trend_rules.unit_days(lots.get(prior["id"]), start, end, use_days)),
                    baseline=trend_rules.PREVIOUS_VERSION,
                    baseline_name=f"{product.name if product else 'Product'} {prior['name']}",
                    recent_days=recent_days,
                    basis_note=note,
                )
        history = [
            row for row in bucket["history"] if _day(row.event_at) >= recent_start - timedelta(days=days_of_history)
        ]
        history_units = (
            trend_rules.unit_days(
                lots.get(version_ref),
                recent_start - timedelta(days=days_of_history),
                recent_start - timedelta(days=1),
                use_days,
            )
            if days_of_history and by_units
            else None
        )
        own = trend_rules.check(
            len(bucket["recent"]),
            len(history),
            days_of_history,
            scale=_scale(recent_units, history_units),
            recent_days=recent_days,
            basis_note=note,
        )
        # J26: with both baselines, the stronger comparison, saying which.
        found.append((key, bucket, product, version, trend_rules.stronger(own, against_previous)))
    adjusted = trend_rules.adjust([entry[-1] for entry in found])
    tested = sum(1 for result in adjusted if result.p_value is not None)
    items = []
    for (key, bucket, product, version, _), result in zip(found, adjusted):
        product_ref, version_ref, problem = key
        if product_id is not None and product_ref != product_id:
            continue
        name = f"{product.name if product else 'Product'} {version.version_identifier if version else '(version not recorded)'}"
        if problem:
            label = "no problem code" if problem == logic.UNSPECIFIED_PROBLEM else problem.replace("_", " ").lower()
            name = f"{name} · {label}"
        recent = sorted(bucket["listed"], key=lambda row: _day(row.event_at), reverse=True)
        items.append(
            {
                "key": f"{product_ref}|{version_ref}|{problem or ''}",
                "product": {
                    "id": str(product_ref),
                    "business_id": getattr(product, "business_id", None),
                    # The organization's own identifier (SAMPLE-ORBIT-300): Home tells the sample's from yours by it.
                    "identifier": getattr(product, "product_identifier", None),
                    "name": getattr(product, "name", None),
                },
                "product_version": (
                    {
                        "id": str(version_ref),
                        "business_id": version.business_id,
                        "version_identifier": version.version_identifier,
                    }
                    if version
                    else None
                ),
                "problem": problem,
                "name": name,
                **result.as_dict(),
                # Recent records not counted on their own: linked to an earlier record of the same event (S2).
                "linked_records": len(bucket["listed"]) - len(bucket["recent"]),
                "sentence": trend_rules.sentence(name, result),
                "recent_complaints": [
                    {"id": str(row.id), "business_id": row.business_id} for row in recent[: CITED_MAX * 3]
                ],
                "open_signals": signals.get((product_ref, version_ref, problem), []),
                "_counted": len(bucket["recent"]) + len(bucket["history"]),
                "_recent_ids": [row.id for row in bucket["recent"]],
            }
        )
    # The lots of each group's recent complaints (0.10.72, B5: "lots 003-004" in the trend's sentence).
    wanted = {complaint_id for item in items for complaint_id in item["_recent_ids"]}
    lot_of = (
        dict(
            db.query(Complaint.id, LotBatch.lot_identifier)
            .join(LotBatch, (LotBatch.tenant_id == Complaint.tenant_id) & (LotBatch.id == Complaint.lot_batch_id))
            .filter(Complaint.tenant_id == tenant_id, Complaint.id.in_(wanted))
            .all()
        )
        if wanted
        else {}
    )
    behind = version_changes(
        db, tenant_id, {item["product_version"]["id"] for item in items if item["product_version"]}
    )
    for item in items:
        named = [lot_of[key] for key in item.pop("_recent_ids") if key in lot_of]
        item["lots"] = sorted(set(named))
        # How many of the recent complaints each lot has (0.10.77: "003 (4), 004 (4), 005 (1)").
        item["lot_counts"] = {lot: named.count(lot) for lot in item["lots"]}
        # The recorded changes to a component of the version (0.10.92, A10: the supplier change behind the lots).
        item["changes"] = behind.get(item["product_version"]["id"], []) if item["product_version"] else []
    items.sort(
        key=lambda item: (
            trend_rules.RESULT_ORDER[item["result"]],
            item["p_adjusted"] if item["p_adjusted"] is not None else 1.0,
            item["p_value"] if item["p_value"] is not None else 1.0,
            -item["recent"],
            item["name"],
        )
    )
    counted = sum(item.pop("_counted") for item in items)
    results = Counter(item["result"] for item in items)
    return {
        "grouping": grouping,
        "recent_days": trend_rules.RECENT_DAYS,
        "history_days": trend_rules.HISTORY_DAYS,
        "min_complaints": trend_rules.MIN_COMPLAINTS,
        "thresholds": {"significant": trend_rules.SIGNIFICANT_P, "elevated": trend_rules.ELEVATED_P},
        "summary": {
            "groups": len(items),
            # The groups assessed across the whole board, which the adjusted chances allow for.
            "groups_tested": tested,
            "complaints_counted": counted,
            "linked_records": sum(item["linked_records"] for item in items),
            **{code.lower(): results.get(code, 0) for code in trend_rules.RESULT_ORDER},
        },
        "truncated": truncated,
        "note": (
            "A check beside the count rule, never a verdict: it compares each group's last 30 days with its own "
            "history and, for a version that replaced another, with that version too, and shows the stronger "
            "comparison; it never raises a trend to review by itself. The result allows for the number of groups assessed at "
            "once (the adjusted chance), and an event linked from several records counts once. Where every lot has a "
            "quantity, the comparison follows the units in the field; elsewhere, and for single-use or consumable "
            "products, it counts by calendar days, so a version shipped in growing numbers can show a higher rate for "
            "that reason alone. Add lot quantities to your lot import to count per unit."
        ),
        "basis": {
            "units": sum(1 for item in items if item["basis"] == trend_rules.UNITS),
            "time": sum(1 for item in items if item["basis"] == trend_rules.TIME and not item["basis_note"]),
            "single_use": sum(1 for item in items if item["basis"] == trend_rules.TIME and item["basis_note"]),
        },
        "items": items,
    }


def trend_for_signal(db: Session, signal: Signal, today: date | None = None) -> dict | None:
    """The trend check of the signal's own group: its product version and problem, or the whole version when the
    signal's complaints are about several problems (a signal raised by hand). Read from the organization's whole
    board, so its adjusted value is the board's (S4)."""
    if signal.product_id is None:
        return None
    grouping = "problem" if signal.problem_key else "version"
    board = trend_board(db, signal.tenant_id, grouping=grouping, today=today)
    key = f"{signal.product_id}|{signal.product_version_id}|{signal.problem_key or ''}"
    return next((item for item in board["items"] if item["key"] == key), None)


# ------------------------------------------------------------------------------------------------------ summary


def _signal_complaints(db: Session, signal: Signal) -> list:
    return (
        db.query(Complaint, LotBatch.lot_identifier)
        .join(SignalComplaint, service.LINKED_COMPLAINT)
        .outerjoin(LotBatch, (LotBatch.tenant_id == Complaint.tenant_id) & (LotBatch.id == Complaint.lot_batch_id))
        .filter(SignalComplaint.tenant_id == signal.tenant_id, SignalComplaint.signal_id == signal.id)
        .order_by(EVENT_AT.desc(), Complaint.id)
        .all()
    )


def _ref(complaint: Complaint) -> str:
    return complaint.business_id or complaint.complaint_identifier or str(complaint.id)


def _cite(rows) -> list[str]:
    return [_ref(row) for row in rows][:CITED_MAX]


def _words(text: str | None) -> set[str]:
    """The words a complaint description stands for in "Recurring words" (see NEGATIONS)."""
    found: set[str] = set()
    for clause in CLAUSE.split(IDENTIFIER.sub(" ", str(text or "").lower())):
        for token in clause.split():
            if token in NEGATIONS or token.endswith("n't"):
                break
            for word in WORD.findall(token):
                word = word.strip("-")
                if word not in STOPWORDS and word not in OUTCOME_WORDS and word not in FILLER_WORDS:
                    found.add(word)
    return found


def records_summary(db: Session, signal: Signal) -> dict:
    """A signal's complaints summarized from their fields; every sentence cites the complaints it rests on."""
    rows = _signal_complaints(db, signal)
    complaints = [row for row, _ in rows]
    lots = {row.id: lot for row, lot in rows}
    total = len(complaints)
    sentences: list[dict] = []
    if not total:
        return {"author": "RECORDS", "complaints": 0, "sentences": []}

    def add(text: str, cited) -> None:
        sentences.append({"text": text, "complaints": _cite(cited)})

    days = sorted(_day(row.event_timestamp or row.complaint_timestamp or row.created_at) for row in complaints)
    if signal.problem_key and signal.problem_key != logic.UNSPECIFIED_PROBLEM:
        about = f"about {signal.problem_key.replace('_', ' ').lower()}"
    elif signal.problem_key == logic.UNSPECIFIED_PROBLEM:
        about = "without a problem code"
    else:
        about = "about several problems"
    add(
        f"{total:,} complaint{'s' if total != 1 else ''} {about} between {days[0].isoformat()} and {days[-1].isoformat()}.",
        complaints,
    )
    deaths = [row for row in complaints if row.death]
    injuries = [row for row in complaints if row.serious_injury]
    malfunctions = [row for row in complaints if row.malfunction]
    harm = []
    if deaths:
        harm.append(f"{len(deaths):,} report a death")
    if injuries:
        harm.append(f"{len(injuries):,} a serious injury")
    if malfunctions:
        harm.append(f"{len(malfunctions):,} a malfunction")
    if harm:
        add("; ".join(harm) + ".", deaths + injuries + malfunctions)
    else:
        add("None reports a death, a serious injury or a malfunction.", complaints)
    by_lot = Counter(lot for lot in lots.values() if lot)
    if by_lot:
        lot, count = by_lot.most_common(1)[0]
        named = sum(by_lot.values())
        if count >= 2:
            add(
                f"{count:,} of the {named:,} complaints that name a lot name lot {lot}"
                + (f"; {len(by_lot)} lots in all." if len(by_lot) > 1 else "."),
                [row for row in complaints if lots.get(row.id) == lot],
            )
    by_market = Counter(" ".join(str(row.country or "").split()) for row in complaints if row.country)
    if by_market:
        market, count = by_market.most_common(1)[0]
        add(
            f"{count:,} from {market}" + (f"; {len(by_market):,} markets in all." if len(by_market) > 1 else "."),
            [row for row in complaints if " ".join(str(row.country or "").split()) == market],
        )
    word_rows: dict[str, list] = defaultdict(list)
    for row in complaints:
        for word in _words(row.description):
            word_rows[word].append(row)
    common = sorted(
        ((word, cited) for word, cited in word_rows.items() if len(cited) >= max(2, round(total * 0.4))),
        key=lambda pair: (-len(pair[1]), pair[0]),
    )[:4]
    if common:
        add(
            "Recurring words: " + ", ".join(f'"{word}" ({len(cited):,})' for word, cited in common) + ".",
            common[0][1],
        )
    coded_away = [
        row for row in complaints if review_rules.nff_family(row.problem_code, row.complaint_type, row.status)
    ]
    if coded_away:
        add(f"{len(coded_away)} coded No Fault Found or User Error.", coded_away)
    return {"author": "RECORDS", "complaints": total, "sentences": sentences}


AI_SYSTEM = (
    "You summarize what a group of medical device complaints has in common, for a quality professional. Use only the "
    "complaints given. Write at most 4 short factual sentences. Every sentence must cite the complaint IDs it rests on, "
    "exactly as given. Never state or suggest a root cause, a conclusion, reportability or what to decide; describe "
    'what the records say. Reply as JSON: {"sentences": [{"text": "...", "complaints": ["ID", ...]}]}.'
)
# A summary describes what the records say; any causal wording is dropped (stricter than the case analysis check,
# which must be able to discuss explanations).
CAUSAL_WORDING = re.compile(
    r"(?i)\b(caus(e|es|ed|ing)|due to|because|owing to|result(s|ed)? (of|from|in)|as a result|led to|leads to|"
    r"root[- ]cause|attributabl[ey]|responsible for|triggered by|stems? from)\b"
)
AI_PROVIDER = "mdarix-signal-summary"
AI_VERSION = "R1-MVP-P4-SignalSummary-v1"


def ai_summary(db: Session, signal: Signal, *, actor_ref: str, provider=None) -> dict:
    """The language model's summary of the signal's complaints, every sentence checked; the records summary with the
    reason when the model is off, unavailable, over budget or keeps nothing."""
    from ai.execution import record_ai_execution
    from genai.provider import GenAIProvider, GenAIUnavailable
    from investigator.model_provider import ModelAnalysisUnavailable, asserts_causality_or_decision, parse_json_reply

    fallback = records_summary(db, signal)
    rows = [row for row, _ in _signal_complaints(db, signal)][:SUMMARY_COMPLAINTS_MAX]
    if not rows:
        return {**fallback, "ai": {"status": "NOT_RUN", "reason": "The signal has no complaints"}}
    known = {_ref(row) for row in rows}
    evidence = [
        {
            "id": _ref(row),
            "text": " ".join(
                part
                for part in (
                    str(row.description or ""),
                    f"Problem code: {row.problem_code}." if row.problem_code else "",
                    f"Country: {row.country}." if row.country else "",
                    "Death reported." if row.death else "",
                    "Serious injury reported." if row.serious_injury else "",
                    "Malfunction reported." if row.malfunction else "",
                )
                if part
            ),
        }
        for row in rows
    ]
    provider = provider or GenAIProvider()
    try:
        result = provider.complete(
            f"Summarize what these {len(rows)} complaints about {signal.problem_key or 'one problem'} have in common.",
            {"signal": signal.business_id},
            system=AI_SYSTEM,
            json_output=True,
            max_output_tokens=800,
            evidence=evidence,
        )
    except GenAIUnavailable as exc:
        return {**fallback, "ai": {"status": "REFUSED", "reason": exc.code, "message": exc.user_message}}
    answer = (result.output or {}).get("answer")
    if not answer:
        return {
            **fallback,
            "ai": {"status": (result.output or {}).get("status") or "NO_ANSWER", "reason": "PROVIDER_NOT_CONFIGURED"},
        }
    try:
        parsed = parse_json_reply(answer)
    except ModelAnalysisUnavailable as exc:
        return {**fallback, "ai": {"status": "UNREADABLE", "reason": exc.reason}}
    kept, dropped = [], []
    for item in (parsed.get("sentences") or [])[:4]:
        text = " ".join(str((item or {}).get("text") or "").split())
        cited = [str(ref).strip() for ref in (item or {}).get("complaints") or [] if str(ref).strip()]
        if not text or not cited:
            dropped.append({"text": text, "reason": "NO_CITATION"})
        elif any(ref not in known for ref in cited):
            dropped.append({"text": text, "reason": "CITES_UNKNOWN_COMPLAINT"})
        elif CAUSAL_WORDING.search(text) or asserts_causality_or_decision(text):
            dropped.append({"text": text, "reason": "CAUSAL_OR_DECISION_CLAIM"})
        else:
            kept.append({"text": text, "complaints": cited[:CITED_MAX]})
    execution = record_ai_execution(
        db,
        signal.tenant_id,
        provider=AI_PROVIDER,
        model_name=result.model,
        model_version=result.model_version,
        prompt_template_version=AI_VERSION,
        orchestration_version=AI_VERSION,
        context_refs={"signal_id": str(signal.id), "signal": signal.business_id},
        evidence_refs={"complaints": sorted(known)},
        structured_output={
            "sentences": kept,
            "dropped": dropped,
            # Who wrote it, for the automatic trust check (the provider column names this feature).
            "model": {"provider": result.provider, "model": result.model},
        },
        validation_status="VALIDATED" if kept else "REJECTED",
        latency_ms=result.latency_ms,
        requestor_ref=str(actor_ref),
    )
    if not kept:
        return {
            **fallback,
            "ai": {
                "status": "NOTHING_KEPT",
                "reason": "Every sentence failed a check",
                "dropped": dropped,
                "trust": getattr(execution, "trust", None),
            },
        }
    return {
        "author": "AI",
        "complaints": fallback["complaints"],
        "sentences": kept,
        "records": fallback["sentences"],
        "ai": {
            "status": "COMPLETED",
            "provider": result.provider,
            "model": result.model,
            "ai_execution_id": str(execution.id),
            "dropped": dropped,
            "trust": getattr(execution, "trust", None),
            "label": "AI interpretation: written by AI from the complaints cited, checked sentence by sentence; a "
            "person decides",
        },
    }
