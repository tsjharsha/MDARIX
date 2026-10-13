import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db.data_plane import get_data_plane_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from trust_engine.schemas import AssuranceRequest, AssuranceResponse
from trust_engine.service import TrustEngine, TrustError
from backend.app.access.permissions import AI_RUN, require_permission

router = APIRouter(prefix="/api/v1", tags=["AI Trust Assurance"])
service = TrustEngine()


def fail(e):
    return HTTPException(
        status_code=404 if e.code.endswith("NOT_FOUND") else 400, detail={"code": e.code, "message": e.message}
    )


@router.post(
    "/ai-executions/{execution_id}/assurance",
    response_model=AssuranceResponse,
    dependencies=[Depends(require_permission(AI_RUN))],
)
def assure(
    execution_id: uuid.UUID,
    request: AssuranceRequest,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    try:
        return service.evaluate(db, ctx.tenant_id, execution_id, request)
    except TrustError as e:
        raise fail(e) from e


@router.get("/ai/trust-policy", dependencies=[Depends(get_request_context)])
def trust_policy():
    """The automatic trust check every AI result gets (trust_engine/auto.py), as people read it, and the feature set
    (the static agent catalog is shown only in the full product). Any signed-in user."""
    from backend.app.feature_set import feature_set
    from trust_engine.auto import describe

    return {**describe(), "feature_set": feature_set()}


@router.get("/ai-executions/{execution_id}/assurance", response_model=AssuranceResponse)
def get_assurance(
    execution_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    try:
        return service.get(db, ctx.tenant_id, execution_id)
    except TrustError as e:
        raise fail(e) from e
