"""The platform's side of the platform-cell link (ADR-014).

A cell calls in; the platform never calls a cell. Enrollment exchanges the one-time token from the enrollment bundle
for a certificate under the platform's authority and a credential; from then on every call carries the credential
(``Authorization: Bearer``) and, through the platform's front door, the client certificate whose fingerprint the
front door forwards (``X-Client-Certificate-Fingerprint``; required outside local development). Heartbeats are
metadata only: the schema refuses unknown fields and free text. Packages are signed envelopes the platform stores
as uploaded (reference data, mapping templates, policies); the licence is the one the platform issued the cell.

Platform administrators upload packages, withdraw them and see the fleet (``/platform-admin/console/cells``).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, conint, constr, field_validator
from sqlalchemy.orm import Session

from backend.app.access.authz import _require_platform_admin
from backend.app.access.platform_console import _iso, _tenant_names, _with_tenant
from backend.app.cell_packages import PackageError, platform_public_key, verify
from backend.app.cell_pki import fingerprint, load_platform_ca, sign_csr
from backend.app.db.models.customer_lifecycle import Cell, CellHeartbeat, CellPackageState, Package
from backend.app.db.models.foundation import AuditEvent, Tenant
from backend.app.db.session import get_db
from backend.app.db.tenant_scope import bind_system
from backend.app.runtime_env import is_production_like

router = APIRouter(prefix="/api/v1/cells", tags=["Tenant cells"])
admin_router = APIRouter(prefix="/api/v1", tags=["Tenant cells"])

ACTOR = "system:cell-link"
SAFE = r"^[A-Za-z0-9_.:+-]{1,80}$"
COUNT_KEY = r"^[a-z][a-z0-9_]{0,59}$"
Safe = constr(pattern=SAFE)
PACKAGE_KINDS = ("REFERENCE_DATA", "MAPPING_TEMPLATE", "POLICY")
PACKAGE_STATES = ("RECEIVED", "APPLIED", "FAILED", "REJECTED", "OFFERED")
FINGERPRINT_HEADER = "x-client-certificate-fingerprint"
HEARTBEAT_EVERY_MINUTES = 15


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EnrollRequest(_Strict):
    tenant_id: uuid.UUID
    tenant_key: Safe
    enrollment_token: constr(min_length=20, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")
    csr_pem: constr(max_length=8000)
    software_version: Safe
    schema_version: Safe


class JobReport(_Strict):
    name: Safe
    status: Literal["OK", "FAILED", "NEVER"]
    finished_at: datetime | None = None
    seconds: float | None = Field(default=None, ge=0)
    error_type: Safe | None = None


class PackageReport(_Strict):
    id: uuid.UUID
    state: Literal["RECEIVED", "APPLIED", "FAILED", "REJECTED", "OFFERED"]


class Heartbeat(_Strict):
    """What a cell may tell the platform: versions, a health word, how long it has run, job outcomes, counts and
    package states. No names, no messages, no record content."""

    software_version: Safe
    schema_version: Safe
    health: Literal["ok", "degraded", "down"]
    uptime_seconds: conint(ge=0)
    jobs: list[JobReport] = Field(default_factory=list, max_length=50)
    counts: dict[constr(pattern=COUNT_KEY), conint(ge=0)] = Field(default_factory=dict)
    packages: list[PackageReport] = Field(default_factory=list, max_length=100)

    @field_validator("counts")
    @classmethod
    def _few_counts(cls, value: dict) -> dict:
        if len(value) > 50:
            raise ValueError("at most 50 counts")
        return value


class PackageUpload(_Strict):
    envelope: dict


def mtls_required() -> bool:
    """Whether a cell must present its certificate (through the front door) as well as its credential: outside
    local development always, unless MDARIX_CELL_MTLS_REQUIRED says otherwise."""
    value = os.getenv("MDARIX_CELL_MTLS_REQUIRED", "").strip().lower()
    if value:
        return value in {"1", "true", "yes"}
    return is_production_like()


def _refuse(status: int, code: str, message: str):
    raise HTTPException(status, detail={"code": code, "message": message})


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _audit(db: Session, tenant_id, action: str, entity_id, details: dict, now: datetime) -> None:
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=ACTOR,
            action=action,
            entity_type="Cell",
            entity_id=entity_id,
            details=details,
            created_at=now,
        )
    )


def authenticated_cell(request: Request, db: Session) -> Cell:
    """The cell behind this request: its credential, and its certificate where the front door enforces it."""
    bind_system(db, "cell link: authenticate a cell")
    scheme, _, credential = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not credential.strip():
        _refuse(401, "CELL_CREDENTIAL_REQUIRED", "A cell credential is required")
    cell = db.query(Cell).filter(Cell.credential_hash == _digest(credential.strip())).first()
    if cell is None or cell.status != "ACTIVE":
        _refuse(401, "CELL_NOT_RECOGNIZED", "No active cell holds this credential")
    if mtls_required():
        presented = request.headers.get(FINGERPRINT_HEADER, "").strip().lower()
        if not presented or not hmac.compare_digest(presented, cell.client_certificate_fingerprint or ""):
            _refuse(401, "CELL_CERTIFICATE_REQUIRED", "The front door did not present this cell's certificate")
    return cell


def _offered(db: Session, cell: Cell) -> list[dict]:
    """Released packages this cell has not applied or rejected yet."""
    settled = {
        row.package_id
        for row in db.query(CellPackageState).filter(
            CellPackageState.tenant_id == cell.tenant_id, CellPackageState.state.in_(["APPLIED", "REJECTED"])
        )
    }
    rows = db.query(Package).filter(Package.status == "RELEASED").order_by(Package.released_at).all()
    return [
        {
            "id": str(row.id),
            "kind": row.kind,
            "code": row.code,
            "version": row.version,
            "content_sha256": row.content_sha256,
        }
        for row in rows
        if row.id not in settled
    ]


@router.post("/enroll")
def enroll(payload: EnrollRequest, request: Request, db: Session = Depends(get_db)):
    """The one-time token from the enrollment bundle, for a certificate and a credential."""
    bind_system(db, "cell link: enrollment")
    now = datetime.now(timezone.utc)
    cell = db.query(Cell).filter(Cell.tenant_id == payload.tenant_id).first()
    tenant = db.query(Tenant).filter(Tenant.id == payload.tenant_id).first()
    if cell is None or tenant is None or tenant.tenant_key != payload.tenant_key:
        _refuse(404, "CELL_NOT_FOUND", "No cell is registered for this organization")
    if cell.status != "PROVISIONING" or not cell.enrollment_token_hash:
        _refuse(409, "CELL_ALREADY_ENROLLED", "This cell enrolled already; a new enrollment needs a new bundle")
    if not hmac.compare_digest(cell.enrollment_token_hash, _digest(payload.enrollment_token)):
        _audit(db, cell.tenant_id, "CELL_ENROLLMENT_REFUSED", cell.id, {"reason": "TOKEN_MISMATCH"}, now)
        db.commit()
        _refuse(401, "CELL_ENROLLMENT_TOKEN_INVALID", "The enrollment token does not match")
    try:
        ca_key, ca_cert = load_platform_ca()
        certificate = sign_csr(payload.csr_pem, ca_key, ca_cert, common_name=f"cell:{tenant.tenant_key}")
    except PackageError as exc:
        _refuse(503 if "configured" in str(exc) else 422, "CELL_ENROLLMENT_FAILED", str(exc))
    credential = secrets.token_urlsafe(48)
    cell.credential_hash = _digest(credential)
    cell.client_certificate_fingerprint = fingerprint(certificate)
    cell.enrollment_token_hash = None  # single use
    cell.enrolled_at = now
    cell.status = "ACTIVE"
    cell.software_version = payload.software_version
    cell.schema_version = payload.schema_version
    cell.updated_at = now
    _audit(
        db,
        cell.tenant_id,
        "CELL_ENROLLED",
        cell.id,
        {"fingerprint": cell.client_certificate_fingerprint, "software_version": payload.software_version},
        now,
    )
    db.commit()
    return {
        "cell_id": str(cell.id),
        "certificate_pem": certificate,
        "ca_certificate_pem": ca_cert,
        "credential": credential,
        "licence": cell.licence_envelope,
        "heartbeat_every_minutes": HEARTBEAT_EVERY_MINUTES,
    }


@router.post("/heartbeat")
def heartbeat(payload: Heartbeat, request: Request, db: Session = Depends(get_db)):
    cell = authenticated_cell(request, db)
    now = datetime.now(timezone.utc)
    metrics = {
        "uptime_seconds": payload.uptime_seconds,
        "jobs": [job.model_dump(mode="json") for job in payload.jobs],
        "counts": payload.counts,
        "packages": [item.model_dump(mode="json") for item in payload.packages],
    }
    cell.last_heartbeat_at = now
    cell.health = payload.health
    cell.software_version = payload.software_version
    cell.schema_version = payload.schema_version
    cell.last_heartbeat = metrics
    cell.updated_at = now
    db.add(
        CellHeartbeat(
            id=uuid.uuid4(),
            tenant_id=cell.tenant_id,
            cell_id=cell.id,
            received_at=now,
            software_version=payload.software_version,
            schema_version=payload.schema_version,
            health=payload.health,
            metrics=metrics,
        )
    )
    known = {row.id for row in db.query(Package.id).filter(Package.id.in_([item.id for item in payload.packages]))}
    for item in payload.packages:
        if item.id not in known:
            continue
        state = (
            db.query(CellPackageState)
            .filter(CellPackageState.tenant_id == cell.tenant_id, CellPackageState.package_id == item.id)
            .first()
        )
        if state is None:
            state = CellPackageState(id=uuid.uuid4(), tenant_id=cell.tenant_id, package_id=item.id, state=item.state)
            db.add(state)
        state.state = item.state
        state.reported_at = now
    db.commit()
    return {
        "status": "ok",
        "platform_time": now.isoformat(),
        "licence_sha256": (cell.licence_envelope or {}).get("content_sha256"),
        "packages": _offered(db, cell),
    }


@router.get("/packages")
def packages(request: Request, db: Session = Depends(get_db)):
    cell = authenticated_cell(request, db)
    return {"licence": cell.licence_envelope, "packages": _offered(db, cell)}


@router.get("/packages/{package_id}")
def package_content(package_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    authenticated_cell(request, db)
    row = db.query(Package).filter(Package.id == package_id, Package.status == "RELEASED").first()
    if row is None:
        _refuse(404, "PACKAGE_NOT_FOUND", "No released package has this id")
    return {"id": str(row.id), "kind": row.kind, "code": row.code, "version": row.version, "package": row.envelope}


# ----------------------------------------------------------------------------------------- platform administration


def _package_summary(row: Package, states: dict | None = None) -> dict:
    return {
        "id": str(row.id),
        "kind": row.kind,
        "code": row.code,
        "version": row.version,
        "content_sha256": row.content_sha256,
        "key_id": row.key_id,
        "status": row.status,
        "released_at": _iso(row.released_at),
        "released_by": row.released_by,
        "cells": states or {},
    }


@admin_router.post("/platform-admin/packages")
def upload_package(payload: PackageUpload, request: Request, db: Session = Depends(get_db)):
    """A package signed by the release pipeline, offered to every cell as released. The platform verifies it with
    the same public key the cells pin and stores it as it came; it never re-signs."""
    admin = _require_platform_admin(request, db)
    key = platform_public_key()
    if not key:
        _refuse(503, "PLATFORM_SIGNING_KEY_MISSING", "MDARIX_PLATFORM_SIGNING_PUBLIC_KEY is not configured")
    try:
        content = verify(payload.envelope, key)
    except PackageError as exc:
        _refuse(422, "PACKAGE_REJECTED", f"The package does not verify ({exc})")
    kind = payload.envelope.get("kind")
    code, version = str(content.get("code") or ""), str(content.get("version") or "")
    if kind not in PACKAGE_KINDS:
        _refuse(422, "PACKAGE_KIND", f"Packages are {', '.join(PACKAGE_KINDS)} (licences are issued per cell)")
    import re

    if not re.fullmatch(r"[A-Za-z0-9_.:+-]{1,120}", code) or not re.fullmatch(r"[A-Za-z0-9_.:+-]{1,40}", version):
        _refuse(422, "PACKAGE_IDENTITY", "The content must name a code and a version")
    digest = str(payload.envelope["content_sha256"])
    if db.query(Package).filter(Package.content_sha256 == digest).first() is not None:
        _refuse(409, "PACKAGE_EXISTS", "This package was uploaded already")
    if db.query(Package).filter(Package.kind == kind, Package.code == code, Package.version == version).first():
        _refuse(
            409, "PACKAGE_VERSION_EXISTS", "A package with this kind, code and version exists; release a new version"
        )
    now = datetime.now(timezone.utc)
    row = Package(
        id=uuid.uuid4(),
        kind=kind,
        code=code,
        version=version,
        content_sha256=digest,
        key_id=str(payload.envelope.get("key_id") or "platform"),
        envelope=payload.envelope,
        status="RELEASED",
        released_at=now,
        released_by=str(admin.id),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action="PACKAGE_RELEASED",
            entity_type="Package",
            entity_id=row.id,
            details={"kind": kind, "code": code, "version": version, "content_sha256": digest},
            created_at=now,
        )
    )
    db.commit()
    return _package_summary(row)


@admin_router.get("/platform-admin/packages")
def list_packages(request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    rows = db.query(Package).order_by(Package.kind, Package.code, Package.released_at.desc()).all()
    states: dict[uuid.UUID, dict[str, int]] = {}
    for state in db.query(CellPackageState).all():
        states.setdefault(state.package_id, {})
        states[state.package_id][state.state] = states[state.package_id].get(state.state, 0) + 1
    return {"items": [_package_summary(row, states.get(row.id)) for row in rows]}


@admin_router.post("/platform-admin/packages/{package_id}/withdraw")
def withdraw_package(package_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    admin = _require_platform_admin(request, db)
    row = db.query(Package).filter(Package.id == package_id).first()
    if row is None:
        _refuse(404, "PACKAGE_NOT_FOUND", "No package has this id")
    now = datetime.now(timezone.utc)
    row.status = "WITHDRAWN"
    row.updated_at = now
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action="PACKAGE_WITHDRAWN",
            entity_type="Package",
            entity_id=row.id,
            details={"kind": row.kind, "code": row.code, "version": row.version},
            created_at=now,
        )
    )
    db.commit()
    return _package_summary(row)


@admin_router.get("/platform-admin/console/cells")
def fleet(request: Request, db: Session = Depends(get_db)):
    """Every cell as its heartbeats describe it: where it runs, when it last called, its health and versions,
    failed jobs and package states. Metadata only; a cell's records never reach the platform."""
    _require_platform_admin(request, db)
    now = datetime.now(timezone.utc)
    cells = db.query(Cell).order_by(Cell.created_at).all()
    names = _tenant_names(db, [cell.tenant_id for cell in cells])
    states: dict[uuid.UUID, dict[str, int]] = {}
    for state in db.query(CellPackageState).all():
        states.setdefault(state.tenant_id, {})
        states[state.tenant_id][state.state] = states[state.tenant_id].get(state.state, 0) + 1
    items = []
    for cell in cells:
        heartbeat = cell.last_heartbeat or {}
        jobs = heartbeat.get("jobs") or []
        licence = (cell.licence_envelope or {}).get("content") or {}
        seconds = int((now - cell.last_heartbeat_at).total_seconds()) if cell.last_heartbeat_at else None
        items.append(
            _with_tenant(
                {
                    "id": str(cell.id),
                    "hosting_mode": cell.hosting_mode,
                    "status": cell.status,
                    "enrolled_at": _iso(cell.enrolled_at),
                    "last_heartbeat_at": _iso(cell.last_heartbeat_at),
                    "seconds_since_heartbeat": seconds,
                    "contact": "NEVER"
                    if seconds is None
                    else "CURRENT"
                    if seconds <= HEARTBEAT_EVERY_MINUTES * 60 * 2
                    else "LATE",
                    "health": cell.health,
                    "software_version": cell.software_version,
                    "schema_version": cell.schema_version,
                    "uptime_seconds": heartbeat.get("uptime_seconds"),
                    "jobs_failed": sum(1 for job in jobs if job.get("status") == "FAILED"),
                    "jobs_reported": len(jobs),
                    "counts": heartbeat.get("counts") or {},
                    "packages": states.get(cell.tenant_id, {}),
                    "licence_status": licence.get("status"),
                    "licence_valid_until": licence.get("valid_until"),
                    "licence_sha256": (cell.licence_envelope or {}).get("content_sha256"),
                },
                names,
                cell.tenant_id,
            )
        )
    return {"items": items, "heartbeat_every_minutes": HEARTBEAT_EVERY_MINUTES}
