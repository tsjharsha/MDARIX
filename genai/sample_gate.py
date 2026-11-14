"""Free trials use AI on the sample data only (owner decision AI-D14a), enforced at ``GenAIProvider.complete``.

A Free Trial organization's request is sent only when, before any network code:

1. it lists the records whose content it carries (``records=[{"table", "id", "evidence_id"?}]``), at least one;
2. every evidence block it sends is one of those records (``evidence_id`` names the block);
3. each record, re-read by id in the organization's own session (row-level security), belongs to this
   organization, carries the sample marker ``source_system = "MDARIX_SAMPLE"`` (which only the sample loader may
   write: ``backend/app/trial/sample_marker.py``), and its text still matches the sample catalogue: a sample record
   a person edited (and could have typed real data into) no longer counts as sample;
4. free text the person typed (the Ask question) is at most ``TRIAL_FREE_TEXT_MAX`` characters (decision T3); it is
   masked like everything else.

Otherwise the request is refused with ``GENAI_TRIAL_SAMPLE_ONLY`` ("AI available on paid plans"), counted, and no
call record is written. Paid organizations skip this gate (their data goes only to the paid provider).

The catalogue is every text the sample loader writes: the string constants of ``backend/app/trial/sample*.py``. A
record's text fields match when each is empty or a part of one of those texts (a part of synthetic text is still
synthetic; anything typed in is not). Text built at load time from parts is not in the catalogue, so such a record is
refused: the gate fails closed.
"""

from __future__ import annotations

import ast
import functools
import logging
import re
import uuid
from pathlib import Path

logger = logging.getLogger("mdarix.genai")

TRIAL_FREE_TEXT_MAX = 300
SAMPLE_MODULES = Path(__file__).resolve().parent.parent / "backend" / "app" / "trial"
# Text columns a person can edit and an AI request may carry. Identifiers, codes and states are not narrative.
NARRATIVE_COLUMNS = frozenset(
    {
        "description",
        "narrative",
        "summary",
        "text",
        "content",
        "title",
        "body",
        "notes",
        "name",
        "statement",
        "excerpt",
        "chunk_text",
        "raw_text",
        "subject",
        "event_description",
        "problem_description",
        "reporter_narrative",
        "verbatim",
    }
)
_SPACE = re.compile(r"\s+")


class SampleGateRefused(Exception):
    pass


def _normal(text: str) -> str:
    return _SPACE.sub(" ", text).strip()


@functools.lru_cache(maxsize=1)
def catalogue() -> str:
    """Every string constant of the sample modules, whitespace-normalized, joined by a separator no text holds."""
    found: set[str] = set()
    for path in sorted(SAMPLE_MODULES.glob("sample*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = _normal(node.value)
                if text:
                    found.add(text)
    return "\x00" + "\x00".join(sorted(found)) + "\x00"


def matches_catalogue(value) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return True
    text = _normal(value)
    return not text or text in catalogue()


def _model_for(table: str):
    from backend.app.db.base import Base

    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if getattr(cls, "__tablename__", None) == table:
            return cls
    return None


def _record_problem(db, tenant_id: uuid.UUID, entry: dict) -> str | None:
    from backend.app.trial.sample_source import SAMPLE_SOURCE

    model = _model_for(str(entry.get("table") or ""))
    if model is None:
        return f"unknown record table {entry.get('table')!r}"
    columns = model.__table__.columns
    if "source_system" not in columns or "tenant_id" not in columns:
        return f"{entry.get('table')} records cannot be proven to be sample data"
    try:
        record_id = uuid.UUID(str(entry.get("id")))
    except (TypeError, ValueError):
        return "a record id is not valid"
    row = db.get(model, record_id)
    if row is None or row.tenant_id != tenant_id:
        return "a record is not this organization's"
    if row.source_system != SAMPLE_SOURCE:
        return "a record is not sample data"
    for column in columns:
        if column.name in NARRATIVE_COLUMNS and not matches_catalogue(getattr(row, column.key, None)):
            return f"a sample record was edited ({entry.get('table')}.{column.name})"
    return None


def problem(tenant_id: str, *, records: list[dict], evidence: list[dict], user_text: str | None) -> str | None:
    """Why this trial request may not be sent (None when every record is unedited sample data)."""
    from genai import governance

    if user_text and len(user_text) > TRIAL_FREE_TEXT_MAX:
        return f"typed text longer than {TRIAL_FREE_TEXT_MAX} characters"
    if not records:
        return "the request lists no sample records"
    listed = {str(item.get("evidence_id")) for item in records if item.get("evidence_id")}
    for block in evidence or []:
        block_id = str(block.get("id") or block.get("evidence_identifier") or "")
        if block_id not in listed:
            return "an evidence block is not a listed record"
    db = governance._session(tenant_id)
    try:
        organization = uuid.UUID(tenant_id)
        for entry in records:
            found = _record_problem(db, organization, entry)
            if found:
                return found
    finally:
        db.close()
    return None


def check(tenant_id: str | None, *, records: list[dict], evidence: list[dict], user_text: str | None) -> None:
    """Refuse (``GENAI_TRIAL_SAMPLE_ONLY``, counted) unless the request carries unedited sample data only."""
    from genai import governance
    from genai.provider import GenAIUnavailable

    if tenant_id is None:
        raise GenAIUnavailable("GENAI_TRIAL_SAMPLE_ONLY: no organization")
    try:
        found = problem(tenant_id, records=records, evidence=evidence, user_text=user_text)
    except Exception:
        logger.exception("The sample-data check could not run; refused")
        found = "the sample-data check could not run"
    if found:
        logger.info("Trial AI request refused: %s", found)
        governance.count_refusal(tenant_id)
        raise GenAIUnavailable(f"GENAI_TRIAL_SAMPLE_ONLY: {found}")
