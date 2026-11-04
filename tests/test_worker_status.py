"""The background worker records a heartbeat the console reads, and serves tenants on the shared database too."""

import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import reports.service as report_service
from backend.app.db.data_plane import SHARED_CONTROL_DATA_PLANE
from backend.app.db.models.reporting import ReportJob
from backend.app.db.models.stage2 import WorkerHeartbeat
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, scope_of
from backend.app.worker_status import OUTBOX_WORKER, STALE_AFTER_SECONDS, record_heartbeat, worker_status
from tests.conftest import authenticated_client


def _worker_script():
    spec = importlib.util.spec_from_file_location(
        "run_outbox_worker", Path(__file__).resolve().parents[1] / "scripts" / "run_outbox_worker.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _set_heartbeat_age(service, seconds):
    with SessionLocal() as db:
        db.query(WorkerHeartbeat).filter(WorkerHeartbeat.service == service).update(
            {WorkerHeartbeat.updated_at: datetime.now(timezone.utc) - timedelta(seconds=seconds)}
        )
        db.commit()


@pytest.mark.db
def test_a_heartbeat_reads_as_running_then_stopped_when_it_goes_quiet():
    service = f"test-worker-{uuid.uuid4().hex[:8]}"
    started = datetime.now(timezone.utc)
    with SessionLocal() as db:
        assert worker_status(db, service)["state"] == "NOT_REPORTED"
        record_heartbeat(db, service, "instance-1", started, {"cycles": 1})
        record_heartbeat(db, service, "instance-1", started, {"cycles": 2})  # replaced, not added
        status = worker_status(db, service, with_metrics=True)
        assert status["state"] == "RUNNING" and status["metrics"] == {"cycles": 2}
        assert db.query(WorkerHeartbeat).filter(WorkerHeartbeat.service == service).count() == 1
    _set_heartbeat_age(service, STALE_AFTER_SECONDS + 5)
    with SessionLocal() as db:
        assert worker_status(db, service)["state"] == "STOPPED"
        db.query(WorkerHeartbeat).filter(WorkerHeartbeat.service == service).delete()
        db.commit()


@pytest.mark.db
def test_the_operations_view_shows_the_worker_state_and_its_counters():
    with SessionLocal() as db:
        record_heartbeat(db, OUTBOX_WORKER, "instance-1", datetime.now(timezone.utc), {"cycles": 7, "published": 3})
    operations = authenticated_client().get("/api/v1/platform-admin/console/operations").json()
    assert operations["worker_heartbeat"] == "RUNNING"
    assert operations["worker"]["state"] == "RUNNING" and operations["worker"]["metrics"]["published"] == 3


def test_a_shared_database_tenant_gets_a_session_bound_to_that_tenant():
    worker = _worker_script()
    tenant_id = uuid.uuid4()
    plane = SimpleNamespace(tenant_id=tenant_id, database_ref="shared", connection_secret_ref=SHARED_CONTROL_DATA_PLANE)
    with worker.plane_session(plane) as db:
        assert scope_of(db)["tenant_id"] == str(tenant_id) and not scope_of(db)["system_reason"]


@pytest.fixture
def two_queued_jobs():
    with SessionLocal() as db:
        bind_system(db, "test: report jobs of two tenants")
        tenants = [row[0] for row in db.execute(text("select id from tenants order by created_at limit 2"))]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        jobs = [
            ReportJob(
                id=uuid.uuid4(),
                tenant_id=tenant,
                actor_id="test",
                report_code="TEST",
                output_format="PDF",
                context={},
                hidden_fields=[],
                status="QUEUED",
                created_at=now,
                updated_at=now,
            )
            for tenant in tenants
        ]
        db.add_all(jobs)
        db.commit()
        ids = {job.tenant_id: job.id for job in jobs}
    yield ids
    with SessionLocal() as db:
        bind_system(db, "test cleanup")
        db.query(ReportJob).filter(ReportJob.id.in_(list(ids.values()))).delete(synchronize_session=False)
        db.commit()


@pytest.mark.db
def test_report_jobs_on_the_shared_database_are_taken_for_one_tenant_only(monkeypatch, two_queued_jobs):
    handled = []
    monkeypatch.setattr(
        report_service, "run_report_job", lambda job_id, db: handled.append(job_id) or {"status": "READY"}
    )
    (first, first_job), (second, second_job) = two_queued_jobs.items()
    with SessionLocal() as db:
        bind_system(db, "test: shared database worker")
        report_service.run_pending_report_jobs(db, limit=50, tenant_id=first)
    assert str(first_job) in handled and str(second_job) not in handled
