"""MDARIX IDs (``business_id``) on AI results as the API returns them.

The analysis, hypothesis, unknowns and failure-chain results are AI outputs: their models are also the grounding
context and the stored output of an AI execution. Their ``business_id`` fields are therefore filled here, after the
service has produced (and saved) the result and only for the response, so prompts and stored outputs never change.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Iterator
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.business_ids import business_id_map
from backend.app.db.models.foundation import Evidence, FailureChain, Hypothesis, Unknown
from investigator.schemas import SourceReference


def _source_references(value: Any) -> Iterator[SourceReference]:
    """Every evidence reference inside a result (models and lists of models; raw JSON dicts are not searched)."""
    if isinstance(value, SourceReference):
        yield value
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from _source_references(getattr(value, name))
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _source_references(item)


def with_evidence_business_ids(db: Session, result: BaseModel) -> BaseModel:
    """Set ``evidence_business_id`` on every evidence reference of ``result`` (one query) and return it."""
    references = list(_source_references(result))
    ids = business_id_map(db, Evidence, (reference.evidence_id for reference in references))
    for reference in references:
        reference.evidence_business_id = ids.get(str(reference.evidence_id)) if reference.evidence_id else None
    return result


def _record_business_ids(
    db: Session, model: Any, text_column: Any, tenant_id: Any, investigation_id: Any
) -> tuple[dict[str, str], dict[str, str]]:
    """The investigation's records of ``model`` as ``({str(id): business_id}, {text: business_id})``, one query.

    A result item is matched to its record by id, else by its text: records are written per statement, so an item
    regenerated with the same statement belongs to the record that already holds it (the newest one wins).
    """
    rows = db.execute(
        select(model.id, text_column, model.business_id)
        .where(model.tenant_id == tenant_id, model.investigation_id == investigation_id)
        .order_by(model.created_at.desc().nullslast())
    ).all()
    by_text: dict[str, str] = {}
    for _, text, business_id in rows:
        by_text.setdefault(text, business_id)
    return {str(row_id): business_id for row_id, _, business_id in rows}, by_text


def _fill(
    db: Session,
    model: Any,
    text_column: Any,
    tenant_id: Any,
    investigation_id: uuid.UUID,
    items: Iterable[Any],
    id_attribute: str,
    text_attribute: str,
) -> None:
    items = list(items)
    if not items:
        return
    by_id, by_text = _record_business_ids(db, model, text_column, tenant_id, investigation_id)
    for item in items:
        item.business_id = by_id.get(str(getattr(item, id_attribute))) or by_text.get(getattr(item, text_attribute))


def with_hypothesis_business_ids(db: Session, tenant_id: Any, response):
    """A ``HypothesisSetResponse`` with each proposed hypothesis's MDARIX ID and its evidence references' IDs."""
    hypothesis_set = response.hypothesis_set
    _fill(
        db,
        Hypothesis,
        Hypothesis.statement,
        tenant_id,
        hypothesis_set.investigation_id,
        hypothesis_set.hypotheses,
        "hypothesis_id",
        "statement",
    )
    return with_evidence_business_ids(db, response)


def with_unknown_business_ids(db: Session, tenant_id: Any, response):
    """An ``UnknownResponse`` with each unknown's MDARIX ID (when it is recorded) and its evidence references' IDs."""
    unknown_set = response.unknown_set
    _fill(
        db,
        Unknown,
        Unknown.description,
        tenant_id,
        unknown_set.investigation_id,
        unknown_set.unknowns,
        "unknown_id",
        "statement",
    )
    return with_evidence_business_ids(db, response)


def with_failure_chain_business_ids(db: Session, tenant_id: Any, response):
    """A ``FailureChainResponse`` with each chain's MDARIX ID (when it is recorded) and its evidence references' IDs."""
    chain_set = response.failure_chain_set
    _fill(
        db,
        FailureChain,
        FailureChain.name,
        tenant_id,
        chain_set.investigation_id,
        chain_set.chains,
        "chain_id",
        "chain_statement",
    )
    return with_evidence_business_ids(db, response)
