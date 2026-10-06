"""Problems reported from the help menu of a signed-in screen, and how the support team hears about them.

A user describes what went wrong; the report is stored in their organization (``support_problem_reports``) with who
sent it, from which page, with which request id and browser, and audited ``SUPPORT_PROBLEM_REPORTED``. An outbox
event then has the background worker email ``MDARIX_SUPPORT_EMAIL`` (retried and finally dead-lettered like every
other notification, so a mail outage never loses a report). Platform administrators list open and closed reports
across organizations and close them with a resolution, audited ``SUPPORT_PROBLEM_CLOSED`` in the reporter's
organization, so the customer's own audit trail shows it was handled.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.access.authz import _require_platform_admin
from backend.app.db.models.foundation import AuthUser, Tenant
from backend.app.db.models.pilot_support import SupportProblemReport
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.logging_setup import accept_request_id
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

logger = logging.getLogger("mdarix.support")
router = APIRouter(prefix="/api/v1", tags=["Support"])

STATUSES = ("OPEN", "CLOSED")
EVENT_REPORTED = "SUPPORT_PROBLEM_REPORTED"
LIST_LIMIT = 500
# What one report may hold (the columns of support_problem_reports): longer input is refused with 422.
MAX_SUMMARY_CHARS = 200
MAX_DETAILS_CHARS = 5000
MAX_PATH_CHARS = 512
MAX_REQUEST_ID_CHARS = 64


class ProblemIn(BaseModel):
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_CHARS)
    details: str = Field(min_length=1, max_length=MAX_DETAILS_CHARS)
    path: str | None = Field(default=None, max_length=MAX_PATH_CHARS)
    request_id: str | None = Field(default=None, max_length=128)


class Resolution(BaseModel):
    resolution: str = Field(min_length=3, max_length=2000)


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def _text(value: str | None) -> str:
    """Postgres text cannot hold NUL characters (a pasted error can carry one): they are dropped, not refused."""
    return (value or "").replace("\x00", "")


def _one_line(value: str | None) -> str | None:
    return " ".join(_text(value).split()) or None


def _request_id(value: str | None) -> str | None:
    """A usable caller request id that fits its column (64); a longer one is dropped rather than cut."""
    accepted = accept_request_id(value)
    return accepted if accepted and len(accepted) <= MAX_REQUEST_ID_CHARS else None


def _serialize(row: SupportProblemReport, *, tenant_name: str | None = None, reporter: str | None = None) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "tenant_name": tenant_name,
        "reporter": reporter,
        "summary": row.summary,
        "details": row.details,
        "path": row.path,
        "request_id": row.request_id,
        "user_agent": row.user_agent,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "closed_by": row.closed_by,
        "resolution": row.resolution,
    }


# ------------------------------------------------------------------------------------------- signed-in users


@router.post("/support/problems", status_code=201)
def report_problem(
    payload: ProblemIn,
    request: Request,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    tenant_id, user_id = uuid.UUID(str(ctx.tenant_id)), uuid.UUID(str(ctx.user_id))
    now = datetime.now(timezone.utc)
    summary = _one_line(payload.summary)
    details = _text(payload.details).strip()
    if not summary or not details:
        raise _error(422, "PROBLEM_REPORT_INVALID", "Describe the problem in a few words and in detail")
    row = SupportProblemReport(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        reporter_ref=str(user_id),
        summary=summary[:MAX_SUMMARY_CHARS],
        details=details[:MAX_DETAILS_CHARS],
        path=(_one_line(payload.path) or "")[:MAX_PATH_CHARS] or None,
        request_id=_request_id(payload.request_id),
        user_agent=(request.headers.get("user-agent") or "")[:512] or None,
        status="OPEN",
        created_at=now,
    )
    db.add(row)
    db.flush()
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(user_id),
            action=EVENT_REPORTED,
            entity_type="SupportProblemReport",
            entity_id=row.id,
            correlation_id=ctx.correlation_id,
            details={"report_id": str(row.id), "summary": row.summary, "path": row.path},
            request=request,
            created_at=now,
        )
    )
    # The payload carries only the id: the worker reads the report itself, so no customer text sits in the queue.
    db.add(
        OutboxEvent(
            tenant_id=tenant_id,
            event_name=EVENT_REPORTED,
            aggregate_type="SupportProblemReport",
            aggregate_id=row.id,
            payload={"report_id": str(row.id)},
            occurred_at=now,
        )
    )
    db.commit()
    return {"id": str(row.id), "created_at": row.created_at.isoformat()}


@router.get("/support/problems")
def my_problems(ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)):
    """The caller's own reports in their organization, newest first (what the help menu shows as "your reports")."""
    tenant_id, user_id = uuid.UUID(str(ctx.tenant_id)), uuid.UUID(str(ctx.user_id))
    rows = (
        db.query(SupportProblemReport)
        .filter(SupportProblemReport.tenant_id == tenant_id, SupportProblemReport.user_id == user_id)
        .order_by(SupportProblemReport.created_at.desc())
        .limit(LIST_LIMIT)
        .all()
    )
    return {"items": [_serialize(row) for row in rows]}


# ------------------------------------------------------------------------------------------- worker


def deliver_problem_report(db: Session, payload: dict) -> str:
    """Email the support team about one report (called by the outbox worker in system scope).

    Returns the delivery state. A missing MDARIX_SUPPORT_EMAIL is logged and the event acknowledged (production
    refuses to start without one); a provider failure raises so the outbox retries.
    """
    from auth.emailer import send_operations_alert

    recipient = os.getenv("MDARIX_SUPPORT_EMAIL", "").strip()
    report_id = uuid.UUID(str(payload["report_id"]))
    row = db.get(SupportProblemReport, report_id)
    if row is None:  # discarded meanwhile; nothing to tell anyone
        return "SKIPPED"
    if not recipient:
        logger.warning("MDARIX_SUPPORT_EMAIL is not set; problem report %s was stored but nobody was emailed", row.id)
        return "NOT_CONFIGURED"
    tenant = db.get(Tenant, row.tenant_id)
    organization = (tenant.display_name or tenant.name) if tenant else str(row.tenant_id)
    user = db.get(AuthUser, row.user_id) if row.user_id else None
    reporter = f"{user.display_name} <{user.username}>" if user else row.reporter_ref
    lines = [
        f"Organization: {organization}",
        f"Reported by: {reporter}",
        f"Page: {row.path or 'not given'}",
        f"Request id: {row.request_id or 'not given'}",
        f"Reported at: {row.created_at.isoformat(timespec='seconds')}",
        f"Report id: {row.id}",
        "",
        row.details,
    ]
    return send_operations_alert(
        recipient, f"Problem reported by {organization}: {row.summary}"[:180], "\n".join(lines)
    )


# ------------------------------------------------------------------------------------------- platform admin


def _names(db: Session, rows: list[SupportProblemReport]) -> tuple[dict, dict]:
    tenant_ids = {row.tenant_id for row in rows}
    user_ids = {row.user_id for row in rows if row.user_id}
    tenants = dict(db.query(Tenant.id, Tenant.name).filter(Tenant.id.in_(tenant_ids))) if tenant_ids else {}
    users = dict(db.query(AuthUser.id, AuthUser.username).filter(AuthUser.id.in_(user_ids))) if user_ids else {}
    return tenants, users


@router.get("/platform-admin/support/problems")
def list_problems(
    request: Request, status: str | None = Query(default=None, max_length=20), db: Session = Depends(get_db)
):
    _require_platform_admin(request, db)
    wanted = (status or "").strip().upper() or None
    if wanted and wanted not in STATUSES:
        raise _error(422, "PROBLEM_STATUS_INVALID", "status must be OPEN or CLOSED")
    query = db.query(SupportProblemReport)
    if wanted:
        query = query.filter(SupportProblemReport.status == wanted)
    rows = query.order_by(SupportProblemReport.created_at.desc()).limit(LIST_LIMIT).all()
    tenants, users = _names(db, rows)
    counts = dict(
        db.query(SupportProblemReport.status, func.count(SupportProblemReport.id))
        .group_by(SupportProblemReport.status)
        .all()
    )
    return {
        "items": [
            _serialize(row, tenant_name=tenants.get(row.tenant_id), reporter=users.get(row.user_id)) for row in rows
        ],
        "counts": {name: int(counts.get(name, 0)) for name in STATUSES},
    }


@router.post("/platform-admin/support/problems/{report_id}/close")
def close_problem(report_id: uuid.UUID, payload: Resolution, request: Request, db: Session = Depends(get_db)):
    admin = _require_platform_admin(request, db)
    row = db.query(SupportProblemReport).filter(SupportProblemReport.id == report_id).with_for_update().first()
    if row is None:
        raise _error(404, "PROBLEM_NOT_FOUND", "Problem report not found")
    if row.status == "CLOSED":
        raise _error(409, "PROBLEM_ALREADY_CLOSED", "This report is already closed")
    now = datetime.now(timezone.utc)
    row.status = "CLOSED"
    row.closed_at = now
    row.closed_by = str(admin.id)
    row.resolution = payload.resolution.strip()
    db.add(
        make_audit_event(
            tenant_id=row.tenant_id,
            actor_ref=str(admin.id),
            action="SUPPORT_PROBLEM_CLOSED",
            entity_type="SupportProblemReport",
            entity_id=row.id,
            details={"report_id": str(row.id), "summary": row.summary},
            request=request,
            reason=row.resolution,
            created_at=now,
        )
    )
    db.commit()
    tenants, users = _names(db, [row])
    return _serialize(row, tenant_name=tenants.get(row.tenant_id), reporter=users.get(row.user_id))
