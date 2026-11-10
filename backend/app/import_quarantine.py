"""Stored quarantine (R14): the rows a workspace import sets aside are kept, with their reasons, until a person
corrects them and they are imported again.

A free trial stores them too (0.10.56) and deletes them with the trial. A row is corrected on screen and processed
again, or dismissed with a reason; it also closes when a later import brings its record in, and is replaced when a
later import sets the same record aside again (stage 4, J11). Every free-text value of a stored row is masked
(trial/imports.py stored_value), never kept as sent, and a reason never quotes the words a check found; a corrected row
goes through the same checked import as any other row. A row whose text
suggests harm carries its harm words, so it reaches triage while still quarantined (A2).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.intake import rules as intake_rules
from backend.app.db.models.ingestion import ImportQuarantineRow

OPEN = "OPEN"
REPROCESSED = "REPROCESSED"
DISMISSED = "DISMISSED"
STATUSES = (OPEN, REPROCESSED, DISMISSED)
REASON_MIN, REASON_MAX = 3, 500
# What a row replaced by a later import's set-aside row says (it is dismissed, not lost: the newer row holds it).
REPLACED_NOTE = "Set aside again by a later import: the newer row replaces this one."

# Words that suggest harm to a person: the one starter harm-word list of triage (intake/rules.py, G19), a directly
# negated mention ("no harm") left out. Failures alone are not harm.
HARM_WORDS = intake_rules.HARM_WORDS
_YES = frozenset({"yes", "y", "true", "1"})


def harm_words(row: dict) -> list[str]:
    """Why a row suggests harm: a death or serious-injury column marked yes, then the harm words in its text."""
    found = [column for column in ("death", "serious_injury") if str(row.get(column, "")).strip().lower() in _YES]
    text = " ".join(str(row.get(column, "")) for column in ("description", "complaint_type", "problem_code"))
    return found + intake_rules.harm_words(text)


# The words a check quotes in its reason (trial/imports.py _quoted): left out of a stored reason, which is kept.
_QUOTED = re.compile(r" \(“[^”]*”\)")


def stored_values(row: dict, stored_value) -> dict:
    """The row as it may be stored: ``stored_value(column, value)`` is the import's own masking (trial/imports.py)."""
    return {column: stored_value(column, value) for column, value in row.items()}


def stored_problems(problems: list[str]) -> list[str]:
    """The reasons as they may be stored: without the words a check quoted (they may be personal data)."""
    return [_QUOTED.sub("", problem) for problem in problems]


def store(
    db: Session,
    tenant_id,
    import_ref: uuid.UUID,
    entity: str,
    source: str,
    set_aside: list[tuple[int, dict, list[str]]],
    stored_value,
) -> None:
    """Keep the set-aside rows of one import, in its transaction."""
    now = datetime.now(timezone.utc)
    for line, row, problems in set_aside:
        values = stored_values(row, stored_value)
        db.add(
            ImportQuarantineRow(
                tenant_id=tenant_id,
                import_ref=import_ref,
                entity=entity,
                source=source,
                line=line,
                row=values,
                problems=stored_problems(problems),
                harm_words=harm_words(values),
                status=OPEN,
                created_at=now,
            )
        )


def _view(item: ImportQuarantineRow) -> dict:
    return {
        "id": str(item.id),
        "import_ref": str(item.import_ref),
        "entity": item.entity,
        "line": item.line,
        "row": item.row,
        "problems": item.problems,
        "harm_words": item.harm_words,
        "suggests_harm": bool(item.harm_words),
        "status": item.status,
        "created_at": item.created_at.isoformat(),
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        "resolution_note": item.resolution_note,
    }


def listing(db: Session, tenant_id, status: str = OPEN, import_ref: uuid.UUID | None = None) -> dict:
    """Quarantined rows, those suggesting harm first, and the counts for the reconciliation."""
    query = db.query(ImportQuarantineRow).filter(ImportQuarantineRow.tenant_id == tenant_id)
    if import_ref:
        query = query.filter(ImportQuarantineRow.import_ref == import_ref)
    counts = dict(
        query.with_entities(ImportQuarantineRow.status, func.count()).group_by(ImportQuarantineRow.status).all()
    )
    # Rows suggesting harm first, then oldest, in the query itself so none falls past the limit (A2).
    items = (
        query.filter(ImportQuarantineRow.status == status)
        .order_by(
            func.jsonb_array_length(ImportQuarantineRow.harm_words) == 0,
            ImportQuarantineRow.created_at,
            ImportQuarantineRow.line,
        )
        .limit(500)
        .all()
    )
    return {"counts": _counts(counts), "items": [_view(item) for item in items]}


def _counts(by_status: dict) -> dict:
    return {
        "open": by_status.get(OPEN, 0),
        "reprocessed": by_status.get(REPROCESSED, 0),
        "dismissed": by_status.get(DISMISSED, 0),
    }


def _open_row(db: Session, tenant_id, row_id: uuid.UUID) -> ImportQuarantineRow:
    item = (
        db.query(ImportQuarantineRow)
        .filter(ImportQuarantineRow.tenant_id == tenant_id, ImportQuarantineRow.id == row_id)
        .with_for_update()
        .one_or_none()
    )
    if item is None:
        raise HTTPException(404, detail={"code": "QUARANTINE_ROW_NOT_FOUND", "message": "No such quarantined row"})
    if item.status != OPEN:
        raise HTTPException(
            409,
            detail={
                "code": "QUARANTINE_ROW_CLOSED",
                "message": "This row was already processed again"
                if item.status == REPROCESSED
                else "This row was already dismissed",
            },
        )
    return item


def corrected_row(item: ImportQuarantineRow, changes: dict) -> dict:
    """The row to process again: as stored (personal details masked), with the person's corrections over it. Only the
    row's own columns may be corrected; a column it does not have is refused."""
    stored = {column: str(value or "") for column, value in (item.row or {}).items()}
    unknown = sorted(set(changes) - set(stored))
    if unknown:
        raise HTTPException(
            422,
            detail={
                "code": "QUARANTINE_COLUMN_UNKNOWN",
                "message": f"This row has no column '{unknown[0]}'. Correct only the row's own columns.",
            },
        )
    return {**stored, **{column: str(value or "").strip() for column, value in changes.items()}}


def dismiss(db: Session, tenant_id, row_id: uuid.UUID, reason: str, actor: str, stored_value) -> dict:
    """Dismiss a set-aside row with a reason (a test row, a record already in the QMS...): it leaves the open list and
    Triage. The reason is kept with personal details masked (``stored_value``, the import's own masking)."""
    reason = " ".join(str(reason or "").split())
    if not REASON_MIN <= len(reason) <= REASON_MAX:
        raise HTTPException(
            422,
            detail={
                "code": "QUARANTINE_REASON_REQUIRED",
                "message": f"Say in {REASON_MIN} to {REASON_MAX} characters why this row is dismissed.",
            },
        )
    item = _open_row(db, tenant_id, row_id)
    item.status = DISMISSED
    item.resolution_note = stored_value("reason", reason)
    item.resolved_at = datetime.now(timezone.utc)
    item.resolved_by = actor
    return _view(item)


def record_identity(row: dict | None, columns: list[str]) -> tuple:
    """The values naming one record (a column the file did not have counts as empty)."""
    return tuple((row or {}).get(column) or "" for column in columns)


def close_fixed(
    db: Session, tenant_id, entity: str, columns: list[str], written: set, again: set, actor: str, source: str
) -> list[str]:
    """Earlier imports' open set-aside rows of ``entity`` whose record (the values of its identity ``columns``, as a
    tuple) this import wrote close as processed again, so a fixed row does not stay open and on Triage (J11); those
    whose record this import set aside again are replaced by the newer row; only rows of the same ``source`` (an
    organization's own imports, never the sample's). Returns the closed rows' ids (for the import's audit record)."""
    wanted = {identity for identity in (written | again) if identity[0]}
    if not wanted:
        return []
    now = datetime.now(timezone.utc)
    closed = []
    rows = db.query(ImportQuarantineRow).filter(
        ImportQuarantineRow.tenant_id == tenant_id,
        ImportQuarantineRow.entity == entity,
        ImportQuarantineRow.source == source,
        ImportQuarantineRow.status == OPEN,
        ImportQuarantineRow.row[columns[0]].astext.in_(sorted({identity[0] for identity in wanted})),
    )
    for item in rows.with_for_update():
        identity = record_identity(item.row, columns)
        if identity in written:
            item.status = REPROCESSED
        elif identity in again:
            item.status, item.resolution_note = DISMISSED, REPLACED_NOTE
        else:
            continue  # same first column, another record (another version, component or shipment)
        item.resolved_at, item.resolved_by = now, actor
        closed.append(str(item.id))
    return closed


def reprocess(db: Session, tenant_id, row_id: uuid.UUID, corrected: dict, import_records, policy, actor: str) -> dict:
    """Import the corrected row through the same checks as any import; the stored row is closed only if it passes
    (a failing check answers 422 with its problems and leaves the row open)."""
    item = _open_row(db, tenant_id, row_id)
    corrected = corrected_row(item, corrected)
    try:
        result = import_records(db, tenant_id, item.entity, [corrected], policy)
    except HTTPException as exc:
        # What is still wrong, in the answer's own words, so the screen can say it beside the row (D).
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        issues = (detail.get("report") or {}).get("issues") or []
        if not issues:
            raise
        words = "; ".join(f"{i['column']}: {i['message']}" if i.get("column") else i["message"] for i in issues[:5])
        raise HTTPException(
            exc.status_code, detail={**detail, "message": f"Still not right, so the row stays set aside. {words}"}
        ) from exc
    from backend.app import import_lineage
    from backend.app.trial.imports import TEMPLATES

    # The corrected row keeps the lineage of the import it first came in with (R16).
    import_lineage.write(
        db,
        tenant_id,
        item.import_ref,
        item.entity,
        TEMPLATES[item.entity]["required"],
        [(item.line, corrected)],
        import_lineage.REPROCESSED_MAPPING,
        policy.source,
    )
    item.status = REPROCESSED
    item.resolved_at = datetime.now(timezone.utc)
    item.resolved_by = actor
    return {**result, "quarantine_row": _view(item)}


def counts(db: Session, tenant_id, import_ref: uuid.UUID) -> dict:
    """Open and re-processed rows of one import, now."""
    rows = dict(
        db.query(ImportQuarantineRow.status, func.count())
        .filter(ImportQuarantineRow.tenant_id == tenant_id, ImportQuarantineRow.import_ref == import_ref)
        .group_by(ImportQuarantineRow.status)
        .all()
    )
    return _counts(rows)
