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
# Existing retrieval tests pin the word-hash embedding; tests of the local language model choose it explicitly.
os.environ.setdefault("MDARIX_EMBEDDING_PROVIDER", "deterministic")
# Signatures need an authenticator code by default; the MFA tests (test_mfa_mvp) switch it on themselves, so the
# many governance tests can exercise authority and separation of duties without enrolling every test user.
os.environ.setdefault("MDARIX_REQUIRE_MFA_FOR_SIGNATURES", "false")
# Thousands of sign-ins come from the one test client: rate limits are off unless a test switches them on
# (tests/test_auth_hardening.py). Password hashing uses a lower scrypt cost so the suite stays fast; production
# refuses a cost below 2^17.
os.environ.setdefault("MDARIX_RATE_LIMITS_ENABLED", "false")
# Trial requests wait for review in tests unless a test switches automatic approval on (backend/app/trial/auto_approval.py).
os.environ.setdefault("MDARIX_TRIAL_AUTO_APPROVE", "off")
os.environ.setdefault("MDARIX_PASSWORD_SCRYPT_LOG2_N", "14")
# Provider rest periods stay per process in tests (test_ai_controls.py exercises the shared table itself).
os.environ.setdefault("MDARIX_GENAI_SHARED_REST", "false")
# Tests must not call paid or external services with the developer's .env
# credentials (Groq, Resend). The deterministic provider path is exercised
# instead; individual tests that need provider behaviour set their own env.
# Set MDARIX_TEST_ALLOW_LIVE_PROVIDERS=1 to opt in deliberately.
if os.environ.get("MDARIX_TEST_ALLOW_LIVE_PROVIDERS") != "1":
    os.environ["MDARIX_GENAI_PROVIDER"] = "controlled"
    os.environ["MDARIX_GENAI_API_KEY"] = ""
    os.environ["MDARIX_GENAI_BASE_URL"] = ""
    os.environ["MDARIX_GENAI_FALLBACKS"] = ""  # no fallback provider either (their keys may be in .env)
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
from auth.service import _hash  # noqa: E402
from auth.durable import new_session  # noqa: E402
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
    "test_decision_governance_hardening",
    "test_free_trial",
    # The Platform Admin trial overview and request queue with hundreds of trials (statements, pages, filters).
    "test_trial_overview_scale",
    # Getting started › Automatic insights: headline numbers, trend, records and the questions answered in place.
    "test_trial_insights",
    "test_demo_workspace",
    "test_public_signup_onboarding",
    "test_simulator_ingestion",
    "test_stage2_operations",
    # Read the golden investigation directly, so they need it ingested even when they run first (fresh CI database).
    "test_analysis_reuse",
    "test_grounded_ask",
    # Use the shared test account (authenticated_client), which belongs in the golden organization: loading the
    # golden data first stops a fresh database from creating that account in another organization too.
    "test_admin_route_walk",
    "test_ai_controls",
    "test_audit_hash_chain",
    "test_replay_outbox_script",
    "test_approval_authority_roles",
    "test_customer_lifecycle_subscription",
    "test_business_ids",
    "test_connector_sync",
    "test_tenant_data",
    "test_role_canonicalization",
    "test_erasure_reapply",
    "test_legal_hold",
    "test_person_export",
    "test_retention_audit",
    "test_infra_break_glass",
    "test_infra_backup_role",
    "test_activation_link",
    "test_identity_invitation_delivery",
    "test_customer_admin_workspace",
    "test_csv_safe",
    "test_auth_limits",
    "test_auth_session_lifecycle",
    "test_auth_audit_events",
    "test_auth_signup_acknowledgement",
    "test_customer_admin_erasure_hold",
    # product-reports: seed tagged cases in the golden organization (tests/reports_seed.py).
    "test_reports_content",
    "test_investigation_record",
    "test_stage3_story",
    "test_risk_router",
    "test_regulatory_copilot",
    "test_evaluation_router",
    "test_supplier_reply",
    "test_stage3_refusals",
    # bizid-api: API responses carry each record's business identifier (md26).
    "test_business_ids_platform_api",
    "test_business_ids_ops_api",
    "test_business_ids_custadmin_api",
    "test_business_ids_workspace_api",
    "test_business_ids_reports_api",
    # Phase 1: additional workflow roles (customer-admin API, session, union of permissions) and case deep links.
    "test_additional_roles",
    # Phase 1: workflow tasks (My Work): hooks of existing actions, the task API and the backfill.
    "test_workflow_tasks",
    # Phase 2: signals and triage: the triage API, detection, cases from signals and their lifecycle.
    "test_signals_triage",
    # Lightweight MVP phase 2: the complaint second look and the backlog board (md40).
    "test_complaint_review_api",
    # Lightweight MVP phase 3: the reportability watch and CAPA effectiveness checks (md41).
    "test_reporting_capa_api",
    # Lightweight MVP phase 4: one-click case, trend check, signal summary and the case AI run (md42).
    "test_signals_ai_api",
    # Lightweight MVP phase 5: readiness checks and the management review summary.
    "test_readiness_api",
    # Post-market data and the risk file, per product.
    "test_risk_file_api",
    # Phase 3: case workflow states, versioned scope, readiness and the investigator's own cases.
    "test_case_workflow",
    # Phase 3: case evidence (inventory, links, review, provenance) and evidence requests to colleagues and suppliers.
    "test_evidence_workflow",
    # Phase 4: case intelligence (hypotheses judged and added by people, unknowns, failure chains, observations).
    "test_case_intelligence",
    # Phase 4: Ask MDARIX's structured answer (record-based with AI off, checked model sections) and the AI status.
    "test_ask_structured",
    # Phase 5: risk and regulatory reviews (policy, requests, reviewers, readiness, scope restart) and next steps.
    "test_case_reviews",
    # Phase 5: the controlled Decision Brief (versions, submission gate, quality review, return loops, dashboard).
    "test_decision_brief",
    # Phase 6: the human decision (queue, decision screen, signing, verification, superseding, return, legacy).
    "test_human_decision",
    # Phase 6: follow-ups, late-evidence impact assessments (hooks and the sweep) and the closure criteria of a case.
    "test_decision_followups",
    # Phase 7: trust and audit of a case (timeline, replay, AI runs, integrity, audited export).
    "test_case_audit",
    # Phase 7: the 25 workflow scenarios end to end through the API (fresh organizations, six workflow roles).
    "test_e2e_workflow_scenarios",
    # Customer and tenant administration (edit, activate, suspend; a suspended customer blocks its tenants).
    "test_customer_tenant_admin_workflows",
    # Platform administration lists accounts apart: platform users, customer administrators, customer users.
    "test_platform_accounts",
    # Column sorting of the platform administration lists across every page (sort/order on each list endpoint).
    "test_list_sorting_admin",
    # Column sorting of the workspace lists across every page (signals, complaints, My Work, requests, risks).
    "test_list_sorting_workspace",
    # Every organization-owned table is protected by forced row-level security (md05/md15/md34).
    "test_rls_coverage",
    # CSV import options: import the rows that pass (rejects file for the rest), mask personal data instead of refusing.
    "test_data_import_options",
    # A full export and a purge also need a current authenticator code.
    "test_export_purge_mfa",
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
    "test_business_ids_reports_api",
}


def _ensure_legacy_user(db, tenant):
    """The shared Administrator test account and its membership, created on first use (fresh databases)."""
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
            role="PLATFORM_ADMIN",
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
    return user


def authenticated_client(application=app):
    client = TestClient(application)
    db = SessionLocal()
    tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
    user = _ensure_legacy_user(db, tenant)
    token = new_session(db, user.id, user.tenant_id)
    db.close()
    client.cookies.set("mdarix_session", token)
    return client


@pytest.fixture(autouse=True)
def authenticate_legacy_module(request):
    """Modules in LEGACY_PROTECTED call protected routes through module-level clients: give those a session."""
    if request.module.__name__.split(".")[-1] not in LEGACY_PROTECTED:
        yield
        return
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
        user = _ensure_legacy_user(db, tenant)
        token = new_session(db, user.id, user.tenant_id)
        for value in vars(request.module).values():
            if isinstance(value, TestClient):
                value.cookies.set("mdarix_session", token)
        yield
    finally:
        db.close()


def with_signing_plan(db, tenant) -> None:
    """Give a fresh test organization what every real one has: an active plan with controlled signatures, approval
    authority for Approvers and Leaders, and separation of duties (governance_router.bootstrap and its defaults).
    Without an active plan an organization has no features (access/plan_features.py), so it cannot sign."""
    from backend.app.governance_router import bootstrap, ensure_governance_defaults

    bootstrap(db, tenant)
    ensure_governance_defaults(db, tenant)
