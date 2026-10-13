"""Removing a free trial's sample data, and everything done with it, while the organization's own data stays.

The sample's records carry ``source_system = MDARIX_SAMPLE``. Everything that depends on them goes too, found the way the
database itself links records: every foreign key is followed from the rows already marked for removal (a decision on
the sample case, a second look on a sample complaint, a signal of a sample version, a task on the sample case...), until
nothing new is reached; then the columns that point at any record without a foreign key (a task's source, an evidence
link, a relationship, a signature record, the intelligence history) are swept for the same rows. The audit trail and the
outbox are kept: they are the history of what happened. The organization's own uploads, and what it did with them, do
not depend on the sample and stay.

The owner sees a preview first (``plan``: how many sample records, how much work done on them, and any own record that
would go because it points at sample records), then confirms (``remove``). The chapters already tried are remembered in
the trial request's profile, so the story's progress is not lost. Deletion runs in one transaction, child tables first,
retried while foreign keys hold rows back; if anything would remain, nothing is deleted.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.app.trial.sample_data import SAMPLE_SOURCE

# Columns that point at a record of any table, without a foreign key: swept for removed rows.
GENERIC_REFERENCES = (
    ("workflow_tasks", "source_entity_id"),
    ("evidence_entity_links", "entity_id"),
    ("intelligence_events", "object_id"),
    ("canonical_relationships", "source_entity_id"),
    ("canonical_relationships", "target_entity_id"),
    ("reality_relationships", "source_entity_id"),
    ("reality_relationships", "target_entity_id"),
    ("signed_approval_records", "object_id"),
)
# History that stays: what happened is never rewritten.
KEPT = frozenset({"audit_events", "event_outbox", "erasure_log", "tenants"})
# The records an organization uploads itself (backend/app/trial/imports.py UPLOAD_SOURCE).
OWN_SOURCES = ("TRIAL_UPLOAD", "CSV_IMPORT")
# The sample's records, as people name them, for the preview.
SAMPLE_LABELS = {
    "products": "products",
    "product_versions": "product versions",
    "lot_batches": "lots",
    "complaints": "complaints",
    "investigations": "investigations",
    "evidence": "pieces of evidence",
    "capas": "CAPAs",
    "risks": "risks",
    "suppliers": "suppliers",
    "components": "components",
    "changes": "changes",
}


def _tenant_tables(db: Session) -> list[str]:
    rows = db.execute(
        text(
            "SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' AND column_name = 'tenant_id'"
        )
    )
    return sorted({name for (name,) in rows} - KEPT)


def _columns(db: Session) -> dict[str, set[str]]:
    found: dict[str, set[str]] = defaultdict(set)
    for table, column in db.execute(
        text("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public'")
    ):
        found[table].add(column)
    return found


def _foreign_keys(db: Session) -> list[tuple[str, str, str]]:
    """(child table, child column, parent table) for every foreign key whose parent column is ``id``."""
    rows = db.execute(
        text(
            """
            SELECT c.conrelid::regclass::text, c.confrelid::regclass::text,
                   array(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(n, i)
                         JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.n ORDER BY k.i),
                   array(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(n, i)
                         JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.n ORDER BY k.i)
            FROM pg_constraint c WHERE c.contype = 'f'
            """
        )
    )
    links = []
    for child, parent, child_columns, parent_columns in rows:
        for child_column, parent_column in zip(child_columns, parent_columns):
            if parent_column == "id" and child_column != "id":
                links.append((child, child_column, parent))
    return links


def _ids(db: Session, sql: str, params: dict) -> set[uuid.UUID]:
    return {row[0] for row in db.execute(text(sql), params)}


def plan(db: Session, tenant_id: uuid.UUID) -> dict:
    """Every row the removal deletes, by table (``rows``), and the rows without an ``id`` column that go with them
    (``links``: table -> [(column, parent table)]). Reads only."""
    tables = set(_tenant_tables(db))
    columns = _columns(db)
    doomed: dict[str, set[uuid.UUID]] = defaultdict(set)
    for table in tables:
        if {"source_system", "id"} <= columns[table]:
            doomed[table] |= _ids(
                db,
                f"SELECT id FROM {table} WHERE tenant_id = :tenant AND source_system = :sample",
                {"tenant": tenant_id, "sample": SAMPLE_SOURCE},
            )
    keys = [(child, column, parent) for child, column, parent in _foreign_keys(db) if child in tables]
    generic = [(table, column) for table, column in GENERIC_REFERENCES if table in tables and column in columns[table]]
    changed = True
    while changed:
        changed = False
        for child, column, parent in keys:
            parents = doomed.get(parent)
            if not parents or "id" not in columns[child]:
                continue
            found = (
                _ids(
                    db,
                    f"SELECT id FROM {child} WHERE tenant_id = :tenant AND {column} = ANY(:ids)",
                    {"tenant": tenant_id, "ids": list(parents)},
                )
                - doomed[child]
            )
            if found:
                doomed[child] |= found
                changed = True
        every = set().union(*doomed.values()) if doomed else set()
        for table, column in generic:
            if not every or "id" not in columns[table]:
                continue
            found = (
                _ids(
                    db,
                    f"SELECT id FROM {table} WHERE tenant_id = :tenant AND {column} = ANY(:ids)",
                    {"tenant": tenant_id, "ids": list(every)},
                )
                - doomed[table]
            )
            if found:
                doomed[table] |= found
                changed = True
    links: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for child, column, parent in keys:
        if "id" not in columns[child] and doomed.get(parent):
            links[child].append((column, parent))
    return {"rows": {table: ids for table, ids in doomed.items() if ids}, "links": dict(links)}


def preview(db: Session, tenant_id: uuid.UUID) -> dict:
    """What the removal would delete, as people read it: the sample records by kind, how many records of work done
    on them, and the organization's own uploaded records that would go because they point at sample records."""
    planned = plan(db, tenant_id)
    columns = _columns(db)
    sample: dict[str, int] = {}
    own = 0
    work = 0
    for table, ids in planned["rows"].items():
        if "source_system" in columns[table]:
            counts = dict(
                db.execute(
                    text(f"SELECT source_system, count(*) FROM {table} WHERE id = ANY(:ids) GROUP BY source_system"),
                    {"ids": list(ids)},
                ).all()
            )
            if counts.get(SAMPLE_SOURCE) and table in SAMPLE_LABELS:
                sample[SAMPLE_LABELS[table]] = sample.get(SAMPLE_LABELS[table], 0) + int(counts[SAMPLE_SOURCE])
            own += sum(int(counts.get(source, 0)) for source in OWN_SOURCES)
            work += sum(int(value) for key, value in counts.items() if key not in (SAMPLE_SOURCE, *OWN_SOURCES))
        else:
            work += len(ids)
    return {"sample": sample, "work_on_sample": work, "own_records_affected": own, "has_sample": bool(sample)}


def remove(db: Session, tenant_id: uuid.UUID, remembered: list[str]) -> dict:
    """Delete everything ``plan`` lists, child tables first; raises RuntimeError (after a rollback: nothing deleted)
    when rows would remain. Does not commit: the caller commits it with its audit record and the chapters it
    remembers (``remembered``, returned as given)."""
    planned = plan(db, tenant_id)
    remaining = dict(planned["rows"])
    link_tables = dict(planned["links"])
    deleted: dict[str, int] = {}
    for _ in range(len(remaining) + len(link_tables) + 2):
        progress = False
        for child, refs in list(link_tables.items()):
            savepoint = db.begin_nested()
            try:
                count = 0
                for column, parent in refs:
                    ids = planned["rows"].get(parent) or set()
                    if ids:
                        count += db.execute(
                            text(f"DELETE FROM {child} WHERE tenant_id = :tenant AND {column} = ANY(:ids)"),
                            {"tenant": tenant_id, "ids": list(ids)},
                        ).rowcount
                savepoint.commit()
            except DBAPIError:
                savepoint.rollback()
                continue
            if count:
                deleted[child] = deleted.get(child, 0) + count
            del link_tables[child]
            progress = True
        for table, ids in list(remaining.items()):
            savepoint = db.begin_nested()
            try:
                count = db.execute(
                    text(f"DELETE FROM {table} WHERE tenant_id = :tenant AND id = ANY(:ids)"),
                    {"tenant": tenant_id, "ids": list(ids)},
                ).rowcount
                savepoint.commit()
            except DBAPIError:
                savepoint.rollback()
                continue
            deleted[table] = count
            del remaining[table]
            progress = True
        if not remaining and not link_tables:
            break
        if not progress:
            break
    if remaining or link_tables:
        db.rollback()
        raise RuntimeError("ROWS_REMAIN:" + ",".join(sorted([*remaining, *link_tables])))
    return {"deleted": deleted, "remembered": remembered, "at": datetime.now(timezone.utc).isoformat()}
