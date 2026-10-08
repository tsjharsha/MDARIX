import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.db.data_plane import get_data_plane_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from hypothesis_engine.schemas import HypothesisSetRequest, HypothesisSetResponse
from hypothesis_engine.service import CompetingHypothesisService, HypothesisEngineError
from investigation_workspace.schemas import (
    InvestigationWorkspaceRequest,
    InvestigationWorkspaceResponse,
)
from investigation_workspace.service import (
    InvestigationWorkspaceError,
    InvestigationWorkspaceService,
    with_business_ids,
)
from investigator.business_ids import with_evidence_business_ids, with_hypothesis_business_ids
from investigator.schemas import (
    InvestigationAnalysisRequest,
    InvestigationAnalysisResponse,
)
from investigator.service import EvidenceGroundedInvestigatorService, InvestigatorError
from backend.app.access.permissions import AI_RUN, require_permission
from backend.app.db.tenant_scope import scoped_bind

router = APIRouter(prefix="/api/v1/investigations", tags=["Investigation Workspace"])
service = InvestigationWorkspaceService()
investigator_service = EvidenceGroundedInvestigatorService()
hypothesis_service = CompetingHypothesisService()


def workspace_error(exc: InvestigationWorkspaceError) -> HTTPException:
    status = 404 if exc.code == "INVESTIGATION_NOT_FOUND" else 400
    return HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})


def investigator_error(exc: InvestigatorError) -> HTTPException:
    status = 404 if exc.code in {"INVESTIGATION_NOT_FOUND", "ANALYSIS_NOT_FOUND"} else 400
    return HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})


def hypothesis_error(exc: HypothesisEngineError) -> HTTPException:
    status = 404 if exc.code in {"INVESTIGATION_NOT_FOUND", "HYPOTHESIS_NOT_FOUND"} else 400
    return HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})


@router.get("/{investigation_id}/workspace", response_model=InvestigationWorkspaceResponse)
def get_investigation_workspace(
    investigation_id: uuid.UUID,
    temporal_mode: str = Query("current", pattern="^(current|event|known)$"),
    as_of: datetime | None = None,
    include_retrieval: bool = True,
    retrieval_top_k: int = Query(8, ge=1, le=25),
    data_db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
) -> InvestigationWorkspaceResponse:
    tenant_id = ctx.tenant_id
    request = InvestigationWorkspaceRequest(
        tenant_id=tenant_id,
        investigation_id=investigation_id,
        temporal_mode=temporal_mode,
        as_of=as_of,
        include_retrieval=include_retrieval,
        retrieval_top_k=retrieval_top_k,
    )
    try:
        workspace = service.workspace(data_db, request, data_plane_engine=scoped_bind(data_db))
    except InvestigationWorkspaceError as exc:
        raise workspace_error(exc) from exc
    return with_business_ids(data_db, workspace)


@router.post(
    "/{investigation_id}/analysis",
    response_model=InvestigationAnalysisResponse,
    dependencies=[Depends(require_permission(AI_RUN))],
)
def create_investigation_analysis(
    investigation_id: uuid.UUID,
    request: InvestigationAnalysisRequest,
    data_db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
) -> InvestigationAnalysisResponse:
    tenant_id = ctx.tenant_id
    scoped_request = request.model_copy(update={"tenant_id": tenant_id, "investigation_id": investigation_id})
    try:
        result = investigator_service.analyze(data_db, scoped_request)
    except InvestigatorError as exc:
        raise investigator_error(exc) from exc
    return with_evidence_business_ids(data_db, result)


@router.get("/{investigation_id}/analysis/latest", response_model=InvestigationAnalysisResponse)
def get_latest_investigation_analysis(
    investigation_id: uuid.UUID,
    data_db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
) -> InvestigationAnalysisResponse:
    tenant_id = ctx.tenant_id
    result = investigator_service.latest(data_db, tenant_id, investigation_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail={"code": "ANALYSIS_NOT_FOUND", "message": "No investigation analysis exists"}
        )
    return with_evidence_business_ids(data_db, result)


@router.get("/{investigation_id}/analysis/{analysis_id}", response_model=InvestigationAnalysisResponse)
def get_investigation_analysis(
    investigation_id: uuid.UUID,
    analysis_id: uuid.UUID,
    data_db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
) -> InvestigationAnalysisResponse:
    tenant_id = ctx.tenant_id
    try:
        result = investigator_service.get(data_db, tenant_id, investigation_id, analysis_id)
    except InvestigatorError as exc:
        raise investigator_error(exc) from exc
    return with_evidence_business_ids(data_db, result)


@router.post(
    "/{investigation_id}/hypotheses",
    response_model=HypothesisSetResponse,
    dependencies=[Depends(require_permission(AI_RUN))],
)
def create_hypotheses(
    investigation_id: uuid.UUID,
    request: HypothesisSetRequest,
    data_db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
) -> HypothesisSetResponse:
    tenant_id = ctx.tenant_id
    scoped_request = request.model_copy(update={"tenant_id": tenant_id, "investigation_id": investigation_id})
    try:
        result = hypothesis_service.generate(data_db, scoped_request)
    except HypothesisEngineError as exc:
        raise hypothesis_error(exc) from exc
    return with_hypothesis_business_ids(data_db, tenant_id, result)


@router.get("/{investigation_id}/hypotheses", response_model=HypothesisSetResponse)
def list_latest_hypotheses(
    investigation_id: uuid.UUID,
    data_db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
) -> HypothesisSetResponse:
    tenant_id = ctx.tenant_id
    result = hypothesis_service.latest(data_db, tenant_id, investigation_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail={"code": "HYPOTHESIS_SET_NOT_FOUND", "message": "No hypothesis set exists"}
        )
    return with_hypothesis_business_ids(data_db, tenant_id, result)


@router.get("/{investigation_id}/hypotheses/{hypothesis_id}", response_model=HypothesisSetResponse)
def get_hypothesis(
    investigation_id: uuid.UUID,
    hypothesis_id: uuid.UUID,
    data_db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
) -> HypothesisSetResponse:
    tenant_id = ctx.tenant_id
    try:
        result = hypothesis_service.get(data_db, tenant_id, investigation_id, hypothesis_id)
    except HypothesisEngineError as exc:
        raise hypothesis_error(exc) from exc
    return with_hypothesis_business_ids(data_db, tenant_id, result)
