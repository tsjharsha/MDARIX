"""A case's intelligence as people work it: next to what the AI produced, what people judge and add themselves.

Under ``/api/v1/investigations/{investigation_id}/intelligence``:

- ``GET  /hypotheses``; ``POST /hypotheses`` (a person's own); ``POST /hypotheses/{id}/status`` (a person's
  judgement); ``POST /hypotheses/{id}/evidence`` and ``POST /hypotheses/{id}/evidence/{link_id}/retract``.
- ``GET  /contradictions``: contradicting evidence of hypotheses, contradicting case evidence, and the latest AI
  challenges (labelled as AI interpretation). Read-only.
- ``GET  /unknowns``; ``POST /unknowns``; ``POST /unknowns/{id}/status``.
- ``GET  /failure-chains`` (stored chains, and the latest AI chains as the AI produced them); ``POST /failure-chains``
  (built by a person); ``POST /failure-chains/adopt`` (an AI chain copied into the case);
  ``POST /failure-chains/{id}/links/{link_id}/state``.
- ``GET  /observations``; ``POST /observations`` (a fact, source assertion or derived observation, never an AI
  interpretation).
- ``GET  /history``: every change above, newest first.

Reading needs a signed-in session. Every write needs ``investigation.work`` (linking or withdrawing hypothesis evidence
also ``evidence.review``), refuses a CLOSED or CANCELLED case (409), locks the row it changes, and is recorded in
``intelligence_events`` and the audit trail (``INTELLIGENCE_<EVENT>``) with the reason and the role it was done under.
Another organization's case is "not found". AI output in ``ai_executions`` is only ever read; nothing is deleted.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.app.access.permissions import EVIDENCE_REVIEW, INVESTIGATION_WORK, require_permission
from backend.app.business_ids import as_uuid
from backend.app.case_intelligence import rules
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.evidence_intelligence import EvidenceObservation
from backend.app.db.models.foundation import (
    AIExecution,
    Evidence,
    FailureChain,
    FailureChainEdge,
    FailureChainNode,
    Hypothesis,
    HypothesisEvidence,
    Investigation,
    InvestigationEvidence,
    Unknown,
)
from backend.app.db.models.intelligence import IntelligenceEvent
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import Person, current_person
from backend.app.evidence_workflow.rules import case_closed
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

logger = logging.getLogger("mdarix.case_intelligence")

router = APIRouter(prefix="/api/v1/investigations/{investigation_id}/intelligence", tags=["Case Intelligence"])

OBSERVATIONS_LIMIT = 500


def require_permission_any_of(*permissions: str):
    """A permission guard allowing the request when the person holds at least one of ``permissions`` (403
    PERMISSION_DENIED otherwise)."""
    from backend.app.access.permissions import ALL

    unknown = [permission for permission in permissions if permission not in ALL]
    if not permissions or unknown:
        raise ValueError(f"Unknown permission {unknown}")

    def dependency(
        ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)
    ) -> None:
        from backend.app.access.permissions import effective_permissions

        granted = effective_permissions(db, ctx)
        if not any(permission in granted for permission in permissions):
            raise HTTPException(
                403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Your role does not allow this action",
                    "permission": " or ".join(permissions),
                },
            )

    return dependency


# --------------------------------------------------------------------------------------------------- helpers


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _error(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message, **extra})


def _tenant(ctx: AuthenticatedRequestContext) -> uuid.UUID:
    return uuid.UUID(str(ctx.tenant_id))


def _case(db: Session, tenant_id, investigation_id, *, lock: bool = False) -> Investigation:
    query = db.query(Investigation).filter(Investigation.id == investigation_id, Investigation.tenant_id == tenant_id)
    if lock:
        query = query.with_for_update()
    case = query.first()
    if case is None:
        raise _error(404, "INVESTIGATION_NOT_FOUND", "Investigation is not available")
    return case


def _is_open(case: Investigation) -> bool:
    return not case_closed(getattr(case, "workflow_state", None), case.status)


def _refuse_closed(case: Investigation) -> None:
    if not _is_open(case):
        raise _error(409, "CASE_CLOSED", "The investigation is closed; its analysis can no longer change")


def _names(control_db: Session | None, tenant_id, refs) -> dict[str, str]:
    from backend.app.workflow.people import names_by_id

    if control_db is None:
        return {}
    return names_by_id(control_db, tenant_id, [ref for ref in refs if ref])


def _name(names: dict[str, str], ref) -> str | None:
    key = as_uuid(ref)
    if key is not None:
        return names.get(str(key))
    return "MDARIX" if str(ref or "").startswith("system") else None


def _short(value, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _evidence_ref(ev: Evidence | None) -> dict | None:
    if ev is None:
        return None
    return {"id": str(ev.id), "business_id": ev.business_id, "title": ev.title}


def _case_evidence_ids(db: Session, tenant_id, case_id) -> set[uuid.UUID]:
    """The case's evidence: linked to it, or recorded on it."""
    linked = {
        row[0]
        for row in db.query(InvestigationEvidence.evidence_id).filter(
            InvestigationEvidence.tenant_id == tenant_id, InvestigationEvidence.investigation_id == case_id
        )
    }
    direct = {
        row[0]
        for row in db.query(Evidence.id).filter(Evidence.tenant_id == tenant_id, Evidence.investigation_id == case_id)
    }
    return linked | direct


def _case_evidence(db: Session, tenant_id, case: Investigation, evidence_id) -> Evidence:
    ev = db.query(Evidence).filter(Evidence.tenant_id == tenant_id, Evidence.id == evidence_id).first()
    if ev is None:
        raise _error(404, "EVIDENCE_NOT_FOUND", "Evidence is not available in your organization")
    if ev.investigation_id == case.id:
        return ev
    linked = (
        db.query(InvestigationEvidence.id)
        .filter(
            InvestigationEvidence.tenant_id == tenant_id,
            InvestigationEvidence.investigation_id == case.id,
            InvestigationEvidence.evidence_id == ev.id,
        )
        .first()
    )
    if linked is None:
        raise _error(404, "EVIDENCE_NOT_IN_CASE", "Link the evidence to the investigation first")
    return ev


def _record(
    db: Session,
    *,
    ctx: AuthenticatedRequestContext,
    person: Person,
    permission: str,
    case: Investigation,
    object_type: str,
    object_id,
    entity_type: str,
    event_type: str,
    now: datetime,
    from_value=None,
    to_value=None,
    reason: str | None = None,
    details: dict | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
) -> None:
    """The change in the case's intelligence history and in the audit trail, under the role granting ``permission``."""
    role = person.role_for(permission)
    details = {key: value for key, value in (details or {}).items() if value is not None}
    db.add(
        IntelligenceEvent(
            id=uuid.uuid4(),
            tenant_id=case.tenant_id,
            investigation_id=case.id,
            object_type=object_type,
            object_id=object_id,
            event_type=event_type,
            from_value=_short(from_value, 60),
            to_value=_short(to_value, 60),
            reason=reason,
            actor_ref=person.user_id,
            actor_role=role,
            details=details,
            created_at=now,
        )
    )
    db.add(
        make_audit_event(
            tenant_id=case.tenant_id,
            actor_ref=person.user_id,
            action=rules.audit_action(event_type),
            entity_type=entity_type,
            entity_id=object_id,
            correlation_id=ctx.correlation_id,
            reason=reason,
            old_values=old_values,
            new_values=new_values,
            details={
                "investigation_id": str(case.id),
                "object_type": object_type,
                "actor_role": role,
                **details,
            },
            created_at=now,
        )
    )


def _optional(db: Session, name: str, read, default=None):
    """An optional read inside a SAVEPOINT: AI output that cannot be read never fails the page."""
    try:
        with db.begin_nested():
            return read()
    except Exception:
        logger.warning("Case intelligence: %s could not be read", name, exc_info=True)
        return default


# ------------------------------------------------------------------------------------------------- hypotheses


def _hypothesis_rows(db: Session, tenant_id, case_id, *, include_retired=True, include_superseded=True, ids=None):
    query = db.query(Hypothesis).filter(Hypothesis.tenant_id == tenant_id, Hypothesis.investigation_id == case_id)
    if ids is not None:
        query = query.filter(Hypothesis.id.in_(list(ids)))
    rows = query.order_by(Hypothesis.created_at.desc(), Hypothesis.business_id).all()
    return [
        row
        for row in rows
        if (include_superseded or str(row.status or "").lower() != rules.SUPERSEDED)
        and (include_retired or str(row.human_status or "").upper() != rules.RETIRED)
    ]


def _recorded(db: Session, tenant_id, execution_ids) -> set[str]:
    """The ids among these saved AI results that were recorded with the sample (provider ``sample-recorded``): no
    model was called for them (W1). One lookup; none without ids."""
    from backend.app.trial.sample_ai import PROVIDER as SAMPLE_PROVIDER

    ids = {as_uuid(item) for item in execution_ids if item} - {None}
    if not ids:
        return set()
    rows = db.query(AIExecution.id).filter(
        AIExecution.tenant_id == tenant_id, AIExecution.id.in_(list(ids)), AIExecution.provider == SAMPLE_PROVIDER
    )
    return {str(row.id) for row in rows}


def _hypothesis_items(
    db: Session, control_db: Session | None, tenant_id, case: Investigation, person: Person, rows: list[Hypothesis]
) -> list[dict]:
    ids = [row.id for row in rows]
    # An AI hypothesis names the saved result it came from (source_identifier): recorded with the sample or not.
    recorded = _recorded(
        db, tenant_id, [row.source_identifier for row in rows if rules.origin_code(row.origin) != "HUMAN"]
    )
    links = (
        db.query(HypothesisEvidence)
        .filter(HypothesisEvidence.tenant_id == tenant_id, HypothesisEvidence.hypothesis_id.in_(ids))
        .order_by(HypothesisEvidence.created_at, HypothesisEvidence.id)
        .all()
        if ids
        else []
    )
    evidence_ids = {link.evidence_id for link in links}
    evidence = (
        {
            ev.id: ev
            for ev in db.query(Evidence).filter(Evidence.tenant_id == tenant_id, Evidence.id.in_(list(evidence_ids)))
        }
        if evidence_ids
        else {}
    )
    unknowns = (
        db.query(Unknown)
        .filter(Unknown.tenant_id == tenant_id, Unknown.hypothesis_id.in_(ids))
        .order_by(Unknown.created_at, Unknown.business_id)
        .all()
        if ids
        else []
    )
    names = _names(
        control_db,
        tenant_id,
        [ref for row in rows for ref in (row.created_by, row.status_changed_by)]
        + [ref for link in links for ref in (link.created_by, link.retracted_by)],
    )
    open_case = _is_open(case)
    can_judge = open_case and person.holds(INVESTIGATION_WORK)
    can_link = open_case and person.holds_any(INVESTIGATION_WORK, EVIDENCE_REVIEW)
    by_hypothesis: dict[uuid.UUID, dict[str, list]] = {
        row.id: {"supporting": [], "contradicting": [], "contextual": [], "unresolved": []} for row in rows
    }
    for link in links:
        human = rules.link_is_human(link.created_by_type)
        by_hypothesis[link.hypothesis_id][rules.relation_bucket(link.relation_type)].append(
            {
                "id": str(link.id),
                "evidence": (
                    {
                        "id": str(link.evidence_id),
                        "business_id": evidence[link.evidence_id].business_id,
                        "title": evidence[link.evidence_id].title,
                        "evidence_type": evidence[link.evidence_id].evidence_type,
                    }
                    if link.evidence_id in evidence
                    else {"id": str(link.evidence_id), "business_id": None, "title": None, "evidence_type": None}
                ),
                "relation": rules.relation_bucket(link.relation_type).upper(),
                "rationale": link.rationale,
                "added_by": (_name(names, link.created_by) or rules.SOMEONE) if human else rules.ADDED_BY_AI,
                "created_by_type": link.created_by_type,
                "created_at": _iso(link.created_at),
                "retracted": link.retracted_at is not None,
                "retracted_at": _iso(link.retracted_at),
                "retracted_by_name": _name(names, link.retracted_by),
                "retraction_reason": link.retraction_reason,
            }
        )
    unknowns_by_hypothesis: dict[uuid.UUID, list] = {row.id: [] for row in rows}
    for item in unknowns:
        unknowns_by_hypothesis[item.hypothesis_id].append(
            {
                "id": str(item.id),
                "business_id": item.business_id,
                "description": item.description,
                "status": item.status,
                "status_label": rules.unknown_status_label(item.status),
            }
        )
    items = []
    for row in rows:
        origin = rules.origin_code(row.origin)
        superseded = str(row.status or "").lower() == rules.SUPERSEDED
        created_by_name = _name(names, row.created_by)
        judged_by_name = _name(names, row.status_changed_by)
        ai_status = None if origin == "HUMAN" else row.status
        items.append(
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "statement": row.statement,
                "origin": origin,
                "ai_status": ai_status,
                "ai_status_label": rules.ai_status_label(ai_status),
                "human_status": row.human_status,
                "human_status_label": rules.human_status_label(row.human_status),
                "status_reason": row.status_reason,
                "status_changed_by_name": judged_by_name,
                "status_changed_at": _iso(row.status_changed_at),
                "created_by_name": created_by_name,
                "created_at": _iso(row.created_at),
                "superseded": superseded,
                # RCA fishbone (trrcatools): the cause category and the FMEA failure mode a person gave it.
                "cause_category": row.cause_category,
                "failure_mode_id": str(row.failure_mode_id) if row.failure_mode_id else None,
                "kind_label": rules.kind_label(
                    row.origin, row.human_status, created_by_name=created_by_name, judged_by_name=judged_by_name
                ),
                # W1: recorded with the sample, no model called ("Recorded with the sample · no model was called").
                "recorded": str(row.source_identifier) in recorded,
                "evidence": by_hypothesis[row.id],
                "unknowns": unknowns_by_hypothesis[row.id],
                "actions": {
                    "can_set_status": can_judge and not superseded,
                    "can_link_evidence": can_link and not superseded,
                },
            }
        )
    return items


def _hypothesis_counts(rows: list[Hypothesis], shown: int) -> dict[str, int]:
    origins = [rules.origin_code(row.origin) for row in rows]
    current = [row for row in rows if str(row.status or "").lower() != rules.SUPERSEDED]
    return {
        "shown": shown,
        "ai": sum(1 for code in origins if code == "AI"),
        "system": sum(1 for code in origins if code == "SYSTEM"),
        "human": sum(1 for code in origins if code == "HUMAN"),
        "judged": sum(1 for row in current if row.human_status),
        "not_judged": sum(1 for row in current if not row.human_status and rules.origin_code(row.origin) != "HUMAN"),
        "retired": sum(1 for row in rows if str(row.human_status or "").upper() == rules.RETIRED),
        "superseded": len(rows) - len(current),
    }


def _one_hypothesis(db, control_db, tenant_id, case, person, hypothesis_id) -> dict:
    rows = _hypothesis_rows(db, tenant_id, case.id, ids=[hypothesis_id])
    return _hypothesis_items(db, control_db, tenant_id, case, person, rows)[0]


def _locked_hypothesis(db: Session, tenant_id, case: Investigation, hypothesis_id) -> Hypothesis:
    row = (
        db.query(Hypothesis)
        .filter(
            Hypothesis.tenant_id == tenant_id, Hypothesis.investigation_id == case.id, Hypothesis.id == hypothesis_id
        )
        .with_for_update()
        .first()
    )
    if row is None:
        raise _error(404, "HYPOTHESIS_NOT_FOUND", "Hypothesis is not available in this investigation")
    if str(row.status or "").lower() == rules.SUPERSEDED:
        raise _error(409, "HYPOTHESIS_SUPERSEDED", "This hypothesis was replaced by a newer AI run and cannot change")
    return row


@router.get("/hypotheses")
def list_hypotheses(
    investigation_id: uuid.UUID,
    include_retired: bool = Query(False),
    include_superseded: bool = Query(False),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The case's hypotheses: the AI's (with the AI's status) and people's, each with a person's judgement when there is
    one, its evidence by relation (withdrawn links flagged) and its unknowns. Superseded ones only on request."""
    tenant_id = _tenant(ctx)
    case = _case(db, tenant_id, investigation_id)
    person = current_person(control_db, ctx)
    every = _hypothesis_rows(db, tenant_id, case.id)
    rows = [
        row
        for row in every
        if (include_superseded or str(row.status or "").lower() != rules.SUPERSEDED)
        and (include_retired or str(row.human_status or "").upper() != rules.RETIRED)
    ]
    items = _hypothesis_items(db, control_db, tenant_id, case, person, rows)
    return {
        "items": items,
        "counts": _hypothesis_counts(every, len(items)),
        "actions": {"can_add": _is_open(case) and person.holds(INVESTIGATION_WORK)},
    }


@router.post("/hypotheses", status_code=201, dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def create_hypothesis(
    investigation_id: uuid.UUID,
    payload: rules.HypothesisCreatePayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """A hypothesis a person adds: origin "human", proposed by them, with their reasoning."""
    tenant_id = _tenant(ctx)
    person = current_person(control_db, ctx)
    case = _case(db, tenant_id, investigation_id, lock=True)
    _refuse_closed(case)
    duplicate = (
        db.query(Hypothesis.id)
        .filter(
            Hypothesis.tenant_id == tenant_id,
            Hypothesis.investigation_id == case.id,
            func.lower(Hypothesis.statement) == payload.statement.lower(),
            Hypothesis.status != rules.SUPERSEDED,
        )
        .first()
    )
    if duplicate is not None:
        raise _error(
            409, "HYPOTHESIS_EXISTS", "The investigation already has this hypothesis", hypothesis_id=str(duplicate[0])
        )
    now = now_utc()
    row = Hypothesis(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        investigation_id=case.id,
        statement=payload.statement,
        status=rules.PROPOSED.lower(),
        origin=rules.ORIGIN_HUMAN,
        reviewer_disposition=None,
        human_status=rules.PROPOSED,
        status_reason=payload.rationale,
        status_changed_by=person.user_id,
        status_changed_at=now,
        created_by=person.user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    _record(
        db,
        ctx=ctx,
        person=person,
        permission=INVESTIGATION_WORK,
        case=case,
        object_type=rules.OBJECT_HYPOTHESIS,
        object_id=row.id,
        entity_type="Hypothesis",
        event_type=rules.EVENT_CREATED,
        to_value=rules.PROPOSED,
        reason=payload.rationale,
        details={"business_id": row.business_id, "statement": payload.statement, "origin": "HUMAN"},
        new_values={"statement": payload.statement, "human_status": rules.PROPOSED, "status_reason": payload.rationale},
        now=now,
    )
    db.commit()
    return _one_hypothesis(db, control_db, tenant_id, case, person, row.id)


@router.post("/hypotheses/{hypothesis_id}/status", dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def set_hypothesis_status(
    investigation_id: uuid.UUID,
    hypothesis_id: uuid.UUID,
    payload: rules.HypothesisStatusPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """A person's judgement of a hypothesis (the AI's status stays as it is). An AI hypothesis a person has judged is
    never superseded by a later AI run."""
    tenant_id = _tenant(ctx)
    person = current_person(control_db, ctx)
    case = _case(db, tenant_id, investigation_id, lock=True)
    _refuse_closed(case)
    row = _locked_hypothesis(db, tenant_id, case, hypothesis_id)
    if row.human_status == payload.human_status:
        raise _error(409, "HYPOTHESIS_STATUS_UNCHANGED", "The hypothesis already has this status")
    now = now_utc()
    before = {
        "human_status": row.human_status,
        "status_reason": row.status_reason,
        "reviewer_disposition": row.reviewer_disposition,
    }
    row.human_status = payload.human_status
    row.status_reason = payload.reason
    row.status_changed_by = person.user_id
    row.status_changed_at = now
    if row.reviewer_disposition is None:
        row.reviewer_disposition = rules.HUMAN_JUDGED
    row.updated_at = now
    _record(
        db,
        ctx=ctx,
        person=person,
        permission=INVESTIGATION_WORK,
        case=case,
        object_type=rules.OBJECT_HYPOTHESIS,
        object_id=row.id,
        entity_type="Hypothesis",
        event_type=rules.EVENT_STATUS_CHANGED,
        from_value=before["human_status"],
        to_value=payload.human_status,
        reason=payload.reason,
        details={"business_id": row.business_id, "origin": rules.origin_code(row.origin), "ai_status": row.status},
        old_values=before,
        new_values={
            "human_status": payload.human_status,
            "status_reason": payload.reason,
            "reviewer_disposition": row.reviewer_disposition,
        },
        now=now,
    )
    db.commit()
    return _one_hypothesis(db, control_db, tenant_id, case, person, row.id)


def _evidence_permission(person: Person) -> str:
    return INVESTIGATION_WORK if person.holds(INVESTIGATION_WORK) else EVIDENCE_REVIEW


@router.post(
    "/hypotheses/{hypothesis_id}/evidence",
    status_code=201,
    dependencies=[Depends(require_permission_any_of(INVESTIGATION_WORK, EVIDENCE_REVIEW))],
)
def link_hypothesis_evidence(
    investigation_id: uuid.UUID,
    hypothesis_id: uuid.UUID,
    payload: rules.HypothesisEvidencePayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Link evidence of the case to a hypothesis as supporting, contradicting, contextual or unresolved, with why."""
    tenant_id = _tenant(ctx)
    person = current_person(control_db, ctx)
    case = _case(db, tenant_id, investigation_id, lock=True)
    _refuse_closed(case)
    row = _locked_hypothesis(db, tenant_id, case, hypothesis_id)
    ev = _case_evidence(db, tenant_id, case, payload.evidence_id)
    relation_type = rules.relation_type(payload.relation)
    active = (
        db.query(HypothesisEvidence.id)
        .filter(
            HypothesisEvidence.tenant_id == tenant_id,
            HypothesisEvidence.hypothesis_id == row.id,
            HypothesisEvidence.evidence_id == ev.id,
            HypothesisEvidence.relation_type == relation_type,
            HypothesisEvidence.retracted_at.is_(None),
        )
        .first()
    )
    if active is not None:
        raise _error(
            409,
            "EVIDENCE_ALREADY_LINKED",
            "This evidence is already linked to the hypothesis this way",
            link_id=str(active[0]),
        )
    now = now_utc()
    link = HypothesisEvidence(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        hypothesis_id=row.id,
        evidence_id=ev.id,
        relation_type=relation_type,
        rationale=payload.rationale,
        created_by_type=rules.CREATED_BY_HUMAN,
        created_by=person.user_id,
        created_at=now,
    )
    db.add(link)
    db.flush()
    row.updated_at = now
    _record(
        db,
        ctx=ctx,
        person=person,
        permission=_evidence_permission(person),
        case=case,
        object_type=rules.OBJECT_HYPOTHESIS_EVIDENCE,
        object_id=link.id,
        entity_type="HypothesisEvidence",
        event_type=rules.EVENT_EVIDENCE_LINKED,
        to_value=payload.relation,
        reason=payload.rationale,
        details={
            "business_id": row.business_id,
            "hypothesis_id": str(row.id),
            "evidence_id": str(ev.id),
            "evidence_business_id": ev.business_id,
            "relation": payload.relation,
        },
        new_values={"relation_type": relation_type, "rationale": payload.rationale},
        now=now,
    )
    db.commit()
    return _one_hypothesis(db, control_db, tenant_id, case, person, row.id)


@router.post(
    "/hypotheses/{hypothesis_id}/evidence/{link_id}/retract",
    dependencies=[Depends(require_permission_any_of(INVESTIGATION_WORK, EVIDENCE_REVIEW))],
)
def retract_hypothesis_evidence(
    investigation_id: uuid.UUID,
    hypothesis_id: uuid.UUID,
    link_id: uuid.UUID,
    payload: rules.RetractPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Withdraw a link between evidence and a hypothesis (a person's or the AI's), with why. Nothing is deleted."""
    tenant_id = _tenant(ctx)
    person = current_person(control_db, ctx)
    case = _case(db, tenant_id, investigation_id, lock=True)
    _refuse_closed(case)
    row = _locked_hypothesis(db, tenant_id, case, hypothesis_id)
    link = (
        db.query(HypothesisEvidence)
        .filter(
            HypothesisEvidence.tenant_id == tenant_id,
            HypothesisEvidence.hypothesis_id == row.id,
            HypothesisEvidence.id == link_id,
        )
        .with_for_update()
        .first()
    )
    if link is None:
        raise _error(404, "EVIDENCE_LINK_NOT_FOUND", "This evidence link is not available")
    if link.retracted_at is not None:
        raise _error(409, "EVIDENCE_LINK_RETRACTED", "This evidence link was already withdrawn")
    ev = db.query(Evidence).filter(Evidence.tenant_id == tenant_id, Evidence.id == link.evidence_id).first()
    now = now_utc()
    link.retracted_at = now
    link.retracted_by = person.user_id
    link.retraction_reason = payload.reason
    row.updated_at = now
    relation = rules.relation_bucket(link.relation_type).upper()
    _record(
        db,
        ctx=ctx,
        person=person,
        permission=_evidence_permission(person),
        case=case,
        object_type=rules.OBJECT_HYPOTHESIS_EVIDENCE,
        object_id=link.id,
        entity_type="HypothesisEvidence",
        event_type=rules.EVENT_EVIDENCE_RETRACTED,
        from_value=relation,
        reason=payload.reason,
        details={
            "business_id": row.business_id,
            "hypothesis_id": str(row.id),
            "evidence_id": str(link.evidence_id),
            "evidence_business_id": ev.business_id if ev is not None else None,
            "relation": relation,
            "created_by_type": link.created_by_type,
        },
        old_values={"retracted_at": None},
        new_values={"retracted_at": now.isoformat(), "retraction_reason": payload.reason},
        now=now,
    )
    db.commit()
    return _one_hypothesis(db, control_db, tenant_id, case, person, row.id)


# ---------------------------------------------------------------------------------------------- contradictions


def _hypothesis_ref(row: Hypothesis | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "business_id": row.business_id,
        "statement": row.statement,
        "human_status": row.human_status,
        "human_status_label": rules.human_status_label(row.human_status),
    }


def _link_origin(created_by_type: str | None) -> str:
    """HUMAN, AI or SYSTEM for a hypothesis evidence link (system links come from the hypothesis engine)."""
    code = str(created_by_type or "").strip().lower()
    return {"human": "HUMAN", "ai": "AI"}.get(code, "SYSTEM")


def _after(later, earlier) -> bool:
    if later is None or earlier is None:
        return False
    if later.tzinfo is None:
        later = later.replace(tzinfo=timezone.utc)
    if earlier.tzinfo is None:
        earlier = earlier.replace(tzinfo=timezone.utc)
    return later >= earlier


def _latest_challenges(db: Session, tenant_id, case_id) -> dict | None:
    """The latest Challenger output for the case, as the AI produced it (read-only)."""
    from challenger.service import ChallengerService

    found = ChallengerService().latest(db, tenant_id, case_id)
    if found is None:
        return None
    return {"ai_execution_id": found.ai_execution_id, "set": found.challenge_set.model_dump(mode="json")}


def _evidence_from_references(db: Session, tenant_id, references: list) -> list[dict]:
    ids, identifiers = set(), set()
    for ref in references or ():
        if not isinstance(ref, dict):
            continue
        if as_uuid(ref.get("evidence_id")) is not None:
            ids.add(as_uuid(ref.get("evidence_id")))
        elif ref.get("evidence_identifier"):
            identifiers.add(str(ref.get("evidence_identifier")))
    if not ids and not identifiers:
        return []
    rows = db.query(Evidence).filter(Evidence.tenant_id == tenant_id)
    found = []
    if ids:
        found += rows.filter(Evidence.id.in_(list(ids))).all()
    if identifiers:
        found += rows.filter(Evidence.evidence_identifier.in_(list(identifiers))).all()
    unique = {ev.id: ev for ev in found}
    return [_evidence_ref(ev) for ev in sorted(unique.values(), key=lambda ev: ev.business_id or "")]


@router.get("/contradictions")
def list_contradictions(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """What contradicts the case's thinking: evidence linked to a hypothesis as contradicting (not withdrawn), case
    evidence reviewed as contradicting, and the latest AI challenges (AI interpretation). Says for each whether a person
    has judged the hypothesis since. Read-only."""
    tenant_id = _tenant(ctx)
    case = _case(db, tenant_id, investigation_id)
    hypotheses = {
        row.id: row
        for row in db.query(Hypothesis).filter(
            Hypothesis.tenant_id == tenant_id, Hypothesis.investigation_id == case.id
        )
    }
    current = [key for key, row in hypotheses.items() if str(row.status or "").lower() != rules.SUPERSEDED]
    links = (
        db.query(HypothesisEvidence)
        .filter(
            HypothesisEvidence.tenant_id == tenant_id,
            HypothesisEvidence.hypothesis_id.in_(current),
            HypothesisEvidence.relation_type == rules.CONTRADICT,
            HypothesisEvidence.retracted_at.is_(None),
        )
        .order_by(HypothesisEvidence.created_at.desc())
        .all()
        if current
        else []
    )
    reviews = (
        db.query(InvestigationEvidence)
        .filter(
            InvestigationEvidence.tenant_id == tenant_id,
            InvestigationEvidence.investigation_id == case.id,
            InvestigationEvidence.relationship == "CONTRADICTING",
        )
        .order_by(InvestigationEvidence.reviewed_at.desc().nullslast())
        .all()
    )
    evidence_ids = {link.evidence_id for link in links} | {review.evidence_id for review in reviews}
    evidence = (
        {
            ev.id: ev
            for ev in db.query(Evidence).filter(Evidence.tenant_id == tenant_id, Evidence.id.in_(list(evidence_ids)))
        }
        if evidence_ids
        else {}
    )
    names = _names(
        control_db,
        tenant_id,
        [link.created_by for link in links] + [review.reviewed_by for review in reviews],
    )
    items = []
    for link in links:
        hypothesis = hypotheses.get(link.hypothesis_id)
        origin = _link_origin(link.created_by_type)
        items.append(
            {
                "id": f"hypothesis-link:{link.id}",
                "kind": "HYPOTHESIS_LINK",
                "origin": origin,
                "label": rules.ORIGIN_LABELS["HUMAN"] if origin == "HUMAN" else rules.AI_INTERPRETATION,
                "hypothesis": _hypothesis_ref(hypothesis),
                "evidence": _evidence_ref(evidence.get(link.evidence_id)),
                "rationale": link.rationale,
                "added_by": (_name(names, link.created_by) or rules.SOMEONE)
                if origin == "HUMAN"
                else rules.ADDED_BY_AI,
                "judged_since": bool(
                    hypothesis is not None
                    and hypothesis.human_status
                    and _after(hypothesis.status_changed_at, link.created_at)
                ),
                "hypothesis_judged": bool(hypothesis is not None and hypothesis.human_status),
                "created_at": _iso(link.created_at),
            }
        )
    for review in reviews:
        items.append(
            {
                "id": f"case-evidence:{review.id}",
                "kind": "CASE_EVIDENCE",
                "origin": "HUMAN",
                "label": rules.ORIGIN_LABELS["HUMAN"],
                "hypothesis": None,
                "evidence": _evidence_ref(evidence.get(review.evidence_id)),
                "rationale": review.review_reason or review.relevance,
                "added_by": _name(names, review.reviewed_by),
                "judged_since": False,
                "hypothesis_judged": False,
                "created_at": _iso(review.reviewed_at or review.created_at),
            }
        )
    latest = _optional(db, "latest challenges", lambda: _latest_challenges(db, tenant_id, case.id))
    if latest is not None:
        produced = latest["set"].get("created_at")
        try:
            produced_at = datetime.fromisoformat(str(produced)) if produced else None
        except ValueError:
            produced_at = None
        for challenge in latest["set"].get("challenges") or []:
            hypothesis = hypotheses.get(as_uuid(challenge.get("hypothesis_id")))
            referenced = _optional(
                db,
                "challenge evidence",
                lambda challenge=challenge: _evidence_from_references(
                    db,
                    tenant_id,
                    list(challenge.get("contradiction_references") or [])
                    + list(challenge.get("evidence_references") or []),
                ),
                default=[],
            )
            items.append(
                {
                    "id": f"challenge:{challenge.get('challenge_id')}",
                    "kind": "CHALLENGER",
                    "origin": "AI",
                    "label": rules.AI_INTERPRETATION,
                    "hypothesis": _hypothesis_ref(hypothesis),
                    "evidence": referenced[0] if referenced else None,
                    "rationale": challenge.get("rationale"),
                    "added_by": rules.ADDED_BY_AI,
                    "judged_since": bool(
                        hypothesis is not None
                        and hypothesis.human_status
                        and _after(hypothesis.status_changed_at, produced_at)
                    ),
                    "hypothesis_judged": bool(hypothesis is not None and hypothesis.human_status),
                    "created_at": challenge.get("created_at") or produced,
                    # The challenge as the AI produced it.
                    "statement": challenge.get("statement"),
                    "challenge_type": challenge.get("challenge_type"),
                    "challenge_type_label": rules.ai_status_label(challenge.get("challenge_type")),
                    "severity": challenge.get("severity"),
                    "materiality": challenge.get("materiality"),
                    "all_evidence": referenced,
                    "ai_execution_id": str(latest["ai_execution_id"]) if latest["ai_execution_id"] else None,
                }
            )
    counts = {
        "total": len(items),
        "hypothesis_links": sum(1 for item in items if item["kind"] == "HYPOTHESIS_LINK"),
        "case_evidence": sum(1 for item in items if item["kind"] == "CASE_EVIDENCE"),
        "challenger": sum(1 for item in items if item["kind"] == "CHALLENGER"),
    }
    return {"items": items, "counts": counts}


# ------------------------------------------------------------------------------------------------------ unknowns


def _unknown_items(db: Session, control_db: Session | None, tenant_id, rows: list[Unknown]) -> list[dict]:
    from backend.app.db.models.stage3 import SupplierEvidenceRequest
    from backend.app.evidence_workflow.rules import status_label as request_status_label

    ids = [row.id for row in rows]
    hypothesis_ids = {row.hypothesis_id for row in rows if row.hypothesis_id}
    hypotheses = (
        {
            row.id: row
            for row in db.query(Hypothesis).filter(
                Hypothesis.tenant_id == tenant_id, Hypothesis.id.in_(list(hypothesis_ids))
            )
        }
        if hypothesis_ids
        else {}
    )
    requests: dict[uuid.UUID, list] = {}
    if ids:
        for request in (
            db.query(SupplierEvidenceRequest)
            .filter(SupplierEvidenceRequest.tenant_id == tenant_id, SupplierEvidenceRequest.unknown_id.in_(ids))
            .order_by(SupplierEvidenceRequest.created_at)
        ):
            requests.setdefault(request.unknown_id, []).append(
                {
                    "id": str(request.id),
                    "business_id": request.business_id,
                    "title": request.title,
                    "status": request.status,
                    "status_label": request_status_label(request.status),
                }
            )
    names = _names(control_db, tenant_id, [ref for row in rows for ref in (row.created_by, row.status_changed_by)])
    items = []
    for row in rows:
        hypothesis = hypotheses.get(row.hypothesis_id)
        origin = rules.plain_origin(row.origin)
        items.append(
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "description": row.description,
                "category": row.category,
                "evidence_needed": row.evidence_needed,
                "status": row.status,
                "status_label": rules.unknown_status_label(row.status),
                "origin": origin,
                "origin_label": rules.origin_label(origin),
                "hypothesis": (
                    {"id": str(hypothesis.id), "business_id": hypothesis.business_id, "statement": hypothesis.statement}
                    if hypothesis is not None
                    else None
                ),
                "requests": requests.get(row.id, []),
                "resolution": row.resolution,
                "status_changed_by_name": _name(names, row.status_changed_by),
                "status_changed_at": _iso(row.status_changed_at),
                "created_by_name": _name(names, row.created_by),
                "created_at": _iso(row.created_at),
                "locked": rules.unknown_locked(row.status),
            }
        )
    return items


def _one_unknown(db, control_db, tenant_id, unknown_id) -> dict:
    rows = db.query(Unknown).filter(Unknown.tenant_id == tenant_id, Unknown.id == unknown_id).all()
    return _unknown_items(db, control_db, tenant_id, rows)[0]


@router.get("/unknowns")
def list_unknowns(
    investigation_id: uuid.UUID,
    include_superseded: bool = Query(False),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The case's unknowns (the AI's and people's) with their status, hypothesis, evidence requests and resolution."""
    tenant_id = _tenant(ctx)
    case = _case(db, tenant_id, investigation_id)
    person = current_person(control_db, ctx)
    every = (
        db.query(Unknown)
        .filter(Unknown.tenant_id == tenant_id, Unknown.investigation_id == case.id)
        .order_by(Unknown.created_at.desc(), Unknown.business_id)
        .all()
    )
    rows = [row for row in every if include_superseded or not rules.unknown_locked(row.status)]
    items = _unknown_items(db, control_db, tenant_id, rows)
    statuses = [str(row.status or "").lower() for row in every]
    counts = {"shown": len(items)}
    for status in (*rules.UNKNOWN_STATUSES, rules.SUPERSEDED):
        counts[status] = sum(1 for item in statuses if item == status)
    counts["human"] = sum(1 for row in every if rules.plain_origin(row.origin) == "HUMAN")
    open_case = _is_open(case) and person.holds(INVESTIGATION_WORK)
    return {"items": items, "counts": counts, "actions": {"can_add": open_case, "can_set_status": open_case}}


@router.post("/unknowns", status_code=201, dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def create_unknown(
    investigation_id: uuid.UUID,
    payload: rules.UnknownCreatePayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """An unknown a person records (origin "human"), open, optionally about one hypothesis of the case."""
    tenant_id = _tenant(ctx)
    person = current_person(control_db, ctx)
    case = _case(db, tenant_id, investigation_id, lock=True)
    _refuse_closed(case)
    hypothesis = None
    if payload.hypothesis_id is not None:
        hypothesis = (
            db.query(Hypothesis)
            .filter(
                Hypothesis.tenant_id == tenant_id,
                Hypothesis.investigation_id == case.id,
                Hypothesis.id == payload.hypothesis_id,
            )
            .first()
        )
        if hypothesis is None:
            raise _error(404, "HYPOTHESIS_NOT_FOUND", "Hypothesis is not available in this investigation")
    now = now_utc()
    row = Unknown(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        investigation_id=case.id,
        hypothesis_id=hypothesis.id if hypothesis is not None else None,
        category=payload.category,
        description=payload.description,
        evidence_needed=payload.evidence_needed,
        status=rules.UNKNOWN_OPEN,
        origin=rules.ORIGIN_HUMAN,
        created_by=person.user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    _record(
        db,
        ctx=ctx,
        person=person,
        permission=INVESTIGATION_WORK,
        case=case,
        object_type=rules.OBJECT_UNKNOWN,
        object_id=row.id,
        entity_type="Unknown",
        event_type=rules.EVENT_CREATED,
        to_value=rules.UNKNOWN_OPEN,
        details={
            "business_id": row.business_id,
            "description": payload.description,
            "hypothesis_business_id": hypothesis.business_id if hypothesis is not None else None,
        },
        new_values={
            "description": payload.description,
            "category": payload.category,
            "evidence_needed": payload.evidence_needed,
        },
        now=now,
    )
    db.commit()
    return _one_unknown(db, control_db, tenant_id, row.id)


@router.post("/unknowns/{unknown_id}/status", dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def set_unknown_status(
    investigation_id: uuid.UUID,
    unknown_id: uuid.UUID,
    payload: rules.UnknownStatusPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Move an unknown (open, in progress, resolved, accepted as a limitation, or set aside as no longer relevant)
    with the reason; resolving, accepting or setting it aside keeps the reason as its resolution. Only an open or
    in-progress unknown is set aside, and a superseded unknown never changes again."""
    tenant_id = _tenant(ctx)
    person = current_person(control_db, ctx)
    case = _case(db, tenant_id, investigation_id, lock=True)
    _refuse_closed(case)
    row = (
        db.query(Unknown)
        .filter(Unknown.tenant_id == tenant_id, Unknown.investigation_id == case.id, Unknown.id == unknown_id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise _error(404, "UNKNOWN_NOT_FOUND", "This unknown is not available in this investigation")
    if rules.unknown_locked(row.status):
        raise _error(409, "UNKNOWN_SUPERSEDED", "This unknown was replaced by a newer AI run and cannot change")
    if str(row.status or "").lower() == payload.status:
        raise _error(409, "UNKNOWN_STATUS_UNCHANGED", "The unknown already has this status")
    if not rules.unknown_transition_allowed(row.status, payload.status):
        raise _error(
            409,
            "UNKNOWN_TRANSITION_NOT_ALLOWED",
            "Only an open or in-progress unknown can be set aside as no longer relevant",
        )
    now = now_utc()
    before = {"status": row.status, "resolution": row.resolution}
    row.status = payload.status
    row.resolution = payload.reason if payload.status in rules.RESOLUTION_STATUSES else None
    row.status_changed_by = person.user_id
    row.status_changed_at = now
    row.updated_at = now
    _record(
        db,
        ctx=ctx,
        person=person,
        permission=INVESTIGATION_WORK,
        case=case,
        object_type=rules.OBJECT_UNKNOWN,
        object_id=row.id,
        entity_type="Unknown",
        event_type=rules.EVENT_STATUS_CHANGED,
        from_value=before["status"],
        to_value=payload.status,
        reason=payload.reason,
        details={"business_id": row.business_id, "previous_resolution": before["resolution"]},
        old_values=before,
        new_values={"status": row.status, "resolution": row.resolution},
        now=now,
    )
    db.commit()
    return _one_unknown(db, control_db, tenant_id, row.id)


# ------------------------------------------------------------------------------------------------ failure chains


def _chain_views(db: Session, control_db: Session | None, tenant_id, case: Investigation, chains) -> list[dict]:
    ids = [chain.id for chain in chains]
    if not ids:
        return []
    nodes = (
        db.query(FailureChainNode)
        .filter(FailureChainNode.tenant_id == tenant_id, FailureChainNode.failure_chain_id.in_(ids))
        .order_by(FailureChainNode.failure_chain_id, FailureChainNode.sequence_number)
        .all()
    )
    edges = (
        db.query(FailureChainEdge)
        .filter(FailureChainEdge.tenant_id == tenant_id, FailureChainEdge.failure_chain_id.in_(ids))
        .order_by(FailureChainEdge.created_at, FailureChainEdge.id)
        .all()
    )
    labels = {node.id: node.label for node in nodes}
    sequences = {node.id: node.sequence_number for node in nodes}
    evidence_ids = {edge.evidence_id for edge in edges if edge.evidence_id}
    evidence = (
        {
            ev.id: ev
            for ev in db.query(Evidence).filter(Evidence.tenant_id == tenant_id, Evidence.id.in_(list(evidence_ids)))
        }
        if evidence_ids
        else {}
    )
    reasons: dict[uuid.UUID, str | None] = {}
    edge_ids = [edge.id for edge in edges]
    if edge_ids:
        for event in (
            db.query(IntelligenceEvent)
            .filter(
                IntelligenceEvent.tenant_id == tenant_id,
                IntelligenceEvent.investigation_id == case.id,
                IntelligenceEvent.object_type == rules.OBJECT_FAILURE_CHAIN_LINK,
                IntelligenceEvent.object_id.in_(edge_ids),
                IntelligenceEvent.event_type == rules.EVENT_STATE_CHANGED,
            )
            .order_by(IntelligenceEvent.created_at)
        ):
            reasons[event.object_id] = event.reason
    names = _names(control_db, tenant_id, [chain.created_by for chain in chains] + [edge.updated_by for edge in edges])
    open_case = _is_open(case)
    views = []
    for chain in chains:
        chain_edges = sorted(
            [edge for edge in edges if edge.failure_chain_id == chain.id],
            key=lambda edge: (sequences.get(edge.from_node_id, 0), sequences.get(edge.to_node_id, 0)),
        )
        origin = rules.chain_origin(chain.origin)
        views.append(
            {
                "id": str(chain.id),
                "business_id": chain.business_id,
                "name": chain.name,
                "origin": origin,
                "origin_label": rules.chain_origin_label(origin),
                "status": chain.status,
                "method": chain.method,
                "created_by_name": _name(names, chain.created_by),
                "created_at": _iso(chain.created_at),
                "updated_at": _iso(chain.updated_at),
                "source_ai_execution_id": str(chain.source_ai_execution_id) if chain.source_ai_execution_id else None,
                "nodes": [
                    {
                        "id": str(node.id),
                        "sequence": node.sequence_number,
                        "label": node.label,
                        # RCA 5 Whys: the hypothesis a why is (never a root cause).
                        "hypothesis_id": (
                            str(node.lifecycle_object_id) if node.lifecycle_object_type == "HYPOTHESIS" else None
                        ),
                    }
                    for node in nodes
                    if node.failure_chain_id == chain.id
                ],
                "links": [
                    {
                        "id": str(edge.id),
                        "from_node_id": str(edge.from_node_id),
                        "to_node_id": str(edge.to_node_id),
                        "from_label": labels.get(edge.from_node_id),
                        "to_label": labels.get(edge.to_node_id),
                        "state": rules.link_state(edge.edge_status),
                        "state_label": rules.link_state_label(edge.edge_status),
                        "evidence": _evidence_ref(evidence.get(edge.evidence_id)) if edge.evidence_id else None,
                        "rationale": edge.rationale,
                        "state_reason": reasons.get(edge.id),
                        "updated_by_name": _name(names, edge.updated_by),
                        "updated_at": _iso(edge.updated_at),
                    }
                    for edge in chain_edges
                ],
                "actions": {"can_change_links": open_case},
            }
        )
    return views


def _latest_ai_chains(db: Session, tenant_id, case_id) -> dict | None:
    """The latest failure chains the AI produced for the case, as it produced them (read-only)."""
    from failure_chain.engine import ORCHESTRATION_VERSION, PROVIDER
    from failure_chain.schemas import FailureChainSet
    from failure_chain.service import UnknownsFailureChainService

    found = UnknownsFailureChainService().latest(
        db, tenant_id, case_id, PROVIDER, ORCHESTRATION_VERSION, FailureChainSet
    )
    if found is None:
        return None
    chain_set, execution_id = found
    return {"ai_execution_id": execution_id, "set": chain_set.model_dump(mode="json")}


def _adopted(db: Session, tenant_id, case_id) -> dict[tuple[str, str], str]:
    """``{(ai execution id, ai chain id): stored chain id}`` of the AI chains adopted into the case."""
    found = {}
    for object_id, details in db.query(IntelligenceEvent.object_id, IntelligenceEvent.details).filter(
        IntelligenceEvent.tenant_id == tenant_id,
        IntelligenceEvent.investigation_id == case_id,
        IntelligenceEvent.object_type == rules.OBJECT_FAILURE_CHAIN,
        IntelligenceEvent.event_type == rules.EVENT_ADOPTED,
    ):
        details = details or {}
        found[(str(details.get("ai_execution_id")), str(details.get("ai_chain_id")))] = str(object_id)
    return found


@router.get("/failure-chains")
def list_failure_chains(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The case's stored failure chains (built by people, adopted from an AI run, or seeded), and the latest AI chains
    as the AI produced them, each link with the AI's epistemic status and the state it would keep if adopted."""
    tenant_id = _tenant(ctx)
    case = _case(db, tenant_id, investigation_id)
    person = current_person(control_db, ctx)
    chains = (
        db.query(FailureChain)
        .filter(FailureChain.tenant_id == tenant_id, FailureChain.investigation_id == case.id)
        .order_by(FailureChain.created_at.desc(), FailureChain.business_id)
        .all()
    )
    stored = _chain_views(db, control_db, tenant_id, case, chains)
    can_work = _is_open(case) and person.holds(INVESTIGATION_WORK)
    for view in stored:
        view["actions"]["can_change_links"] = view["actions"]["can_change_links"] and can_work
    latest = _optional(db, "latest failure chains", lambda: _latest_ai_chains(db, tenant_id, case.id))
    ai_latest = None
    if latest is not None:
        adopted = _adopted(db, tenant_id, case.id)
        business = {chain.id: chain.business_id for chain in chains}
        execution = str(latest["ai_execution_id"])
        ai_chains = []
        for chain in latest["set"].get("chains") or []:
            stored_id = adopted.get((execution, str(chain.get("chain_id"))))
            ai_chains.append(
                {
                    **chain,
                    "origin": "AI",
                    "origin_label": rules.AI_INTERPRETATION,
                    "links": [
                        {
                            **link,
                            "state": rules.ai_link_state(link.get("epistemic_status")),
                            "state_label": rules.link_state_label(rules.ai_link_state(link.get("epistemic_status"))),
                        }
                        for link in chain.get("links") or []
                        if isinstance(link, dict)
                    ],
                    "adopted_chain": (
                        {"id": stored_id, "business_id": business.get(as_uuid(stored_id))} if stored_id else None
                    ),
                }
            )
        ai_latest = {
            "ai_execution_id": execution,
            "created_at": latest["set"].get("created_at"),
            "origin": "AI",
            "origin_label": rules.AI_INTERPRETATION,
            "chains": ai_chains,
        }
    return {"stored": stored, "ai_latest": ai_latest, "actions": {"can_add": can_work, "can_adopt": can_work}}


def _chain_of_case(db: Session, tenant_id, case: Investigation, chain_id) -> FailureChain:
    chain = (
        db.query(FailureChain)
        .filter(
            FailureChain.tenant_id == tenant_id, FailureChain.investigation_id == case.id, FailureChain.id == chain_id
        )
        .with_for_update()
        .first()
    )
    if chain is None:
        raise _error(404, "FAILURE_CHAIN_NOT_FOUND", "This failure chain is not available in this investigation")
    return chain


def _store_chain(
    db: Session,
    *,
    tenant_id,
    case: Investigation,
    person: Person,
    name: str,
    origin: str,
    labels: list[str],
    links: list[dict],
    source_ai_execution_id=None,
    now: datetime,
    method: str = "CHAIN",
) -> FailureChain:
    """A chain, its steps (in order) and its links. ``links`` hold from/to indexes into ``labels``."""
    chain = FailureChain(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        investigation_id=case.id,
        name=_short(name, 255),
        status=rules.CHAIN_STATUS_DRAFT,
        origin=origin,
        created_by=person.user_id,
        source_ai_execution_id=source_ai_execution_id,
        method=method,
        created_at=now,
        updated_at=now,
    )
    db.add(chain)
    db.flush()
    nodes = []
    for index, label in enumerate(labels):
        node = FailureChainNode(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            failure_chain_id=chain.id,
            sequence_number=index + 1,
            node_type=rules.NODE_TYPE,
            label=_short(label, 255),
            created_at=now,
        )
        db.add(node)
        nodes.append(node)
    db.flush()
    for link in links:
        db.add(
            FailureChainEdge(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                failure_chain_id=chain.id,
                from_node_id=nodes[link["from_index"]].id,
                to_node_id=nodes[link["to_index"]].id,
                edge_status=link["state"],
                evidence_id=link.get("evidence_id"),
                rationale=link.get("rationale"),
                created_at=now,
                updated_by=person.user_id,
                updated_at=now,
            )
        )
    db.flush()
    return chain


def _one_chain(db, control_db, tenant_id, case, person, chain_id) -> dict:
    chains = db.query(FailureChain).filter(FailureChain.tenant_id == tenant_id, FailureChain.id == chain_id).all()
    view = _chain_views(db, control_db, tenant_id, case, chains)[0]
    view["actions"]["can_change_links"] = view["actions"]["can_change_links"] and person.holds(INVESTIGATION_WORK)
    return view


@router.post("/failure-chains", status_code=201, dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def create_failure_chain(
    investigation_id: uuid.UUID,
    payload: rules.FailureChainCreatePayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """A failure chain a person builds: steps in order and links with their states (never proven causality)."""
    tenant_id = _tenant(ctx)
    person = current_person(control_db, ctx)
    case = _case(db, tenant_id, investigation_id, lock=True)
    _refuse_closed(case)
    for link in payload.links:
        if link.evidence_id is not None:
            _case_evidence(db, tenant_id, case, link.evidence_id)
    now = now_utc()
    chain = _store_chain(
        db,
        tenant_id=tenant_id,
        case=case,
        person=person,
        name=payload.name,
        origin=rules.CHAIN_ORIGIN_HUMAN,
        labels=payload.nodes,
        links=[link.model_dump() for link in payload.links],
        now=now,
    )
    _record(
        db,
        ctx=ctx,
        person=person,
        permission=INVESTIGATION_WORK,
        case=case,
        object_type=rules.OBJECT_FAILURE_CHAIN,
        object_id=chain.id,
        entity_type="FailureChain",
        event_type=rules.EVENT_CREATED,
        to_value=rules.CHAIN_STATUS_DRAFT,
        details={
            "business_id": chain.business_id,
            "name": chain.name,
            "origin": "HUMAN",
            "nodes": len(payload.nodes),
            "links": len(payload.links),
        },
        new_values={
            "name": chain.name,
            "nodes": payload.nodes,
            "links": [
                {"from_index": link.from_index, "to_index": link.to_index, "state": link.state}
                for link in payload.links
            ],
        },
        now=now,
    )
    db.commit()
    return _one_chain(db, control_db, tenant_id, case, person, chain.id)


def _ai_chain_steps(db: Session, tenant_id, ai_chain: dict) -> tuple[list[str], list[dict]]:
    """The steps and links of an AI chain as stored links: each link keeps the AI's epistemic status (mapped to a link
    state, never more than SUPPORTED) and its own wording in the rationale."""
    labels: list[str] = []

    def index_of(label: str) -> int:
        text = " ".join(str(label or "").split()) or "Unnamed step"
        if text not in labels:
            labels.append(text)
        return labels.index(text)

    links = []
    seen = set()
    ordered = sorted(
        (link for link in ai_chain.get("links") or [] if isinstance(link, dict)),
        key=lambda link: int(link.get("sequence") or 0),
    )
    for link in ordered:
        start, end = index_of(link.get("from_entity_or_state")), index_of(link.get("to_entity_or_state"))
        if start == end or (start, end) in seen:
            continue
        seen.add((start, end))
        status = str(link.get("epistemic_status") or "")
        evidence = _optional(
            db,
            "adopted link evidence",
            lambda link=link: _evidence_from_references(db, tenant_id, link.get("evidence_references") or []),
            default=[],
        )
        relationship = " ".join(str(link.get("relationship") or "").split()) or "is linked to"
        state = rules.ai_link_state(status)
        note = f"AI link “{relationship}” (AI epistemic status: {status or 'none'})"
        if rules.state_needs_evidence(state) and not evidence:
            # The AI called it supported but names no evidence of this case: adopted as hypothesized, so an AI claim
            # never enters the case looking established. A person can raise it once they name the evidence.
            state = "HYPOTHESIZED"
            note += "; adopted as hypothesized because it names no evidence of this investigation"
        links.append(
            {
                "from_index": start,
                "to_index": end,
                "state": state,
                "evidence_id": as_uuid(evidence[0]["id"]) if evidence else None,
                "rationale": _short(note, 2000),
            }
        )
    return labels, links


@router.post("/failure-chains/adopt", status_code=201, dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def adopt_failure_chain(
    investigation_id: uuid.UUID,
    payload: rules.AdoptChainPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Copy an AI failure chain into the case (origin AI_ADOPTED). Each link keeps the AI's epistemic status; the AI
    output itself is not changed."""
    from failure_chain.engine import PROVIDER

    tenant_id = _tenant(ctx)
    person = current_person(control_db, ctx)
    case = _case(db, tenant_id, investigation_id, lock=True)
    _refuse_closed(case)
    execution = (
        db.query(AIExecution)
        .filter(
            AIExecution.tenant_id == tenant_id,
            AIExecution.investigation_id == case.id,
            AIExecution.id == payload.ai_execution_id,
            AIExecution.provider == PROVIDER,
        )
        .first()
    )
    output = execution.structured_output if execution is not None else None
    ai_chain = next(
        (
            chain
            for chain in ((output or {}).get("chains") or [] if isinstance(output, dict) else [])
            if isinstance(chain, dict) and str(chain.get("chain_id")).lower() == payload.ai_chain_id
        ),
        None,
    )
    if ai_chain is None:
        raise _error(404, "AI_CHAIN_NOT_FOUND", "This AI failure chain is not available in this investigation")
    existing = _adopted(db, tenant_id, case.id).get((str(execution.id), payload.ai_chain_id))
    if existing is not None:
        raise _error(
            409, "CHAIN_ALREADY_ADOPTED", "This AI failure chain is already in the investigation", chain_id=existing
        )
    labels, links = _ai_chain_steps(db, tenant_id, ai_chain)
    if not links:
        raise _error(422, "AI_CHAIN_EMPTY", "This AI failure chain has no links to adopt")
    now = now_utc()
    name = " ".join(str(ai_chain.get("chain_statement") or "").split()) or "Adopted AI failure chain"
    chain = _store_chain(
        db,
        tenant_id=tenant_id,
        case=case,
        person=person,
        name=name,
        origin=rules.CHAIN_ORIGIN_ADOPTED,
        labels=labels,
        links=links,
        source_ai_execution_id=execution.id,
        now=now,
    )
    _record(
        db,
        ctx=ctx,
        person=person,
        permission=INVESTIGATION_WORK,
        case=case,
        object_type=rules.OBJECT_FAILURE_CHAIN,
        object_id=chain.id,
        entity_type="FailureChain",
        event_type=rules.EVENT_ADOPTED,
        to_value=rules.CHAIN_STATUS_DRAFT,
        details={
            "business_id": chain.business_id,
            "name": chain.name,
            "origin": "AI_ADOPTED",
            "ai_execution_id": str(execution.id),
            "ai_execution_business_id": execution.business_id,
            "ai_chain_id": payload.ai_chain_id,
            "ai_overall_status": ai_chain.get("overall_status"),
            "links": len(links),
        },
        new_values={"name": chain.name, "link_states": [link["state"] for link in links]},
        now=now,
    )
    db.commit()
    return _one_chain(db, control_db, tenant_id, case, person, chain.id)


@router.post(
    "/failure-chains/{chain_id}/links/{link_id}/state",
    dependencies=[Depends(require_permission(INVESTIGATION_WORK))],
)
def set_link_state(
    investigation_id: uuid.UUID,
    chain_id: uuid.UUID,
    link_id: uuid.UUID,
    payload: rules.LinkStatePayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """A new state for one link of a stored chain, with the reason (and optionally the evidence it rests on)."""
    tenant_id = _tenant(ctx)
    person = current_person(control_db, ctx)
    case = _case(db, tenant_id, investigation_id, lock=True)
    _refuse_closed(case)
    chain = _chain_of_case(db, tenant_id, case, chain_id)
    edge = (
        db.query(FailureChainEdge)
        .filter(
            FailureChainEdge.tenant_id == tenant_id,
            FailureChainEdge.failure_chain_id == chain.id,
            FailureChainEdge.id == link_id,
        )
        .with_for_update()
        .first()
    )
    if edge is None:
        raise _error(404, "FAILURE_CHAIN_LINK_NOT_FOUND", "This link is not available in the failure chain")
    ev = _case_evidence(db, tenant_id, case, payload.evidence_id) if payload.evidence_id is not None else None
    before_state = rules.link_state(edge.edge_status)
    evidence_id = ev.id if ev is not None else edge.evidence_id
    if rules.state_needs_evidence(payload.state) and evidence_id is None:
        raise _error(422, "EVIDENCE_REQUIRED", rules.EVIDENCE_REQUIRED_MESSAGE)
    if before_state == payload.state and edge.edge_status == payload.state and evidence_id == edge.evidence_id:
        raise _error(409, "LINK_STATE_UNCHANGED", "The link already has this state")
    now = now_utc()
    before = {
        "state": edge.edge_status,
        "evidence_id": str(edge.evidence_id) if edge.evidence_id else None,
    }
    edge.edge_status = payload.state
    edge.evidence_id = evidence_id
    edge.updated_by = person.user_id
    edge.updated_at = now
    chain.updated_at = now
    _record(
        db,
        ctx=ctx,
        person=person,
        permission=INVESTIGATION_WORK,
        case=case,
        object_type=rules.OBJECT_FAILURE_CHAIN_LINK,
        object_id=edge.id,
        entity_type="FailureChainEdge",
        event_type=rules.EVENT_STATE_CHANGED,
        from_value=before_state,
        to_value=payload.state,
        reason=payload.reason,
        details={
            "business_id": chain.business_id,
            "failure_chain_id": str(chain.id),
            "evidence_business_id": ev.business_id if ev is not None else None,
        },
        old_values=before,
        new_values={"state": payload.state, "evidence_id": str(evidence_id) if evidence_id else None},
        now=now,
    )
    db.commit()
    return _one_chain(db, control_db, tenant_id, case, person, chain.id)


# -------------------------------------------------------------------------------------------------- observations


def _observation_view(
    row: EvidenceObservation,
    evidence: dict,
    names: dict[str, str],
    reviewed: dict | None = None,
    recorded: set[str] | frozenset = frozenset(),
) -> dict:
    from backend.app.ai_review import UNREVIEWED_LABEL

    state = (reviewed or {}).get(str(row.id), (None, None))[0]
    not_reviewed = state == "NOT_REVIEWED"
    kind = rules.observation_kind(row.epistemic_type, row.observation_type, row.extraction_method)
    origin = rules.observation_origin(row.origin, row.extraction_method)
    return {
        "id": str(row.id),
        "statement": row.statement,
        "epistemic_type": kind,
        "epistemic_label": rules.epistemic_label(kind),
        "origin": origin,
        "origin_label": rules.origin_label(origin),
        "evidence": _evidence_ref(evidence.get(row.evidence_id))
        or {"id": str(row.evidence_id), "business_id": None, "title": None},
        "created_by_name": _name(names, row.created_by),
        "quality_status": row.quality_status,
        "limitations": row.limitations,
        "rationale": (row.effective_context or {}).get("rationale")
        if isinstance(row.effective_context, dict)
        else None,
        "created_at": _iso(row.created_at),
        # A model's proposal: NOT_REVIEWED, ACCEPTED, EDITED or REJECTED; each observation is reviewed on its own
        # (POST /api/v1/ai-outputs/{observation id}/review).
        "ai_review_state": state,
        "ai_execution_id": str(row.ai_execution_id) if row.ai_execution_id else None,
        "ai_label": UNREVIEWED_LABEL if not_reviewed else None,
        # W1: a proposal recorded with the sample (no model was called), never a live one.
        "recorded": str(row.ai_execution_id) in recorded,
    }


def _observation_query(db: Session, tenant_id, case: Investigation):
    evidence_ids = list(_case_evidence_ids(db, tenant_id, case.id))
    condition = EvidenceObservation.investigation_id == case.id
    if evidence_ids:
        condition = or_(condition, EvidenceObservation.evidence_id.in_(evidence_ids))
    return db.query(EvidenceObservation).filter(EvidenceObservation.tenant_id == tenant_id, condition)


def _observation_views(db: Session, control_db: Session | None, tenant_id, rows) -> list[dict]:
    evidence_ids = {row.evidence_id for row in rows}
    evidence = (
        {
            ev.id: ev
            for ev in db.query(Evidence).filter(Evidence.tenant_id == tenant_id, Evidence.id.in_(list(evidence_ids)))
        }
        if evidence_ids
        else {}
    )
    from backend.app.ai_review import observation_reviews

    names = _names(control_db, tenant_id, [row.created_by for row in rows])
    reviewed = observation_reviews(db, tenant_id, rows)
    recorded = _recorded(db, tenant_id, {row.ai_execution_id for row in rows})
    return [_observation_view(row, evidence, names, reviewed, recorded) for row in rows]


@router.get("/observations")
def list_observations(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Observations on the case's evidence and those recorded in the case, newest first, each with its kind (fact,
    source assertion, derived observation, AI interpretation) and who made it."""
    tenant_id = _tenant(ctx)
    case = _case(db, tenant_id, investigation_id)
    person = current_person(control_db, ctx)
    query = _observation_query(db, tenant_id, case)
    every = query.with_entities(
        EvidenceObservation.epistemic_type,
        EvidenceObservation.observation_type,
        EvidenceObservation.extraction_method,
        EvidenceObservation.origin,
    ).all()
    counts = {"total": len(every), **dict.fromkeys(rules.EPISTEMIC_LABELS, 0), "human": 0}
    for kind, observation_type, method, origin in every:
        counts[rules.observation_kind(kind, observation_type, method)] += 1
        if rules.observation_origin(origin, method) == "HUMAN":
            counts["human"] += 1
    rows = query.order_by(EvidenceObservation.created_at.desc(), EvidenceObservation.id).limit(OBSERVATIONS_LIMIT).all()
    return {
        "items": _observation_views(db, control_db, tenant_id, rows),
        "counts": counts,
        "limited": len(every) > OBSERVATIONS_LIMIT,
        "actions": {"can_add": _is_open(case) and person.holds(INVESTIGATION_WORK)},
    }


@router.post("/observations", status_code=201, dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def create_observation(
    investigation_id: uuid.UUID,
    payload: rules.ObservationCreatePayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """An observation a person records on evidence of the case: a fact, a source assertion or a derived observation
    (origin HUMAN). An AI interpretation is never recorded by a person."""
    tenant_id = _tenant(ctx)
    person = current_person(control_db, ctx)
    case = _case(db, tenant_id, investigation_id, lock=True)
    _refuse_closed(case)
    ev = _case_evidence(db, tenant_id, case, payload.evidence_id)
    now = now_utc()
    row = EvidenceObservation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        evidence_id=ev.id,
        statement=payload.statement,
        observation_type=rules.HUMAN_OBSERVATION_TYPE,
        extraction_method=rules.HUMAN_EXTRACTION_METHOD,
        quality_status=rules.HUMAN_QUALITY_STATUS,
        effective_context={"rationale": payload.rationale} if payload.rationale else None,
        epistemic_type=payload.epistemic_type,
        origin=rules.OBSERVATION_ORIGIN_HUMAN,
        created_by=person.user_id,
        investigation_id=case.id,
        created_at=now,
    )
    db.add(row)
    db.flush()
    _record(
        db,
        ctx=ctx,
        person=person,
        permission=INVESTIGATION_WORK,
        case=case,
        object_type=rules.OBJECT_OBSERVATION,
        object_id=row.id,
        entity_type="EvidenceObservation",
        event_type=rules.EVENT_CREATED,
        to_value=payload.epistemic_type,
        reason=payload.rationale,
        details={
            "evidence_id": str(ev.id),
            "evidence_business_id": ev.business_id,
            "statement": payload.statement,
            "epistemic_type": payload.epistemic_type,
        },
        new_values={"statement": payload.statement, "epistemic_type": payload.epistemic_type},
        now=now,
    )
    db.commit()
    return _observation_views(db, control_db, tenant_id, [row])[0]


# ------------------------------------------------------------------------------------------------------ history


@router.get("/history")
def intelligence_history(
    investigation_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(rules.HISTORY_PAGE_SIZE_DEFAULT, ge=1, le=rules.HISTORY_PAGE_SIZE_MAX),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Every change people made to the case's intelligence, newest first, with who, under which role and why."""
    tenant_id = _tenant(ctx)
    case = _case(db, tenant_id, investigation_id)
    query = db.query(IntelligenceEvent).filter(
        IntelligenceEvent.tenant_id == tenant_id, IntelligenceEvent.investigation_id == case.id
    )
    total = query.count()
    rows = (
        query.order_by(IntelligenceEvent.created_at.desc(), IntelligenceEvent.id)
        .limit(page_size)
        .offset((page - 1) * page_size)
        .all()
    )
    names = _names(control_db, tenant_id, [row.actor_ref for row in rows])
    items = []
    for row in rows:
        details = dict(row.details or {})
        items.append(
            {
                "id": str(row.id),
                "object_type": row.object_type,
                "object_label": rules.OBJECT_LABELS.get(row.object_type, row.object_type),
                "object_id": str(row.object_id),
                "object_business_id": details.get("business_id"),
                "event_type": row.event_type,
                "event_label": rules.event_label(row.event_type),
                "from_value": row.from_value,
                "to_value": row.to_value,
                "reason": row.reason,
                "actor_name": _name(names, row.actor_ref),
                "actor_role": row.actor_role,
                "details": details,
                "created_at": _iso(row.created_at),
            }
        )
    return {"items": items, "total": total, "page": page, "page_size": page_size}
