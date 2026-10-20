"""Many rows in a few INSERT statements (NEW-4, release 0.10.38).

The session's own flush sends one INSERT per new object for most MDARIX tables: their ids and business ids are made by
the database, and the pg8000 driver sends an executemany one row at a time. An INSERT ... RETURNING of a list of rows
lets SQLAlchemy batch them instead ("insertmanyvalues", up to 1,000 rows a statement). The rows are not loaded into
the session; the caller reads them back if it needs them.
"""

from __future__ import annotations

from sqlalchemy import insert
from sqlalchemy.orm import Session


def insert_rows(db: Session, model, rows: list[dict]) -> None:
    """Insert ``rows`` (column values by attribute name) into ``model``'s table, in batches."""
    if rows:
        db.execute(insert(model).returning(model.id), rows).all()
