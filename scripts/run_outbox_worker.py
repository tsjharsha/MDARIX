"""Run the continuously operating transactional-outbox worker."""

import json
import logging
import os
import signal
import sys
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


@contextmanager
def plane_session(plane):
    """A session on one tenant's business data: its dedicated database, or (for tenants without one) the shared
    control database bound to that tenant, as the API does (data_plane.get_data_plane_db)."""
    if plane.connection_secret_ref == SHARED_CONTROL_DATA_PLANE:
        db = SessionLocal()
        bind_tenant(db, plane.tenant_id)
    else:
        db = session_factory(plane.database_ref, plane.connection_secret_ref)()
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
    from backend.app.notifications import handle_event

    with SessionLocal() as db:
        bind_system(db, f"outbox worker: deliver {event_name}")
        if handle_event(db, event_name, payload):
            return
    # Events nobody needs to be told about (for example audit-only events) are acknowledged.
    if os.getenv("MDARIX_OUTBOX_PUBLISHER", "noop") == "noop":
        return
    raise RuntimeError("OUTBOX_PUBLISHER_NOT_IMPLEMENTED")


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
        logging.getLogger(__name__).exception("worker heartbeat could not be recorded")


def process_pending_reports(limit: int = 10):
    """Drain report jobs from every registered tenant data plane."""
    claimed = ready = failed = 0
    with SessionLocal() as control_db:
        bind_system(control_db, "report worker: list registered data planes")
        planes = control_db.query(TenantDataPlane).filter(TenantDataPlane.status == "ACTIVE").all()
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
                logging.getLogger(__name__).exception("report worker plane failed tenant=%s", plane.tenant_id)
                failed += 1
    return {"claimed": claimed, "ready": ready, "failed": failed}


if __name__ == "__main__":
    from backend.app.logging_setup import configure_logging

    configure_logging()

    def stop(_signum, _frame):
        nonlocal_stop[0] = True

    nonlocal_stop = [False]
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    worker = OutboxWorker(
        publish, max_attempts=int(os.getenv("MDARIX_OUTBOX_MAX_ATTEMPTS", "5")), alert=alert_dead_letter
    )
    interval = int(os.getenv("MDARIX_OUTBOX_INTERVAL_SECONDS", "5"))
    instance_id, started_at = str(uuid.uuid4()), datetime.now(timezone.utc)
    while not nonlocal_stop[0]:
        worker.recover_stale_claims()
        stats = worker.process_once(limit=int(os.getenv("MDARIX_OUTBOX_BATCH_SIZE", "50")))
        reports = process_pending_reports(limit=int(os.getenv("MDARIX_REPORT_WORKER_BATCH_SIZE", "10")))
        metrics = {**worker.metrics.snapshot(), "report_jobs": reports}
        write_heartbeat({**metrics, "last_cycle": stats})
        record_database_heartbeat(instance_id, started_at, {**metrics, "last_cycle": stats})
        logging.getLogger(__name__).info(
            "outbox metrics=%s cycle=%s reports=%s", worker.metrics.snapshot(), stats, reports
        )
        import time

        time.sleep(max(0, interval))
    logging.getLogger(__name__).info("outbox worker stopped gracefully")
