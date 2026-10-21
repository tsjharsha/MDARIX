"""Run the continuously operating transactional-outbox worker.

The worker delivers one event per transaction (outbox/worker.py), records a heartbeat for the platform console and the
container health check every cycle, and stops promptly on SIGTERM/SIGINT: the event in hand is finished, nothing new
is started. Staging and production refuse to start with a missing or unsafe configuration (the API's own gate), and
an unsupported ``MDARIX_OUTBOX_PUBLISHER`` is refused here, at startup, rather than on the first unhandled event.
"""

import json
import logging
import os
import signal
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# The worker is launched as ``python scripts/run_outbox_worker.py`` inside
# the image, so Python initially searches ``/app/scripts``. Add the image
# root explicitly so repository packages resolve consistently in containers.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from outbox.worker import OutboxWorker
from backend.app.db.data_plane import SHARED_CONTROL_DATA_PLANE, session_factory
from backend.app.db.models.customer_lifecycle import TenantDataPlane
from backend.app.db.models.enterprise import ConnectorRun, ConnectorSourceRecord
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from backend.app.worker_status import OUTBOX_WORKER, record_heartbeat
from integration.api_contract import idempotency_key
from uuid import UUID
from reports.service import run_pending_report_jobs

logger = logging.getLogger(__name__)

# Delivery adapters for events no built-in handler takes. ``noop`` acknowledges them (audit-only events); nothing
# else exists yet, and a name that is not implemented must be refused before the worker takes any event.
SUPPORTED_PUBLISHERS = ("noop",)


def configured_publisher() -> str:
    """The MDARIX_OUTBOX_PUBLISHER value, or SystemExit explaining what is supported when it is something else."""
    value = os.getenv("MDARIX_OUTBOX_PUBLISHER", "noop").strip().lower() or "noop"
    if value not in SUPPORTED_PUBLISHERS:
        raise SystemExit(
            f"OUTBOX_PUBLISHER_NOT_IMPLEMENTED: MDARIX_OUTBOX_PUBLISHER={value!r} names a delivery adapter this build "
            f"does not have. Supported values: {', '.join(SUPPORTED_PUBLISHERS)} (events without a built-in handler "
            "are acknowledged). Unset the variable or set it to noop."
        )
    return value


@contextmanager
def plane_session(plane):
    """A session on one tenant's business data: its dedicated database, or (for tenants without one) the shared
    control database bound to that tenant, as the API does (data_plane.get_data_plane_db)."""
    if plane.connection_secret_ref == SHARED_CONTROL_DATA_PLANE:
        db = SessionLocal()
    else:
        db = session_factory(plane.database_ref, plane.connection_secret_ref)()
    # A dedicated database holds one tenant, but its row-level security is forced like the shared one's (md05, md34):
    # the session is bound to the tenant either way, or every statement sees nothing.
    bind_tenant(db, plane.tenant_id)
    try:
        yield db
    finally:
        db.close()


def route_provider_event_to_data_plane(payload):
    """Persist a provider event in its approved tenant data plane.

    The control-plane outbox remains the delivery/retry ledger. This handler
    is the worker's business-data boundary: it resolves the plane only from
    the central registry and never from event-supplied connection details.
    """
    tenant_id = UUID(str(payload.get("tenant_id")))
    provider = str(payload.get("provider") or payload.get("source_system") or "UNKNOWN")
    entity = str(payload.get("entity") or "Record")
    record = payload.get("record") or {}
    external_id = str(payload.get("external_id") or record.get("external_id") or record.get("id") or "")
    version = str(payload.get("record_version") or record.get("record_version") or record.get("version") or "") or None
    fingerprint = str(
        payload.get("idempotency_key")
        or payload.get("fingerprint")
        or idempotency_key(str(tenant_id), provider, entity, record)
    )
    with SessionLocal() as control_db:
        bind_system(control_db, "outbox worker: resolve the tenant's data plane")
        plane = (
            control_db.query(TenantDataPlane)
            .filter(TenantDataPlane.tenant_id == tenant_id, TenantDataPlane.status == "ACTIVE")
            .one_or_none()
        )
        if plane is None:
            raise RuntimeError("DATA_PLANE_NOT_REGISTERED")
        with plane_session(plane) as data_db:
            existing = (
                data_db.query(ConnectorSourceRecord)
                .filter(
                    ConnectorSourceRecord.tenant_id == tenant_id,
                    ConnectorSourceRecord.source_system == provider,
                    ConnectorSourceRecord.source_record_id == external_id,
                    ConnectorSourceRecord.source_record_version == version,
                )
                .first()
            )
            if existing:
                return
            now = datetime.now(timezone.utc)
            run = ConnectorRun(
                tenant_id=tenant_id,
                connection_id="outbox-worker",
                source_system=provider,
                run_type="INCREMENTAL",
                status="COMPLETED",
                records_received=1,
                records_accepted=1,
                schema_drift_status="MATCH",
                started_at=now,
                completed_at=now,
                created_at=now,
            )
            data_db.add(run)
            data_db.flush()
            data_db.add(
                ConnectorSourceRecord(
                    tenant_id=tenant_id,
                    connector_run_id=run.id,
                    source_system=provider,
                    source_record_id=external_id,
                    source_record_version=version,
                    fingerprint=fingerprint,
                    processing_status="INGESTED",
                    ingested_at=now,
                    created_at=now,
                )
            )
            data_db.commit()


def publish(event_name, payload):
    if event_name == "PROVIDER_RECORD_RECEIVED":
        route_provider_event_to_data_plane(payload)
        return
    if event_name == "TENANT_EXPORT_REQUESTED":
        from backend.app.tenant_export import run_export

        run_export(payload["export_id"])
        return
    if event_name == "RECORD_EMBEDDINGS_REQUESTED":
        # An import's records, embedded here instead of in the API (retrieval/record_evidence.py).
        from retrieval.record_evidence import run_embeddings_job

        run_embeddings_job(payload)
        return
    if event_name == "SUPPORT_PROBLEM_REPORTED":
        from backend.app.support_api import deliver_problem_report

        with SessionLocal() as db:
            bind_system(db, "outbox worker: email the support team about a reported problem")
            deliver_problem_report(db, payload)
        return
    from backend.app.notifications import handle_event

    with SessionLocal() as db:
        bind_system(db, f"outbox worker: deliver {event_name}")
        if handle_event(db, event_name, payload):
            return
    # Events nobody needs to be told about (for example audit-only events) are acknowledged by the noop publisher;
    # configured_publisher() already refused anything else at startup.
    configured_publisher()


def alert_dead_letter(payload):
    """Deliver an operational alert without exposing event payload data (backend/app/alerts.py)."""
    from backend.app.alerts import send_alert

    send_alert(
        "Event dead-lettered",
        f"{payload.get('event_name')} (event {payload.get('event_id')}) failed {payload.get('attempts')} times: "
        f"{payload.get('error')}. Review it in Platform Admin > Operations > Dead letters.",
    )


def write_heartbeat(metrics):
    """Publish a small, secret-free heartbeat for a local/sidecar monitor."""
    target = os.getenv("MDARIX_OUTBOX_HEARTBEAT_FILE", "").strip()
    if not target:
        return
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            {
                "service": "mdarix-outbox-worker",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "metrics": metrics,
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def record_database_heartbeat(instance_id, started_at, metrics):
    """Record the heartbeat where the platform console reads it. A failure is logged, never fatal to the worker."""
    try:
        with SessionLocal() as db:
            bind_system(db, "outbox worker: record heartbeat")
            record_heartbeat(db, OUTBOX_WORKER, instance_id, started_at, metrics)
    except Exception:
        logger.exception("worker heartbeat could not be recorded")


def process_pending_reports(limit: int = 10):
    """Drain report jobs from every registered tenant data plane."""
    from backend.app.deployment_role import served_tenants_clause

    claimed = ready = failed = 0
    with SessionLocal() as control_db:
        bind_system(control_db, "report worker: list registered data planes")
        # A cell drains its own organization's report jobs only.
        planes = (
            control_db.query(TenantDataPlane)
            .filter(TenantDataPlane.status == "ACTIVE", served_tenants_clause(TenantDataPlane.tenant_id))
            .all()
        )
        for plane in planes:
            try:
                with plane_session(plane) as data_db:
                    # The shared database holds every such tenant's jobs: take only this tenant's.
                    shared = plane.connection_secret_ref == SHARED_CONTROL_DATA_PLANE
                    result = run_pending_report_jobs(
                        data_db, limit=limit, tenant_id=plane.tenant_id if shared else None
                    )
                    claimed += result["claimed"]
                    ready += result["ready"]
                    failed += result["failed"]
            except Exception:
                logger.exception("report worker plane failed tenant=%s", plane.tenant_id)
                failed += 1
    return {"claimed": claimed, "ready": ready, "failed": failed}


def main(shutdown: threading.Event | None = None) -> int:
    from backend.app.config_check import enforce
    from backend.app.logging_setup import configure_logging

    configure_logging()
    enforce()
    configured_publisher()
    shutdown = shutdown or threading.Event()

    def stop(_signum, _frame):
        logger.info("outbox worker shutdown requested")
        shutdown.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    worker = OutboxWorker(publish, alert=alert_dead_letter, should_stop=shutdown.is_set)
    interval = int(os.getenv("MDARIX_OUTBOX_INTERVAL_SECONDS", "5"))
    batch = int(os.getenv("MDARIX_OUTBOX_BATCH_SIZE", "50"))
    report_batch = int(os.getenv("MDARIX_REPORT_WORKER_BATCH_SIZE", "10"))
    instance_id, started_at = str(uuid.uuid4()), datetime.now(timezone.utc)
    while not shutdown.is_set():
        try:
            worker.recover_stale_claims()
            stats = worker.process_once(limit=batch)
            reports = process_pending_reports(limit=report_batch)
            metrics = {**worker.metrics.snapshot(), "report_jobs": reports, "last_cycle": stats}
            write_heartbeat(metrics)
            record_database_heartbeat(instance_id, started_at, metrics)
            logger.info("outbox metrics=%s cycle=%s reports=%s", worker.metrics.snapshot(), stats, reports)
        except Exception:  # the database may be briefly unavailable; the next cycle tries again
            logger.exception("outbox worker cycle failed")
        shutdown.wait(max(0, interval))
    logger.info("outbox worker stopped gracefully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
