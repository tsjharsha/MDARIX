"""Where a record came from, as one chip and one line (W1, spec 3.5): the sample, an import, created in MDARIX, or a
customer's own system. Read from columns every master-data and business row already has."""

from __future__ import annotations

from typing import Any

from backend.app.trial.sample_source import SAMPLE_SOURCE

IMPORTS = {"TRIAL_UPLOAD", "CSV_IMPORT"}


def _day(value: Any) -> str | None:
    if value is None:
        return None
    return value.date().isoformat() if hasattr(value, "date") else str(value)[:10]


def origin(
    source_system: str | None, source_identifier: str | None = None, loaded_at: Any = None, created_at: Any = None
) -> dict[str, Any]:
    """``{kind, label, detail, system, external_id, loaded_at}`` for one record. ``kind`` is SAMPLE, IMPORTED, MDARIX
    or EXTERNAL; a record with no source system was made in MDARIX."""
    system = str(source_system or "").strip()
    loaded = _day(loaded_at)
    if system == SAMPLE_SOURCE:
        kind, label, detail = "SAMPLE", "Sample", "Fictional sample data"
    elif system.upper() in IMPORTS:
        kind, label = "IMPORTED", "Your import"
        detail = f"Imported on {loaded or 'an unknown date'}" + (
            f" · ID {source_identifier}" if source_identifier else ""
        )
    elif not system or system.upper().startswith("MDARIX"):
        kind, label = "MDARIX", "Created in MDARIX"
        created = _day(created_at)
        detail = f"Created on {created}" if created else "Created in MDARIX"
    else:
        kind, label = "EXTERNAL", f"From {system}"
        parts = [f"ID {source_identifier}" if source_identifier else None, f"last loaded {loaded}" if loaded else None]
        detail = " · ".join(part for part in parts if part) or f"Loaded from {system}"
    return {
        "kind": kind,
        "label": label,
        "detail": detail,
        "system": system or None,
        "external_id": source_identifier,
        "loaded_at": loaded,
    }


def of_row(row: Any) -> dict[str, Any]:
    """The origin of a mapping row read with ``source_system``, ``source_identifier``, ``ingestion_timestamp`` and
    ``created_at`` (any of them may be missing)."""
    get = row.get if hasattr(row, "get") else lambda key: getattr(row, key, None)
    return origin(get("source_system"), get("source_identifier"), get("ingestion_timestamp"), get("created_at"))
