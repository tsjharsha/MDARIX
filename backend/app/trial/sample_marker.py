"""The sample marker ``source_system = "MDARIX_SAMPLE"`` is reserved for the sample loader (trial plan step N7).

Free trials may use AI on sample data only, and the AI gate (``genai/sample_gate.py``) recognises sample records by
this marker. So no request may set it: every request field that becomes a record's ``source_system`` (a mapping, a
master mapping, a connector run, a connector's ``source_object``, a mapping preview) refuses it with 422, and the
connector gateway refuses it as a source. The sample modules (``backend/app/trial/sample*.py``) write it from code;
no request value reaches them.
"""

from __future__ import annotations

from backend.app.trial.sample_source import SAMPLE_SOURCE

RESERVED_MESSAGE = f"{SAMPLE_SOURCE} is reserved for MDARIX's own sample data; use your system's name as the source"


def is_reserved(value) -> bool:
    """The marker, however it is spelt or padded."""
    return isinstance(value, str) and value.strip().upper() == SAMPLE_SOURCE


def refuse_reserved(value):
    """A pydantic validator body: the value unchanged, or ValueError (422) for the marker."""
    if is_reserved(value):
        raise ValueError(RESERVED_MESSAGE)
    return value


def refuse_reserved_in(configuration: dict | None) -> dict | None:
    """A connector configuration whose ``source_object`` (used as the records' source) is the marker is refused."""
    if isinstance(configuration, dict):
        for key in ("source_object", "source_system"):
            refuse_reserved(configuration.get(key))
    return configuration
