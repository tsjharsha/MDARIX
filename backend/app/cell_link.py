"""The cell's side of the platform-cell link (ADR-014).

A cell calls the platform, outbound only, every quarter hour (the ``platform-sync`` job): it enrolls once with the
one-time token from its enrollment bundle, sends a heartbeat that carries versions, health, job outcomes and counts
and nothing else, and fetches the platform's signed packages. The licence is applied automatically; other packages
are stored as offered for the administrator (adoption follows in a later phase). Everything the cell receives is
verified against the pinned platform key before it is stored.

The cell keeps serving when the platform is unreachable. A licence that has passed its end date is honoured for a
grace period (``GRACE_DAYS``, decision D6); after that the cell is read-only (``backend/app/main.py`` refuses state
changes outside sign-in) until a licence arrives, and nothing is ever deleted.

The cell's identity lives in files (``MDARIX_CELL_IDENTITY_DIR``): its private key, its certificate, the platform
authority's certificate and its credential. Never in the database.
"""

from __future__ import annotations

import json
import logging
import os
import re
import ssl
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.cell_licence import apply_licence
from backend.app.cell_packages import PackageError, platform_public_key, verify
from backend.app.cell_pki import csr_pem, generate_key
from backend.app.db.models.customer_lifecycle import CellLicence, ReceivedPackage
from backend.app.db.models.foundation import AuditEvent
from backend.app.deployment_role import is_cell
from backend.app.runtime_env import is_local

logger = logging.getLogger("mdarix.cell_link")
ACTOR = "system:cell-link"
GRACE_DAYS = 30
CACHE_SECONDS = 60
TIMEOUT_SECONDS = 20
_STARTED = time.monotonic()
_read_only_cache: dict = {"checked": 0.0, "value": None}
COUNTS = {
    "users_active": "SELECT count(*) FROM auth_users WHERE tenant_id = :t AND status = 'ACTIVE'",
    "products": "SELECT count(*) FROM products WHERE tenant_id = :t",
    "complaints": "SELECT count(*) FROM complaints WHERE tenant_id = :t",
    "investigations": "SELECT count(*) FROM investigations WHERE tenant_id = :t",
    "evidence": "SELECT count(*) FROM evidence WHERE tenant_id = :t",
    "signed_decisions": "SELECT count(*) FROM signed_approval_records WHERE tenant_id = :t",
}


class LinkError(RuntimeError):
    """The platform could not be reached or refused the cell; the cell keeps serving."""


# ------------------------------------------------------------------------------------------- identity


def platform_url() -> str:
    return os.getenv("MDARIX_PLATFORM_URL", "").strip().rstrip("/")


def identity_dir() -> Path:
    configured = os.getenv("MDARIX_CELL_IDENTITY_DIR", "").strip()
    return Path(configured or (".mdarix-cell" if is_local() else "/var/lib/mdarix/cell"))


def identity() -> dict | None:
    """The enrolled identity (file paths and the credential), or None before enrollment."""
    folder = identity_dir()
    credential, certificate, key = folder / "credential", folder / "cell.crt", folder / "cell.key"
    if not (credential.is_file() and certificate.is_file() and key.is_file()):
        return None
    return {
        "credential": credential.read_text(encoding="ascii").strip(),
        "certificate_file": str(certificate),
        "key_file": str(key),
        "ca_file": str(folder / "ca.crt") if (folder / "ca.crt").is_file() else None,
    }


def _write_secret(path: Path, content: str) -> None:
    path.write_text(content, encoding="ascii")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


# ------------------------------------------------------------------------------------------- transport


def transport(
    method: str, url: str, body: dict | None, headers: dict, who: dict | None, timeout: float
) -> tuple[int, dict]:
    """One HTTPS call to the platform with the cell's certificate; (status, JSON body). Replaced in tests."""
    context = ssl.create_default_context(cafile=os.getenv("MDARIX_PLATFORM_CA_FILE", "").strip() or None)
    if who and who.get("certificate_file") and who.get("key_file"):
        context.load_cert_chain(who["certificate_file"], who["key_file"])
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urlrequest.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "User-Agent": "MDARIX-cell/1.0",
            **({"Content-Type": "application/json"} if data is not None else {}),
            **headers,
        },
    )
    try:
        with urlrequest.urlopen(request, timeout=timeout, context=context) as response:
            payload = response.read(5_000_000)
            return response.status, json.loads(payload) if payload else {}
    except HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except ValueError:
            return exc.code, {}
    except (URLError, TimeoutError, ssl.SSLError, ValueError) as exc:
        raise LinkError(f"PLATFORM_UNREACHABLE:{type(exc).__name__}") from exc


_transport = transport


def _call(method: str, path: str, body: dict | None = None, who: dict | None = None) -> tuple[int, dict]:
    base = platform_url()
    if not base:
        raise LinkError("PLATFORM_URL_NOT_CONFIGURED")
    headers = {"Authorization": f"Bearer {who['credential']}"} if who else {}
    return _transport(method, f"{base}{path}", body, headers, who, TIMEOUT_SECONDS)


# ------------------------------------------------------------------------------------------- what the cell says


def _safe(value) -> str:
    return re.sub(r"[^A-Za-z0-9_.:+-]", "-", str(value or ""))[:80] or "unknown"


def software_version() -> str:
    from backend.app.version import release

    return _safe(release())


def schema_version(db: Session) -> str:
    try:
        return _safe(db.execute(text("SELECT version_num FROM alembic_version")).scalar())
    except Exception:
        return "unknown"


def heartbeat_payload(db: Session, tenant_id) -> dict:
    """Versions, a health word, uptime, the outcome of each scheduled job, a few record counts and the package
    states. Every string is reduced to a safe token: the platform refuses anything else."""
    from backend.app.db.models.stage2 import SchedulerRun
    from backend.app.scheduler import active_jobs

    runs = {row.job: row for row in db.query(SchedulerRun).all()}
    jobs = []
    for job in active_jobs():
        run = runs.get(job.name)
        if run is None or run.last_finished_at is None:
            jobs.append({"name": _safe(job.name), "status": "NEVER"})
            continue
        jobs.append(
            {
                "name": _safe(job.name),
                "status": "OK" if run.last_status == "OK" else "FAILED",
                "finished_at": run.last_finished_at.isoformat(),
                "error_type": _safe(run.last_error.split(":")[0]) if run.last_error else None,
            }
        )
    counts = {}
    for name, sql in COUNTS.items():
        try:
            counts[name] = int(db.execute(text(sql), {"t": tenant_id}).scalar() or 0)
        except Exception:
            counts[name] = 0
    packages = [
        {"id": str(row.id), "state": row.status}
        for row in db.query(ReceivedPackage).filter(ReceivedPackage.tenant_id == tenant_id).limit(100)
    ]
    try:
        from backend.app.readiness import public_status

        health = public_status()[1].get("status", "degraded")
    except Exception:
        health = "degraded"
    return {
        "software_version": software_version(),
        "schema_version": schema_version(db),
        "health": health if health in {"ok", "degraded", "down"} else "degraded",
        "uptime_seconds": int(time.monotonic() - _STARTED),
        "jobs": jobs[:50],
        "counts": counts,
        "packages": packages,
    }


def _audit(db: Session, tenant_id, action: str, details: dict, now: datetime, entity_id=None) -> None:
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=ACTOR,
            action=action,
            entity_type="PlatformLink",
            entity_id=entity_id,
            details=details,
            created_at=now,
        )
    )


# ------------------------------------------------------------------------------------------- the link


def enroll(db: Session, tenant_id, tenant_key: str, token: str) -> dict:
    """Exchange the one-time enrollment token for the cell's certificate and credential, kept in files."""
    key_pem = generate_key()
    status, payload = _call(
        "POST",
        "/api/v1/cells/enroll",
        {
            "tenant_id": str(tenant_id),
            "tenant_key": tenant_key,
            "enrollment_token": token,
            "csr_pem": csr_pem(key_pem, f"cell:{tenant_key}"),
            "software_version": software_version(),
            "schema_version": schema_version(db),
        },
    )
    if status != 200:
        code = (payload.get("detail") or {}).get("code", status) if isinstance(payload, dict) else status
        raise LinkError(f"ENROLLMENT_REFUSED:{code}")
    folder = identity_dir()
    folder.mkdir(parents=True, exist_ok=True)
    _write_secret(folder / "cell.key", key_pem)
    (folder / "cell.crt").write_text(payload["certificate_pem"], encoding="ascii")
    (folder / "ca.crt").write_text(payload.get("ca_certificate_pem") or "", encoding="ascii")
    _write_secret(folder / "credential", payload["credential"])
    now = datetime.now(timezone.utc)
    _audit(db, tenant_id, "CELL_ENROLLED", {"platform": platform_url(), "cell_id": payload.get("cell_id")}, now)
    db.commit()
    return {"enrolled": True, "cell_id": payload.get("cell_id"), "licence": payload.get("licence")}


def _receive_licence(db: Session, tenant_id, envelope: dict, key: str) -> dict:
    digest = str(envelope.get("content_sha256") or "")
    if digest and db.query(CellLicence).filter(CellLicence.content_sha256 == digest).first() is not None:
        return {"status": "CURRENT", "content_sha256": digest}
    now = datetime.now(timezone.utc)
    try:
        outcome = apply_licence(db, envelope, key, now=now)
    except PackageError as exc:
        _audit(db, tenant_id, "LICENCE_REJECTED", {"reason": str(exc), "content_sha256": digest}, now)
        db.commit()
        return {"status": "REJECTED", "reason": str(exc), "content_sha256": digest}
    clear_cache()
    return {
        **outcome,
        "licence_status": outcome.get("status"),
        "status": "APPLIED" if outcome.get("applied") else "CURRENT",
    }


def _receive_package(db: Session, tenant_id, meta: dict, who: dict, key: str) -> dict:
    try:
        package_id = uuid.UUID(str(meta.get("id")))
    except ValueError:
        return {"id": meta.get("id"), "status": "IGNORED"}
    existing = db.get(ReceivedPackage, package_id)
    if existing is not None:
        return {"id": str(package_id), "status": existing.status}
    status, payload = _call("GET", f"/api/v1/cells/packages/{package_id}", None, who)
    if status != 200 or not isinstance(payload, dict):
        return {"id": str(package_id), "status": "UNAVAILABLE"}
    envelope = payload.get("package") or {}
    now = datetime.now(timezone.utc)
    detail = None
    try:
        content = verify(envelope, key)
        if envelope.get("kind") == "LICENCE":
            raise PackageError("PACKAGE_KIND")
        state = "OFFERED"  # the administrator adopts it (impact report and adoption: a later phase)
    except PackageError as exc:
        content, state, detail = {}, "REJECTED", {"reason": str(exc)}
    row = ReceivedPackage(
        id=package_id,
        tenant_id=tenant_id,
        kind=str(envelope.get("kind") or meta.get("kind") or "UNKNOWN")[:40],
        code=str(content.get("code") or meta.get("code") or "")[:120],
        version=str(content.get("version") or meta.get("version") or "")[:40],
        content_sha256=str(envelope.get("content_sha256") or meta.get("content_sha256") or "")[:64],
        key_id=str(envelope.get("key_id") or "unknown")[:80],
        envelope=envelope,
        status=state,
        received_at=now,
        detail=detail,
    )
    db.add(row)
    _audit(
        db,
        tenant_id,
        "PACKAGE_REJECTED" if state == "REJECTED" else "PACKAGE_RECEIVED",
        {
            "kind": row.kind,
            "code": row.code,
            "version": row.version,
            "content_sha256": row.content_sha256,
            **(detail or {}),
        },
        now,
        entity_id=package_id,
    )
    db.commit()
    return {"id": str(package_id), "status": state, "kind": row.kind, "code": row.code, "version": row.version}


def sync(db: Session, tenant_id, tenant_key: str) -> dict:
    """One round of the link: enroll if needed, heartbeat, licence, packages. Raises LinkError when the platform
    cannot be reached or refuses the cell; the scheduler records and alerts, the cell keeps serving."""
    summary: dict = {"enrolled": False, "heartbeat": None, "licence": None, "packages": []}
    who = identity()
    if who is None:
        token = os.getenv("MDARIX_CELL_ENROLLMENT_TOKEN", "").strip()
        if not token:
            raise LinkError("NOT_ENROLLED: set MDARIX_CELL_ENROLLMENT_TOKEN from the enrollment bundle")
        summary["enrolled"] = enroll(db, tenant_id, tenant_key, token)["enrolled"]
        who = identity()
    status, answer = _call("POST", "/api/v1/cells/heartbeat", heartbeat_payload(db, tenant_id), who)
    if status == 401:
        raise LinkError("CELL_NOT_RECOGNIZED: the platform refused the cell's credential; re-enroll with a new bundle")
    if status != 200:
        raise LinkError(f"HEARTBEAT_REFUSED:{status}")
    summary["heartbeat"] = "SENT"
    status, listing = _call("GET", "/api/v1/cells/packages", None, who)
    if status != 200 or not isinstance(listing, dict):
        raise LinkError(f"PACKAGES_UNAVAILABLE:{status}")
    key = platform_public_key()
    if listing.get("licence"):
        summary["licence"] = _receive_licence(db, tenant_id, listing["licence"], key)
    for meta in listing.get("packages") or []:
        if isinstance(meta, dict):
            summary["packages"].append(_receive_package(db, tenant_id, meta, who, key))
    return summary


# ------------------------------------------------------------------------------------------- the licence state


def licence_state(db: Session, tenant_id, now: datetime | None = None) -> dict:
    """VALID, GRACE (past its end, within GRACE_DAYS), EXPIRED (read-only), SUSPENDED, or NONE (no cell licence:
    a MULTI deployment's plans apply as before)."""
    now = now or datetime.now(timezone.utc)
    row = (
        db.query(CellLicence).filter(CellLicence.tenant_id == tenant_id).order_by(CellLicence.applied_at.desc()).first()
    )
    if row is None:
        return {"state": "NONE", "read_only": False, "valid_until": None, "grace_until": None, "licence_id": None}
    grace_until = row.valid_until + timedelta(days=GRACE_DAYS) if row.valid_until else None
    if row.status == "SUSPENDED":
        state = "SUSPENDED"
    elif row.valid_until is None or now <= row.valid_until:
        state = "VALID"
    elif now <= grace_until:
        state = "GRACE"
    else:
        state = "EXPIRED"
    return {
        "state": state,
        "read_only": state == "EXPIRED",
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "grace_until": grace_until.isoformat() if grace_until else None,
        "licence_id": str(row.id),
    }


def clear_cache() -> None:
    _read_only_cache.update({"checked": 0.0, "value": None})


def read_only() -> dict | None:
    """In a CELL whose licence has expired past its grace period: the licence state to refuse state changes with;
    otherwise None. Checked once a minute."""
    if not is_cell():
        return None
    now = time.monotonic()
    if now - _read_only_cache["checked"] < CACHE_SECONDS:
        return _read_only_cache["value"]
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system
    from backend.app.deployment_role import cell_tenant_id

    value = None
    try:
        with SessionLocal() as db:
            bind_system(db, "cell link: licence state")
            state = licence_state(db, cell_tenant_id())
            value = state if state["read_only"] else None
    except Exception:
        logger.exception("The licence state could not be read; the cell stays writable")
    _read_only_cache.update({"checked": now, "value": value})
    return value
