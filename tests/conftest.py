"""Shared test configuration.

- Local runs default to the dedicated ``mdarix_r1_test`` database so the suite
  never writes into the demo database (``mdarix_r1``). CI and any caller that
  exports ``POSTGRES_DB`` explicitly keep their own value. This must run before
  any backend module is imported, because the engine is created at import time.
- Every test is marked ``unit``, ``db`` or ``dataplane`` (see ``pytest.ini``).
- Database tests get the synthetic AcmeCare golden dataset loaded on demand, so
  they no longer depend on alphabetical file order.
- Legacy protected-route modules get an authenticated session cookie.
"""

import os

os.environ.setdefault("POSTGRES_DB", "mdarix_r1_test")
# The application fails safe to production when MDARIX_ENV is unset; the suite exercises development behaviour.
os.environ.setdefault("MDARIX_ENV", "development")
# Tests must not call paid or external services with the developer's .env
# credentials (Groq, Resend). The deterministic provider path is exercised
# instead; individual tests that need provider behaviour set their own env.
# Set MDARIX_TEST_ALLOW_LIVE_PROVIDERS=1 to opt in deliberately.
if os.environ.get("MDARIX_TEST_ALLOW_LIVE_PROVIDERS") != "1":
    os.environ["MDARIX_GENAI_PROVIDER"] = "controlled"
    os.environ["MDARIX_GENAI_API_KEY"] = ""
    os.environ["MDARIX_GENAI_BASE_URL"] = ""
    os.environ["RESEND_API_KEY"] = ""
    # Account emails go through SMTP (auth/emailer.py loads .env itself). Present-but-empty values stop
    # python-dotenv from filling them in, so no test can send a real email. Tests that exercise SMTP patch
    # smtplib and set their own values.
    for _smtp_key in (
        "MDARIX_SMTP_HOST",
        "MDARIX_SMTP_USERNAME",
        "MDARIX_SMTP_PASSWORD",
        "MDARIX_SMTP_FROM",
        "MDARIX_SMTP_VERIFIED_DOMAIN",
        "MDARIX_TRIAL_ALERT_EMAIL",
    ):
        os.environ[_smtp_key] = ""

import uuid  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from backend.app.main import app  # noqa: E402
from auth.service import _hash, auth_service  # noqa: E402
from auth.durable import persist_session  # noqa: E402
from backend.app.db.models.foundation import AuthUser, Investigation, Tenant, TenantMembership  # noqa: E402
from backend.app.db.session import SessionLocal  # noqa: E402

GOLDEN_TENANT_KEY = "ACME_CARE_SYNTHETIC"
GOLDEN_INVESTIGATION = "INV-001"

# Modules that need the control-plane PostgreSQL database.
DB_MODULES = {
    "test_day2_database",
    "test_day4_ingestion",
    "test_day5_normalization",
    "test_day6_reality_graph",
    "test_day7_product360_temporal",
    "test_day8_evidence",
    "test_day9_retrieval",
    "test_day10_investigation_workspace",
    "test_day11_ai_investigator",
    "test_day12_hypothesis_engine",
    "test_day15_decision_center",
    "test_day17_briefs",
    "test_day18_trust_assurance",
    "test_day23_governance_security",
    "test_day26_ask_api",
    "test_day27_authorized_retrieval",
    "test_day28_lifecycle_retrieval",
    "test_mapping_catalog_stage1",
    "test_mapping_studio_stage4",
    "test_master_data",
    "test_mfa_mvp",
    "test_free_trial",
    "test_demo_workspace",
    "test_public_signup_onboarding",
    "test_simulator_ingestion",
    "test_stage2_operations",
}
# Modules that additionally need the four tenant data-plane databases.
DATAPLANE_MODULES = {"test_data_plane_routing"}


def pytest_collection_modifyitems(config, items):
    for item in items:
        module = item.module.__name__.split(".")[-1]
        if module in DATAPLANE_MODULES:
            item.add_marker(pytest.mark.db)
            item.add_marker(pytest.mark.dataplane)
            item.fixturenames.insert(0, "golden_dataset")
        elif module in DB_MODULES:
            item.add_marker(pytest.mark.db)
            item.fixturenames.insert(0, "golden_dataset")
        else:
            item.add_marker(pytest.mark.unit)


@pytest.fixture(scope="session")
def golden_dataset():
    """Ingest and normalize the synthetic golden dataset once, only if it is missing."""
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == GOLDEN_TENANT_KEY).first()
        present = (
            tenant is not None
            and db.query(Investigation)
            .filter(
                Investigation.tenant_id == tenant.id,
                Investigation.investigation_identifier == GOLDEN_INVESTIGATION,
            )
            .first()
            is not None
        )
    finally:
        db.close()
    if not present:
        from ingestion.normalization.service import NormalizationService
        from ingestion.services.ingestion_service import GOLDEN_SOURCE, IngestionService

        IngestionService(GOLDEN_SOURCE).ingest_all()
        NormalizationService().normalize_all()


def access_api_source() -> str:
    """Source text of the access/admin/platform API (backend/app/access/*.py) for static contract tests."""
    from pathlib import Path

    package = Path(__file__).resolve().parents[1] / "backend" / "app" / "access"
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(package.glob("*.py")))


def frontend_app_source() -> str:
    """Source of the authenticated web app (main.tsx, app/ and features/) for static UI contract tests."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "frontend" / "src"
    files = [src / "main.tsx", *sorted((src / "app").rglob("*.ts*")), *sorted((src / "features").rglob("*.tsx"))]
    return "\n".join(path.read_text(encoding="utf-8") for path in files if not path.name.endswith(".test.ts"))


def golden_investigation_id() -> str:
    """Return the id of golden investigation INV-001 in the synthetic tenant."""
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == GOLDEN_TENANT_KEY).one()
        investigation = (
            db.query(Investigation)
            .filter(
                Investigation.tenant_id == tenant.id,
                Investigation.investigation_identifier == GOLDEN_INVESTIGATION,
            )
            .one()
        )
        return str(investigation.id)
    finally:
        db.close()


LEGACY_PROTECTED = {
    "test_day6_reality_graph",
    "test_day7_product360_temporal",
    "test_day8_evidence",
    "test_day9_retrieval",
    "test_day10_investigation_workspace",
    "test_day11_ai_investigator",
    "test_day12_hypothesis_engine",
    "test_day15_decision_center",
    "test_day17_briefs",
    "test_day18_trust_assurance",
}


def authenticated_client(application=app):
    client = TestClient(application)
    db = SessionLocal()
    tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
    user = (
        db.query(AuthUser)
        .filter(AuthUser.tenant_id == tenant.id, AuthUser.username == "legacy-test-auth@synthetic.invalid")
        .first()
    )
    token = auth_service.signin_persisted(
        "legacy-test-auth@synthetic.invalid",
        "LegacyTestPassword123!",
        user_id=user.id,
        display_name=user.display_name,
        tenant_id=user.tenant_id,
        password_hash=user.password_hash,
        role=user.role,
        status=user.status,
        email_verified=user.email_verified,
    )
    persist_session(db, token, user.id, user.tenant_id)
    db.close()
    client.cookies.set("mdarix_session", token)
    return client


@pytest.fixture(autouse=True)
def authenticate_legacy_module(request):
    if request.module.__name__.split(".")[-1] not in LEGACY_PROTECTED:
        yield
        return
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
        email = "legacy-test-auth@synthetic.invalid"
        user = db.query(AuthUser).filter(AuthUser.tenant_id == tenant.id, AuthUser.username == email).first()
        now = datetime.now(timezone.utc)
        if user is None:
            user = AuthUser(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                username=email,
                display_name="Legacy Test Auth",
                company="Test",
                password_hash=_hash("LegacyTestPassword123!"),
                role="Administrator",
                status="ACTIVE",
                email_verified=True,
                created_at=now,
                updated_at=now,
            )
            db.add(user)
            db.flush()
        membership = (
            db.query(TenantMembership)
            .filter(TenantMembership.tenant_id == tenant.id, TenantMembership.user_id == user.id)
            .first()
        )
        if membership is None:
            db.add(
                TenantMembership(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    user_id=user.id,
                    status="ACTIVE",
                    is_default=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        db.commit()
        token = auth_service.signin_persisted(
            email,
            "LegacyTestPassword123!",
            user_id=user.id,
            display_name=user.display_name,
            tenant_id=user.tenant_id,
            password_hash=user.password_hash,
            role=user.role,
            status=user.status,
            email_verified=user.email_verified,
        )
        persist_session(db, token, user.id, user.tenant_id)
        for value in vars(request.module).values():
            if not isinstance(value, type) and hasattr(value, "cookies") and hasattr(value, "get"):
                value.cookies.set("mdarix_session", token)
        yield
    finally:
        db.close()
