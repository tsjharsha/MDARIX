"""Many free trials at once, cheaply, for the Platform Admin trial overview and trial request queue at launch scale.

Each seeded trial has what the overview reads (customer and tenant on the shared data plane, a Free Trial
subscription, its owner and the sample author, its trial request with Getting started answers) and, for some, what it
counts: a hidden complaint decided, an upload of its own, a readiness summary exported, feedback and a demo request.
The full sample dataset is not seeded: the overview's cost is in the queries it runs per trial, and those run whether
or not the sample records are there.

Everything is written in one transaction on one connection (``scale_session``) and rolled back at the end, and the
trials sit on a plan of their own (``SCALE_PLAN``), which the tests make the overview read instead of the Free Trial
plan, so the figures do not depend on the other trials in the test database and nothing is left behind.
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.customer_lifecycle import _tenant
from backend.app.db.models.complaint_review import ComplaintSecondLook
from backend.app.db.data_plane import TRIAL_SHARED_DATA_PLANE
from backend.app.db.models.customer_lifecycle import Customer, TenantDataPlane
from backend.app.db.models.foundation import AuditEvent, AuthUser, Complaint, PlanDefinition, Product
from backend.app.db.models.stage2 import DemoRequest, OnboardingRequest, SubscriptionLifecycle, TrialFeedback
from backend.app.db.session import engine
from backend.app.trial.imports import UPLOAD_SOURCE
from backend.app.trial.sample_data import SAMPLE_SOURCE

SCALE_PLAN = "FREE_TRIAL_SCALE_TEST"


@contextmanager
def scale_session():
    """A session on one connection whose transaction is rolled back at the end (nothing seeded stays)."""
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, autoflush=False, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


class QueryCounter:
    """Counts the SQL statements this process sends (every engine: the request's, the middleware's) and the time."""

    def __init__(self):
        self.statements: list[str] = []

    def _record(self, _conn, _cursor, statement, *_args):
        self.statements.append(statement)

    def __enter__(self):
        event.listen(Engine, "before_cursor_execute", self._record)
        self.started = time.perf_counter()
        return self

    def __exit__(self, *_exc):
        self.elapsed_ms = (time.perf_counter() - self.started) * 1000
        event.remove(Engine, "before_cursor_execute", self._record)

    @property
    def count(self) -> int:
        return len(self.statements)


def scale_plan(session: Session, now: datetime) -> PlanDefinition:
    plan = PlanDefinition(
        id=uuid.uuid4(),
        code=SCALE_PLAN,
        name="Free Trial (scale test)",
        version="v1",
        status="ACTIVE",
        effective_from=now,
        created_at=now,
        updated_at=now,
    )
    session.add(plan)
    session.flush()
    return plan


def seed_trials(session: Session, count: int, tag: str, now: datetime, plan: PlanDefinition | None = None) -> list:
    """``count`` trials named ``<tag> Devices <n>``; returns their tenant ids in seeding order.

    Trial ``n`` varies by ``n % 5``: 0 ended three days ago, 1 ends in three days, the rest run 10 to 29 more days.
    Every third trial decided a hidden complaint, every fourth uploaded its own complaint and product, every fifth
    exported the readiness summary, every sixth gave feedback and every seventh booked a demo.
    """
    plan = plan or scale_plan(session, now)
    tenant_ids = []
    for number in range(count):
        name = f"{tag} Devices {number:04d}"
        customer = Customer(
            id=uuid.uuid4(),
            customer_identifier=f"CSC{uuid.uuid4().hex[:12].upper()}",
            legal_name=name,
            display_name=name,
            customer_type="CUSTOMER",
            country="UNSPECIFIED",
            lifecycle_status="ACTIVE",
            lock_version=1,
            created_at=now,
            updated_at=now,
        )
        tenant = _tenant(
            customer_id=customer.id,
            tenant_identifier=f"TSC{uuid.uuid4().hex[:12].upper()}",
            tenant_key=f"TRIAL_SCALE_{tag}_{number:04d}_{uuid.uuid4().hex[:4]}",
            name=name,
            lifecycle_status="ACTIVE",
            now=now,
            region="UNSPECIFIED",
            residency_region="UNSPECIFIED",
        )
        session.add(customer)
        session.flush()
        session.add(tenant)
        session.flush()
        session.add(
            TenantDataPlane(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                database_ref=f"trial-shared:{tenant.tenant_key}",
                connection_secret_ref=TRIAL_SHARED_DATA_PLANE,
                region="UNSPECIFIED",
                residency_region="UNSPECIFIED",
                schema_version="control-plane",
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            )
        )
        kind = number % 5
        expires = (
            now - timedelta(days=3)
            if kind == 0
            else now + timedelta(days=3)
            if kind == 1
            else now + timedelta(days=10 + number % 20)
        )
        session.add(
            SubscriptionLifecycle(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                plan_id=plan.id,
                plan_version=plan.version,
                starts_at=expires - timedelta(days=30),
                expires_at=expires,
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            )
        )
        email = f"owner-{tag.lower()}-{number:04d}-{uuid.uuid4().hex[:6]}@example.invalid"
        author = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            username=f"sample-author+{tenant.id.hex[:12]}@sample.invalid",
            display_name="Sample author",
            company="MDARIX sample data",
            password_hash="!",
            role="Leader",
            status="DISABLED",
            email_verified=False,
            created_at=now - timedelta(days=31),
            updated_at=now,
        )
        owner = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            username=email,
            display_name=f"Owner {number}",
            company=name,
            password_hash="!",
            role="Leader",
            status="INVITED" if number % 2 else "ACTIVE",
            email_verified=False,
            created_at=now - timedelta(days=30),
            updated_at=now,
        )
        session.add_all([author, owner])
        if number % 8 == 0:
            session.add(
                AuthUser(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    username=f"colleague-{tag.lower()}-{number:04d}-{uuid.uuid4().hex[:6]}@example.invalid",
                    display_name="Colleague",
                    company=name,
                    password_hash="!",
                    role="Leader",
                    status="ACTIVE",
                    email_verified=False,
                    created_at=now - timedelta(days=20),
                    updated_at=now,
                )
            )
        profile = {"citations": ["RISK_FILE"] if number % 2 else []}
        if number % 9 == 4:
            profile["tried_before_sample_removed"] = ["REPORTING_CLOCKS"]
        session.add(
            OnboardingRequest(
                id=uuid.uuid4(),
                email=email,
                display_name=f"Owner {number}",
                organization=name,
                status="APPROVED",
                profile=profile,
                tenant_id=tenant.id,
                created_at=now - timedelta(days=31, minutes=number),
                updated_at=now,
                reviewed_at=now - timedelta(days=30),
            )
        )
        if number % 3 == 0:
            flagged = Complaint(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                complaint_identifier=f"SAMPLE-RV-{number:04d}",
                description="Cancelled, but the customer reported a burn",
                source_system=SAMPLE_SOURCE,
                created_at=now,
                updated_at=now,
            )
            session.add(flagged)
            session.flush()
            session.add(
                ComplaintSecondLook(
                    tenant_id=tenant.id,
                    complaint_id=flagged.id,
                    decision="CONFIRMED",
                    reason="Meets our complaint definition",
                    decided_by=str(owner.id),
                )
            )
        if number % 4 == 0:
            session.add(
                Complaint(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    complaint_identifier=f"OWN-{number:04d}",
                    description="Display flickers at start-up",
                    source_system=UPLOAD_SOURCE,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                Product(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    product_identifier=f"OWN-PUMP-{number:04d}",
                    name="Own pump",
                    source_system=UPLOAD_SOURCE,
                    created_at=now,
                    updated_at=now,
                )
            )
        if number % 5 == 2:
            session.add(
                AuditEvent(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    actor_ref=str(owner.id),
                    action="READINESS_SUMMARY_EXPORTED",
                    entity_type="Tenant",
                    entity_id=tenant.id,
                    details={},
                    created_at=now - timedelta(hours=number % 24),
                )
            )
        if number % 6 == 0:
            session.add(
                TrialFeedback(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    user_id=owner.id,
                    organization_name=name,
                    rating_overall=4,
                    recommend_score=8,
                    consent_text="Private",
                    consent_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
        if number % 7 == 0:
            session.add(
                DemoRequest(
                    id=uuid.uuid4(),
                    display_name=f"Owner {number}",
                    email=email,
                    phone="+10000000000",
                    status="NEW",
                    source="TRIAL",
                    trial_tenant_id=tenant.id,
                    organization=name,
                    created_at=now - timedelta(days=1),
                    updated_at=now,
                )
            )
        tenant_ids.append(tenant.id)
    session.flush()
    return tenant_ids


def seed_requests(session: Session, count: int, tag: str, now: datetime) -> None:
    """``count`` website trial requests waiting for review, the newest first, named ``<tag> Prospect <n>``."""
    for number in range(count):
        session.add(
            OnboardingRequest(
                id=uuid.uuid4(),
                email=f"prospect-{tag.lower()}-{number:04d}-{uuid.uuid4().hex[:6]}@example.invalid",
                display_name=f"Prospect {number}",
                organization=f"{tag} Prospect {number:04d}",
                status="DECLINED" if number % 10 == 9 else "PENDING_REVIEW",
                decision_reason="Not a device company" if number % 10 == 9 else None,
                profile={},
                created_at=now + timedelta(minutes=1, seconds=number),
                updated_at=now,
            )
        )
    session.flush()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def shadow_trial_requests(session: Session) -> None:
    """Hide the test database's other trial requests for this transaction: a temporary ``onboarding_requests`` table
    (searched before ``public``) takes their place until the rollback, so the queue holds only what is seeded here."""
    session.execute(
        text(
            "CREATE TEMP TABLE onboarding_requests (LIKE public.onboarding_requests INCLUDING DEFAULTS) ON COMMIT DROP"
        )
    )
    session.execute(text("ALTER TABLE pg_temp.onboarding_requests ALTER COLUMN business_id DROP NOT NULL"))


@contextmanager
def endpoint_on(session: Session):
    """The API's database dependency yields ``session`` (the seeded, uncommitted data), and the Free Trial plan is
    the scale-test plan, for the duration."""
    from backend.app.db.session import get_db
    from backend.app.main import app
    from backend.app.trial import service

    def _db():
        yield session

    app.dependency_overrides[get_db] = _db
    original = service.FREE_TRIAL_PLAN
    service.FREE_TRIAL_PLAN = SCALE_PLAN
    try:
        yield
    finally:
        service.FREE_TRIAL_PLAN = original
        app.dependency_overrides.pop(get_db, None)


def benchmark(sizes=(25, 100, 300), trials_query: str = "", requests_query: str = "") -> list[dict]:
    """Queries and milliseconds of GET /platform-admin/trials and GET /platform-admin/trial-requests with ``n`` trials
    (and ``n`` waiting requests besides the trials' own), for each ``n``."""
    from tests.conftest import authenticated_client

    client = authenticated_client()
    results = []
    for size in sizes:
        with scale_session() as session:
            now = utc_now()
            shadow_trial_requests(session)
            seed_trials(session, size, "BENCH", now)
            seed_requests(session, size, "BENCH", now)
            with endpoint_on(session):
                client.get(f"/api/v1/platform-admin/trials{trials_query}")  # warm the code paths once
                with QueryCounter() as trials:
                    response = client.get(f"/api/v1/platform-admin/trials{trials_query}")
                assert response.status_code == 200, response.text
                trial_items = len(response.json()["items"])
                client.get(f"/api/v1/platform-admin/trial-requests{requests_query}")
                with QueryCounter() as requests:
                    queue = client.get(f"/api/v1/platform-admin/trial-requests{requests_query}")
                assert queue.status_code == 200, queue.text
                # The Approved tab: every request on the page has a trial workspace to look up.
                with QueryCounter() as approved:
                    approved_queue = client.get("/api/v1/platform-admin/trial-requests?status=APPROVED")
                assert approved_queue.status_code == 200, approved_queue.text
                results.append(
                    {
                        "n": size,
                        "trials_queries": trials.count,
                        "trials_ms": round(trials.elapsed_ms),
                        "trials_items": trial_items,
                        "requests_queries": requests.count,
                        "requests_ms": round(requests.elapsed_ms),
                        "requests_items": len(queue.json()["items"]),
                        "approved_queries": approved.count,
                        "approved_ms": round(approved.elapsed_ms),
                        "approved_items": len(approved_queue.json()["items"]),
                    }
                )
    return results
