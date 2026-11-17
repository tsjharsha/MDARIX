"""What /health/ready reports.

The API is *ready* when its database answers as the role it runs as and the schema is at the migration this code
was built for (a deploy that skipped its migration job is taken out of rotation instead of failing at random).
Data planes, object storage, the background worker, the scheduler, email and the clock (B6a G19) are checked too; when one fails the
report says ``degraded`` but the API stays in rotation, since most screens still work. Results are cached for a few
seconds so frequent probes do not load the databases. ``public_status`` reduces the report to one word for
``/health/status``.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
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
        # The log has the whole reason (review O1); the report only its leading code (NOT_REPORTED, STALE, ...), so it
        # names no host, database or count.
        message = str(exc)
        head = message.split(":", 1)[0].strip()
        logger.warning("Readiness check %s failed: %s: %s", name, type(exc).__name__, message)
        return {
            "name": name,
            "ok": False,
            "error": type(exc).__name__,
            "reason": head if re.fullmatch(r"[A-Z][A-Z0-9_]+", head) else "FAILED",
            "ms": round((time.perf_counter() - started) * 1000, 1),
        }


def _database() -> dict:
    from backend.app.db.session import runtime_engine

    with runtime_engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    expected = expected_schema_head()
    if expected and version != expected:
        raise RuntimeError(f"SCHEMA_MISMATCH: schema at {version}, this build needs {expected}")
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
        raise RuntimeError(f"UNREACHABLE: {', '.join(failed)}")
    if outdated:
        raise RuntimeError(f"SCHEMA_OUTDATED: run scripts/migrate_data_planes.py for {', '.join(outdated)}")
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


_embedding_checked = False  # the pinned model was found once: its files do not change while the process runs


def _embedding_model() -> dict:
    """The pinned local embedding model is in the cache (review O2): without it evidence search falls back to
    structured matches only. Hashing the weights is done until it has passed once."""
    global _embedding_checked
    from retrieval.embedding_provider import local_model_problem

    if (os.getenv("MDARIX_EMBEDDING_PROVIDER") or "local").strip().lower() == "deterministic":
        return {"provider": "deterministic"}
    if not _embedding_checked:
        problem = local_model_problem()
        if problem:
            raise RuntimeError(f"MODEL_MISSING: {problem}")
        _embedding_checked = True
    return {"provider": "local"}


# The outbox's queue lag: how long the longest-waiting event that is due has waited. The worker cycles every few
# seconds, so fifteen minutes means it is stopped, stuck or overwhelmed (0.10.88, DEV-13).
OUTBOX_MAX_LAG = timedelta(minutes=15)


def outbox_backlog(db) -> dict:
    """Events waiting to be published: how many, how many are retrying after a failure, how many of those failed
    sending e-mail (the provider refused it: EmailDeliveryError, or the notifications' NotificationFailed), and the lag of the longest-waiting one that is due (an event backing off is not due yet)."""
    from backend.app.db.tenant_scope import bind_system

    bind_system(db, "readiness: outbox backlog")
    row = db.execute(
        text(
            "SELECT count(*), count(*) FILTER (WHERE attempts > 0), "
            "count(*) FILTER (WHERE attempts > 0 AND (last_error LIKE 'EmailDeliveryError%' "
            "OR last_error LIKE 'NotificationFailed%')), "
            "EXTRACT(EPOCH FROM now() - min(coalesce(next_attempt_at, occurred_at)) "
            "FILTER (WHERE coalesce(next_attempt_at, occurred_at) <= now())) "
            "FROM event_outbox WHERE published_at IS NULL AND dead_lettered_at IS NULL"
        )
    ).one()
    return {
        "waiting": int(row[0]),
        "retrying": int(row[1]),
        "email_failing": int(row[2]),
        "lag_seconds": int(row[3] or 0),
    }


def _outbox() -> dict:
    from backend.app.db.session import SessionLocal

    db = SessionLocal()
    try:
        backlog = outbox_backlog(db)
    finally:
        db.close()
    if backlog["lag_seconds"] > OUTBOX_MAX_LAG.total_seconds():
        raise RuntimeError(f"LAGGING: the oldest due event has waited {backlog['lag_seconds']}s")
    return backlog


def _email(failing: int = 0) -> dict:
    """Configured, and not failing: ``failing`` e-mails the outbox retries after the provider refused them (read by
    the outbox check) make it degraded."""
    from auth.emailer import delivery_off, smtp_configuration_status

    if delivery_off():
        return {"delivery": "off"}  # a demo or local run that must not e-mail anyone: by design, not a fault
    if not smtp_configuration_status().get("configured"):
        raise RuntimeError("NOT_CONFIGURED: SMTP has no host, account or sender")
    if failing:
        raise RuntimeError(f"DELIVERY_FAILING: {failing} e-mail(s) waiting to be retried")
    return {}


# The operations-alerts job runs every 5 minutes; three missed runs mean the scheduler is not doing its work.
SCHEDULER_WATCH_JOB = "operations-alerts"
SCHEDULER_MAX_AGE = timedelta(minutes=15)


def _scheduler(job: str = SCHEDULER_WATCH_JOB, max_age: timedelta = SCHEDULER_MAX_AGE) -> dict:
    """The scheduler has finished ``job`` within ``max_age`` (scheduler_runs is platform-level, no tenant scope)."""
    from backend.app.db.models.stage2 import SchedulerRun
    from backend.app.db.session import SessionLocal

    db = SessionLocal()
    try:
        row = db.get(SchedulerRun, job)
        finished = row.last_finished_at if row is not None else None
    finally:
        db.close()
    if finished is None:
        raise RuntimeError("NOT_REPORTED")
    age = (datetime.now(timezone.utc) - finished).total_seconds()
    if age > max_age.total_seconds():
        raise RuntimeError(f"STALE: last run {int(age)}s ago")
    return {"seconds_since": int(age)}


def _clock() -> dict:
    """B6a G19: app vs database vs NTP within 1 s (backend/app/clock_check.py); unknown or above the limit is not ok."""
    from backend.app import clock_check

    started = time.perf_counter()
    try:
        result = clock_check.check()
    except Exception as exc:  # a probe must report, never raise
        logger.warning("Readiness check clock failed: %s", type(exc).__name__)
        result = {"state": clock_check.UNKNOWN, "error": type(exc).__name__}
    ok = result["state"] == clock_check.OK
    return {"name": "clock", "ok": ok, **result, "ms": round((time.perf_counter() - started) * 1000, 1)}


def _trial_ai_chain() -> dict:
    """Review G10: the free-trial AI chain (MDARIX_AI_TRIAL_CHAIN). Off when no chain is set. Otherwise each provider:
    usable (vetted, configured, on loopback where required), resting after a failure, and for a gateway on this server
    whether its port accepts a connection (no request is sent to any AI service). Not ok when no provider is usable,
    reachable and awake, or when no AI feature is switched on for the server (MDARIX_AI_FEATURES). It reports and
    alerts like the clock: it leaves the readiness status as it is, since AI is never required for the service."""
    import socket
    from urllib.parse import urlparse

    from genai import provider as genai
    from genai.features import platform_features

    names = genai.trial_chain_names()
    if not names:
        return {"state": "OFF"}
    problems = genai.trial_chain_problems(names)
    resting_until = genai._resting_until()
    providers = []
    for name in names:
        item = {"provider": name, "usable": name not in problems, "resting": resting_until.get(name, 0) > time.time()}
        if name in ("freellmapi", "omniroute") and item["usable"]:
            url = os.getenv(f"MDARIX_GENAI_{name.upper()}_BASE_URL") or genai.OPENAI_COMPATIBLE[name][0]
            parsed = urlparse(url)
            try:
                socket.create_connection((parsed.hostname, parsed.port or 80), timeout=1.0).close()
                item["reachable"] = True
            except OSError:
                item["reachable"] = False
        providers.append(item)
    features = sorted(platform_features())
    if not features:
        raise RuntimeError("NO_AI_FEATURES: the trial chain is set but MDARIX_AI_FEATURES lists no feature")
    if not any(p["usable"] and not p["resting"] and p.get("reachable", True) for p in providers):
        raise RuntimeError(f"TRIAL_AI_CHAIN_DOWN: {providers}")
    return {"state": "ON", "providers": providers, "features": features}


def readiness_report() -> dict:
    global _cached
    with _lock:
        now = time.monotonic()
        if _cached and now - _cached[0] < _CACHE_SECONDS:
            return _cached[1]
        database = _check("database", _database)
        outbox = _check("outbox", _outbox)
        others = [
            _check("data_planes", _data_planes),
            _check("object_storage", _object_storage),
            _check("worker", _worker),
            outbox,
            _check("scheduler", _scheduler),
            _check("email", lambda: _email(outbox.get("email_failing", 0))),
            _check("embedding_model", _embedding_model),
        ]
        status = "ready" if database["ok"] else "not_ready"
        if status == "ready" and not all(item["ok"] for item in others):
            status = "degraded"
        # B6a G19: reported, and alerted by the operations job, but it leaves the status (and the public status page)
        # as it was (spec 3.4).
        report = {"status": status, "checks": [database, *others, _clock(), _check("trial_ai_chain", _trial_ai_chain)]}
        # Cached from when the report is ready: probes that time out (a database down) take longer than the cache.
        _cached = (time.monotonic(), report)
        return report


# What /health/status says for each readiness state: the public word and the HTTP status.
_PUBLIC = {"ready": ("ok", 200), "degraded": ("degraded", 200), "not_ready": ("down", 503)}


def public_status() -> tuple[int, dict]:
    """(HTTP status, body) for the public status endpoint: one word, no component names, errors or timings, so a
    status page can poll it without learning anything about the deployment. Shares the readiness cache."""
    word, code = _PUBLIC.get(readiness_report()["status"], ("down", 503))
    return code, {"status": word}
