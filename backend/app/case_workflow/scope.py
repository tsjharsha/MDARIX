"""A case's scope: what it investigates (the question, product versions, included and excluded complaints, lots,
markets, failure modes, dates and objectives), kept as versions in ``investigation_scope_versions``.

The latest version is the current scope; older versions are never changed. Saving a scope writes a new version, makes
the case's question the scope's question and keeps the case's complaint links (``investigation_complaints``) equal to
the included complaints, so every screen and report that reads those links sees the scope.

The pure functions at the top (diff, warnings, conflicts) need no database.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.business_ids import as_uuid, wanted_ids
from backend.app.db.models.case_scope import InvestigationScopeVersion

# Who wrote a version when no person did (version 1 of cases that existed before scopes, written by the migration).
SYSTEM_PREFIX = "system"
SYSTEM_NAME = "MDARIX"


# ------------------------------------------------------------------------------------------------- pure functions


def id_list(values) -> list[str]:
    """Distinct UUIDs as strings, in their first order; empty and malformed values are dropped."""
    seen: list[str] = []
    for value in values or ():
        key = as_uuid(value)
        if key is not None and str(key) not in seen:
            seen.append(str(key))
    return seen


def excluded_list(items) -> list[dict]:
    """``[{complaint_id, reason}]`` with one entry per complaint (the first wins) and the reason trimmed."""
    result: list[dict] = []
    seen: set[str] = set()
    for item in items or ():
        data = item if isinstance(item, dict) else {}
        key = as_uuid(data.get("complaint_id"))
        if key is None or str(key) in seen:
            continue
        seen.add(str(key))
        result.append({"complaint_id": str(key), "reason": " ".join(str(data.get("reason") or "").split())})
    return result


def excluded_lots(items) -> list[dict]:
    """``[{lot_id, reason}]`` with one entry per lot (the first wins) and the reason trimmed (tr08)."""
    result: list[dict] = []
    for item in items or ():
        data = item if isinstance(item, dict) else {}
        key = as_uuid(data.get("lot_id"))
        if key is not None and str(key) not in {entry["lot_id"] for entry in result}:
            result.append({"lot_id": str(key), "reason": " ".join(str(data.get("reason") or "").split())})
    return result


def text_list(values, *, limit: int = 120) -> list[str]:
    """Distinct non-empty strings (compared without case), trimmed, in their first order."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        text = " ".join(str(value or "").split())[:limit]
        if text and text.lower() not in seen:
            seen.add(text.lower())
            result.append(text)
    return result


def conflicting_complaints(included_ids, excluded) -> list[str]:
    """Complaints both included and excluded (a scope must say one or the other)."""
    excluded_ids = {item["complaint_id"] for item in excluded_list(excluded)}
    return [complaint_id for complaint_id in id_list(included_ids) if complaint_id in excluded_ids]


def _question_key(text: str | None) -> str:
    return " ".join(str(text or "").split())


def scope_diff(previous: dict | None, current: dict) -> dict:
    """What changed from ``previous`` (None for the first version) to ``current``: complaints added to and removed from
    the included set, complaints newly excluded, versions added and removed, and whether the question changed. Ids are
    strings, in the order of the version they come from."""
    previous = previous or {}
    before_included = set(id_list(previous.get("included_complaint_ids")))
    after_included = id_list(current.get("included_complaint_ids"))
    before_excluded = {item["complaint_id"] for item in excluded_list(previous.get("excluded_complaints"))}
    before_versions = set(id_list(previous.get("product_version_ids")))
    after_versions = id_list(current.get("product_version_ids"))
    return {
        "added_complaints": [item for item in after_included if item not in before_included],
        "removed_complaints": [
            item for item in id_list(previous.get("included_complaint_ids")) if item not in set(after_included)
        ],
        "newly_excluded": [
            item["complaint_id"]
            for item in excluded_list(current.get("excluded_complaints"))
            if item["complaint_id"] not in before_excluded
        ],
        "versions_added": [item for item in after_versions if item not in before_versions],
        "versions_removed": [
            item for item in id_list(previous.get("product_version_ids")) if item not in set(after_versions)
        ],
        "question_changed": bool(previous)
        and _question_key(previous.get("question")) != _question_key(current.get("question")),
    }


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def scope_warnings(complaints: list[dict], version_ids, date_from, date_to) -> list[str]:
    """Things worth a second look but not wrong: an included complaint on a version outside the chosen versions, or
    dated outside the chosen dates. Each complaint is ``{label, product_version_id, date}``."""
    versions = set(id_list(version_ids))
    start, end = _as_date(date_from), _as_date(date_to)
    warnings: list[str] = []
    for complaint in complaints:
        label = complaint.get("label") or "A complaint"
        version = as_uuid(complaint.get("product_version_id"))
        if versions and version is not None and str(version) not in versions:
            warnings.append(f"{label} is on a product version outside the chosen versions")
        when = _as_date(complaint.get("date"))
        if when is not None and start is not None and when < start:
            warnings.append(f"{label} is dated {when.isoformat()}, before the scope starts ({start.isoformat()})")
        if when is not None and end is not None and when > end:
            warnings.append(f"{label} is dated {when.isoformat()}, after the scope ends ({end.isoformat()})")
    return warnings


def diff_counts(diff: dict) -> dict:
    """The diff as counts, for the audit trail."""
    return {
        key: (len(value) if isinstance(value, list) else bool(value))
        for key, value in diff.items()
        if key != "question_changed"
    } | {"question_changed": bool(diff.get("question_changed"))}


# ---------------------------------------------------------------------------------------------------- database


def refuse(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def versions_of(db: Session, tenant_id, investigation_id) -> list[InvestigationScopeVersion]:
    """Every scope version of the case, newest first."""
    return (
        db.query(InvestigationScopeVersion)
        .filter(
            InvestigationScopeVersion.tenant_id == as_uuid(tenant_id),
            InvestigationScopeVersion.investigation_id == as_uuid(investigation_id),
        )
        .order_by(InvestigationScopeVersion.version.desc())
        .all()
    )


def latest_version(db: Session, tenant_id, investigation_id) -> InvestigationScopeVersion | None:
    return (
        db.query(InvestigationScopeVersion)
        .filter(
            InvestigationScopeVersion.tenant_id == as_uuid(tenant_id),
            InvestigationScopeVersion.investigation_id == as_uuid(investigation_id),
        )
        .order_by(InvestigationScopeVersion.version.desc())
        .first()
    )


def as_data(row: InvestigationScopeVersion) -> dict:
    """A stored version as plain data (ids as strings)."""
    return {
        "version": row.version,
        "question": row.question,
        "product_version_ids": id_list(row.product_version_ids),
        "included_complaint_ids": id_list(row.included_complaint_ids),
        "excluded_complaints": excluded_list(row.excluded_complaints),
        "lot_ids": id_list(row.lot_ids),
        "excluded_lots": excluded_lots(row.excluded_lots),
        "lot_impact": row.lot_impact,
        "markets": text_list(row.markets),
        "failure_mode_ids": id_list(row.failure_mode_ids),
        "date_from": row.date_from,
        "date_to": row.date_to,
        "objectives": row.objectives,
        "change_reason": row.change_reason,
        "reviews_must_restart": bool(row.reviews_must_restart),
        "conclusions_invalidated": bool(row.conclusions_invalidated),
        "created_by": row.created_by,
        "created_role": row.created_role,
        "created_at": row.created_at,
    }


def linked_complaint_ids(db: Session, case) -> list[str]:
    from backend.app.db.models.foundation import InvestigationComplaint

    rows = (
        db.query(InvestigationComplaint.complaint_id)
        .filter(InvestigationComplaint.tenant_id == case.tenant_id, InvestigationComplaint.investigation_id == case.id)
        .order_by(InvestigationComplaint.created_at, InvestigationComplaint.complaint_id)
        .all()
    )
    return id_list(row[0] for row in rows)


def versions_of_complaints(db: Session, tenant_id, complaint_ids) -> list[str]:
    """The distinct product versions the complaints are on."""
    from backend.app.db.models.foundation import Complaint

    ids = wanted_ids(complaint_ids)
    if not ids:
        return []
    rows = (
        db.query(Complaint.product_version_id)
        .filter(
            Complaint.tenant_id == as_uuid(tenant_id),
            Complaint.id.in_(list(ids)),
            Complaint.product_version_id.isnot(None),
        )
        .distinct()
        .all()
    )
    return sorted(id_list(row[0] for row in rows))


def derived_scope(db: Session, case) -> dict:
    """The scope of a case that has no stored version yet (created before scopes, or by an import): its question, its
    linked complaints and their versions. Shown as version 0; the first save writes version 1."""
    included = linked_complaint_ids(db, case)
    return {
        "version": 0,
        "question": case.investigation_question,
        "product_version_ids": versions_of_complaints(db, case.tenant_id, included),
        "included_complaint_ids": included,
        "excluded_complaints": [],
        "lot_ids": [],
        "excluded_lots": [],
        "lot_impact": None,
        "markets": [],
        "failure_mode_ids": [],
        "date_from": None,
        "date_to": None,
        "objectives": None,
        "change_reason": None,
        "reviews_must_restart": False,
        "conclusions_invalidated": False,
        "created_by": None,
        "created_role": None,
        "created_at": None,
    }


def current_scope(db: Session, case) -> dict:
    row = latest_version(db, case.tenant_id, case.id)
    return as_data(row) if row is not None else derived_scope(db, case)


def write_version(
    db: Session, case, data: dict, *, actor_ref: str, actor_role: str | None, now: datetime
) -> InvestigationScopeVersion:
    """Store ``data`` as the case's next scope version. The caller holds the case row lock. Does not commit."""
    highest = (
        db.query(func.max(InvestigationScopeVersion.version))
        .filter(
            InvestigationScopeVersion.tenant_id == case.tenant_id,
            InvestigationScopeVersion.investigation_id == case.id,
        )
        .scalar()
    )
    row = InvestigationScopeVersion(
        id=uuid.uuid4(),
        tenant_id=case.tenant_id,
        investigation_id=case.id,
        version=int(highest or 0) + 1,
        question=str(data.get("question") or case.investigation_question or "").strip(),
        product_version_ids=id_list(data.get("product_version_ids")),
        included_complaint_ids=id_list(data.get("included_complaint_ids")),
        excluded_complaints=excluded_list(data.get("excluded_complaints")),
        lot_ids=id_list(data.get("lot_ids")),
        excluded_lots=excluded_lots(data.get("excluded_lots")),
        lot_impact=data.get("lot_impact"),
        markets=text_list(data.get("markets")),
        failure_mode_ids=id_list(data.get("failure_mode_ids")),
        date_from=data.get("date_from"),
        date_to=data.get("date_to"),
        objectives=(str(data.get("objectives")).strip() or None) if data.get("objectives") else None,
        change_reason=(str(data.get("change_reason")).strip() or None) if data.get("change_reason") else None,
        reviews_must_restart=bool(data.get("reviews_must_restart")),
        conclusions_invalidated=bool(data.get("conclusions_invalidated")),
        created_by=str(actor_ref),
        created_role=actor_role,
        created_at=now,
    )
    db.add(row)
    db.flush()
    if row.reviews_must_restart:
        # The case's risk and regulatory reviews were of the earlier scope: they are superseded with this version
        # (backend/app/case_reviews/service.py). Never fails the save.
        from backend.app.case_reviews.service import restart_reviews

        restart_reviews(db, case, version=row.version, actor_ref=actor_ref, actor_role=actor_role, now=now)
    return row


def lots_of_complaints(db: Session, tenant_id, complaint_ids) -> list[str]:
    """The distinct lots the complaints name."""
    from backend.app.db.models.foundation import Complaint

    ids = wanted_ids(complaint_ids)
    if not ids:
        return []
    rows = (
        db.query(Complaint.lot_batch_id)
        .filter(
            Complaint.tenant_id == as_uuid(tenant_id),
            Complaint.id.in_(list(ids)),
            Complaint.lot_batch_id.isnot(None),
        )
        .distinct()
        .all()
    )
    return sorted(id_list(row[0] for row in rows))


def first_version(
    db: Session,
    case,
    *,
    complaint_ids,
    actor_ref: str,
    actor_role: str | None,
    now: datetime,
    with_lots: bool = False,
) -> InvestigationScopeVersion:
    """Version 1 of a newly opened case: its question, the complaints it was opened with and their versions, and with
    ``with_lots`` the lots those complaints name (a case opened from a signal in one step)."""
    included = id_list(complaint_ids)
    data = {
        "question": case.investigation_question,
        "included_complaint_ids": included,
        "product_version_ids": versions_of_complaints(db, case.tenant_id, included),
    }
    if with_lots:
        data["lot_ids"] = lots_of_complaints(db, case.tenant_id, included)
    return write_version(
        db,
        case,
        data,
        actor_ref=actor_ref,
        actor_role=actor_role,
        now=now,
    )


def record_question_change(
    db: Session, case, *, reason: str, actor_ref: str, actor_role: str | None, now: datetime
) -> InvestigationScopeVersion:
    """A new scope version when the case's question is edited elsewhere: the current scope with the new question,
    the edit's reason as its change reason. Does not commit."""
    data = current_scope(db, case)
    data.update({"question": case.investigation_question, "change_reason": reason})
    data["reviews_must_restart"] = False
    data["conclusions_invalidated"] = False
    return write_version(db, case, data, actor_ref=actor_ref, actor_role=actor_role, now=now)


def sync_complaint_links(db: Session, case, included_ids, now: datetime) -> tuple[list[str], list[str]]:
    """Make the case's complaint links equal to the included complaints: link the missing ones, remove the links of
    complaints no longer included. Returns (linked, unlinked). Does not commit."""
    from backend.app.db.models.foundation import InvestigationComplaint

    wanted = id_list(included_ids)
    current = linked_complaint_ids(db, case)
    linked = [item for item in wanted if item not in set(current)]
    unlinked = [item for item in current if item not in set(wanted)]
    for complaint_id in linked:
        db.add(
            InvestigationComplaint(
                id=uuid.uuid4(),
                tenant_id=case.tenant_id,
                investigation_id=case.id,
                complaint_id=uuid.UUID(complaint_id),
                created_at=now,
            )
        )
    if unlinked:
        db.query(InvestigationComplaint).filter(
            InvestigationComplaint.tenant_id == case.tenant_id,
            InvestigationComplaint.investigation_id == case.id,
            InvestigationComplaint.complaint_id.in_([uuid.UUID(item) for item in unlinked]),
        ).delete(synchronize_session=False)
    if linked or unlinked:
        db.flush()
    return linked, unlinked


def check_references(db: Session, case, data: dict) -> list[dict]:
    """Every id of the scope must be the organization's own; complaints and versions must be of the case's product.
    Raises 422 otherwise. Returns the included complaints as ``{id, label, product_version_id, date}`` for the
    warnings."""
    from backend.app.db.models.foundation import Complaint, FailureMode, LotBatch, ProductVersion

    tenant_id = case.tenant_id
    versions = id_list(data.get("product_version_ids"))
    if versions:
        found = {
            str(row[0])
            for row in db.query(ProductVersion.id).filter(
                ProductVersion.tenant_id == tenant_id,
                ProductVersion.product_id == case.product_id,
                ProductVersion.id.in_([uuid.UUID(item) for item in versions]),
            )
        }
        if len(found) != len(versions):
            raise refuse(
                422, "VERSION_NOT_FOR_PRODUCT", "Every product version must be a version of this case's product"
            )
    included = id_list(data.get("included_complaint_ids"))
    excluded = [item["complaint_id"] for item in excluded_list(data.get("excluded_complaints"))]
    complaints = id_list([*included, *excluded])
    rows = {}
    if complaints:
        rows = {
            str(row.id): row
            for row in db.query(Complaint).filter(
                Complaint.tenant_id == tenant_id,
                Complaint.product_id == case.product_id,
                Complaint.id.in_([uuid.UUID(item) for item in complaints]),
            )
        }
        if len(rows) != len(complaints):
            raise refuse(
                422,
                "COMPLAINT_NOT_FOR_PRODUCT",
                "Every complaint must belong to this case's product in your organization",
            )
    for model, key, code, label in (
        (LotBatch, "lot_ids", "LOT_NOT_FOUND", "lot"),
        (FailureMode, "failure_mode_ids", "FAILURE_MODE_NOT_FOUND", "failure mode"),
    ):
        ids = id_list(data.get(key))
        if not ids:
            continue
        found = {
            str(row[0])
            for row in db.query(model.id).filter(
                model.tenant_id == tenant_id, model.id.in_([uuid.UUID(item) for item in ids])
            )
        }
        if len(found) != len(ids):
            raise refuse(422, code, f"Every {label} must be one of your organization's records")
    return [
        {
            "id": complaint_id,
            "label": rows[complaint_id].business_id or rows[complaint_id].complaint_identifier,
            "product_version_id": rows[complaint_id].product_version_id,
            "date": rows[complaint_id].event_timestamp or rows[complaint_id].complaint_timestamp,
        }
        for complaint_id in included
    ]


# ------------------------------------------------------------------------------------------------ serialization


def creator_name(names: dict[str, str], created_by: str | None) -> str | None:
    if not created_by:
        return None
    if str(created_by).startswith(SYSTEM_PREFIX):
        return SYSTEM_NAME
    key = as_uuid(created_by)
    return names.get(str(key)) if key is not None else None


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def summary(data: dict, names: dict[str, str]) -> dict:
    """One line of the version history."""
    return {
        "version": data["version"],
        "created_at": _iso(data.get("created_at")),
        "created_by_name": creator_name(names, data.get("created_by")),
        "created_role": data.get("created_role"),
        "change_reason": data.get("change_reason"),
        "reviews_must_restart": bool(data.get("reviews_must_restart")),
        "conclusions_invalidated": bool(data.get("conclusions_invalidated")),
    }


def names_for(control_db: Session | None, tenant_id, refs) -> dict[str, str]:
    if control_db is None:
        return {}
    from backend.app.workflow.people import names_by_id

    try:
        return names_by_id(control_db, tenant_id, refs)
    except Exception:
        return {}


def references(db: Session, tenant_id, data_list: list[dict]) -> dict:
    """Every record the versions name, read in one query per kind."""
    from backend.app.db.models.foundation import Complaint, FailureMode, LotBatch, ProductVersion

    tenant = as_uuid(tenant_id)
    complaint_ids = wanted_ids(
        [
            *(item for data in data_list for item in data.get("included_complaint_ids") or ()),
            *(item["complaint_id"] for data in data_list for item in data.get("excluded_complaints") or ()),
        ]
    )
    complaints = (
        {
            str(row.id): row
            for row in db.query(Complaint).filter(Complaint.tenant_id == tenant, Complaint.id.in_(list(complaint_ids)))
        }
        if complaint_ids
        else {}
    )
    version_ids = wanted_ids(
        [
            *(item for data in data_list for item in data.get("product_version_ids") or ()),
            *(row.product_version_id for row in complaints.values()),
        ]
    )
    versions = (
        {
            str(row.id): row
            for row in db.query(ProductVersion).filter(
                ProductVersion.tenant_id == tenant, ProductVersion.id.in_(list(version_ids))
            )
        }
        if version_ids
        else {}
    )
    lot_ids = wanted_ids(
        [
            *(item for data in data_list for item in data.get("lot_ids") or ()),
            *(item["lot_id"] for data in data_list for item in data.get("excluded_lots") or ()),
        ]
    )
    lots = (
        {
            str(row.id): row
            for row in db.query(LotBatch).filter(LotBatch.tenant_id == tenant, LotBatch.id.in_(list(lot_ids)))
        }
        if lot_ids
        else {}
    )
    mode_ids = wanted_ids(item for data in data_list for item in data.get("failure_mode_ids") or ())
    modes = (
        {
            str(row.id): row
            for row in db.query(FailureMode).filter(FailureMode.tenant_id == tenant, FailureMode.id.in_(list(mode_ids)))
        }
        if mode_ids
        else {}
    )
    return {"complaints": complaints, "versions": versions, "lots": lots, "failure_modes": modes}


def _version_item(versions: dict, version_id) -> dict:
    row = versions.get(str(version_id))
    return {
        "id": str(version_id),
        "business_id": row.business_id if row is not None else None,
        "version_identifier": row.version_identifier if row is not None else None,
    }


def _complaint_item(refs: dict, complaint_id) -> dict:
    row = refs["complaints"].get(str(complaint_id))
    if row is None:
        return {
            "id": str(complaint_id),
            "business_id": None,
            "complaint_identifier": None,
            "description": None,
            "severity": None,
            "product_version": None,
        }
    version = refs["versions"].get(str(row.product_version_id)) if row.product_version_id else None
    return {
        "id": str(row.id),
        "business_id": row.business_id,
        "complaint_identifier": row.complaint_identifier,
        "description": row.description,
        "severity": row.severity,
        "product_version": (
            {"business_id": version.business_id, "version_identifier": version.version_identifier}
            if version is not None
            else None
        ),
    }


def serialize(data: dict, refs: dict, names: dict[str, str]) -> dict:
    """A scope version as the screens show it: every record with its business id and name."""
    lots, modes = refs["lots"], refs["failure_modes"]
    return {
        "version": data["version"],
        "question": data.get("question"),
        "product_versions": [_version_item(refs["versions"], item) for item in data.get("product_version_ids") or ()],
        "included_complaints": [_complaint_item(refs, item) for item in data.get("included_complaint_ids") or ()],
        "excluded_complaints": [
            {**_complaint_item(refs, item["complaint_id"]), "reason": item.get("reason")}
            for item in data.get("excluded_complaints") or ()
        ],
        "lots": [
            {
                "id": str(item),
                "business_id": lots[str(item)].business_id if str(item) in lots else None,
                "lot_identifier": lots[str(item)].lot_identifier if str(item) in lots else None,
            }
            for item in data.get("lot_ids") or ()
        ],
        # Lots a person left out, with the reason (the lot impact list, tr08).
        "excluded_lots": [
            {
                "id": item["lot_id"],
                "lot_identifier": lots[item["lot_id"]].lot_identifier if item["lot_id"] in lots else None,
                "reason": item.get("reason"),
            }
            for item in data.get("excluded_lots") or ()
        ],
        "markets": list(data.get("markets") or ()),
        "failure_modes": [
            {
                "id": str(item),
                "business_id": modes[str(item)].business_id if str(item) in modes else None,
                "identifier": modes[str(item)].failure_mode_identifier if str(item) in modes else None,
                "name": modes[str(item)].name if str(item) in modes else None,
            }
            for item in data.get("failure_mode_ids") or ()
        ],
        "date_from": _iso(data.get("date_from")),
        "date_to": _iso(data.get("date_to")),
        "objectives": data.get("objectives"),
        "change_reason": data.get("change_reason"),
        "reviews_must_restart": bool(data.get("reviews_must_restart")),
        "conclusions_invalidated": bool(data.get("conclusions_invalidated")),
        "created_at": _iso(data.get("created_at")),
        "created_by_name": creator_name(names, data.get("created_by")),
    }


def labelled_diff(diff: dict, refs: dict) -> dict:
    """The diff with each complaint and version as ``{id, business_id, label}``."""

    def complaint(item):
        row = refs["complaints"].get(str(item))
        return {
            "id": str(item),
            "business_id": row.business_id if row is not None else None,
            "label": row.complaint_identifier if row is not None else None,
        }

    def version(item):
        row = refs["versions"].get(str(item))
        return {
            "id": str(item),
            "business_id": row.business_id if row is not None else None,
            "label": row.version_identifier if row is not None else None,
        }

    return {
        "added_complaints": [complaint(item) for item in diff["added_complaints"]],
        "removed_complaints": [complaint(item) for item in diff["removed_complaints"]],
        "newly_excluded": [complaint(item) for item in diff["newly_excluded"]],
        "versions_added": [version(item) for item in diff["versions_added"]],
        "versions_removed": [version(item) for item in diff["versions_removed"]],
        "question_changed": bool(diff["question_changed"]),
    }
