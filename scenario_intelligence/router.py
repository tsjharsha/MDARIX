import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from auth.service import auth_service
from backend.app.db.data_plane import get_data_plane_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.fault_injection import dependency_failure_simulated
from .schemas import ScenarioRequest, ScenarioResponse
from .service import ScenarioError, ScenarioService
from backend.app.access.permissions import AI_RUN, require_permission

router = APIRouter(prefix="/api/v1/investigations", tags=["Day 32 Scenario Intelligence"])
service = ScenarioService()


def _context(request: Request) -> dict:
    try:
        return auth_service.context(request.cookies.get("mdarix_session", ""))
    except ValueError as exc:
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Authentication required"}) from exc


@router.post(
    "/{investigation_id}/scenarios", response_model=ScenarioResponse, dependencies=[Depends(require_permission(AI_RUN))]
)
def execute_scenario(
    investigation_id: uuid.UUID, request: Request, data: ScenarioRequest, db: Session = Depends(get_data_plane_db)
):
    context = _context(request)
    tenant_id = uuid.UUID(context["tenant_id"])
    correlation = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    try:
        if dependency_failure_simulated():
            raise RuntimeError("simulated scenario dependency failure")
        result = service.execute(db, tenant_id, investigation_id, data, context["user_id"])
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=context["user_id"],
                action="DAY32_SCENARIO_EXECUTED",
                entity_type="Investigation",
                entity_id=investigation_id,
                correlation_id=correlation,
                details={
                    "scenario_type": data.scenario_type,
                    "temporal_mode": data.temporal_mode,
                    "persist": data.persist,
                    "status": result["status"],
                },
            )
        )
        db.commit()
        return result
    except ScenarioError as exc:
        status = 404 if exc.code.endswith("NOT_FOUND") else 400
        raise HTTPException(status, detail={"code": exc.code, "message": exc.message}) from exc
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=context["user_id"],
                action="DAY32_DEPENDENCY_FAILED",
                entity_type="Investigation",
                entity_id=investigation_id,
                correlation_id=correlation,
                details={
                    "reason": "DEPENDENCY_UNAVAILABLE",
                    "operation": "SCENARIO",
                    "temporal_mode": data.temporal_mode,
                },
            )
        )
        db.commit()
        raise HTTPException(
            status_code=503,
            detail={
                "code": "DEPENDENCY_UNAVAILABLE",
                "message": "Scenario dependency is temporarily unavailable",
                "correlation_id": correlation,
            },
        ) from exc
