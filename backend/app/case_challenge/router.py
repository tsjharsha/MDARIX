"""The investigation challenge (B5a), under ``/api/v1/investigations/{investigation_id}/challenge``:

- ``GET`` the rule drafts (H-0 to H-5) and challenge questions (C-1 to C-9) computed on read from the case's records,
  each draft with what was done with it (adopted as HYP-n, dismissed with a reason, or not acted on), each question
  with its answer from the brief draft. The first view of each scope version is audited (``CHALLENGE_VIEWED``).
- ``POST /drafts/adopt``: the draft becomes a hypothesis tagged with its rule and version; the facts the person ticks
  become unreviewed "record summary" evidence linked for or against it (``DRAFT_ADOPTED``).
- ``POST /drafts/dismiss`` with a reason (``DRAFT_DISMISSED``).
- ``POST /questions/answer``: the answer, or "not applicable" with a reason, kept in the brief draft's narrative so the
  signature covers it (``CHALLENGE_ANSWERED``).

Drafts are stored only when a person adopts or dismisses them (B5-D1). MDARIX never decides a root cause, never ranks
a draft and never writes a hypothesis by itself. Writes need ``investigation.work`` and refuse a closed case (409);
another organization's case is "not found". Off with ``MDARIX_CHALLENGE=off`` (feature_set.py).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.access.permissions import INVESTIGATION_WORK, require_permission
from backend.app.case_challenge import facts as facts_module
from backend.app.case_challenge import questions as question_rules
from backend.app.case_challenge import rules
from backend.app.case_intelligence import rules as intelligence
from backend.app.case_intelligence.router import _case, _error, _refuse_closed, _tenant, now_utc
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import Evidence, Hypothesis, HypothesisEvidence
from backend.app.db.models.intelligence import IntelligenceEvent
from backend.app.db.session import get_db
from backend.app.decision_brief import rules as brief_rules
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import current_person
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1/investigations/{investigation_id}/challenge", tags=["Investigation challenge"])

OBJECT_DRAFT = "CHALLENGE_DRAFT"
OBJECT_VIEW = "CHALLENGE"
REASON_MIN = 10
SIDES = {"for": "support", "against": "contradict"}


class AdoptPayload(BaseModel):
    key: str = Field(min_length=3, max_length=400)
    # The facts the person ticks: ``{"side": "for" | "against", "index": n}``; each becomes a record summary.
    facts: list[dict] = Field(default_factory=list, max_length=40)


class DismissPayload(BaseModel):
    key: str = Field(min_length=3, max_length=400)
    reason: str = Field(min_length=REASON_MIN, max_length=2000)


class AnswerPayload(BaseModel):
    key: str = Field(min_length=3, max_length=400)
    text: str = Field(min_length=question_rules.ANSWER_MIN, max_length=question_rules.ANSWER_MAX)
    not_applicable: bool = False


def _draft_object(case, key: str) -> uuid.UUID:
    """A stable id for a draft of this case (drafts are computed, so they have no row of their own)."""
    return uuid.uuid5(case.id, key)


def _actions(db: Session, case) -> dict[str, dict]:
    """``{draft key: the latest adopt or dismiss}``."""
    rows = (
        db.query(IntelligenceEvent)
        .filter(
            IntelligenceEvent.tenant_id == case.tenant_id,
            IntelligenceEvent.investigation_id == case.id,
            IntelligenceEvent.object_type == OBJECT_DRAFT,
        )
        .order_by(IntelligenceEvent.created_at)
        .all()
    )
    found: dict[str, dict] = {}
    for row in rows:
        details = row.details or {}
        found[details.get("key")] = {
            "state": row.event_type,
            "reason": row.reason,
            "hypothesis": details.get("hypothesis_business_id"),
            "by": row.actor_ref,
            "at": row.created_at,
        }
    return found


def challenge_view(db: Session, case, now) -> dict:
    """Drafts, questions and what people did with them (also read by the brief composer)."""
    facts = facts_module.read(db, case, now)
    found = rules.drafts(facts)
    asked = question_rules.questions(facts, found)
    actions = _actions(db, case)
    # The answers kept in the latest brief version's narrative, changeable while that version is a draft.
    answers, editable = facts["brief"]["narrative"].get("challenge_answers") or {}, facts["brief"]["draft"]
    for draft in found:
        draft["action"] = actions.get(draft["key"])
    for item in asked:
        item["answer"] = answers.get(item["key"])
    return {
        "rule_version": rules.RULE_VERSION,
        "as_of": now,
        "scope_version": facts["scope_version"],
        "fingerprint": facts_module.fingerprint(facts),
        "notice": "Drafted by rule from your records. Drafts are explanations to test, not findings; you decide.",
        "summary": {
            "complaints": len(facts["complaints"]),
            "no_version": sum(1 for c in facts["complaints"] if c["version_id"] is None),
            "no_lot": sum(1 for c in facts["complaints"] if c["lot_id"] is None),
            "outside": len(facts["outside"]),
            "changes": len(facts["changes"]),
        },
        "drafts": found,
        "questions": asked,
        "blocking": [item["key"] for item in question_rules.blocking(asked, answers)],
        "answers_editable": editable,
        "facts": facts,
    }


def _audit(db, ctx, case, person_ref, action, entity_type, entity_id, now, *, reason=None, details=None):
    db.add(
        make_audit_event(
            tenant_id=case.tenant_id,
            actor_ref=person_ref,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            correlation_id=ctx.correlation_id,
            reason=reason,
            details={"investigation_id": str(case.id), **(details or {})},
            created_at=now,
        )
    )


def _event(db, case, person, object_id, event_type, now, *, reason=None, details=None, object_type=OBJECT_DRAFT):
    db.add(
        IntelligenceEvent(
            id=uuid.uuid4(),
            tenant_id=case.tenant_id,
            investigation_id=case.id,
            object_type=object_type,
            object_id=object_id,
            event_type=event_type,
            reason=reason,
            actor_ref=person.user_id,
            actor_role=person.role_for(INVESTIGATION_WORK),
            details=details or {},
            created_at=now,
        )
    )


def _public(view: dict) -> dict:
    """The view without the raw facts (they hold every record read; the drafts and questions cite what matters)."""
    return {key: value for key, value in view.items() if key != "facts"}


@router.get("")
def read_challenge(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    case = _case(db, _tenant(ctx), investigation_id)
    now = now_utc()
    view = challenge_view(db, case, now)
    seen = (
        db.query(IntelligenceEvent.id)
        .filter(
            IntelligenceEvent.tenant_id == case.tenant_id,
            IntelligenceEvent.investigation_id == case.id,
            IntelligenceEvent.object_type == OBJECT_VIEW,
            IntelligenceEvent.details["scope_version"].astext == str(view["scope_version"]),
        )
        .first()
    )
    if seen is None:
        person = current_person(control_db, ctx)
        details = {"scope_version": view["scope_version"], "drafts": [d["rule"] for d in view["drafts"]]}
        _event(db, case, person, case.id, "VIEWED", now, details=details, object_type=OBJECT_VIEW)
        _audit(db, ctx, case, person.user_id, "CHALLENGE_VIEWED", "Investigation", case.id, now, details=details)
        db.commit()
    return _public(view)


def _current_draft(view: dict, key: str) -> dict:
    draft = next((item for item in view["drafts"] if item["key"] == key), None)
    if draft is None:
        raise _error(409, "DRAFT_NOT_CURRENT", "This draft no longer follows from the records; open Challenge again")
    if draft["rule"] == "H-0":
        raise _error(
            409, "DRAFT_NOT_ADOPTABLE", "'Not enough records' is a list of what is missing, not an explanation"
        )
    return draft


@router.post("/drafts/adopt", status_code=201, dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def adopt_draft(
    investigation_id: uuid.UUID,
    payload: AdoptPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The draft becomes a hypothesis a person proposes, tagged with the rule that drafted it; each ticked fact becomes
    an unreviewed record summary linked for or against it, to be reviewed like any evidence."""
    person = current_person(control_db, ctx)
    case = _case(db, _tenant(ctx), investigation_id, lock=True)
    _refuse_closed(case)
    now = now_utc()
    view = challenge_view(db, case, now)
    draft = _current_draft(view, payload.key)
    if (draft["action"] or {}).get("state") == "ADOPTED":
        raise _error(409, "DRAFT_ALREADY_ADOPTED", f"Already adopted as {draft['action']['hypothesis']}")
    ticked = []
    for item in payload.facts:
        side, index = item.get("side"), item.get("index")
        if side not in SIDES or not isinstance(index, int) or not 0 <= index < len(draft[side]):
            raise _error(422, "FACT_NOT_IN_DRAFT", "Tick facts listed for or against this draft")
        if (side, index) not in [(s, i) for s, i, _ in ticked]:
            ticked.append((side, index, draft[side][index]))
    hypothesis = Hypothesis(
        id=uuid.uuid4(),
        tenant_id=case.tenant_id,
        investigation_id=case.id,
        statement=draft["statement"],
        status=intelligence.PROPOSED.lower(),
        origin=intelligence.ORIGIN_HUMAN,
        human_status=intelligence.PROPOSED,
        status_reason=f"Drafted by rule {draft['rule']} v{draft['rule_version']} from the records; adopted.",
        status_changed_by=person.user_id,
        status_changed_at=now,
        created_by=person.user_id,
        draft_rule=draft["rule"],
        draft_rule_version=draft["rule_version"],
        created_at=now,
        updated_at=now,
    )
    db.add(hypothesis)
    db.flush()
    summaries = []
    for n, (side, _, fact) in enumerate(ticked, 1):
        cited = ", ".join(record["ref"] for record in fact["records"][:30])
        evidence = Evidence(
            id=uuid.uuid4(),
            tenant_id=case.tenant_id,
            evidence_identifier=f"{hypothesis.business_id}-RS{n:02d}"[:120],
            investigation_id=case.id,
            evidence_type="record_summary",
            title=fact["text"][:255],
            source_reference=f"Rule {draft['rule']} v{draft['rule_version']}: {cited}"[:2000] if cited else None,
            reliability_status="unreviewed",
            fact_type="derived_fact",
            content=fact["text"],
            source_system="MDARIX",
            created_at=now,
            updated_at=now,
        )
        db.add(evidence)
        db.flush()
        db.add(
            HypothesisEvidence(
                id=uuid.uuid4(),
                tenant_id=case.tenant_id,
                hypothesis_id=hypothesis.id,
                evidence_id=evidence.id,
                relation_type=SIDES[side],
                rationale=f"Record summary ticked from draft {draft['rule']} ({side}).",
                created_by_type="human",
                created_by=person.user_id,
                created_at=now,
            )
        )
        summaries.append({"evidence": evidence.business_id, "side": side})
    details = {
        "key": draft["key"],
        "rule": draft["rule"],
        "rule_version": draft["rule_version"],
        "fingerprint": view["fingerprint"],
        "hypothesis_business_id": hypothesis.business_id,
        "record_summaries": summaries,
    }
    _event(db, case, person, _draft_object(case, draft["key"]), "ADOPTED", now, details=details)
    _event(
        db,
        case,
        person,
        hypothesis.id,
        intelligence.EVENT_CREATED,
        now,
        details={"business_id": hypothesis.business_id, "origin": "HUMAN", "draft_rule": draft["rule"]},
        object_type=intelligence.OBJECT_HYPOTHESIS,
    )
    _audit(db, ctx, case, person.user_id, "DRAFT_ADOPTED", "Hypothesis", hypothesis.id, now, details=details)
    db.commit()
    return {
        "hypothesis": {"id": str(hypothesis.id), "business_id": hypothesis.business_id},
        "record_summaries": summaries,
    }


@router.post("/drafts/dismiss", dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def dismiss_draft(
    investigation_id: uuid.UUID,
    payload: DismissPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    person = current_person(control_db, ctx)
    case = _case(db, _tenant(ctx), investigation_id, lock=True)
    _refuse_closed(case)
    now = now_utc()
    view = challenge_view(db, case, now)
    draft = _current_draft(view, payload.key)
    if (draft["action"] or {}).get("state") == "ADOPTED":
        raise _error(
            409, "DRAFT_ALREADY_ADOPTED", f"Already adopted as {draft['action']['hypothesis']}; retire it there"
        )
    reason = payload.reason.strip()
    details = {
        "key": draft["key"],
        "rule": draft["rule"],
        "rule_version": draft["rule_version"],
        "fingerprint": view["fingerprint"],
    }
    _event(db, case, person, _draft_object(case, draft["key"]), "DISMISSED", now, reason=reason, details=details)
    _audit(
        db, ctx, case, person.user_id, "DRAFT_DISMISSED", "Investigation", case.id, now, reason=reason, details=details
    )
    db.commit()
    return {"key": draft["key"], "state": "DISMISSED", "reason": reason}


@router.post("/questions/answer", dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def answer_question(
    investigation_id: uuid.UUID,
    payload: AnswerPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The author's answer (or "not applicable" with the reason), kept in the brief draft: the brief's content hash
    covers the narrative, so the decision maker's signature covers the answers."""
    from backend.app.decision_brief.router import _draft

    person = current_person(control_db, ctx)
    case = _case(db, _tenant(ctx), investigation_id, lock=True)
    _refuse_closed(case)
    now = now_utc()
    view = challenge_view(db, case, now)
    question = next((item for item in view["questions"] if item["key"] == payload.key), None)
    if question is None:
        raise _error(409, "QUESTION_NOT_CURRENT", "This question no longer follows from the records")
    row = _draft(db, case)
    narrative = brief_rules.with_contributor(row.narrative, person.user_id)
    answers = dict(narrative.get("challenge_answers") or {})
    answers[question["key"]] = {
        "rule": question["rule"],
        "rule_version": question["rule_version"],
        "question": question["text"],
        "text": payload.text.strip(),
        "not_applicable": payload.not_applicable,
        "answered_by": person.user_id,
        "answered_at": now.isoformat(),
    }
    narrative["challenge_answers"] = answers
    row.narrative = narrative
    row.content_hash = brief_rules.content_hash(row.content, narrative)
    row.updated_at = now
    details = {"key": question["key"], "rule": question["rule"], "not_applicable": payload.not_applicable}
    _audit(db, ctx, case, person.user_id, "CHALLENGE_ANSWERED", "DecisionBriefVersion", row.id, now, details=details)
    db.commit()
    return {"key": question["key"], "answer": answers[question["key"]]}
