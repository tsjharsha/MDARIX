"""Demo requests from the website: a visitor leaves a name, work email and phone number and MDARIX staff call back.

The submit endpoint is public, like free-trial sign-up. It stores only what the visitor typed (plus a one-way hash of
the sending address, used for rate limiting), creates nothing else, and is limited per email, per sending address and
per day overall. Platform Administrators list the requests and mark them contacted or closed.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.access.authz import _require_platform_admin
from backend.app.db.models.foundation import AuditEvent
from backend.app.db.models.stage2 import DemoRequest
from backend.app.db.session import get_db

router = APIRouter(prefix="/api/v1", tags=["Demo requests"])

STATUSES = ("NEW", "CONTACTED", "CLOSED")
_EMAIL = re.compile(r"^[^@\s<>()\[\],;:\"]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
_PHONE = re.compile(r"^\+?[0-9 ()\-.]{7,30}$")
# Letters (any script), spaces and the punctuation people's names use; no digits, links or markup.
_NAME = re.compile(r"^[^\W\d_](?:[^\W\d_]|[ .'\-])*$")


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


class DemoRequestIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    phone: str = Field(min_length=7, max_length=30)
    # Hidden on the form; people never fill it, so a value means an automated submission.
    website: str | None = Field(default=None, max_length=200)


class StatusChange(BaseModel):
    status: str = Field(min_length=3, max_length=40)
    note: str | None = Field(default=None, max_length=500)


def _invalid(field: str, message: str) -> HTTPException:
    return HTTPException(422, detail={"code": "DEMO_REQUEST_INVALID", "field": field, "message": message})


def _clean(payload: DemoRequestIn) -> tuple[str, str, str]:
    name = " ".join(payload.name.split())
    email = payload.email.strip().lower()
    phone = " ".join(payload.phone.split())
    if not _NAME.match(name):
        raise _invalid("name", "Enter your name using letters only")
    if not _EMAIL.match(email):
        raise _invalid("email", "Enter a valid email address")
    if not _PHONE.match(phone) or len(re.sub(r"\D", "", phone)) < 7:
        raise _invalid("phone", "Enter a valid phone number, with the country code if outside your country")
    return name, email, phone


def _source_hash(request: Request) -> str | None:
    address = request.client.host if request.client else None
    if os.getenv("MDARIX_TRUST_PROXY_HEADERS", "").lower() in {"1", "true", "yes"}:
        address = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or address
    if not address:
        return None
    salt = os.getenv("MDARIX_DEMO_REQUEST_SALT", "mdarix-demo-requests")
    return hashlib.sha256(f"{salt}:{address}".encode()).hexdigest()


def _accepted() -> dict:
    return {"status": "DEMO_REQUEST_RECEIVED"}


def _alert(display_name: str, email: str, phone: str) -> None:
    """Email the MDARIX team about the request. Runs after the response; failures are only logged."""
    recipient = (os.getenv("MDARIX_DEMO_ALERT_EMAIL") or os.getenv("MDARIX_TRIAL_ALERT_EMAIL") or "").strip()
    if not recipient:
        return
    from auth.emailer import send_demo_request_alert

    try:
        send_demo_request_alert(recipient, display_name=display_name, email=email, phone=phone)
    except Exception as exc:  # the request is already saved; an alert failure must never surface to the visitor
        logging.getLogger(__name__).warning("Demo request alert failed: %s", type(exc).__name__)


@router.post("/public/demo-requests")
def submit_demo_request(
    payload: DemoRequestIn, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
):
    if payload.website:
        return _accepted()  # automated submission: answer as usual, store nothing
    name, email, phone = _clean(payload)
    now = datetime.now(timezone.utc)
    # The same person asking again while their request is open is the same request.
    if (
        db.query(DemoRequest.id)
        .filter(
            DemoRequest.email == email, DemoRequest.status == "NEW", DemoRequest.created_at >= now - timedelta(days=7)
        )
        .first()
    ):
        return _accepted()
    source = _source_hash(request)
    per_hour = _env_int("MDARIX_DEMO_REQUESTS_PER_SOURCE_HOUR", 5)
    per_day = _env_int("MDARIX_DEMO_REQUESTS_PER_DAY", 200)
    if source:
        recent = (
            db.query(func.count(DemoRequest.id))
            .filter(DemoRequest.source_hash == source, DemoRequest.created_at >= now - timedelta(hours=1))
            .scalar()
        )
        if recent >= per_hour:
            raise HTTPException(
                429, detail={"code": "DEMO_REQUEST_LIMIT", "message": "Too many requests. Please try again later."}
            )
    if (
        db.query(func.count(DemoRequest.id)).filter(DemoRequest.created_at >= now - timedelta(days=1)).scalar()
        >= per_day
    ):
        raise HTTPException(
            429, detail={"code": "DEMO_REQUEST_LIMIT", "message": "Too many requests. Please try again later."}
        )
    db.add(
        DemoRequest(
            id=uuid.uuid4(),
            display_name=name,
            email=email,
            phone=phone,
            status="NEW",
            source_hash=source,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()
    background.add_task(_alert, name, email, phone)
    return _accepted()


def _serialize(row: DemoRequest) -> dict:
    return {
        "id": str(row.id),
        "name": row.display_name,
        "email": row.email,
        "phone": row.phone,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "handled_at": row.handled_at.isoformat() if row.handled_at else None,
        "note": row.note,
    }


@router.get("/platform-admin/demo-requests")
def list_demo_requests(request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    rows = db.query(DemoRequest).order_by(DemoRequest.created_at.desc()).limit(500).all()
    items = [_serialize(row) for row in rows]
    return {"items": items, "counts": {status: sum(1 for i in items if i["status"] == status) for status in STATUSES}}


@router.post("/platform-admin/demo-requests/{request_id}/status")
def change_demo_request_status(
    request_id: uuid.UUID, payload: StatusChange, request: Request, db: Session = Depends(get_db)
):
    admin = _require_platform_admin(request, db)
    status = payload.status.strip().upper()
    if status not in STATUSES:
        raise HTTPException(
            422, detail={"code": "DEMO_REQUEST_STATUS_INVALID", "message": "Status must be new, contacted or closed"}
        )
    row = db.query(DemoRequest).filter(DemoRequest.id == request_id).with_for_update().first()
    if row is None:
        raise HTTPException(404, detail={"code": "DEMO_REQUEST_NOT_FOUND", "message": "Demo request not found"})
    now = datetime.now(timezone.utc)
    previous = row.status
    row.status = status
    row.note = (payload.note or "").strip() or row.note
    row.handled_by = admin.id
    row.handled_at = now
    row.updated_at = now
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action="DEMO_REQUEST_STATUS_CHANGED",
            entity_type="DemoRequest",
            entity_id=row.id,
            details={"request_id": str(row.id), "from": previous, "to": status},
            created_at=now,
        )
    )
    db.commit()
    return _serialize(row)
