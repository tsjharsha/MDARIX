import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import Investigation
from backend.app.db.data_plane import get_data_plane_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.fault_injection import dependency_failure_simulated
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from challenger.schemas import ChallengeRequest, ChallengeResponse
from challenger.service import ChallengerError, ChallengerService
from investigator.business_ids import with_evidence_business_ids
from backend.app.access.permissions import AI_RUN, require_permission

router = APIRouter(prefix="/api/v1/investigations", tags=["AI Challenger"])
service = ChallengerService()


def err(e):
    return HTTPException(
        status_code=404 if e.code.endswith("NOT_FOUND") else 400, detail={"code": e.code, "message": e.message}
    )


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
    "/{investigation_id}/challenges",
    response_model=ChallengeResponse,
    dependencies=[Depends(require_permission(AI_RUN))],
)
def create_challenges(
    investigation_id: uuid.UUID,
    request: Request,
    data: ChallengeRequest,
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
        result = service.generate(
            db, data.model_copy(update={"tenant_id": tenant_id, "investigation_id": investigation_id})
        )
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=context["user_id"],
                action="DAY31_CHALLENGER_EXECUTED",
                entity_type="Investigation",
                correlation_id=correlation,
                details={"result_count": len(result.challenge_set.challenges), "temporal_mode": data.temporal_mode},
            )
        )
        db.commit()
    except ChallengerError as e:
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
                    "operation": "CHALLENGER",
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
    return with_evidence_business_ids(db, result)


@router.get("/{investigation_id}/challenges", response_model=ChallengeResponse)
def latest_challenges(
    investigation_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    result = service.latest(db, uuid.UUID(ctx.tenant_id), investigation_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail={"code": "CHALLENGE_SET_NOT_FOUND", "message": "No challenge set exists"}
        )
    return with_evidence_business_ids(db, result)
