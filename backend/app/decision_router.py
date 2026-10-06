import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.session import get_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from decision_center.schemas import (
    AdvisoryRequest,
    DecisionContextRequest,
    DecisionCreateRequest,
    ReviewCreateRequest,
)
from decision_center.service import OPTIONS, DecisionCenterError, DecisionCenterService
from backend.app.access.permissions import AI_RUN, RECORDS_WRITE, require_permission

router = APIRouter(prefix="/api/v1/investigations", tags=["Decision Center"])
service = DecisionCenterService()


def error(exc: DecisionCenterError) -> HTTPException:
    status = 404 if exc.code.endswith("NOT_FOUND") else 409 if exc.code == "DECISION_LOCKED" else 400
    return HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})


@router.get("/decisions/{decision_id}")
def get_decision(
    decision_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from backend.app.db.models.foundation import Decision

    item = db.query(Decision).filter(Decision.tenant_id == ctx.tenant_id, Decision.id == decision_id).first()
    if not item:
        raise HTTPException(
            404, detail={"code": "DECISION_NOT_FOUND", "message": "Decision is not available for this tenant"}
        )
    return _decision_payload(item)


@router.post("/decisions/{decision_id}/reviews", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def review_decision(
    decision_id: uuid.UUID,
    request: ReviewCreateRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from backend.app.db.models.foundation import Decision
    from backend.app.governance_router import approval_denial, session_actor, tenant

    # The reviewer is the signed-in user; a name in the request body is never trusted.
    request = request.model_copy(update={"reviewer_ref": ctx.user_id})
    if request.disposition.strip().upper() == "APPROVED":
        # Approving through a review decides the case, so it needs the same authority and separation of
        # duties as a signature.
        decision = db.query(Decision).filter(Decision.tenant_id == ctx.tenant_id, Decision.id == decision_id).first()
        if decision is None:
            raise HTTPException(
                404, detail={"code": "DECISION_NOT_FOUND", "message": "Decision is not available for this tenant"}
            )
        actor = session_actor(control_db, ctx)
        organization = tenant(control_db, actor)  # same tenant check and policy setup as signing
        denial = approval_denial(control_db, organization.id, actor["active_role"], decision, ctx.user_id)
        if denial:
            raise HTTPException(403, detail={"code": denial[0], "message": denial[1]})
    try:
        review = service.review(db, ctx.tenant_id, decision_id, request)
        return {
            "id": review.id,
            "decision_id": review.decision_id,
            "disposition": review.disposition,
            "reviewer_ref": review.reviewer_ref,
            "comments": review.comments,
            "review_timestamp": review.review_timestamp,
        }
    except DecisionCenterError as exc:
        raise error(exc) from exc


@router.get("/{investigation_id}/decision-context")
def decision_context(
    investigation_id: uuid.UUID,
    request: DecisionContextRequest = Depends(),
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    try:
        return service.context(db, ctx.tenant_id, investigation_id, request)
    except DecisionCenterError as exc:
        raise error(exc) from exc


@router.post("/{investigation_id}/decision-advisory", dependencies=[Depends(require_permission(AI_RUN))])
def decision_advisory(
    investigation_id: uuid.UUID,
    request: AdvisoryRequest,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    try:
        return service.advisory(db, ctx.tenant_id, investigation_id, request)
    except DecisionCenterError as exc:
        raise error(exc) from exc


@router.post("/{investigation_id}/decisions", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def create_decision(
    investigation_id: uuid.UUID,
    request: DecisionCreateRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    if request.selected_action not in OPTIONS:
        raise HTTPException(
            400, detail={"code": "INVALID_DECISION_OPTION", "message": "Decision option is not controlled"}
        )
    # The author is the signed-in user; a name in the request body is never trusted.
    request = request.model_copy(update={"authorized_by_ref": ctx.user_id})
    try:
        decision = service.create_decision(db, ctx.tenant_id, investigation_id, request)
    except DecisionCenterError as exc:
        raise error(exc) from exc
    # A new decision awaits an approver: tell them (every approver but its author). Queued on the control database
    # after the decision is saved; a queueing failure is logged and never undoes the decision.
    from backend.app.governance_router import _notify

    if _notify(
        "notify_review_pending",
        control_db,
        tenant_id=ctx.tenant_id,
        decision_id=decision.id,
        submitted_by_user_id=str(ctx.user_id),
        reference=decision.decision_identifier,
    ):
        control_db.commit()
    return _decision_payload(decision)


@router.get("/{investigation_id}/decisions")
def list_decisions(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from backend.app.db.models.foundation import Decision

    tenant_id = ctx.tenant_id
    try:
        service._investigation(db, tenant_id, investigation_id)
    except DecisionCenterError as exc:
        raise error(exc) from exc
    return [
        _decision_payload(item)
        for item in db.query(Decision)
        .filter(Decision.tenant_id == tenant_id, Decision.investigation_id == investigation_id)
        .order_by(Decision.decision_timestamp.desc())
        .all()
    ]


def _decision_payload(item):
    return {
        "id": item.id,
        "decision_identifier": item.decision_identifier,
        "decision_type": item.decision_type,
        "decision_status": item.decision_status,
        "decision_readiness": item.decision_readiness,
        "selected_action": item.selected_action or item.disposition,
        "human_decision": item.human_decision,
        "rationale": item.rationale,
        "authorized_by_ref": item.authorized_by_ref,
        "decision_timestamp": item.decision_timestamp,
        "updated_at": item.updated_at,
        "temporal_context": item.temporal_context,
        "limitations": item.limitations,
        "advisory_execution_id": item.advisory_execution_id,
    }
