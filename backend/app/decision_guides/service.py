"""Which guide version an assessment uses (T-G15): the organization's published version of a market's guide, or
MDARIX's starter when it has none. An assessment keeps the version it was started with; a new one uses the version
published when it starts. Reads only; never commits."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from backend.app.db.models.guides_communications import DecisionGuideVersion
from backend.app.decision_guides import rules
from backend.app.reportability import markets


def published(db: Session, tenant_id: uuid.UUID, market: str) -> DecisionGuideVersion | None:
    return (
        db.query(DecisionGuideVersion)
        .filter(
            DecisionGuideVersion.tenant_id == tenant_id,
            DecisionGuideVersion.market == market,
            DecisionGuideVersion.state == rules.PUBLISHED,
        )
        .one_or_none()
    )


def of_row(row: DecisionGuideVersion) -> markets.QuestionSet:
    return rules.build(row.market, row.code, row.questions or [])


def current(db: Session | None, tenant_id, market: str) -> markets.QuestionSet:
    """The question set a new assessment of ``market`` uses now."""
    if db is None or tenant_id is None:
        return rules.starter(market)
    row = published(db, uuid.UUID(str(tenant_id)), market)
    return of_row(row) if row is not None else rules.starter(market)


def by_code(db: Session, tenant_id, market: str, code: str | None) -> markets.QuestionSet:
    """The question set of the version an assessment was started with (the current one when it names none)."""
    if not code:
        return current(db, tenant_id, market)
    if code == rules.starter(market).version:
        return rules.starter(market)
    row = (
        db.query(DecisionGuideVersion)
        .filter(
            DecisionGuideVersion.tenant_id == uuid.UUID(str(tenant_id)),
            DecisionGuideVersion.market == market,
            DecisionGuideVersion.code == code,
        )
        .one_or_none()
    )
    # A version that is not stored (the routine path's basis, a sample of an older release) reads as the starter.
    return of_row(row) if row is not None else rules.starter(market)


def current_codes(db: Session | None, tenant_id) -> dict[str, str]:
    """``{market: the code of its current version}`` for every market."""
    found = {market: rules.starter(market).version for market in markets.MARKETS}
    if db is None or tenant_id is None:
        return found
    for market, code in db.query(DecisionGuideVersion.market, DecisionGuideVersion.code).filter(
        DecisionGuideVersion.tenant_id == uuid.UUID(str(tenant_id)),
        DecisionGuideVersion.state == rules.PUBLISHED,
    ):
        found[market] = code
    return found
