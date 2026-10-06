import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.business_ids import business_id_of
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
    return _decision_payload(item, _investigation_business_id(db, item))


@router.post("/decisions/{decision_id}/reviews", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def review_decision(
    decision_id: uuid.UUID,
    request: ReviewCreateRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from backend.app.db.models.foundation import Decision
    from backend.app.governance_router import (
        SELF_REVIEW_DENIED,
        approval_denial,
        is_decision_author,
        session_actor,
        tenant,
    )

    # The reviewer is the signed-in user; a name in the request body is never trusted.
    request = request.model_copy(update={"reviewer_ref": ctx.user_id})
    decision = db.query(Decision).filter(Decision.tenant_id == ctx.tenant_id, Decision.id == decision_id).first()
    if decision is None:
        raise HTTPException(
            404, detail={"code": "DECISION_NOT_FOUND", "message": "Decision is not available for this tenant"}
        )
    if is_decision_author(decision, ctx.user_id):
        # Segregation of duties: nobody reviews their own decision, whatever the disposition.
        raise HTTPException(403, detail={"code": SELF_REVIEW_DENIED[0], "message": SELF_REVIEW_DENIED[1]})
    if request.disposition.strip().upper() == "APPROVED":
        # Approving through a review decides the case, so it needs the same authority and separation of
        # duties as a signature.
        actor = session_actor(control_db, ctx)
        organization = tenant(control_db, actor)  # same tenant check and policy setup as signing
        denial = approval_denial(control_db, organization.id, actor["roles"], decision, ctx.user_id)
        if denial:
            raise HTTPException(403, detail={"code": denial[0], "message": denial[1]})
    try:
        review = service.review(db, ctx.tenant_id, decision_id, request)
        result = {
            "id": review.id,
            "decision_id": review.decision_id,
            "disposition": review.disposition,
            "reviewer_ref": review.reviewer_ref,
            "comments": review.comments,
            "review_timestamp": review.review_timestamp,
        }
    except DecisionCenterError as exc:
        raise error(exc) from exc
    # A review that sends the decision back returns it to its author as a task; an approving review leaves the
    # approval task open (the signature is still pending). Saved after the review; never undoes it.
    from backend.app.workflow.hooks import on_decision_reviewed

    on_decision_reviewed(db, control_db, decision, actor_user_id=ctx.user_id, disposition=request.disposition)
    return result


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

    investigation_business_id = _investigation_business_id(db, decision)
    if _notify(
        "notify_review_pending",
        control_db,
        tenant_id=ctx.tenant_id,
        decision_id=decision.id,
        submitted_by_user_id=str(ctx.user_id),
        reference=decision.business_id,
        investigation_business_id=investigation_business_id,
    ):
        control_db.commit()
    result = _decision_payload(decision, investigation_business_id)
    # The decision waits in the approvers' queue as a task. Saved after the decision; never undoes it.
    from backend.app.workflow.hooks import on_decision_created

    on_decision_created(db, control_db, decision, actor_user_id=ctx.user_id)
    return result


@router.get("/{investigation_id}/decisions")
def list_decisions(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from backend.app.db.models.foundation import Decision
    from backend.app.governance_router import decision_actions

    tenant_id = ctx.tenant_id
    try:
        investigation = service._investigation(db, tenant_id, investigation_id)
    except DecisionCenterError as exc:
        raise error(exc) from exc
    rows = (
        db.query(Decision)
        .filter(Decision.tenant_id == tenant_id, Decision.investigation_id == investigation_id)
        .order_by(Decision.decision_timestamp.desc())
        .all()
    )
    # What the signed-in user may do with each decision (review, approve, sign), by the endpoints' own rules, so the
    # Decision center offers only those; and each author's name, so nobody reads an account UUID.
    actions = decision_actions(control_db, ctx, rows)
    authors = _author_names(control_db, ctx.tenant_id, rows)
    return [
        {
            **_decision_payload(item, investigation.business_id),
            "authorized_by_name": authors.get(str(item.authorized_by_ref or "")),
            "actions": actions.get(item.id),
        }
        for item in rows
    ]


def _author_names(control_db: Session, tenant_id, decisions) -> dict[str, str]:
    """Each decision author's name (display name, else sign-in name) by their reference. An author recorded by
    name rather than by account (older decisions) keeps that name; an account reference that matches nobody has no
    name."""
    from backend.app.db.models.foundation import AuthUser

    names: dict[str, str] = {}
    accounts: dict[uuid.UUID, str] = {}
    for item in decisions:
        ref = str(item.authorized_by_ref or "")
        if not ref.strip():
            continue
        try:
            accounts[uuid.UUID(ref.strip())] = ref
        except ValueError:
            names[ref] = ref.strip()
    if accounts:
        for user in control_db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id, AuthUser.id.in_(list(accounts))):
            name = (user.display_name or "").strip() or (user.username or "").strip()
            if name:
                names[accounts[user.id]] = name
    return names


def _investigation_business_id(db: Session, decision) -> str | None:
    from backend.app.db.models.foundation import Investigation

    return business_id_of(db, Investigation, decision.investigation_id)


def _decision_payload(item, investigation_business_id: str | None = None):
    return {
        "id": item.id,
        "business_id": item.business_id,
        "investigation_business_id": investigation_business_id,
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
