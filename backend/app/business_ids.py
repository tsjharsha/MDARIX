"""Business identifiers in API responses (migration md26; CUST000001, CMP000001).

Every business object returns its ``business_id`` next to its UUID ``id``. When a response references another
business object by UUID (a complaint's investigation, a tenant's customer) and the screen shows that reference, the
response also carries ``<role>_business_id``. Responses built from ORM rows read ``row.business_id`` directly; this
module looks up the identifiers of referenced rows that the response has only as UUIDs, in one query per model.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session


def as_uuid(value: Any) -> uuid.UUID | None:
    """``value`` as a UUID, or None when it is empty or not a UUID (references in JSON payloads are strings)."""
    if value is None or value == "":
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def wanted_ids(values: Iterable[Any]) -> set[uuid.UUID]:
    """The distinct UUIDs among ``values``; empty and malformed values are dropped."""
    return {item for item in (as_uuid(value) for value in values) if item is not None}


def business_id_map(db: Session, model: Any, ids: Iterable[Any]) -> dict[str, str]:
    """``{str(id): business_id}`` for the rows of ``model`` whose id is in ``ids``, read in one query.

    Ids that are empty, malformed or not found are left out, so callers read the map with ``.get(str(id))``.
    """
    wanted = wanted_ids(ids)
    if not wanted:
        return {}
    rows = db.execute(select(model.id, model.business_id).where(model.id.in_(wanted))).all()
    return {str(row_id): business_id for row_id, business_id in rows}


def business_id_of(db: Session, model: Any, row_id: Any) -> str | None:
    """The business identifier of one ``model`` row by its UUID, or None when there is no such row."""
    key = as_uuid(row_id)
    if key is None:
        return None
    return business_id_map(db, model, [key]).get(str(key))


def complaint_ref(complaint: Any) -> str | None:
    """The one ID a screen shows for a complaint (J18, V2): the customer's own reference (``complaint_identifier``),
    else its MDARIX ID. The other is shown only as "also known as" in the complaint's details. A complaint is an ORM
    row or a mapping with both fields. Documents, exports and signed records keep the IDs they always named."""
    if isinstance(complaint, dict):
        return complaint.get("complaint_identifier") or complaint.get("business_id")
    return complaint.complaint_identifier or complaint.business_id
