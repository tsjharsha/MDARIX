"""Signer training API: the starter documents a signature relies on, the signed-in person's records of them, and the
acknowledgement of a document's current version (T-G40P).

Every signed-in member of the organization reads the documents and records their own acknowledgement; nobody records
one for someone else. Each acknowledgement is in the audit trail. In a free trial it is a practice record.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.signer_training import service

router = APIRouter(prefix="/api/v1/signer-training", tags=["Signer training"])


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def is_trial(control_db: Session, tenant_id) -> bool:
    from backend.app.trial.service import trial_subscription

    return trial_subscription(control_db, tenant_id) is not None


class AcknowledgeRequest(BaseModel):
    version: str = Field(max_length=60)
    statement: str = Field(max_length=200)


@router.get("")
def training(
    documents: str | None = Query(None, max_length=400),
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The starter documents (all, or the codes asked for), each with its content and the person's record of it."""
    tenant_id = uuid.UUID(ctx.tenant_id)
    every = service.documents(db, tenant_id)
    wanted = [every[code] for code in (documents.split(",") if documents else every) if code in every]
    states = service.status(db, tenant_id, ctx.user_id, wanted)
    return {"documents": [{**item, **(service.content(item["code"], db, tenant_id) or {})} for item in states]}


@router.post("/{document_code}/acknowledge")
def acknowledge(
    document_code: str,
    payload: AcknowledgeRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Record that the person read the document's current version ("I have read version ...")."""
    tenant_id = uuid.UUID(ctx.tenant_id)
    document = service.documents(db, tenant_id).get(document_code)
    if document is None:
        raise _error(404, "DOCUMENT_NOT_FOUND", "No such document")
    if payload.version != document.version:
        raise _error(409, "VERSION_CHANGED", f"The current version is {document.version}: read it and acknowledge it")
    if " ".join(payload.statement.split()) != service.statement(document.version):
        raise _error(422, "STATEMENT_REQUIRED", f'Confirm "{service.statement(document.version)}"')
    now = datetime.now(timezone.utc)
    trial = is_trial(control_db, tenant_id)
    row, created = service.acknowledge(db, tenant_id, ctx.user_id, document, now, trial=trial)
    if created:
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=ctx.user_id,
                action="SIGNER_TRAINING_ACKNOWLEDGED",
                entity_type="SignerTrainingRecord",
                entity_id=row.id,
                correlation_id=ctx.correlation_id,
                details={"document": document.code, "version": document.version, "method": row.method},
                created_at=now,
            )
        )
        db.commit()
    return {"documents": service.status(db, tenant_id, ctx.user_id, [document])}
