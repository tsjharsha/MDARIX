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
synthetic; anything typed in is not). Text the loader builds at load time from parts (its f-strings, such as a bulk
complaint's "Customer reported {symptom} on {revision}, lot {lot}.") matches when it has the f-string's exact shape and
every filled-in part is itself sample text or a server-style identifier (review G2): a person who keeps the sentence
but types real text into a part is still refused. Anything else is refused: the gate fails closed.

Every text column is checked (String, Text and the strings inside JSONB), deny by default, not a list of names: the
prompts send columns such as ``investigations.investigation_question`` and a complaint's status, type, problem code,
severity and country (review S1). For an evidence record the text of its search chunks is checked too, since Ask and
case analysis send the chunk text. Only identifier and actor columns are skipped (``_skipped``): they hold keys the
server writes, never typed narrative.
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
# Keys and markers the server writes, never narrative: they are not compared with the catalogue.
SKIPPED_COLUMNS = frozenset({"business_id", "source_system", "source_identifier", "tenant_id"})
# A state or code the server sets (MEDIUM, CLOSED, NOT_REPORTABLE): one upper-case token, no spaces.
# shortcut: a single upper-case word typed into a sample record passes; narrative and contact details need spaces or
# lower case. Tighten to per-column enums if a prompt ever sends a free single-word field.
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,39}")
# An identifier the loader writes into a sentence (SAMPLE-ORBIT-300-LOT-003, 012, 2026-11-17): no spaces, no lower case.
_IDENTIFIER = re.compile(r"[A-Z0-9][A-Z0-9_.:+-]{0,59}")
# The loader marks sample titles with this suffix (the rest of the title is catalogue text).
SAMPLE_SUFFIX = "(Sample)"
_SPACE = re.compile(r"\s+")


def _sample_paths() -> list[Path]:
    # The flagship story's sentences (trial/flagship.py, such as SIGNAL_TEXT) are built into sample records too (W1, G-06).
    return [*sorted(SAMPLE_MODULES.glob("sample*.py")), SAMPLE_MODULES / "flagship.py"]


class SampleGateRefused(Exception):
    pass


def _normal(text: str) -> str:
    return _SPACE.sub(" ", text).strip()


@functools.lru_cache(maxsize=1)
def catalogue() -> str:
    """Every string constant of the sample modules, whitespace-normalized, joined by a separator no text holds."""
    found: set[str] = set()
    for path in _sample_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = _normal(node.value)
                if text:
                    found.add(text)
    return "\x00" + "\x00".join(sorted(found)) + "\x00"


@functools.lru_cache(maxsize=1)
def templates() -> tuple[re.Pattern, ...]:
    """The sample modules' f-strings as patterns: their literal text exact (whitespace-normalized), each ``{...}`` one
    filled-in part."""
    found: set[str] = set()
    for path in _sample_paths():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.JoinedStr):
                continue
            parts = [
                re.escape(_SPACE.sub(" ", part.value)) if isinstance(part, ast.Constant) else "(.+?)"
                for part in node.values
            ]
            # A bare "{x}" or "{a}{b}" says nothing about the shape; its parts are checked as plain text anyway.
            if any(isinstance(part, ast.Constant) and part.value.strip() for part in node.values):
                found.add("".join(parts).strip())
    return tuple(re.compile(pattern, re.DOTALL) for pattern in sorted(found))


def _sample_part(text: str) -> bool:
    text = text.strip()
    # A part may itself be built from parts (SIGNAL_TEXT inside the signal sentence); each level is shorter, so it ends.
    return not text or bool(_IDENTIFIER.fullmatch(text)) or text in catalogue() or _built_from_parts(text)


def _built_from_parts(text: str) -> bool:
    """True when ``text`` has the shape of one of the loader's f-strings and every part filled in is sample text."""
    for pattern in templates():
        found = pattern.fullmatch(text)
        if found and all(_sample_part(part) for part in found.groups()):
            return True
    return False


def matches_catalogue(value) -> bool:
    """True when every text in ``value`` (a string, or the strings anywhere inside a JSON value) is sample text."""
    if isinstance(value, dict):
        return all(matches_catalogue(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(matches_catalogue(item) for item in value)
    if not isinstance(value, str):
        return True
    text = _normal(value)
    if text.endswith(SAMPLE_SUFFIX):
        text = text[: -len(SAMPLE_SUFFIX)].strip()
    return not text or bool(_CODE.fullmatch(text)) or text in catalogue() or _built_from_parts(text)


def _skipped(name: str) -> bool:
    """Identifier and actor columns (keys and account references the server writes)."""
    return name in SKIPPED_COLUMNS or name.endswith(("_identifier", "_ref", "_id", "_owner"))


def _text_columns(model):
    from sqlalchemy import String, Text
    from sqlalchemy.dialects.postgresql import JSONB

    return [
        column
        for column in model.__table__.columns
        if isinstance(column.type, (String, Text, JSONB)) and not _skipped(column.name)
    ]


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
    for column in _text_columns(model):
        if not matches_catalogue(getattr(row, column.key, None)):
            return f"a sample record was edited ({entry.get('table')}.{column.name})"
    if model.__tablename__ == "evidence":
        from backend.app.db.models.evidence_intelligence import EvidenceChunk

        chunks = db.query(EvidenceChunk.text_content).filter(
            EvidenceChunk.tenant_id == tenant_id, EvidenceChunk.evidence_id == record_id
        )
        if not all(matches_catalogue(text) for (text,) in chunks):
            return "a sample record was edited (evidence_chunks.text_content)"
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
