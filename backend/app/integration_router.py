import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from integration.gateway import ConnectionConfig, MappingDefinition, preview
from backend.app.access.permissions import RECORDS_WRITE, require_permission

router = APIRouter(prefix="/api/v1/integrations", tags=["Integration Gateway"])


class PreviewRequest(BaseModel):
    connection_id: str
    connector_type: str = "FILE"
    source_system_type: str = "SIMULATED"
    records: list[dict]
    target_entity: str
    mapping_version: str
    rules: dict


@router.post("/preview", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def mapping_preview(request: PreviewRequest, ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    config = ConnectionConfig(
        ctx.tenant_id, request.connection_id, "preview", request.connector_type, request.source_system_type
    )
    return {
        "connection": config.safe_dict(),
        "preview": preview(
            request.records,
            MappingDefinition(
                request.source_system_type, request.target_entity, request.mapping_version, request.rules
            ),
        ),
    }


def _file_storage_problem() -> str | None:
    """None when uploaded files can be stored now (object storage answers a write or bucket check), else why not."""
    from backend.app.readiness import _object_storage

    try:
        _object_storage()
    except Exception as exc:  # any storage failure means files cannot be received
        return type(exc).__name__
    return None


@router.get("/health/{connector_type}")
def connector_health(connector_type: str, ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    """What this deployment can say about a connector type, without overstating it.

    FILE is checked for real: uploads need object storage, so it is HEALTHY only when storage answers now. REST and
    DATABASE are only CONFIGURED (a default address is set) or NOT_CONFIGURED: a customer's own system is checked
    per connector (Customer Administration > Integrations > Test), never assumed healthy here.
    """
    if connector_type not in {"FILE", "REST", "DATABASE"}:
        raise HTTPException(400, detail={"code": "UNSUPPORTED_CONNECTOR", "message": "Connector type is not supported"})
    if connector_type == "FILE":
        problem = _file_storage_problem()
        return {
            "tenant_id": ctx.tenant_id,
            "connector_type": connector_type,
            "status": "HEALTHY" if problem is None else "UNAVAILABLE",
            "configuration_valid": problem is None,
            "limitations": [] if problem is None else [f"Object storage is not available ({problem})."],
        }
    configured = bool(
        os.getenv("MDARIX_CONNECTOR_REST_BASE_URL" if connector_type == "REST" else "MDARIX_CONNECTOR_DATABASE_URL")
    )
    return {
        "tenant_id": ctx.tenant_id,
        "connector_type": connector_type,
        "status": "CONFIGURED" if configured else "NOT_CONFIGURED",
        "configuration_valid": configured,
        "limitations": ["Reachability is tested per connector, not here."]
        if configured
        else ["Provider credentials or endpoint are not configured."],
    }
