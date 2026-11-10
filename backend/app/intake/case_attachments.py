"""B7 step 7 (spec 4.1, G15): files on a Case (photos, logs, a letter), on need to know.

- ``POST /api/v1/intake/{id}/attachments``: one file, by a person who logs Cases. The checks are those of evidence
  uploads: permitted type (PDF, text, CSV, PNG, JPEG), 10 MB, the organization's attachment quota (B7-D16, Settings ›
  Oversight, 100 MB by default), the virus scan (an infected file is never stored) and content matching its type. The
  name is kept masked; the stored key never contains it. Audited ``CASE_ATTACHMENT_ADDED``.
- ``GET /api/v1/intake/{id}/attachments`` and ``GET .../{attachment_id}``: the people who work Cases (log, classify or
  review them). A download is audited ``CASE_ATTACHMENT_OPENED``. Another organization's Case answers 404.
"""

from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.app.access.permissions import CASE_CLASSIFY, CASE_LOG, QUALITY_REVIEW
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.intake import CaseAttachment, IntakeEvent
from backend.app.downloads import attachment
from backend.app.enterprise_audit import make_audit_event
from backend.app.intake import service
from backend.app.intake.router import require_any_permission_audited
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1/intake", tags=["Intake"])
UPLOADERS = require_any_permission_audited(CASE_LOG)
READERS = require_any_permission_audited(CASE_LOG, CASE_CLASSIFY, QUALITY_REVIEW)


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def _event(db: Session, tenant_id, event_id) -> IntakeEvent:
    event = db.query(IntakeEvent).filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.id == event_id).first()
    if event is None:
        raise _error(404, "INTAKE_NOT_FOUND", "No such case in your organization")
    return event


def _view(row: CaseAttachment) -> dict:
    return {
        "id": str(row.id),
        "file_name": row.filename_masked,
        "content_type": row.content_type,
        "size": row.size,
        "source": row.source,
        "usable": row.usable,
        "unusable_reason": row.unusable_reason,
        "created_by": row.created_by,
        "created_at": service._iso(row.created_at),
    }


def _audit(db: Session, ctx, action: str, row: CaseAttachment, event: IntakeEvent) -> None:
    db.add(
        make_audit_event(
            tenant_id=row.tenant_id,
            actor_ref=ctx.user_id,
            action=action,
            entity_type="CaseAttachment",
            entity_id=row.id,
            correlation_id=ctx.correlation_id,
            details={"case": event.reference, "size": row.size, "sha256": row.sha256, "content_type": row.content_type},
        )
    )


@router.post("/{event_id}/attachments", dependencies=[UPLOADERS])
def add_attachment(
    event_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Store one file on the Case (plain ``def``: the scan and the storage write block)."""
    from object_storage.service import ObjectStorageService, StorageError, refused_upload

    from backend.app.stage3_workflow_router import (
        ALLOWED_ATTACHMENT_TYPES,
        MAX_ATTACHMENT_BYTES,
        _content_matches_type,
        attachment_bytes_used,
        attachment_quota_bytes,
        safe_filename,
    )
    from backend.app.trial.imports import file_label

    tenant_id = uuid.UUID(str(ctx.tenant_id))
    event = _event(db, tenant_id, event_id)
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_ATTACHMENT_TYPES:
        raise _error(415, "UNSUPPORTED_ATTACHMENT_TYPE", "Add a PDF, text, CSV, PNG or JPEG file")
    content = file.file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise _error(413, "ATTACHMENT_TOO_LARGE", "A file can be up to 10 MB")
    if attachment_bytes_used(db, tenant_id) + len(content) > attachment_quota_bytes(db, tenant_id):
        raise _error(413, "TENANT_ATTACHMENT_QUOTA_EXCEEDED", "Your organization's file storage is full")
    storage = ObjectStorageService()
    if not storage.scan(content, content_type):
        raise _error(422, "MALWARE_SCAN_REJECTED", "The file failed the virus scan: it was not stored")
    if not _content_matches_type(content, content_type):
        raise _error(415, "ATTACHMENT_CONTENT_MISMATCH", "The file's content does not match its type")
    try:
        stored = storage.put(str(tenant_id), f"case-{event.id}-{uuid.uuid4().hex}", content, content_type=content_type)
    except StorageError as exc:
        raise refused_upload(exc) from exc
    row = CaseAttachment(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        intake_event_id=event.id,
        object_key=stored["object_key"],
        filename_masked=file_label(safe_filename(file.filename)) or "file",
        content_type=content_type,
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        source="UPLOAD",
        created_by=str(ctx.user_id),
        created_at=service.now_utc(),
    )
    db.add(row)
    _audit(db, ctx, "CASE_ATTACHMENT_ADDED", row, event)
    db.commit()
    return _view(row)


@router.get("/{event_id}/attachments", dependencies=[READERS])
def list_attachments(
    event_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    event = _event(db, tenant_id, event_id)
    rows = (
        db.query(CaseAttachment)
        .filter(CaseAttachment.tenant_id == tenant_id, CaseAttachment.intake_event_id == event.id)
        .order_by(CaseAttachment.created_at)
        .all()
    )
    return {"items": [_view(row) for row in rows]}


@router.get("/{event_id}/attachments/{attachment_id}", dependencies=[READERS])
def open_attachment(
    event_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from object_storage.service import ObjectStorageService

    tenant_id = uuid.UUID(str(ctx.tenant_id))
    event = _event(db, tenant_id, event_id)
    row = (
        db.query(CaseAttachment)
        .filter(
            CaseAttachment.tenant_id == tenant_id,
            CaseAttachment.intake_event_id == event.id,
            CaseAttachment.id == attachment_id,
        )
        .first()
    )
    if row is None or not row.object_key or not row.usable:
        raise _error(404, "ATTACHMENT_NOT_FOUND", "The file is not available")
    try:
        content = ObjectStorageService().get(str(tenant_id), row.object_key)
    except FileNotFoundError as exc:
        raise _error(404, "ATTACHMENT_NOT_FOUND", "The file is not available") from exc
    _audit(db, ctx, "CASE_ATTACHMENT_OPENED", row, event)
    db.commit()
    return Response(
        content=content, media_type=row.content_type, headers={"Content-Disposition": attachment(row.filename_masked)}
    )
