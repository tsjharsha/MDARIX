"""Stored quarantine (R14): the rows a workspace import sets aside are kept, with their reasons, until a person
corrects them and they are imported again.

A free trial never stores them (its uploader gets the rejects file back instead). Personal data in a stored row is
masked, never kept as sent; a corrected row goes through the same checked import as any other row. A row whose text
suggests harm carries its harm words, so it reaches triage while still quarantined (A2).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.intake import rules as intake_rules
from backend.app.db.models.ingestion import ImportQuarantineRow

OPEN = "OPEN"
REPROCESSED = "REPROCESSED"

# Words that suggest harm to a person: the one starter harm-word list of triage (intake/rules.py, G19), a directly
# negated mention ("no harm") left out. Failures alone are not harm.
HARM_WORDS = intake_rules.HARM_WORDS
_YES = frozenset({"yes", "y", "true", "1"})


def harm_words(row: dict) -> list[str]:
    """Why a row suggests harm: a death or serious-injury column marked yes, then the harm words in its text."""
    found = [column for column in ("death", "serious_injury") if str(row.get(column, "")).strip().lower() in _YES]
    text = " ".join(str(row.get(column, "")) for column in ("description", "complaint_type", "problem_code"))
    return found + intake_rules.harm_words(text)


def stored_values(row: dict, personal_data, mask) -> dict:
    """The row as it may be stored: each value that holds personal data is masked (``personal_data`` and ``mask`` are
    the import's own checks, trial/imports.py)."""
    return {column: mask(value) if value and personal_data(value) else value for column, value in row.items()}


def store(
    db: Session,
    tenant_id,
    import_ref: uuid.UUID,
    entity: str,
    source: str,
    set_aside: list[tuple[int, dict, list[str]]],
    personal_data,
    mask,
) -> None:
    """Keep the set-aside rows of one import, in its transaction."""
    now = datetime.now(timezone.utc)
    for line, row, problems in set_aside:
        values = stored_values(row, personal_data, mask)
        db.add(
            ImportQuarantineRow(
                tenant_id=tenant_id,
                import_ref=import_ref,
                entity=entity,
                source=source,
                line=line,
                row=values,
                problems=problems,
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
    return {
        "counts": {"open": counts.get(OPEN, 0), "reprocessed": counts.get(REPROCESSED, 0)},
        "items": [_view(item) for item in items],
    }


def reprocess(db: Session, tenant_id, row_id: uuid.UUID, corrected: dict, import_records, policy, actor: str) -> dict:
    """Import the corrected row through the same checks as any import; the stored row is closed only if it passes
    (a failing check answers 422 with its problems and leaves the row open)."""
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
            409, detail={"code": "QUARANTINE_ROW_CLOSED", "message": "This row was already re-processed"}
        )
    result = import_records(db, tenant_id, item.entity, [corrected], policy)
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
    return {"open": rows.get(OPEN, 0), "reprocessed": rows.get(REPROCESSED, 0)}
