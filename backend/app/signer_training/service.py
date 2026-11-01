"""The documents a signature relies on, and who holds a training record on their current versions.

The documents are MDARIX's starter documents: each market's question set (``US-starter-1``..., or the organization's own
published guide version, ``US-v2``..., T-G15) and the harm-severity
scale (``scale-starter-1``), read from backend/app/reportability/markets.py, and the disposition rules
(``disposition-starter-1``, backend/app/complaint_disposition/rules.py) and classification coding criteria
(``coding-starter-1``, backend/app/complaint_classification/rules.py), so a new version there makes every record of the
earlier version out of date at once. In a free trial a record is a practice acknowledgement: the person opened
the document and confirmed "I have read version ..." (T-G40P); MDARIX runs no training. The MVP keeps the same table
for the customer's own records (trainer, method, evidence) and adds its complaint-handling procedure as a document.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.complaint_classification import rules as coding
from backend.app.complaint_disposition import rules as disposition
from backend.app.db.models.market_assessment import SignerTrainingRecord
from backend.app.reportability import markets

TRIAL_METHOD = "practice acknowledgement in a free trial"
WORKSPACE_METHOD = "read and acknowledged in MDARIX"
HARM_SCALE = "HARM_SCALE"
DISPOSITION_RULES = "DISPOSITION_RULES"
CODING_CRITERIA = "CODING_CRITERIA"


@dataclass(frozen=True)
class Document:
    code: str
    title: str
    version: str

    def as_dict(self) -> dict:
        return {"code": self.code, "title": self.title, "version": self.version, "statement": statement(self.version)}


def statement(version: str) -> str:
    return f"I have read version {version}"


def question_set_code(market: str) -> str:
    return f"QUESTION_SET_{market}"


def documents(db: Session | None = None, tenant_id=None) -> dict[str, Document]:
    """Every document, at its current version (read now, so a changed version takes effect at once). With the
    organization's data plane, a market's question set is its published guide version when it has one (T-G15)."""
    from backend.app.decision_guides.service import current_codes

    codes = current_codes(db, tenant_id)
    found = {}
    for market, question_set in markets.QUESTION_SETS.items():
        code = codes[market]
        title = f"{question_set.title}: " + (
            "starter questions" if code == question_set.version else f"your guide version {code}"
        )
        found[question_set_code(market)] = Document(question_set_code(market), title, code)
    found[HARM_SCALE] = Document(HARM_SCALE, "Harm-severity scale (starter)", markets.SCALE_VERSION)
    found[DISPOSITION_RULES] = Document(
        DISPOSITION_RULES, "Complaint disposition rules (starter)", disposition.RULES_VERSION
    )
    found[CODING_CRITERIA] = Document(
        CODING_CRITERIA, "Classification coding criteria (starter)", coding.CODING_CRITERIA_VERSION
    )
    return found


def for_market(market: str, db: Session | None = None, tenant_id=None) -> list[Document]:
    """What a market conclusion relies on: the market's question set (its current version) and the harm-severity
    scale."""
    every = documents(db, tenant_id)
    return [every[question_set_code(market)], every[HARM_SCALE]]


def for_disposition() -> list[Document]:
    """What a disposition (and the routine path's one signature) relies on: the disposition rules and the coding
    criteria the classification is confirmed under."""
    every = documents()
    return [every[DISPOSITION_RULES], every[CODING_CRITERIA]]


def content(code: str, db: Session | None = None, tenant_id=None) -> dict | None:
    """What the person reads before acknowledging."""
    if code == HARM_SCALE:
        return {"scale": markets.scale()}
    if code == DISPOSITION_RULES:
        return {"rules": list(disposition.DISPOSITION_RULES)}
    if code == CODING_CRITERIA:
        return {"rules": list(coding.CODING_CRITERIA)}
    for market in markets.MARKETS:
        if code == question_set_code(market):
            from backend.app.decision_guides.service import current

            return {"question_set": current(db, tenant_id, market).as_dict()}
    return None


def _held(db: Session, tenant_id: uuid.UUID, wanted: list[Document], users: list[str] | None = None):
    query = db.query(
        SignerTrainingRecord.user_id, SignerTrainingRecord.document_code, SignerTrainingRecord.document_version
    ).filter(
        SignerTrainingRecord.tenant_id == tenant_id,
        SignerTrainingRecord.document_code.in_([document.code for document in wanted]),
    )
    if users is not None:
        query = query.filter(SignerTrainingRecord.user_id.in_(users))
    current = {document.code: document.version for document in wanted}
    held: dict[str, set[str]] = {}
    for user_id, code, version in query:
        if current.get(code) == version:
            held.setdefault(user_id, set()).add(code)
    return held


def missing(db: Session, tenant_id: uuid.UUID, user_id: str, wanted: list[Document]) -> list[Document]:
    """The documents of ``wanted`` the person holds no record of at their current version."""
    held = _held(db, tenant_id, wanted, [str(user_id)]).get(str(user_id), set())
    return [document for document in wanted if document.code not in held]


def holders(db: Session, tenant_id: uuid.UUID, wanted: list[Document], exclude: str | None = None) -> list[str]:
    """The people (user ids) holding a current record of every document of ``wanted``: who could sign instead."""
    codes = {document.code for document in wanted}
    return sorted(user for user, held in _held(db, tenant_id, wanted).items() if held >= codes and user != exclude)


def status(db: Session, tenant_id: uuid.UUID, user_id: str, wanted: list[Document]) -> list[dict]:
    """Each document with whether the person's record of it is current, out of date, or missing."""
    rows = (
        db.query(SignerTrainingRecord)
        .filter(
            SignerTrainingRecord.tenant_id == tenant_id,
            SignerTrainingRecord.user_id == str(user_id),
            SignerTrainingRecord.document_code.in_([document.code for document in wanted]),
        )
        .order_by(SignerTrainingRecord.trained_at)
        .all()
    )
    found = []
    for document in wanted:
        mine = [row for row in rows if row.document_code == document.code]
        current = next((row for row in mine if row.document_version == document.version), None)
        state = "CURRENT" if current else "OUT_OF_DATE" if mine else "MISSING"
        latest = current or (mine[-1] if mine else None)
        found.append(
            {
                **document.as_dict(),
                "state": state,
                "held_version": latest.document_version if latest else None,
                "trained_at": latest.trained_at.isoformat() if latest else None,
                "method": latest.method if latest else None,
            }
        )
    return found


def acknowledge(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: str,
    document: Document,
    now: datetime,
    *,
    trial: bool,
    source_system: str | None = None,
) -> tuple[SignerTrainingRecord, bool]:
    """Record the person's acknowledgement of the document's current version: ``(record, created)``. Once per version.
    Flushes but never commits."""
    existing = (
        db.query(SignerTrainingRecord)
        .filter(
            SignerTrainingRecord.tenant_id == tenant_id,
            SignerTrainingRecord.user_id == str(user_id),
            SignerTrainingRecord.document_code == document.code,
            SignerTrainingRecord.document_version == document.version,
        )
        .first()
    )
    if existing is not None:
        return existing, False
    row = SignerTrainingRecord(
        tenant_id=tenant_id,
        user_id=str(user_id),
        document_code=document.code,
        document_version=document.version,
        trained_at=now,
        method=TRIAL_METHOD if trial else WORKSPACE_METHOD,
        trainer=None,
        evidence={"opened": True, "statement": statement(document.version), "document_title": document.title},
        recorded_by=str(user_id),
        source_system=source_system,
        created_at=now,
    )
    db.add(row)
    db.flush()
    return row, True
