import hashlib
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.db.models.regulatory import RegulatoryDocument, RegulatoryDocumentVersion
from backend.app.enterprise_audit import make_audit_event
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from regulatory_intelligence.service import RegulatoryDraftService

router = APIRouter(prefix="/api/v1/regulatory", tags=["Regulatory Intelligence"])


class RegulatoryDraftRequest(BaseModel):
    document_type: str = Field(pattern="^(ESTAR_510K|GSPR|CER|IFU)$")
    claims: list[dict] = Field(default_factory=list, max_length=500)
    citations: list[dict] = Field(default_factory=list, max_length=1000)
    document_identifier: str | None = Field(default=None, min_length=1, max_length=120)
    title: str | None = Field(default=None, max_length=255)
    change_reason: str = Field(default="Initial regulatory draft", min_length=1, max_length=1000)


class RegulatoryStatusRequest(BaseModel):
    status: str = Field(pattern="^(DRAFT|IN_REVIEW|APPROVED|ARCHIVED)$")
    expected_lock_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


def _hash_content(content: dict, citations: list[dict]) -> str:
    payload = json.dumps({"content": content, "citations": citations}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


@router.post("/draft")
def generate_regulatory_draft(
    payload: RegulatoryDraftRequest,
    db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Generate a bounded, citation-checked draft for the authenticated tenant.

    This endpoint organizes authorized client-supplied context. It does not infer
    regulatory compliance, make a submission decision, or replace human approval.
    """
    draft = RegulatoryDraftService().generate(payload.document_type, payload.model_dump())
    now = datetime.now(timezone.utc)
    identifier = payload.document_identifier or f"REG-{uuid.uuid4().hex[:12].upper()}"
    document = db.query(RegulatoryDocument).filter(
        RegulatoryDocument.tenant_id == ctx.tenant_id,
        RegulatoryDocument.document_identifier == identifier,
    ).first()
    if document is None:
        document = RegulatoryDocument(
            id=uuid.uuid4(), tenant_id=ctx.tenant_id, document_identifier=identifier,
            document_type=draft.document_type, title=payload.title or draft.title,
            status="DRAFT", current_version=0, lock_version=1,
            created_by=str(ctx.user_id), created_at=now, updated_at=now,
        )
        db.add(document)
    elif document.document_type != draft.document_type:
        raise HTTPException(409, detail={"code": "REGULATORY_DOCUMENT_TYPE_CONFLICT", "message": "Document identifier already belongs to another document type"})
    next_version = document.current_version + 1
    document.current_version = next_version
    document.status = "DRAFT"
    document.title = payload.title or document.title
    document.updated_at = now
    content = {"sections": draft.sections, "limitations": draft.limitations, "human_review_required": True}
    version = RegulatoryDocumentVersion(
        id=uuid.uuid4(), tenant_id=ctx.tenant_id, document_id=document.id, version=next_version,
        content=content, citations=draft.citations, source_context={"document_type": draft.document_type},
        content_hash=_hash_content(content, draft.citations), status="DRAFT",
        change_reason=payload.change_reason, created_by=str(ctx.user_id), created_at=now,
    )
    db.add(version)
    db.add(make_audit_event(tenant_id=ctx.tenant_id, actor_ref=str(ctx.user_id), action="REGULATORY_DOCUMENT_VERSION_CREATED", entity_type="RegulatoryDocument", entity_id=document.id, details={"document_identifier": identifier, "version": next_version}, created_at=now))
    db.commit()
    return {
        "tenant_id": str(ctx.tenant_id),
        "document_id": str(document.id),
        "document_identifier": identifier,
        "version": next_version,
        "draft": {
            "document_type": draft.document_type,
            "title": draft.title,
            "sections": draft.sections,
            "citations": draft.citations,
            "limitations": draft.limitations,
            "human_review_required": draft.human_review_required,
        },
    }


@router.get("/documents")
def list_regulatory_documents(db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    rows = db.query(RegulatoryDocument).filter(RegulatoryDocument.tenant_id == ctx.tenant_id).order_by(RegulatoryDocument.updated_at.desc()).all()
    return [{"id": str(row.id), "document_identifier": row.document_identifier, "document_type": row.document_type, "title": row.title, "status": row.status, "current_version": row.current_version, "lock_version": row.lock_version} for row in rows]


@router.get("/documents/{document_id}")
def get_regulatory_document(document_id: uuid.UUID, db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    document = db.query(RegulatoryDocument).filter(RegulatoryDocument.id == document_id, RegulatoryDocument.tenant_id == ctx.tenant_id).first()
    if document is None:
        raise HTTPException(404, detail={"code": "REGULATORY_DOCUMENT_NOT_FOUND", "message": "Regulatory document is not available"})
    versions = db.query(RegulatoryDocumentVersion).filter(RegulatoryDocumentVersion.document_id == document.id, RegulatoryDocumentVersion.tenant_id == ctx.tenant_id).order_by(RegulatoryDocumentVersion.version.desc()).all()
    return {"id": str(document.id), "document_identifier": document.document_identifier, "document_type": document.document_type, "title": document.title, "status": document.status, "current_version": document.current_version, "lock_version": document.lock_version, "versions": [{"id": str(v.id), "version": v.version, "content": v.content, "citations": v.citations, "content_hash": v.content_hash, "status": v.status, "change_reason": v.change_reason, "created_by": v.created_by} for v in versions]}


@router.post("/documents/{document_id}/status")
def update_regulatory_status(document_id: uuid.UUID, payload: RegulatoryStatusRequest, db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    document = db.query(RegulatoryDocument).filter(RegulatoryDocument.id == document_id, RegulatoryDocument.tenant_id == ctx.tenant_id, RegulatoryDocument.lock_version == payload.expected_lock_version).first()
    if document is None:
        raise HTTPException(409, detail={"code": "REGULATORY_DOCUMENT_VERSION_CONFLICT", "message": "Document changed; reload before updating"})
    allowed = {"DRAFT": {"IN_REVIEW", "ARCHIVED"}, "IN_REVIEW": {"DRAFT", "APPROVED", "ARCHIVED"}, "APPROVED": {"ARCHIVED"}, "ARCHIVED": set()}
    if payload.status not in allowed.get(document.status, set()):
        raise HTTPException(409, detail={"code": "REGULATORY_DOCUMENT_TRANSITION_INVALID", "message": f"Cannot transition from {document.status} to {payload.status}"})
    now = datetime.now(timezone.utc); previous = document.status
    document.status = payload.status; document.lock_version += 1; document.updated_at = now
    db.add(make_audit_event(tenant_id=ctx.tenant_id, actor_ref=str(ctx.user_id), action="REGULATORY_DOCUMENT_STATUS_CHANGED", entity_type="RegulatoryDocument", entity_id=document.id, details={"from": previous, "to": payload.status, "reason": payload.reason, "lock_version": document.lock_version}, created_at=now))
    db.commit()
    return {"id": str(document.id), "status": document.status, "lock_version": document.lock_version}
