import hashlib
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.session import get_db
from backend.app.db.models.regulatory import RegulatoryDocument, RegulatoryDocumentVersion
from backend.app.enterprise_audit import make_audit_event
from backend.app.mfa import signatures_require_mfa
from backend.app.role_codes import is_administrator_role
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from regulatory_intelligence.service import RegulatoryDraftService
from regulatory_intelligence.estar import generate_estar_package
from backend.app.access.permissions import (
    AI_RUN,
    DATA_EXPORT,
    RECORDS_WRITE,
    REGULATORY_APPROVE,
    effective_role,
    permissions_for_role,
    require_permission,
)

router = APIRouter(prefix="/api/v1/regulatory", tags=["Regulatory Intelligence"])


class RegulatoryDraftRequest(BaseModel):
    document_type: str = Field(pattern="^(ESTAR_510K|GSPR|CER|IFU)$")
    claims: list[dict] = Field(default_factory=list, max_length=500)
    citations: list[dict] = Field(default_factory=list, max_length=1000)
    authoring_sections: dict[str, str] = Field(default_factory=dict, max_length=40)
    document_identifier: str | None = Field(default=None, min_length=1, max_length=120)
    title: str | None = Field(default=None, max_length=255)
    change_reason: str = Field(default="Initial regulatory draft", min_length=1, max_length=1000)
    # The organization's records the model may draft from: one case (its authorized context) and/or a version.
    investigation_id: uuid.UUID | None = None
    product_version_id: uuid.UUID | None = None


class RegulatoryStatusRequest(BaseModel):
    status: str = Field(pattern="^(DRAFT|IN_REVIEW|APPROVED|ARCHIVED)$")
    expected_lock_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)
    # Approval is a controlled, signature-grade action: the approver re-authenticates exactly as for signing a
    # decision (password, and an authenticator code when signatures require MFA).
    password: str | None = Field(default=None, max_length=128)
    mfa_code: str | None = Field(default=None, min_length=6, max_length=12)


def _hash_content(content: dict, citations: list[dict]) -> str:
    payload = json.dumps({"content": content, "citations": citations}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


@router.post("/draft", dependencies=[Depends(require_permission(AI_RUN))])
def generate_regulatory_draft(
    payload: RegulatoryDraftRequest,
    db: Session = Depends(get_db),
    data_db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Draft a regulatory document for the authenticated tenant: the citation-checked rules draft, with section text
    written by the language model from the organization's authorized records (regulatory_intelligence/copilot.py).

    The model's text is advisory (``authoritative: false``) and every section needs human review; citations and
    causal wording are checked per section. When AI is switched off, over budget, not allowed or unavailable, the
    layout-only draft is returned with ``status: RULES_ONLY`` and a ``reason_code``. Nothing here infers regulatory
    compliance, makes a submission decision, or replaces human approval.
    """
    from backend.app.db.models.foundation import Investigation, ProductVersion
    from regulatory_intelligence.copilot import draft_with_model, grounded_context

    tenant_id = uuid.UUID(str(ctx.tenant_id))
    for model, value, code in (
        (Investigation, payload.investigation_id, "INVESTIGATION_NOT_FOUND"),
        (ProductVersion, payload.product_version_id, "PRODUCT_VERSION_NOT_FOUND"),
    ):
        if value is not None and (
            data_db.query(model.id).filter(model.id == value, model.tenant_id == tenant_id).first() is None
        ):
            raise HTTPException(404, detail={"code": code, "message": "Not found in your organization"})
    request = payload.model_dump(mode="json")
    draft = RegulatoryDraftService().generate(payload.document_type, request)
    context = grounded_context(
        data_db,
        tenant_id=tenant_id,
        document_type=draft.document_type,
        request=request,
        rules_draft=draft,
        investigation_id=payload.investigation_id,
        product_version_id=payload.product_version_id,
    )
    sections, assistance = draft_with_model(
        document_type=draft.document_type, title=payload.title, rules_draft=draft, context=context
    )
    now = datetime.now(timezone.utc)
    identifier = payload.document_identifier or f"REG-{uuid.uuid4().hex[:12].upper()}"
    document = (
        data_db.query(RegulatoryDocument)
        .filter(
            RegulatoryDocument.tenant_id == ctx.tenant_id,
            RegulatoryDocument.document_identifier == identifier,
        )
        .first()
    )
    if document is None:
        document = RegulatoryDocument(
            id=uuid.uuid4(),
            tenant_id=ctx.tenant_id,
            document_identifier=identifier,
            document_type=draft.document_type,
            title=payload.title or draft.title,
            status="DRAFT",
            current_version=0,
            lock_version=1,
            created_by=str(ctx.user_id),
            created_at=now,
            updated_at=now,
        )
        data_db.add(document)
    elif document.document_type != draft.document_type:
        raise HTTPException(
            409,
            detail={
                "code": "REGULATORY_DOCUMENT_TYPE_CONFLICT",
                "message": "Document identifier already belongs to another document type",
            },
        )
    elif document.status != "DRAFT":
        # An approved or archived document is a controlled record: new content goes into a new document. A
        # document in review returns to draft first (a recorded status change) before its text can change.
        raise HTTPException(
            409,
            detail={
                "code": "REGULATORY_DOCUMENT_LOCKED",
                "message": (
                    "This document is in review; return it to draft before changing its text"
                    if document.status == "IN_REVIEW"
                    else f"This document is {document.status.lower()}; start a new document for new content"
                ),
            },
        )
    next_version = document.current_version + 1
    document.current_version = next_version
    document.status = "DRAFT"
    document.title = payload.title or document.title
    document.updated_at = now
    content = {
        "sections": sections,
        "limitations": draft.limitations,
        "human_review_required": True,
        "ai_assistance": assistance,
    }
    version = RegulatoryDocumentVersion(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        document_id=document.id,
        version=next_version,
        content=content,
        citations=draft.citations,
        source_context={
            "document_type": draft.document_type,
            "investigation_id": str(payload.investigation_id) if payload.investigation_id else None,
            "product_version_id": str(payload.product_version_id) if payload.product_version_id else None,
            "evidence_available": (assistance.get("checks") or {}).get("evidence_available", []),
        },
        content_hash=_hash_content(content, draft.citations),
        status="DRAFT",
        change_reason=payload.change_reason,
        created_by=str(ctx.user_id),
        created_at=now,
    )
    data_db.add(version)
    db.add(
        make_audit_event(
            tenant_id=ctx.tenant_id,
            actor_ref=str(ctx.user_id),
            action="REGULATORY_DOCUMENT_VERSION_CREATED",
            entity_type="RegulatoryDocument",
            entity_id=document.id,
            details={
                "document_identifier": identifier,
                "version": next_version,
                "ai_status": assistance["status"],
                "reason_code": assistance["reason_code"],
                "provider": assistance.get("provider"),
                "model": assistance.get("model"),
                "sections_drafted": assistance["sections_drafted"],
            },
            created_at=now,
        )
    )
    data_db.commit()
    db.commit()
    return {
        "status": assistance["status"],
        "reason_code": assistance["reason_code"],
        "user_message": assistance["user_message"],
        "human_review_required": True,
        "authoritative": False,
        "tenant_id": str(ctx.tenant_id),
        "document_id": str(document.id),
        "document_identifier": identifier,
        "version": next_version,
        "draft": {
            "document_type": draft.document_type,
            "title": draft.title,
            "sections": sections,
            "citations": draft.citations,
            "limitations": draft.limitations,
            "human_review_required": draft.human_review_required,
            "ai_assistance": assistance,
        },
    }


@router.get("/documents")
def list_regulatory_documents(
    db: Session = Depends(get_db),
    data_db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    rows = (
        data_db.query(RegulatoryDocument)
        .filter(RegulatoryDocument.tenant_id == ctx.tenant_id)
        .order_by(RegulatoryDocument.updated_at.desc())
        .all()
    )
    return [
        {
            "id": str(row.id),
            "document_identifier": row.document_identifier,
            "document_type": row.document_type,
            "title": row.title,
            "status": row.status,
            "current_version": row.current_version,
            "lock_version": row.lock_version,
        }
        for row in rows
    ]


@router.get("/documents/{document_id}")
def get_regulatory_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    data_db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    document = (
        data_db.query(RegulatoryDocument)
        .filter(RegulatoryDocument.id == document_id, RegulatoryDocument.tenant_id == ctx.tenant_id)
        .first()
    )
    if document is None:
        raise HTTPException(
            404, detail={"code": "REGULATORY_DOCUMENT_NOT_FOUND", "message": "Regulatory document is not available"}
        )
    versions = (
        data_db.query(RegulatoryDocumentVersion)
        .filter(
            RegulatoryDocumentVersion.document_id == document.id, RegulatoryDocumentVersion.tenant_id == ctx.tenant_id
        )
        .order_by(RegulatoryDocumentVersion.version.desc())
        .all()
    )
    return {
        "id": str(document.id),
        "document_identifier": document.document_identifier,
        "document_type": document.document_type,
        "title": document.title,
        "status": document.status,
        "current_version": document.current_version,
        "lock_version": document.lock_version,
        "versions": [
            {
                "id": str(v.id),
                "version": v.version,
                "content": v.content,
                "citations": v.citations,
                "content_hash": v.content_hash,
                "status": v.status,
                "change_reason": v.change_reason,
                "created_by": v.created_by,
            }
            for v in versions
        ],
    }


@router.post("/documents/{document_id}/status")
def update_regulatory_status(
    document_id: uuid.UUID,
    payload: RegulatoryStatusRequest,
    db: Session = Depends(get_db),
    data_db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    document = (
        data_db.query(RegulatoryDocument)
        .filter(
            RegulatoryDocument.id == document_id,
            RegulatoryDocument.tenant_id == ctx.tenant_id,
            RegulatoryDocument.lock_version == payload.expected_lock_version,
        )
        .first()
    )
    if document is None:
        raise HTTPException(
            409,
            detail={
                "code": "REGULATORY_DOCUMENT_VERSION_CONFLICT",
                "message": "Document changed; reload before updating",
            },
        )
    allowed = {
        "DRAFT": {"IN_REVIEW", "ARCHIVED"},
        "IN_REVIEW": {"DRAFT", "APPROVED", "ARCHIVED"},
        "APPROVED": {"ARCHIVED"},
        "ARCHIVED": set(),
    }
    if payload.status not in allowed.get(document.status, set()):
        raise HTTPException(
            409,
            detail={
                "code": "REGULATORY_DOCUMENT_TRANSITION_INVALID",
                "message": f"Cannot transition from {document.status} to {payload.status}",
            },
        )
    # Approval needs the regulatory-approval permission and a different person from the author (segregation of
    # duties); every other transition needs permission to change records.
    role = effective_role(db, ctx)
    granted = permissions_for_role(role)
    needed = REGULATORY_APPROVE if payload.status == "APPROVED" else RECORDS_WRITE
    if payload.status == "APPROVED" and is_administrator_role(role):
        # Administrators never approve controlled records, whatever their permissions (they can write the rules).
        from backend.app.governance_router import ADMINISTRATOR_CANNOT_SIGN

        code, message = ADMINISTRATOR_CANNOT_SIGN
        raise HTTPException(403, detail={"code": code, "message": message})
    if needed not in granted:
        raise HTTPException(
            403,
            detail={
                "code": "PERMISSION_DENIED",
                "message": "Your role does not allow this action",
                "permission": needed,
            },
        )
    if payload.status == "APPROVED":
        # Anyone who wrote the document or any version of its text is an author and cannot approve it.
        authors = {str(document.created_by or "")} | {
            str(created_by)
            for (created_by,) in data_db.query(RegulatoryDocumentVersion.created_by).filter(
                RegulatoryDocumentVersion.document_id == document.id,
                RegulatoryDocumentVersion.tenant_id == ctx.tenant_id,
            )
        }
        if str(ctx.user_id) in authors:
            raise HTTPException(
                403,
                detail={"code": "SOD_DENIED", "message": "An author of a regulatory document cannot also approve it"},
            )
        if not payload.password:
            raise HTTPException(
                403,
                detail={
                    "code": "REAUTHENTICATION_REQUIRED",
                    "message": "Enter your password (and authenticator code) to approve this document",
                },
            )
        from backend.app.governance_router import verify_signing_credentials

        def refused(action: str) -> None:
            db.add(
                make_audit_event(
                    tenant_id=ctx.tenant_id,
                    actor_ref=str(ctx.user_id),
                    action=action,
                    entity_type="RegulatoryDocument",
                    entity_id=document.id,
                    details={"attempted": "APPROVED", "document_identifier": document.document_identifier},
                )
            )

        verify_signing_credentials(
            db, ctx, password=payload.password, mfa_code=payload.mfa_code, record_refusal=refused
        )
    now = datetime.now(timezone.utc)
    previous = document.status
    document.status = payload.status
    document.lock_version += 1
    document.updated_at = now
    db.add(
        make_audit_event(
            tenant_id=ctx.tenant_id,
            actor_ref=str(ctx.user_id),
            action="REGULATORY_DOCUMENT_STATUS_CHANGED",
            entity_type="RegulatoryDocument",
            entity_id=document.id,
            details={
                "from": previous,
                "to": payload.status,
                "reason": payload.reason,
                "lock_version": document.lock_version,
            },
            created_at=now,
        )
    )
    if payload.status == "APPROVED":
        current = (
            data_db.query(RegulatoryDocumentVersion)
            .filter(
                RegulatoryDocumentVersion.document_id == document.id,
                RegulatoryDocumentVersion.tenant_id == ctx.tenant_id,
                RegulatoryDocumentVersion.version == document.current_version,
            )
            .first()
        )
        db.add(
            make_audit_event(
                tenant_id=ctx.tenant_id,
                actor_ref=str(ctx.user_id),
                action="REGULATORY_DOCUMENT_APPROVED",
                entity_type="RegulatoryDocument",
                entity_id=document.id,
                reason=payload.reason,
                details={
                    "document_identifier": document.document_identifier,
                    "version": document.current_version,
                    "content_hash": current.content_hash if current else None,
                    "reauthenticated": True,
                    "mfa_checked": signatures_require_mfa(),
                },
                created_at=now,
            )
        )
    data_db.commit()
    db.commit()
    return {"id": str(document.id), "status": document.status, "lock_version": document.lock_version}


@router.get("/documents/{document_id}/estar", dependencies=[Depends(require_permission(DATA_EXPORT))])
def download_estar_preparation(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    data_db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    document = (
        data_db.query(RegulatoryDocument)
        .filter(RegulatoryDocument.id == document_id, RegulatoryDocument.tenant_id == ctx.tenant_id)
        .first()
    )
    if document is None:
        raise HTTPException(
            404, detail={"code": "REGULATORY_DOCUMENT_NOT_FOUND", "message": "Regulatory document is not available"}
        )
    version = (
        data_db.query(RegulatoryDocumentVersion)
        .filter(
            RegulatoryDocumentVersion.document_id == document.id,
            RegulatoryDocumentVersion.tenant_id == ctx.tenant_id,
            RegulatoryDocumentVersion.version == document.current_version,
        )
        .first()
    )
    if version is None:
        raise HTTPException(
            409,
            detail={
                "code": "REGULATORY_DOCUMENT_VERSION_MISSING",
                "message": "Current document version is unavailable",
            },
        )
    if document.document_type != "ESTAR_510K":
        raise HTTPException(
            422,
            detail={
                "code": "ESTAR_DOCUMENT_TYPE_REQUIRED",
                "message": "Only ESTAR_510K documents can produce an eSTAR preparation package",
            },
        )
    sections = version.content.get("sections", [])
    try:
        package = generate_estar_package(
            tenant_id=str(ctx.tenant_id),
            title=document.title,
            sections=sections,
            citations=version.citations,
            document_version=version.version,
        )
    except ValueError as exc:
        # A section without text cannot go into the package: complete the document first.
        raise HTTPException(
            422,
            detail={"code": "ESTAR_PREPARATION_INVALID", "message": "Complete every section before preparing eSTAR"},
        ) from exc
    return Response(
        content=package["content"],
        media_type=package["content_type"],
        headers={
            "Content-Disposition": f'attachment; filename="{package["filename"]}"',
            "X-MDARIX-XML-Validation": "passed",
            "X-MDARIX-Human-Review": "required",
        },
    )
