"""Browser-side errors reported by the web application's error boundary (``POST /api/v1/client-errors``).

The endpoint is public: an error can happen on the sign-in page or after a session expired, and the report is the
only trace the operator gets. It is therefore defensive: rate limited per address, the body is capped, every value is
cut to its column, and nothing that goes wrong while storing the report reaches the browser (the answer is 202 either
way; a failure is logged with the request id). When the request carries a valid session cookie the report is filed
under that organization and user, otherwise it is anonymous (``tenant_id`` empty), which the row-level policy allows.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from auth.cookies import read_session_token
from auth.durable import hash_token
from backend.app.version import release
from backend.app.client_ip import client_ip
from backend.app.db.models.pilot_support import ClientErrorReport
from backend.app.db.models.stage2 import AuthSession
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.logging_setup import accept_request_id, current_request_id
from backend.app.rate_limit import enforce

logger = logging.getLogger("mdarix.client_errors")
router = APIRouter(prefix="/api/v1", tags=["Client errors"])

# A stack trace with source maps is a few kilobytes; anything near this is not an error report.
MAX_BODY_BYTES = 64 * 1024
MAX_STACK_CHARS = 20_000
# The column holds 64 characters; a longer id is not ours and is dropped rather than cut (a cut id matches nothing).
MAX_REQUEST_ID_CHARS = 64


class ClientErrorIn(BaseModel):
    """What the browser sends. Only the body cap bounds the values: a long message or stack is cut to its column
    when stored (path 512, message 1000, stack MAX_STACK_CHARS, component 200, user agent 512), not refused, because
    a refused report is a lost one."""

    path: str = Field(min_length=1)
    message: str = Field(min_length=1)
    stack: str | None = None
    component: str | None = None
    request_id: str | None = None


def _session_identity(request: Request) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """(tenant_id, user_id) of a live session cookie, or (None, None). Reads only; the session is not touched."""
    token = read_session_token(request)
    if not token:
        return None, None
    db = SessionLocal()
    try:
        session = (
            db.query(AuthSession)
            .filter(
                AuthSession.session_hash == hash_token(token),
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > datetime.now(timezone.utc),
            )
            .first()
        )
        if session is None:
            return None, None
        return session.tenant_id, session.user_id
    finally:
        db.close()


def _text(value: str | None) -> str:
    """Postgres text cannot hold NUL characters; a report quoting one must still be stored, so they are dropped."""
    return (value or "").replace("\x00", "")


def _request_id(value: str | None) -> str | None:
    accepted = accept_request_id(value)
    return accepted if accepted and len(accepted) <= MAX_REQUEST_ID_CHARS else None


async def _capped_body(request: Request) -> bytes | None:
    """The request body, or None once it passes MAX_BODY_BYTES: read in chunks, so a body sent without (or with a
    false) Content-Length is never held in memory beyond the cap."""
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY_BYTES:
            return None
    return bytes(body)


def _store(report: ClientErrorIn, request: Request, tenant_id, user_id) -> uuid.UUID:

    db = SessionLocal()
    try:
        if tenant_id is not None:
            bind_tenant(db, tenant_id)
        row = ClientErrorReport(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            path=_text(report.path).strip()[:512] or "-",
            message=" ".join(_text(report.message).split())[:1000] or "-",
            stack=_text(report.stack).strip()[:MAX_STACK_CHARS] or None,
            component=_text(report.component).strip()[:200] or None,
            user_agent=_text(request.headers.get("user-agent"))[:512] or None,
            request_id=_request_id(report.request_id),
            release=release(),
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _accepted() -> JSONResponse:
    return JSONResponse(status_code=202, content={"accepted": True})


@router.post("/client-errors", status_code=202)
async def report_client_error(request: Request):
    enforce("client-errors:ip", client_ip(request))
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(413, detail={"code": "REPORT_TOO_LARGE", "message": "The error report is too large"})
    body = await _capped_body(request)
    if body is None:
        raise HTTPException(413, detail={"code": "REPORT_TOO_LARGE", "message": "The error report is too large"})
    try:
        report = ClientErrorIn.model_validate_json(body)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(422, detail={"code": "REPORT_INVALID", "message": "path and message are required"}) from exc
    try:
        tenant_id, user_id = _session_identity(request)
        report_id = _store(report, request, tenant_id, user_id)
        # The message can quote customer data; the log line names the place, the id and who, never the text.
        logger.warning(
            "client error reported id=%s path=%s component=%s signed_in=%s",
            report_id,
            report.path[:200],
            (report.component or "")[:200],
            user_id is not None,
        )
    except Exception:  # the browser is already in an error state; never add a failed report on top
        logger.exception("client error report could not be stored request_id=%s", current_request_id(request))
    return _accepted()
