from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.db.data_plane import get_data_plane_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from retrieval.schemas import RetrievalRequest, RetrievalResponse
from retrieval.service import RetrievalError, TrustedRetrievalService
from backend.app.access.permissions import AI_RUN, RECORDS_WRITE, require_permission

router = APIRouter(prefix="/api/v1/retrieval", tags=["Trusted Evidence Retrieval"])
service = TrustedRetrievalService()
SEARCH_LIMIT_MESSAGE = "You have run many searches in a few minutes. Please wait a moment and try again."


@router.post("/index", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def index_evidence_chunks(
    reprocess: bool = Query(False),
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
) -> dict[str, Any]:
    tenant_id = ctx.tenant_id
    return service.index_evidence_chunks(db, tenant_id, reprocess=reprocess)


@router.post("/query", response_model=RetrievalResponse, dependencies=[Depends(require_permission(AI_RUN))])
def query_retrieval(
    request: RetrievalRequest,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
) -> RetrievalResponse:
    from backend.app.rate_limit import enforce

    enforce("search:user", ctx.user_id, SEARCH_LIMIT_MESSAGE)
    tenant_id = ctx.tenant_id
    scoped_request = request.model_copy(update={"tenant_id": tenant_id})
    try:
        return service.retrieve(db, scoped_request)
    except RetrievalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
