"""Every scheduled job keeps each organization's work in that organization (RSK-026).

The scheduler runs every job in system scope (backend/app/scheduler.py ``_run_locked``), so row-level security does
not separate organizations there: each job must take the organization from the row it works on, or open a session
bound to it. For every job the scheduler registers, a test below gives two organizations data the job acts on (or
data it must leave alone) and proves that the rows, e-mails and outbox events written land only in the organization
the source row belongs to. ``test_every_registered_job_has_a_scope_test`` fails when a job is added without one.

Jobs that only flush run in a session that is rolled back; jobs that commit run only for the two organizations of the
test (``_serve_only`` limits the deployment's organizations as a cell does, or the job's own selector is narrowed),
so other tests' organizations in the shared test database are never touched.
"""

from __future__ import annotations

import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from backend.app import scheduler
from backend.app.db.models.foundation import AuditEvent, AuthUser, Product, Tenant
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from tests.test_free_trial import _clean_trial_workspaces  # noqa: F401  (module fixture: trial business rows)

pytestmark = pytest.mark.db

NOW = lambda: datetime.now(timezone.utc)  # noqa: E731

# Every job in scheduler.JOBS and the test that proves its organization scope.
SCOPE_TESTS = {
    "platform-sync": "test_platform_sync_reports_only_the_cells_own_organization",
    "tenant-lifecycle": "test_tenant_lifecycle_applies_and_tells_only_the_organization_the_schedule_belongs_to",
    "subscription-lifecycle": "test_subscription_lifecycle_reminds_and_expires_each_organization_on_its_own_row",
    "trial-reminders": "test_trial_reminders_are_queued_for_the_trial_each_subscription_belongs_to",
    "trial-retention": "test_trial_retention_deletes_only_the_trial_whose_period_ended",
    "trial-sample-clock": "test_trial_sample_clock_moves_only_the_trial_whose_day_has_turned",
    "embedding-catch-up": "test_embedding_catch_up_embeds_each_organizations_evidence_in_that_organization",
    "support-access-expiry": "test_support_access_expiry_ends_and_tells_each_organization_about_its_own_grant",
    "operations-alerts": "test_operations_alerts_write_nothing_into_any_organization",
    "export-expiry": "test_export_expiry_deletes_only_the_expired_export_under_its_own_organization",
    "connector-sync": "test_connector_sync_files_each_providers_records_and_failures_in_their_own_organization",
    "purge-completion": "test_purge_completion_finishes_only_the_organization_left_purging",
    "signal_detection": "test_signal_detection_groups_only_the_organizations_own_complaints",
    "late_evidence_sweep": "test_late_evidence_sweep_asks_the_owner_in_the_cases_own_organization",
    "reporting_reminders": "test_reporting_reminders_are_raised_in_the_complaints_own_organization",
    "due-alerts": "test_due_alerts_go_only_to_people_of_the_items_organization",
    "signature-settlement": "test_signature_settlement_reads_each_receipt_only_in_the_signatures_organization",
    "readiness-digest": "test_readiness_digest_is_queued_and_sent_per_organization_to_its_own_leads",
    "audit-chain-verification": "test_audit_chain_verification_names_only_the_organization_whose_trail_broke",
}


def test_every_registered_job_has_a_scope_test():
    assert set(SCOPE_TESTS) == {job.name for job in scheduler.JOBS}
    module = sys.modules[__name__]
    assert all(callable(getattr(module, name, None)) for name in SCOPE_TESTS.values())


# ------------------------------------------------------------------------------------------- helpers


def _org(label: str) -> uuid.UUID:
    from backend.app.customer_lifecycle import build_customer_tenant

    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db,
            tenant_key=f"{label}_{uuid.uuid4().hex[:8].upper()}",
            name=f"Scope {label}",
            status="ACTIVE",
            now=NOW(),
        )
        db.add(customer)
        db.add(tenant)
        db.commit()  # registers the organization on the shared plane (migration md20)
        return tenant.id


@pytest.fixture
def pair():
    """Two fresh customer organizations, removed afterwards."""
    from backend.app.trial.retention import purge_trial

    first, second = _org("SCOPE_A"), _org("SCOPE_B")
    yield first, second
    for tenant_id in (first, second):
        with SessionLocal() as db:
            try:
                purge_trial(db, tenant_id, "test:scheduled-job-scope-cleanup")
            except Exception:
                db.rollback()


def _person(tenant_id, role: str) -> str:
    """An active person of ``tenant_id`` with ``role``; returns the account id."""
    from tests.test_signals_triage import _client

    return _client(tenant_id, role)[1]


@contextmanager
def _system(rollback: bool = True):
    """A session in system scope, as _run_locked opens it; rolled back at the end unless the job commits."""
    db = SessionLocal()
    bind_system(db, "test: scheduled job scope")
    try:
        yield db
    finally:
        if rollback:
            db.rollback()
        db.close()


def _job(name: str):
    return next(job for job in scheduler.JOBS if job.name == name)


def _serve_only(monkeypatch, *tenant_ids) -> None:
    """Limit the deployment to ``tenant_ids`` (as a cell is limited to its own), wherever the clause was imported."""
    from backend.app import deployment_role

    original = deployment_role.served_tenants_clause
    ids = [uuid.UUID(str(item)) for item in tenant_ids]
    for module in list(sys.modules.values()):
        if getattr(module, "served_tenants_clause", None) is original:
            monkeypatch.setattr(module, "served_tenants_clause", lambda column: column.in_(ids))


@pytest.fixture
def mail(monkeypatch):
    """Capture every e-mail a notification handler would send: ``send(event)`` delivers one queued event and
    returns its recipients."""
    from backend.app import notifications

    captured: list[str] = []
    monkeypatch.setattr(notifications, "_deliver", lambda send, recipients, **details: captured.extend(recipients))

    def send(db, event) -> set[str]:
        captured.clear()
        notifications.handle_event(db, event.event_name, event.payload)
        return set(captured)

    return send


def _usernames(db, tenant_id) -> set[str]:
    return {name for (name,) in db.query(AuthUser.username).filter(AuthUser.tenant_id == tenant_id)}


def _statuses(db, tenant_id) -> dict:
    return {
        user.id: (user.username, user.status) for user in db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id)
    }


def _user_ids(db, tenant_id) -> set[str]:
    return {str(user_id) for (user_id,) in db.query(AuthUser.id).filter(AuthUser.tenant_id == tenant_id)}


def _assert_event_scoped(event: OutboxEvent, owner) -> None:
    """The event belongs to ``owner``, and a payload naming an organization names the same one."""
    assert event.tenant_id == owner, (event.event_name, event.tenant_id, owner)
    named = (event.payload or {}).get("tenant_id")
    assert named in (None, str(owner)), (event.event_name, named, owner)


def _alerts(monkeypatch) -> list:
    sent: list = []
    monkeypatch.setattr(scheduler, "send_alert", lambda subject, body: sent.append((subject, body)))
    monkeypatch.setattr("backend.app.alerts.send_alert", lambda subject, body: sent.append((subject, body)) or {})
    return sent


def _plan_id(db, *, trial: bool):
    """The Free Trial plan, or a paid one; made in the (rolled-back) session when the database has none."""
    from backend.app.db.models.foundation import PlanDefinition
    from backend.app.trial.service import FREE_TRIAL_PLAN, _free_trial_plan

    if trial:
        return _free_trial_plan(db, NOW()).id
    found = db.query(PlanDefinition.id).filter(PlanDefinition.code != FREE_TRIAL_PLAN).first()
    if found:
        return found[0]
    plan = PlanDefinition(
        id=uuid.uuid4(),
        code=f"SCOPE_{uuid.uuid4().hex[:6].upper()}",
        name="Scope test plan",
        description="Scope test plan",
        version="v1",
        status="ACTIVE",
        effective_from=NOW(),
        created_at=NOW(),
        updated_at=NOW(),
    )
    db.add(plan)
    db.flush()
    return plan.id


def _subscription(db, tenant_id, *, trial: bool, expires_at: datetime):
    """The organization's subscription (made when it has none), ending at ``expires_at``."""
    from backend.app.db.models.stage2 import SubscriptionLifecycle

    plan_id = _plan_id(db, trial=trial)
    row = db.query(SubscriptionLifecycle).filter(SubscriptionLifecycle.tenant_id == tenant_id).first()
    if row is None:
        row = SubscriptionLifecycle(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            plan_id=plan_id,
            plan_version="1",
            starts_at=NOW() - timedelta(days=300),
            created_at=NOW(),
        )
        db.add(row)
    row.plan_id = plan_id
    row.expires_at, row.grace_ends_at, row.status, row.updated_at = expires_at, None, "ACTIVE", NOW()
    db.flush()
    return row


def _events(db, **filters) -> list[OutboxEvent]:
    query = db.query(OutboxEvent)
    for key, value in filters.items():
        column = getattr(OutboxEvent, key)
        query = query.filter(column.in_(value) if isinstance(value, (list, set, tuple)) else column == value)
    return query.all()


def _product(tenant_id, name: str = "Scope Pump") -> uuid.UUID:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_identifier=f"SC-{uuid.uuid4().hex[:8].upper()}",
            name=name,
            created_at=NOW(),
            updated_at=NOW(),
        )
        db.add(row)
        db.commit()
        return row.id


# ------------------------------------------------------------------------------------------- platform jobs


def test_tenant_lifecycle_applies_and_tells_only_the_organization_the_schedule_belongs_to(pair, mail):
    from backend.app.db.models.customer_lifecycle import TenantAccessTransition

    first, second = pair
    _person(first, "CUSTOMER_ADMIN")
    _person(second, "CUSTOMER_ADMIN")
    with _system() as db:
        rows = {}
        for tenant_id, effective in ((first, NOW() - timedelta(minutes=1)), (second, NOW() + timedelta(days=1))):
            rows[tenant_id] = TenantAccessTransition(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                transition_type="SCHEDULED",
                suspension_type="SUSPENSION",
                from_status="ACTIVE",
                to_status="SUSPENDED",
                reason="Scope test",
                remarks="Scope test",
                effective_at=effective,
                notify_customer_admin=True,
                performed_by=uuid.uuid4(),
                created_at=NOW(),
            )
            db.add(rows[tenant_id])
        db.flush()
        _job("tenant-lifecycle").run(db, {})
        db.flush()

        assert db.get(Tenant, first).status == "SUSPENDED" and db.get(Tenant, second).status == "ACTIVE"
        assert rows[second].transition_type == "SCHEDULED"
        (event,) = _events(db, aggregate_id=[row.id for row in rows.values()])
        assert event.aggregate_id == rows[first].id
        _assert_event_scoped(event, first)
        audits = db.query(AuditEvent).filter(AuditEvent.action == "SCHEDULED_TENANT_LIFECYCLE_APPLIED")
        assert {row.tenant_id for row in audits.filter(AuditEvent.tenant_id.in_(pair))} == {first}
        recipients = mail(db, event)
        assert recipients and recipients <= _usernames(db, first)


def test_subscription_lifecycle_reminds_and_expires_each_organization_on_its_own_row(pair, mail):
    first, second = pair
    _person(first, "CUSTOMER_ADMIN")
    _person(second, "CUSTOMER_ADMIN")
    with _system() as db:
        reminded = _subscription(db, first, trial=False, expires_at=NOW() + timedelta(days=5))
        expired = _subscription(db, second, trial=False, expires_at=NOW() - timedelta(minutes=1))
        _job("subscription-lifecycle").run(db, {})
        db.flush()

        owners = {reminded.id: first, expired.id: second}
        events = _events(db, aggregate_id=list(owners))
        assert any(event.aggregate_id == reminded.id for event in events)
        for event in events:
            _assert_event_scoped(event, owners[event.aggregate_id])
            recipients = mail(db, event)
            assert recipients and recipients <= _usernames(db, owners[event.aggregate_id])
        assert reminded.status == "ACTIVE" and db.get(Tenant, first).status == "ACTIVE"
        assert expired.status != "ACTIVE"
        changed = db.query(AuditEvent).filter(
            AuditEvent.action == "SUBSCRIPTION_STATUS_CHANGED", AuditEvent.entity_id.in_(list(owners))
        )
        assert {(row.tenant_id, row.entity_id) for row in changed} == {(second, expired.id)}


def test_trial_reminders_are_queued_for_the_trial_each_subscription_belongs_to(pair):
    first, second = pair
    with _system() as db:
        week = _subscription(db, first, trial=True, expires_at=NOW() + timedelta(days=5))
        day = _subscription(db, second, trial=True, expires_at=NOW() + timedelta(hours=12))
        _job("trial-reminders").run(db, {})
        db.flush()

        owners = {week.id: first, day.id: second}
        events = _events(db, event_name="TRIAL_REMINDER", aggregate_id=list(owners))
        assert {event.aggregate_id for event in events} == set(owners)
        for event in events:
            _assert_event_scoped(event, owners[event.aggregate_id])
            assert event.payload["subscription_id"] == str(event.aggregate_id)
        stages = {owners[event.aggregate_id]: event.payload["stage"] for event in events}
        assert stages == {first: "7_DAY", second: "1_DAY"}


def test_trial_sample_clock_moves_only_the_trial_whose_day_has_turned(trials, monkeypatch):
    from backend.app.db.models.stage2 import OnboardingRequest
    from backend.app.trial import sample_clock

    first, second = trials
    real = sample_clock.keep_current
    seen = []

    def ours_only(control, data, tenant_id, now=None):
        if tenant_id not in trials:
            return {"moved": False, "why": "CURRENT"}
        seen.append(tenant_id)
        return real(control, data, tenant_id, now)

    monkeypatch.setattr(sample_clock, "keep_current", ours_only)
    with _system(rollback=False) as control:
        request = control.query(OnboardingRequest).filter(OnboardingRequest.tenant_id == first).one()
        anchor = datetime.fromisoformat(request.profile[sample_clock.ANCHOR])
        request.profile = {**request.profile, sample_clock.ANCHOR: (anchor - timedelta(days=3)).isoformat()}
        control.commit()
    before = {tenant_id: _sample_times(tenant_id) for tenant_id in trials}
    anchors = {tenant_id: _anchor(tenant_id) for tenant_id in trials}

    with _system(rollback=False) as db:
        result = _job("trial-sample-clock").run(db, {})
        db.commit()

    assert set(seen) == set(trials) and result["moved"] >= 1
    assert _sample_times(second) == before[second] and _anchor(second) == anchors[second]
    moved = _sample_times(first)
    # Whole days of wall time on the trial's own calendar (so a summer-time change shows as an hour in UTC): at least
    # the three days its anchor was moved back.
    days = {round((moved[key] - before[first][key]) / timedelta(days=1)) for key in moved}
    assert len(days) == 1 and days.pop() in (3, 4)


def test_trial_retention_deletes_only_the_trial_whose_period_ended(trials, monkeypatch):
    from backend.app.trial import retention
    from tests.test_trial_p2_journey import _audited, _complaints, _end_trial

    first, second = trials
    _alerts(monkeypatch)
    _end_trial(first, 31)
    kept = {"complaints": _complaints(second), "audit": _audited(second, "TRIAL_APPROVED")}
    with _system() as db:
        kept["users"] = _statuses(db, second)
    real = retention.trials_due
    monkeypatch.setattr(
        retention, "trials_due", lambda db, now=None: [t for t in real(db, now) if t["tenant_id"] in map(str, trials)]
    )
    with _system(rollback=False) as db:
        result = _job("trial-retention").run(db, {})
        db.commit()

    assert result["purged"] == 1
    with _system() as db:
        assert db.get(Tenant, first).status == "ARCHIVED" and db.get(Tenant, second).status == "ACTIVE"
        assert _statuses(db, second) == kept["users"]
    assert _complaints(first) == 0 and _complaints(second) == kept["complaints"] > 0
    assert _audited(second, "TRIAL_APPROVED") == kept["audit"]


@pytest.fixture(scope="module")
def trials():
    """Two real trial workspaces with their sample story (the trial jobs need the trial plane and sample data)."""
    from tests.test_free_trial import _approved_trial_client
    from tests.test_trial_p2_journey import _purge

    made = tuple(uuid.UUID(_approved_trial_client()[1]["tenant_id"]) for _ in range(2))
    yield made
    _purge(*made)


def _sample_times(tenant_id) -> dict:
    from backend.app.db.models.market_assessment import ComplaintMarketAssessment

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        rows = db.query(ComplaintMarketAssessment).filter(
            ComplaintMarketAssessment.tenant_id == tenant_id,
            ComplaintMarketAssessment.source_system == "MDARIX_SAMPLE",
            ComplaintMarketAssessment.signed_at.isnot(None),
        )
        return {row.id: row.signed_at for row in rows}


def _anchor(tenant_id) -> str:
    from backend.app.db.models.stage2 import OnboardingRequest
    from backend.app.trial import sample_clock

    with _system() as db:
        request = db.query(OnboardingRequest).filter(OnboardingRequest.tenant_id == tenant_id).one()
        return request.profile[sample_clock.ANCHOR]


def test_support_access_expiry_ends_and_tells_each_organization_about_its_own_grant(pair, mail):
    from backend.app.db.models.customer_lifecycle import SupportAccessGrant
    from tests.support_grants import grant_support_access

    first, second = pair
    for tenant_id in pair:
        _person(tenant_id, "CUSTOMER_ADMIN")
    grants = {grant_support_access(tenant_id): tenant_id for tenant_id in pair}
    running = grant_support_access(second)
    with _system() as db:
        for grant_id in grants:
            db.get(SupportAccessGrant, grant_id).expires_at = NOW() - timedelta(seconds=1)
        db.flush()
        _job("support-access-expiry").run(db, {})
        db.flush()

        assert {db.get(SupportAccessGrant, grant_id).status for grant_id in grants} == {"EXPIRED"}
        assert db.get(SupportAccessGrant, running).status != "EXPIRED"
        events = [
            event
            for event in _events(db, event_name="SUPPORT_ACCESS_ENDED", tenant_id=list(pair))
            if event.payload.get("grant_id") in {str(grant_id) for grant_id in [*grants, running]}
        ]
        assert {uuid.UUID(event.payload["grant_id"]) for event in events} == set(grants)
        for event in events:
            owner = grants[uuid.UUID(event.payload["grant_id"])]
            _assert_event_scoped(event, owner)
            if event.payload.get("recipient_user_id"):
                assert event.payload["recipient_user_id"] in _user_ids(db, owner)
            recipients = mail(db, event)
            assert recipients and recipients <= _usernames(db, owner)
        audits = db.query(AuditEvent).filter(
            AuditEvent.action == "SUPPORT_ACCESS_EXPIRED", AuditEvent.entity_id.in_(list(grants))
        )
        assert {(row.tenant_id, row.entity_id) for row in audits} == {(owner, grant) for grant, owner in grants.items()}


def test_operations_alerts_write_nothing_into_any_organization(pair, monkeypatch):
    """A platform-level job: it counts the queue and watches the worker, and its alerts name no organization."""
    first, second = pair
    alerts = _alerts(monkeypatch)
    with _system() as db:
        outbox_before = db.query(OutboxEvent).count()
        audit_before = db.query(AuditEvent).count()
        _job("operations-alerts").run(db, {})
        db.flush()
        assert db.query(OutboxEvent).count() == outbox_before and db.query(AuditEvent).count() == audit_before
    assert not any(str(tenant_id) in subject + body for subject, body in alerts for tenant_id in pair)


def test_platform_sync_reports_only_the_cells_own_organization(pair, monkeypatch):
    """A cell serves one organization per process; even with another organization's rows in the same database, the
    heartbeat counts and packages are the cell's own (backend/app/cell_link.py)."""
    from backend.app import cell_link

    first, second = pair
    _product(first)
    for _ in range(3):
        _product(second)
    _person(second, "INVESTIGATOR")
    with _system(rollback=False) as db:
        key = db.get(Tenant, first).tenant_key
    monkeypatch.setenv("MDARIX_CELL_TENANT_ID", str(first))
    monkeypatch.setenv("MDARIX_CELL_TENANT_KEY", key)
    monkeypatch.setattr(cell_link, "identity", lambda: {"cell_id": "scope-test"})
    sent = []

    def call(method, path, body=None, who=None):
        sent.append((method, path, body))
        return 200, {"packages": []} if method == "GET" else {}

    monkeypatch.setattr(cell_link, "_call", call)
    with _system() as db:
        _job("platform-sync").run(db, {})
    (heartbeat,) = [body for method, path, body in sent if path == "/api/v1/cells/heartbeat"]
    assert heartbeat["counts"]["products"] == 1 and heartbeat["counts"]["users_active"] == 0
    assert str(second) not in str(heartbeat)


# ------------------------------------------------------------------------------------------- cell jobs


def test_export_expiry_deletes_only_the_expired_export_under_its_own_organization(pair, monkeypatch, tmp_path):
    from backend.app.db.models.stage2 import TenantExport
    from object_storage.service import ObjectStorageService
    from tests.test_tenant_data import use_local_storage

    use_local_storage(monkeypatch, tmp_path)
    first, second = pair
    storage = ObjectStorageService()
    # The same file name in both organizations: only the expired one's own copy may go.
    keys = {
        tenant_id: storage.put(str(tenant_id), "exports/scope.zip", b"export", internal=True)["object_key"]
        for tenant_id in pair
    }
    with _system() as db:
        rows = {}
        for tenant_id, expires in ((first, NOW() - timedelta(minutes=1)), (second, NOW() + timedelta(days=3))):
            rows[tenant_id] = TenantExport(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                requested_by="scope-test",
                reason="Scope test",
                status="READY",
                object_key=keys[tenant_id],
                created_at=NOW() - timedelta(days=7),
                completed_at=NOW() - timedelta(days=7),
                expires_at=expires,
            )
            db.add(rows[tenant_id])
        db.flush()
        _job("export-expiry").run(db, {})
        db.flush()
        assert rows[first].status == "EXPIRED" and rows[first].object_key is None
        assert rows[second].status == "READY" and rows[second].object_key == keys[second]
    assert storage.list_tenant_objects(str(first)) == []
    assert storage.list_tenant_objects(str(second)) == [keys[second]]


def test_connector_sync_files_each_providers_records_and_failures_in_their_own_organization(pair, monkeypatch, mail):
    import backend.app.access.connector_sync as sync
    from backend.app.db.models.enterprise import ConnectorRun
    from backend.app.db.models.foundation import ConnectorConfiguration
    from tests.test_connector_sync import BASE, _error, _Reply

    first, second = pair
    for tenant_id in pair:
        _person(tenant_id, "CUSTOMER_ADMIN")
    tenant_keys = {first: f"KA{uuid.uuid4().hex[:6]}", second: f"KB{uuid.uuid4().hex[:6]}"}
    pages = {
        f"{BASE}?tenant={tenant_keys[first]}": {"tenant_key": tenant_keys[first], "records": [{"id": "a-1"}]},
        f"{BASE}?tenant={tenant_keys[second]}": [_error(500), _error(500), _error(500)],
    }

    def urlopen(request, timeout=None):
        reply = pages.get(request.full_url, {"records": []})  # any other scheduled connection reads nothing
        if isinstance(reply, list):
            reply = reply.pop(0) if reply else {"records": []}
        if isinstance(reply, Exception):
            raise reply
        return _Reply(reply)

    monkeypatch.setattr(sync, "safe_urlopen", urlopen)
    monkeypatch.setattr(sync, "_safe_provider_url", lambda endpoint, path, timeout=10: BASE)
    monkeypatch.setattr(sync, "_connector_credential", lambda configuration, row: None)
    monkeypatch.setattr(sync.time, "sleep", lambda seconds: None)
    code = f"SCOPE-{uuid.uuid4().hex[:6]}"  # the same code in both organizations
    with _system(rollback=False) as db:
        for tenant_id in pair:
            db.add(
                ConnectorConfiguration(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    code=code,
                    connector_type="QMS",
                    configuration={
                        "endpoint": "https://provider.example/api",
                        "sync_every_minutes": 60,
                        "source_object": "Complaint",
                        "tenant_key": tenant_keys[tenant_id],
                    },
                    status="ACTIVE",
                    created_at=NOW(),
                    updated_at=NOW(),
                )
            )
        db.commit()
    try:
        with _system(rollback=False) as db:
            _job("connector-sync").run(db, {})
            db.commit()
        with _system() as db:
            runs = db.query(ConnectorRun).filter(ConnectorRun.connection_id == code).all()
            assert {(run.tenant_id, run.status) for run in runs} == {(first, "COMPLETED"), (second, "FAILED")}
            assert [run.records_received for run in runs if run.tenant_id == first] == [1]
            records = _events(db, event_name="PROVIDER_RECORD_RECEIVED", tenant_id=list(pair))
            assert [(event.tenant_id, event.payload["external_id"]) for event in records] == [(first, "a-1")]
            _assert_event_scoped(records[0], first)
            (failure,) = _events(db, event_name="CONNECTOR_SYNC_FAILED", tenant_id=list(pair))
            _assert_event_scoped(failure, second)
            recipients = mail(db, failure)
            assert recipients and recipients <= _usernames(db, second)
    finally:
        with _system(rollback=False) as db:
            db.query(OutboxEvent).filter(OutboxEvent.tenant_id.in_(list(pair))).delete(synchronize_session=False)
            db.query(ConnectorRun).filter(ConnectorRun.connection_id == code).delete(synchronize_session=False)
            db.query(ConnectorConfiguration).filter(ConnectorConfiguration.code == code).delete(
                synchronize_session=False
            )
            db.commit()


def test_purge_completion_finishes_only_the_organization_left_purging(pair, monkeypatch, tmp_path):
    from backend.app import tenant_purge
    from object_storage.service import ObjectStorageService
    from tests.test_tenant_data import WAIVED, BrokenStorage, _set_status, use_local_storage

    use_local_storage(monkeypatch, tmp_path)
    _alerts(monkeypatch)
    first, second = pair
    storage = ObjectStorageService()
    for tenant_id in pair:
        _product(tenant_id)
        storage.put(str(tenant_id), "evidence/report.txt", b"stored evidence", internal=True)
    _set_status(first, "SUSPENDED")
    with SessionLocal() as db:
        left = tenant_purge.purge_tenant(
            db, first, "test", reason="Scope test: file store down", storage=BrokenStorage(), evidence=WAIVED
        )
    assert left["status"] == "PURGING"
    with _system() as db:
        audit_before = db.query(AuditEvent).filter(AuditEvent.tenant_id == second).count()
    real = tenant_purge.tenants_purging
    monkeypatch.setattr(tenant_purge, "tenants_purging", lambda db: [t for t in real(db) if t.id in pair])
    with _system(rollback=False) as db:
        _job("purge-completion").run(db, {})
        db.commit()

    with _system() as db:
        assert db.get(Tenant, first).status == "ARCHIVED" and db.get(Tenant, second).status == "ACTIVE"
        assert db.query(Product).filter(Product.tenant_id == second).count() == 1
        assert db.query(AuditEvent).filter(AuditEvent.tenant_id == second).count() == audit_before
    assert storage.list_tenant_objects(str(first)) == []
    assert len(storage.list_tenant_objects(str(second))) == 1


def test_embedding_catch_up_embeds_each_organizations_evidence_in_that_organization(pair, monkeypatch):
    from backend.app.db.models.evidence_intelligence import EvidenceChunk
    from backend.app.db.models.foundation import Evidence
    from backend.app.db.models.retrieval_intelligence import EvidenceChunkEmbedding
    from evidence.extractors.chunker import EvidenceChunker

    _serve_only(monkeypatch, *pair)
    chunks = {}
    for tenant_id, words in zip(pair, ("Pump occlusion alarm validation", "Catheter kink bench test")):
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            evidence = Evidence(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                evidence_identifier=f"SCOPE-EV-{uuid.uuid4().hex[:8]}",
                evidence_type="VALIDATION_REPORT",
                title=words,
                source_system="QMS",
                reliability_status="validated",
                fact_type="source_fact",
                content=f"{words}. " * 20,
                effective_timestamp=NOW(),
                ingestion_timestamp=NOW(),
                created_at=NOW(),
                updated_at=NOW(),
            )
            db.add(evidence)
            db.commit()
            EvidenceChunker(target_chunk_size=240).create_chunks_for_evidence(
                db, tenant_id, evidence.id, evidence.content, {}
            )
            db.commit()
            chunks[tenant_id] = {
                row.id for row in db.query(EvidenceChunk).filter(EvidenceChunk.evidence_id == evidence.id)
            }
    with _system(rollback=False) as db:
        result = _job("embedding-catch-up").run(db, {})
        db.commit()

    assert result["indexed"] >= sum(len(ids) for ids in chunks.values())
    with _system() as db:
        rows = db.query(EvidenceChunkEmbedding).filter(EvidenceChunkEmbedding.tenant_id.in_(list(pair))).all()
        for tenant_id in pair:
            assert {row.chunk_id for row in rows if row.tenant_id == tenant_id} == chunks[tenant_id]


def test_signal_detection_groups_only_the_organizations_own_complaints(pair, monkeypatch):
    from backend.app.db.models.signals import Signal, SignalComplaint
    from backend.app.db.models.workflow import WorkflowTask
    from tests.test_signals_triage import _seed

    _serve_only(monkeypatch, *pair)
    seeds = {tenant_id: _seed(tenant_id, complaints=3, problem="OCCLUSION") for tenant_id in pair}
    with _system(rollback=False) as db:
        _job("signal_detection").run(db, {})
        db.commit()

    with _system() as db:
        for tenant_id in pair:
            (signal,) = db.query(Signal).filter(Signal.tenant_id == tenant_id).all()
            members = db.query(SignalComplaint).filter(SignalComplaint.signal_id == signal.id).all()
            assert {str(row.complaint_id) for row in members} == set(seeds[tenant_id]["complaint_ids"])
            assert {row.tenant_id for row in members} == {tenant_id}
            tasks = db.query(WorkflowTask).filter(WorkflowTask.source_entity_id == signal.id).all()
            assert tasks and {task.tenant_id for task in tasks} == {tenant_id}


def test_late_evidence_sweep_asks_the_owner_in_the_cases_own_organization(pair, monkeypatch):
    from backend.app.db.models.workflow import WorkflowTask
    from tests.test_decision_followups import _assessments, _client, _decide, _evidence, _open, _seed

    _serve_only(monkeypatch, *pair)
    cases = {}
    for tenant_id in pair:
        client, owner = _client(tenant_id, "INVESTIGATOR", "Scope")
        case = _open(client, _seed(tenant_id))
        _decide(tenant_id, case["id"], state="CLOSED", decided_at=NOW() - timedelta(hours=2))
        cases[tenant_id] = (case["id"], _evidence(tenant_id, case_id=case["id"], ingested_at=NOW()), owner)
    with _system(rollback=False) as db:
        _job("late_evidence_sweep").run(db, {})
        db.commit()

    with _system() as db:
        for tenant_id, (case_id, late, owner) in cases.items():
            (row,) = _assessments(tenant_id, case_id)
            assert row.tenant_id == tenant_id and str(row.evidence_id) == late
            task = db.get(WorkflowTask, row.task_id)
            assert task.tenant_id == tenant_id and str(task.assigned_user_id) == owner
            assert owner in _user_ids(db, tenant_id)


def test_reporting_reminders_are_raised_in_the_complaints_own_organization(pair, monkeypatch):
    from backend.app.db.models.workflow import WorkflowTask
    from tests.test_reporting_capa_api import REASON, SETTINGS, _client, _complaint, _product

    _serve_only(monkeypatch, *pair)
    urgent = {}
    for tenant_id in pair:
        reviewer = _client(tenant_id, "REGULATORY_REVIEWER")
        settings = reviewer.get(SETTINGS)
        assert settings.status_code == 200, settings.text
        chosen = settings.json()["templates"][:2]
        saved = reviewer.put(SETTINGS, json={"windows": chosen, "lookback_days": 365, "reason": REASON})
        assert saved.status_code == 200, saved.text
        product = str(_product(tenant_id))
        urgent[tenant_id] = _complaint(tenant_id, product, aware_days_ago=29, country="US", death=True)
    with _system(rollback=False) as db:
        _job("reporting_reminders").run(db, {})
        db.commit()

    with _system() as db:
        tasks = (
            db.query(WorkflowTask)
            .filter(
                WorkflowTask.task_type == "REPORTABILITY_DECISION",
                WorkflowTask.source_entity_id.in_([uuid.UUID(item) for item in urgent.values()]),
            )
            .all()
        )
        assert {(task.tenant_id, str(task.source_entity_id)) for task in tasks} == {
            (tenant_id, complaint) for tenant_id, complaint in urgent.items()
        }


def test_due_alerts_go_only_to_people_of_the_items_organization(pair, monkeypatch):
    from backend.app.db.models.oversight import DueAlert
    from backend.app.workflow import tasks as task_service

    _serve_only(monkeypatch, *pair)
    items = {}
    for tenant_id in pair:
        owner = _person(tenant_id, "INVESTIGATOR")
        _person(tenant_id, "LEADER")
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            task = task_service.create_task(
                db,
                tenant_id,
                task_type="FOLLOW_UP",
                title="Scope test: overdue follow-up",
                source_type="ScopeTest",
                source_id=uuid.uuid4(),
                assigned_user_id=uuid.UUID(owner),
                due_at=NOW() - timedelta(days=2),
                created_by="test",
            )
            db.commit()
            items[tenant_id] = f"task:{task.id}"
    with _system(rollback=False) as db:
        _job("due-alerts").run(db, {})
        db.commit()

    with _system() as db:
        for tenant_id, key in items.items():
            alerts = db.query(DueAlert).filter(DueAlert.item_key.in_(list(items.values()))).all()
            mine = [alert for alert in alerts if alert.item_key == key]
            assert mine and {alert.tenant_id for alert in mine} == {tenant_id}
            assert {alert.recipient_id for alert in mine} <= _user_ids(db, tenant_id)


def test_signature_settlement_reads_each_receipt_only_in_the_signatures_organization(pair, monkeypatch):
    """A's signature has its receipt in A's data; B's has none, but a receipt naming B's signature sits in A's data.
    B's signature must not be completed from A's receipt: it is abandoned, in B."""
    from backend.app import signing_commit
    from backend.app.db.models.foundation import SignedApprovalRecord

    _alerts(monkeypatch)
    first, second = pair
    signatures = {}
    with _system(rollback=False) as db:
        for tenant_id in pair:
            row = SignedApprovalRecord(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                object_type="ScopeTest",
                object_id=uuid.uuid4(),
                object_version="1",
                decision_type="SCOPE_TEST",
                decision="APPROVE",
                remarks="Scope test",
                signer_user_id="scope-signer",
                signer_role="Approver",
                signature_meaning="Scope test",
                content_fingerprint="f" * 64,
                signature_hash="a" * 64,
                status=signing_commit.PENDING,
                signed_at=NOW() - timedelta(minutes=5),
                created_at=NOW() - timedelta(minutes=5),
            )
            db.add(row)
            signatures[tenant_id] = row.id
        db.commit()
    for signature_id in signatures.values():  # both receipts in A's data
        with SessionLocal() as data:
            bind_tenant(data, first)
            data.add(
                AuditEvent(
                    id=uuid.uuid4(),
                    tenant_id=first,
                    actor_ref="scope-signer",
                    action=signing_commit.RECEIPT,
                    entity_type="SignedApprovalRecord",
                    entity_id=signature_id,
                    details={
                        "status": "SIGNED",
                        "control_audit": [
                            {
                                "tenant_id": str(first),
                                "actor_ref": "scope-signer",
                                "action": "SCOPE_SIGNATURE_COMPLETED",
                                "entity_type": "ScopeTest",
                                "entity_id": str(signature_id),
                                "created_at": NOW().isoformat(),
                            }
                        ],
                    },
                    created_at=NOW(),
                )
            )
            data.commit()
    with _system(rollback=False) as db:
        _job("signature-settlement").run(db, {})
        db.commit()

    with _system() as db:
        assert db.get(SignedApprovalRecord, signatures[first]).status == "SIGNED"
        assert db.get(SignedApprovalRecord, signatures[second]) is None  # abandoned, not signed
        abandoned = db.query(AuditEvent).filter(AuditEvent.action == signing_commit.ABANDONED).all()
        mine = [row for row in abandoned if (row.details or {}).get("signature_id") == str(signatures[second])]
        assert [row.tenant_id for row in mine] == [second]
        completed = db.query(AuditEvent).filter(AuditEvent.action == "SCOPE_SIGNATURE_COMPLETED").all()
        assert {(row.tenant_id, row.entity_id) for row in completed} == {(first, signatures[first])}


def test_readiness_digest_is_queued_and_sent_per_organization_to_its_own_leads(pair, monkeypatch, mail):
    from backend.app.readiness_home import digest

    _serve_only(monkeypatch, *pair)
    monkeypatch.setattr(digest, "due", lambda now: True)
    leads = {tenant_id: _person(tenant_id, "LEADER") for tenant_id in pair}
    try:
        with _system(rollback=False) as db:
            _job("readiness-digest").run(db, {})
            db.commit()
        with _system() as db:
            events = _events(db, event_name=digest.EVENT, tenant_id=list(pair))
            assert sorted(event.tenant_id for event in events) == sorted(pair)
            for event in events:
                _assert_event_scoped(event, event.tenant_id)
                lead = db.get(AuthUser, uuid.UUID(leads[event.tenant_id]))
                assert mail(db, event) == {lead.username}
    finally:
        with _system(rollback=False) as db:
            db.query(OutboxEvent).filter(OutboxEvent.tenant_id.in_(list(pair))).delete(synchronize_session=False)
            db.commit()


def test_audit_chain_verification_names_only_the_organization_whose_trail_broke(pair, monkeypatch):
    from sqlalchemy import text

    from tests.test_audit_hash_chain import _add

    alerts = _alerts(monkeypatch)
    first, second = pair
    with _system() as db:
        for tenant_id in pair:
            _add(db, tenant_id, "SCOPE_CHAIN")
        state: dict = {}
        scheduler.audit_chain_verification(db, state)
        assert not [item for item in state.get("reported_broken", []) if item.split(":")[0] in map(str, pair)]
        anchor = state["anchors"][str(first)]
        db.execute(text("ALTER TABLE audit_events DISABLE TRIGGER audit_events_immutable"))
        db.execute(
            text("UPDATE audit_events SET event_hash = :fake WHERE tenant_id = :tenant AND chain_seq = :seq"),
            {"fake": "a" * 64, "tenant": first, "seq": anchor["seq"]},
        )
        result = _job("audit-chain-verification").run(db, state)
        broken = {item["tenant_id"] for item in result["broken"]}
        assert str(first) in broken and str(second) not in broken
        assert str(second) in state["anchors"]
    named = " ".join(body for _subject, body in alerts)
    assert str(first) in named and str(second) not in named
