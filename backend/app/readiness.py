"""What /health/ready reports.

The API is *ready* when its database answers as the role it runs as and the schema is at the migration this code
was built for (a deploy that skipped its migration job is taken out of rotation instead of failing at random).
Data planes, object storage, the background worker and email are checked too; when one fails the report says
``degraded`` but the API stays in rotation, since most screens still work. Results are cached for a few seconds so
frequent probes do not load the databases.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from functools import lru_cache
from pathlib import Path

from sqlalchemy import text

logger = logging.getLogger(__name__)

_CACHE_SECONDS = 10
_lock = threading.Lock()
_cached: tuple[float, dict] | None = None
_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def expected_schema_head() -> str | None:
    """The newest migration in this build (None when the migration files are not shipped with it)."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config(str(_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(_ROOT / "infrastructure" / "database" / "migrations"))
        heads = ScriptDirectory.from_config(config).get_heads()
        return heads[0] if len(heads) == 1 else None
    except Exception:
        logger.exception("Could not read the migration head")
        return None


def _check(name: str, func) -> dict:
    started = time.perf_counter()
    try:
        detail = func() or {}
        return {"name": name, "ok": True, **detail, "ms": round((time.perf_counter() - started) * 1000, 1)}
    except Exception as exc:  # a probe must report, never raise
        logger.warning("Readiness check %s failed: %s", name, type(exc).__name__)
        return {
            "name": name,
            "ok": False,
            "error": type(exc).__name__,
            "ms": round((time.perf_counter() - started) * 1000, 1),
        }


def _database() -> dict:
    from backend.app.db.session import runtime_engine

    with runtime_engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    expected = expected_schema_head()
    if expected and version != expected:
        raise RuntimeError(f"schema at {version}, this build needs {expected}")
    return {"schema": version}


def _data_planes() -> dict:
    from backend.app.db.data_plane import SHARED_CONTROL_DATA_PLANE, plane_schema_ok, session_factory
    from backend.app.db.models.customer_lifecycle import TenantDataPlane
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system

    control = SessionLocal()
    try:
        bind_system(control, "readiness: list registered data planes")
        planes = [
            (row.database_ref, row.connection_secret_ref)
            for row in control.query(TenantDataPlane).filter(TenantDataPlane.status == "ACTIVE")
            if row.connection_secret_ref != SHARED_CONTROL_DATA_PLANE
        ]
    finally:
        control.close()
    failed, outdated = [], []
    for database_ref, secret_ref in sorted(set(planes)):
        try:
            session = session_factory(database_ref, secret_ref)()
            try:
                session.execute(text("SELECT 1")).scalar_one()
            finally:
                session.close()
        except Exception:
            failed.append(database_ref)
            continue
        if not plane_schema_ok(database_ref, secret_ref):
            outdated.append(database_ref)
    if failed:
        raise RuntimeError(f"unreachable: {', '.join(failed)}")
    if outdated:
        raise RuntimeError(f"schema not at head (run scripts/migrate_data_planes.py): {', '.join(outdated)}")
    return {"dedicated": len(set(planes))}


def _object_storage() -> dict:
    provider = (os.getenv("MDARIX_OBJECT_STORAGE_PROVIDER") or "local").lower()
    from object_storage.service import ObjectStorageService

    storage = ObjectStorageService()
    if provider == "s3":
        storage.client.head_bucket(Bucket=storage.bucket)
    else:
        probe = storage.root / ".readiness"
        probe.write_bytes(b"ok")
        probe.unlink()
    return {"provider": provider}


def _worker() -> dict:
    from backend.app.db.session import SessionLocal
    from backend.app.worker_status import worker_status

    db = SessionLocal()
    try:
        status = worker_status(db)
    finally:
        db.close()
    if status["state"] != "RUNNING":
        raise RuntimeError(status["state"])
    return {"seconds_since": status["seconds_since"]}


def _email() -> dict:
    from auth.emailer import smtp_configuration_status

    if not smtp_configuration_status().get("configured"):
        raise RuntimeError("SMTP not configured")
    return {}


def readiness_report() -> dict:
    global _cached
    with _lock:
        now = time.monotonic()
        if _cached and now - _cached[0] < _CACHE_SECONDS:
            return _cached[1]
        database = _check("database", _database)
        others = [
            _check("data_planes", _data_planes),
            _check("object_storage", _object_storage),
            _check("worker", _worker),
            _check("email", _email),
        ]
        status = "ready" if database["ok"] else "not_ready"
        if status == "ready" and not all(item["ok"] for item in others):
            status = "degraded"
        report = {"status": status, "checks": [database, *others]}
        _cached = (now, report)
        return report
