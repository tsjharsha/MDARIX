import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import Investigation
from backend.app.db.data_plane import get_data_plane_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.saved_results import nothing_saved
from backend.app.fault_injection import dependency_failure_simulated
from failure_chain.service import UnknownsFailureChainError, UnknownsFailureChainService
from investigator.business_ids import with_failure_chain_business_ids, with_unknown_business_ids
from failure_chain.engine import ORCHESTRATION_VERSION as F_VERSION
from failure_chain.engine import PROVIDER as F_PROVIDER
from failure_chain.schemas import (
    FailureChainRequest,
    FailureChainResponse,
    FailureChainSet,
)
from unknowns.engine import ORCHESTRATION_VERSION as U_VERSION
from unknowns.engine import PROVIDER as U_PROVIDER
from unknowns.schemas import UnknownRequest, UnknownResponse, UnknownSet
from backend.app.access.permissions import AI_RUN, require_permission

router = APIRouter(prefix="/api/v1/investigations", tags=["Unknowns and Failure Chains"])
service = UnknownsFailureChainService()


def err(e):
    return HTTPException(status_code=400, detail={"code": e.code, "message": e.message})


def _authorize_investigation(db: Session, tenant_id: uuid.UUID, investigation_id: uuid.UUID) -> None:
    if (
        db.query(Investigation.id)
        .filter(Investigation.id == investigation_id, Investigation.tenant_id == tenant_id)
        .first()
        is None
    ):
        raise HTTPException(
            status_code=404, detail={"code": "INVESTIGATION_NOT_FOUND", "message": "Investigation not found"}
        )


@router.post(
    "/{investigation_id}/unknowns", response_model=UnknownResponse, dependencies=[Depends(require_permission(AI_RUN))]
)
def create_unknowns(
    investigation_id: uuid.UUID,
    request: Request,
    data: UnknownRequest,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    # Same tenant check as failure chains: another tenant's investigation is simply not found.
    tenant_id = uuid.UUID(ctx.tenant_id)
    _authorize_investigation(db, tenant_id, investigation_id)
    try:
        result = service.unknowns(
            db, data.model_copy(update={"tenant_id": tenant_id, "investigation_id": investigation_id})
        )
    except UnknownsFailureChainError as e:
        raise err(e) from e
    return with_unknown_business_ids(db, tenant_id, result)


@router.get("/{investigation_id}/unknowns", response_model=UnknownResponse)
def latest_unknowns(
    investigation_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    item = service.latest(db, uuid.UUID(ctx.tenant_id), investigation_id, U_PROVIDER, U_VERSION, UnknownSet)
    if not item:
        # 404, or 200 with nothing saved for the case workspace (?missing=empty; backend/app/saved_results.py, UX-15).
        return nothing_saved(request, "unknown_set", "UNKNOWN_SET_NOT_FOUND", "No unknown set exists")
    result, row = item
    return with_unknown_business_ids(
        db, uuid.UUID(ctx.tenant_id), UnknownResponse(unknown_set=result, persisted=True, ai_execution_id=row)
    )


@router.post(
    "/{investigation_id}/failure-chains",
    response_model=FailureChainResponse,
    dependencies=[Depends(require_permission(AI_RUN))],
)
def create_chains(
    investigation_id: uuid.UUID,
    request: Request,
    data: FailureChainRequest,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    context = {"tenant_id": ctx.tenant_id, "user_id": ctx.user_id}
    tenant_id = uuid.UUID(ctx.tenant_id)
    correlation = ctx.correlation_id
    try:
        _authorize_investigation(db, tenant_id, investigation_id)
        if dependency_failure_simulated():
            raise RuntimeError("simulated analysis dependency failure")
        result = service.chains(
            db, data.model_copy(update={"tenant_id": tenant_id, "investigation_id": investigation_id})
        )
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=context["user_id"],
                action="DAY31_FAILURE_CHAIN_EXECUTED",
                entity_type="Investigation",
                correlation_id=correlation,
                details={"result_count": len(result.failure_chain_set.chains), "temporal_mode": data.temporal_mode},
            )
        )
        db.commit()
    except UnknownsFailureChainError as e:
        raise err(e) from e
    except HTTPException:
        raise
    except Exception as exc:
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=context["user_id"],
                action="DAY31_DEPENDENCY_FAILED",
                entity_type="Investigation",
                correlation_id=correlation,
                details={
                    "operation": "FAILURE_CHAIN",
                    "reason": "DEPENDENCY_UNAVAILABLE",
                    "temporal_mode": data.temporal_mode,
                },
            )
        )
        db.commit()
        raise HTTPException(
            status_code=503,
            detail={
                "code": "DEPENDENCY_UNAVAILABLE",
                "message": "Analysis dependency is temporarily unavailable",
                "correlation_id": correlation,
            },
        ) from exc
    return with_failure_chain_business_ids(db, tenant_id, result)


@router.get("/{investigation_id}/failure-chains", response_model=FailureChainResponse)
def latest_chains(
    investigation_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    item = service.latest(db, uuid.UUID(ctx.tenant_id), investigation_id, F_PROVIDER, F_VERSION, FailureChainSet)
    if not item:
        return nothing_saved(request, "failure_chain_set", "FAILURE_CHAIN_SET_NOT_FOUND", "No failure-chain set exists")
    result, row = item
    return with_failure_chain_business_ids(
        db,
        uuid.UUID(ctx.tenant_id),
        FailureChainResponse(failure_chain_set=result, persisted=True, ai_execution_id=row),
    )
