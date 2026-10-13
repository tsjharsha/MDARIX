"""Free trial end to end: request -> Platform Admin approval -> activation -> sample workspace -> CSV import."""

import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from auth.durable import issue_invitation
from backend.app.db.models.customer_lifecycle import TenantDataPlane
from backend.app.db.models.foundation import AuthUser, Complaint, Product, Tenant
from backend.app.db.models.stage2 import OnboardingRequest, SubscriptionLifecycle
from backend.app.db.session import SessionLocal
from backend.app.main import app
from backend.app.trial.service import trial_subscription
from backend.app.db.session import engine
from tests.conftest import authenticated_client
from tests.signup_profile import PROFILE, PROFILE_LINES

PASSWORD = "Trial password 2026!"

# Business tables a trial workspace writes to, children first. Other tests count rows in some of these across the
# whole test database, so trial workspaces created here must not leave business data behind.
_TRIAL_BUSINESS_TABLES = (
    # Signals detected from imported complaints (md28) reference complaints, products and cases.
    "signal_events",
    "signal_complaints",
    "investigation_signals",
    "signals",
    "signal_rules",
    # The rest of the sample story (backend/app/trial/sample_data.py seed_story_examples) and what people do with it.
    "complaint_second_looks",
    "complaint_reportability",
    "capa_effectiveness_checks",
    "capas",
    "risks",
    "reportability_settings",
    "retrieval_queries",  # Ask logs its evidence search against the investigation
    "evidence_entity_links",  # imported records are linked to their evidence for AI search
    "evidence_chunk_embeddings",
    "evidence_chunks",
    "investigation_evidence",
    "investigation_complaints",
    "evidence",
    "investigations",
    "complaints",
    "lot_batches",
    "product_components",
    "component_suppliers",
    "components",
    "product_versions",
    "products",
    "suppliers",
    "changes",
    "manufacturing_sites",
)


def _purge_trial_business_data():
    # Everything a trial's records led to (a case analysis writes hypotheses, AI runs and their checks, ...): the
    # purge's own table list, for every trial workspace at once, retried while foreign keys hold rows back; then the
    # tables above, as before.
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.orm import Session as _Session

    from backend.app.trial.retention import _existing_tables

    trials = "tenant_id IN (SELECT id FROM tenants WHERE tenant_key LIKE :pattern)"
    with _Session(engine) as db:
        remaining = _existing_tables(db)
        for _ in range(len(remaining)):
            progress = False
            for table in list(remaining):
                savepoint = db.begin_nested()
                try:
                    db.execute(text(f"DELETE FROM {table} WHERE {trials}"), {"pattern": "TRIAL\\_%"})
                    savepoint.commit()
                except DBAPIError:
                    savepoint.rollback()
                    continue
                remaining.remove(table)
                progress = True
            if not remaining or not progress:
                break
        db.commit()
    with engine.begin() as connection:
        for table in _TRIAL_BUSINESS_TABLES:
            connection.execute(
                text(f"DELETE FROM {table} WHERE tenant_id IN (SELECT id FROM tenants WHERE tenant_key LIKE :pattern)"),
                {"pattern": "TRIAL\\_%"},
            )


@pytest.fixture(autouse=True, scope="module")
def _clean_trial_workspaces():
    _purge_trial_business_data()
    yield
    _purge_trial_business_data()


def _request_trial(organization="Trial Devices Inc") -> str:
    email = f"trial-{uuid.uuid4().hex[:10]}@example.invalid"
    response = TestClient(app).post(
        "/api/v1/auth/signup",
        json={"email": email, "display_name": "Taylor Quality", "organization": organization, **PROFILE},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ONBOARDING_REQUEST_ACCEPTED"
    return email


def _request_id(admin, email) -> str:
    items = admin.get("/api/v1/platform-admin/trial-requests").json()["items"]
    return next(item["id"] for item in items if item["email"] == email)


def _activation_token(approval: dict, email: str) -> str:
    if approval.get("activation_path"):
        return parse_qs(urlparse(approval["activation_path"]).query)["token"][0]
    db = SessionLocal()
    try:
        user = db.query(AuthUser).filter(AuthUser.username == email).one()
        return issue_invitation(db, user.id, user.tenant_id)
    finally:
        db.close()


def _approved_trial_client():
    admin = authenticated_client()
    email = _request_trial()
    approval = admin.post(f"/api/v1/platform-admin/trial-requests/{_request_id(admin, email)}/approve")
    assert approval.status_code == 200, approval.text
    body = approval.json()
    user = TestClient(app)
    activated = user.post(
        "/api/v1/auth/activate-account", json={"token": _activation_token(body, email), "password": PASSWORD}
    )
    assert activated.status_code == 200, activated.text
    signed_in = user.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD})
    assert signed_in.status_code == 200, signed_in.text
    return user, body, email


def test_signup_no_longer_needs_a_password_and_creates_nothing_but_a_request():
    email = _request_trial()
    db = SessionLocal()
    try:
        row = db.query(OnboardingRequest).filter(OnboardingRequest.email == email).one()
        assert row.status == "PENDING_REVIEW" and row.tenant_id is None
        assert db.query(AuthUser).filter(AuthUser.username == email).first() is None
    finally:
        db.close()


def test_only_platform_admins_can_review_trial_requests():
    email = _request_trial()
    anonymous = TestClient(app)
    assert anonymous.get("/api/v1/platform-admin/trial-requests").status_code == 401
    admin = authenticated_client()
    request_id = _request_id(admin, email)
    assert anonymous.post(f"/api/v1/platform-admin/trial-requests/{request_id}/approve").status_code == 401


def test_approval_creates_a_private_trial_workspace_with_sample_data():
    user, approval, email = _approved_trial_client()
    assert approval["status"] == "APPROVED" and approval["tenant_key"].startswith("TRIAL_")
    db = SessionLocal()
    try:
        tenant_id = uuid.UUID(approval["tenant_id"])
        account = db.query(AuthUser).filter(AuthUser.username == email).one()
        assert account.tenant_id == tenant_id and account.role == "LEADER" and account.status == "ACTIVE"
        subscription = trial_subscription(db, tenant_id)
        assert 29 <= (subscription.expires_at - datetime.now(timezone.utc)).days <= 30
        plane = db.query(TenantDataPlane).filter(TenantDataPlane.tenant_id == tenant_id).one()
        assert plane.status == "ACTIVE"
        assert db.query(Product).filter(Product.tenant_id == tenant_id).count() == 3
        # 28 sample complaints and the 9 of the rest of the story (hidden complaints, reporting clocks).
        assert db.query(Complaint).filter(Complaint.tenant_id == tenant_id).count() == 37
    finally:
        db.close()

    status = user.get("/api/v1/trial/status").json()
    assert status["is_trial"] and status["days_left"] == 30 and status["sample"]["products"] == 3
    # The workspace tells the trial team when its data will be deleted: 30 days after the trial ends.
    ends, deleted = (datetime.fromisoformat(status[key]) for key in ("expires_at", "data_deleted_at"))
    assert deleted - ends == timedelta(days=30)
    # The workspace dashboard reads the trial's own data, not another tenant's.
    counts = user.get("/api/v1/analytics/command-center").json()["counts"]
    assert counts["products"] == 3 and counts["complaints"] == 37
    insights = user.get("/api/v1/trial/insights").json()
    assert insights["scope"] == "sample data" and insights["findings"]


def test_a_trial_shows_the_mvp_and_counts_the_sample_data_it_explains(monkeypatch):
    """A free trial always gets the MVP interface, even where the deployment runs the full product, and Getting
    started counts the sample records it explains; any other organization keeps the deployment's setting."""
    monkeypatch.delenv("MDARIX_FEATURE_SET", raising=False)
    user, _approval, _email = _approved_trial_client()
    assert user.get("/api/v1/session/context").json()["feature_set"] == "mvp"
    sample = user.get("/api/v1/trial/status").json()["sample"]
    assert sample == {"products": 3, "lots": 15, "complaints": 37, "investigations": 1, "capas": 2, "risks": 3}
    assert authenticated_client().get("/api/v1/session/context").json()["feature_set"] == "full"


def test_a_request_cannot_be_approved_twice_or_after_decline():
    admin = authenticated_client()
    email = _request_trial()
    request_id = _request_id(admin, email)
    assert (
        admin.post(f"/api/v1/platform-admin/trial-requests/{request_id}/decline", json={"reason": "x"}).status_code
        == 422
    )
    declined = admin.post(
        f"/api/v1/platform-admin/trial-requests/{request_id}/decline", json={"reason": "Not a device company"}
    )
    assert declined.status_code == 200 and declined.json()["status"] == "DECLINED"
    again = admin.post(f"/api/v1/platform-admin/trial-requests/{request_id}/approve")
    assert again.status_code == 409


def test_csv_import_checks_everything_before_saving():
    user, approval, _ = _approved_trial_client()
    template = user.get("/api/v1/trial/templates/products.csv")
    assert template.status_code == 200 and template.text.startswith("product_id,product_name,version")

    products = "product_id,product_name,version,version_release_date\nPUMP-1,Pump One,Rev A,2026-01-10\nPUMP-1,Pump One,Rev B,2026-06-01\n"
    check = user.post("/api/v1/trial/imports/products/check", content=products).json()
    assert check["ready"] and check["new_records"] == 3
    assert user.post("/api/v1/trial/imports/products", content=products).status_code == 200

    lots = "lot_id,product_id,version\nL-100,PUMP-1,Rev B\n"
    assert user.post("/api/v1/trial/imports/lots", content=lots).status_code == 200

    # A column the template does not know (here a person's name) is left out, said back and never stored; personal
    # data in the columns that are read is refused, and nothing is saved.
    extra = "complaint_id,product_id,description,patient_name\nC-1,PUMP-1,Alarm,Jane\n"
    report = user.post("/api/v1/trial/imports/complaints/check", content=extra).json()
    assert report["ready"] and report["ignored_columns"] == ["patient_name"]
    assert "Jane" not in str(report["preview"])
    personal = (
        "complaint_id,product_id,description\n"
        "C-1,PUMP-1,Reported by Dr. Smith on 555-123-4567\n"
        "C-2,NOPE,Alarm sounded\n"
    )
    report = user.post("/api/v1/trial/imports/complaints/check", content=personal).json()
    messages = " ".join(issue["message"] for issue in report["issues"])
    assert not report["ready"] and "personal data" in messages
    rejected = user.post("/api/v1/trial/imports/complaints", content=personal)
    assert rejected.status_code == 422

    good = (
        "complaint_id,product_id,description,version,lot_id,received_date\n"
        "C-1,PUMP-1,Occlusion alarm with no occlusion present,Rev B,L-100,2026-07-02\n"
        "C-2,PUMP-1,Occlusion alarm during setup,Rev B,L-100,2026-07-09\n"
    )
    imported = user.post("/api/v1/trial/imports/complaints", content=good)
    assert imported.status_code == 200, imported.text
    assert imported.json()["created"] == 2 and imported.json()["insights"]["scope"] == "your data"
    # Re-uploading updates instead of duplicating.
    assert user.post("/api/v1/trial/imports/complaints", content=good).json()["updated"] == 2
    status = user.get("/api/v1/trial/status").json()
    assert status["own_data"] == {"products": 1, "lots": 1, "complaints": 2}
    assert status["usage"]["rows"] == 6


def test_a_quality_system_export_uploads_as_it_comes_and_the_second_look_reads_it():
    """One complaints export, with the quality system's own headers, an extra column, products and lots not loaded and
    its own statuses: the trial reads it, adds what it names, and the second look finds the cancelled harm record."""
    user, _approval, _ = _approved_trial_client()
    export = (
        "Complaint Number,Product Code,Product Name,Complaint Description,Lot #,Date Received,State,Serious Injury,"
        "Patient Name\n"
        "TW-0001,ACME-PUMP,Acme Infusion Pump,Pump stopped during infusion and the patient was injured. Duplicate.,"
        "LOT-77,2026-08-02,Cancelled,Y,J. Doe\n"
        "TW-0002,ACME-PUMP,Acme Infusion Pump,Display flickers at start-up,LOT-77,2026-08-09,Open,N,\n"
    )
    check = user.post("/api/v1/trial/imports/complaints/check", content=export).json()
    assert check["ready"], check["issues"]
    assert check["ignored_columns"] == ["Patient Name"]
    assert {"header": "Complaint Number", "column": "complaint_id"} in check["columns"]
    assert check["also_creates"] == {"products": 1, "lots": 1}
    assert check["new_records"] == 4  # two complaints, the product and the lot
    imported = user.post("/api/v1/trial/imports/complaints", content=export)
    assert imported.status_code == 200, imported.text
    db = SessionLocal()
    try:
        product = (
            db.query(Product)
            .filter(Product.product_identifier == "ACME-PUMP")
            .order_by(Product.created_at.desc())
            .first()
        )
        assert product.name == "Acme Infusion Pump"
        complaint = db.query(Complaint).filter(Complaint.complaint_identifier == "TW-0001").one()
        assert complaint.status == "cancelled" and complaint.serious_injury is True
    finally:
        db.close()
    flagged = {item["complaint_identifier"] for item in user.get("/api/v1/complaints/second-look").json()["items"]}
    assert "TW-0001" in flagged and "TW-0002" not in flagged


def test_import_is_only_for_trial_workspaces():
    customer = authenticated_client()
    assert customer.get("/api/v1/trial/status").json() == {"is_trial": False}
    assert customer.post("/api/v1/trial/imports/products/check", content="product_id\n").status_code == 404


def test_trial_closes_on_its_end_date():
    user, approval, email = _approved_trial_client()
    db = SessionLocal()
    try:
        row = (
            db.query(SubscriptionLifecycle)
            .filter(SubscriptionLifecycle.tenant_id == uuid.UUID(approval["tenant_id"]))
            .one()
        )
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    assert user.get("/api/v1/trial/status").status_code == 403
    again = TestClient(app).post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD})
    assert again.status_code == 403 and again.json()["detail"]["code"] == "TRIAL_ENDED"
    db = SessionLocal()
    try:
        # Ending the trial keeps the workspace and its data for conversion.
        assert db.query(Tenant).filter(Tenant.id == uuid.UUID(approval["tenant_id"])).one().status == "ACTIVE"
    finally:
        db.close()


def test_ask_mdarix_is_grounded_in_the_trial_sample_investigation():
    user, approval, _ = _approved_trial_client()
    db = SessionLocal()
    try:
        from backend.app.db.models.foundation import Investigation

        investigation = (
            db.query(Investigation)
            .filter(
                Investigation.tenant_id == uuid.UUID(approval["tenant_id"]),
                Investigation.investigation_identifier == "SAMPLE-INV-001",
            )
            .one()
        )
        investigation_id = str(investigation.id)
    finally:
        db.close()
    answer = user.post(
        "/api/v1/stage3/interactions",
        json={
            "prompt": "Why did pressure-alarm complaints rise after Rev B?",
            "investigation_id": investigation_id,
            "page_context": "ASK_MDARIX",
            "temporal_mode": "CURRENT",
        },
    )
    assert answer.status_code == 200, answer.text
    response = answer.json()["response"]
    assert response["grounding"]["tenant_scope_enforced"] is True
    cited = {item["evidence_identifier"] for item in response["sources_provenance"]}
    assert cited and all(identifier.startswith("SAMPLE-EV-") for identifier in cited)


def _activate_and_sign_in(email: str, token: str) -> TestClient:
    client = TestClient(app)
    assert client.post("/api/v1/auth/activate-account", json={"token": token, "password": PASSWORD}).status_code == 200
    assert client.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD}).status_code == 200
    return client


def test_trial_owner_invites_colleagues_up_to_the_user_limit():
    owner, approval, owner_email = _approved_trial_client()
    assert owner.get("/api/v1/trial/status").json()["is_owner"] is True

    first = f"colleague-{uuid.uuid4().hex[:8]}@example.invalid"
    invited = owner.post("/api/v1/trial/team", json={"email": first, "display_name": "Casey Review"})
    assert invited.status_code == 200, invited.text
    second = f"colleague-{uuid.uuid4().hex[:8]}@example.invalid"
    assert owner.post("/api/v1/trial/team", json={"email": second, "display_name": "Robin QA"}).status_code == 200
    # Three users is the limit, an existing account cannot be invited again, and bad input is refused.
    full = owner.post("/api/v1/trial/team", json={"email": "extra@example.invalid", "display_name": "Extra"})
    assert full.status_code == 409 and full.json()["detail"]["code"] == "TRIAL_USER_LIMIT_REACHED"
    assert owner.post("/api/v1/trial/team", json={"email": owner_email, "display_name": "Me"}).status_code == 409

    roster = owner.get("/api/v1/trial/team").json()
    assert roster["seats_used"] == 3 and roster["can_invite"] is True
    assert [member["is_owner"] for member in roster["members"]].count(True) == 1

    colleague = _activate_and_sign_in(first, _activation_token(invited.json(), first))
    assert colleague.get("/api/v1/trial/status").json()["is_owner"] is False
    # A colleague works in the same workspace but cannot invite or administer.
    assert colleague.get("/api/v1/analytics/command-center").json()["counts"]["products"] == 3
    refused = colleague.post("/api/v1/trial/team", json={"email": "x@example.invalid", "display_name": "X"})
    assert refused.status_code == 403
    assert colleague.get("/api/v1/platform-admin/trial-requests").status_code == 403


def test_closed_trial_data_is_deleted_after_30_days():
    user, approval, email = _approved_trial_client()
    _recent, recent_approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        for target, ended in (
            (tenant_id, now - timedelta(days=31)),
            (uuid.UUID(recent_approval["tenant_id"]), now - timedelta(days=10)),
        ):
            row = db.query(SubscriptionLifecycle).filter(SubscriptionLifecycle.tenant_id == target).one()
            row.expires_at = ended
        db.commit()
    finally:
        db.close()

    admin = authenticated_client()
    due = {item["tenant_id"] for item in admin.get("/api/v1/platform-admin/trial-retention").json()["due"]}
    assert approval["tenant_id"] in due and recent_approval["tenant_id"] not in due
    assert TestClient(app).post("/api/v1/platform-admin/trial-retention/run").status_code == 401
    run = admin.post("/api/v1/platform-admin/trial-retention/run").json()
    purged = next(item for item in run["trials"] if item["tenant_id"] == approval["tenant_id"])
    assert purged["deleted_records"]["products"] == 3 and purged["not_deleted_tables"] == []

    db = SessionLocal()
    try:
        assert db.query(Product).filter(Product.tenant_id == tenant_id).count() == 0
        assert db.query(Tenant).filter(Tenant.id == tenant_id).one().status == "ARCHIVED"
        # The trial's people are pseudonymized: their email address is gone and nobody can sign in.
        assert db.query(AuthUser).filter(AuthUser.username == email).count() == 0
        assert {user.status for user in db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id)} == {"REMOVED"}
        # The trial that closed 10 days ago keeps its data.
        assert db.query(Product).filter(Product.tenant_id == uuid.UUID(recent_approval["tenant_id"])).count() == 3
    finally:
        db.close()
    assert user.get("/api/v1/trial/status").status_code == 401
    assert TestClient(app).post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD}).status_code != 200
    queue = admin.get("/api/v1/platform-admin/trial-requests").json()["items"]
    request = next(item for item in queue if item["tenant_id"] == approval["tenant_id"])
    assert request["data_deleted"] is True
    # The requester's job title goes with the rest of their personal data; the company facts stay.
    assert "job_title" not in request["profile"] and request["profile"]["country"] == "United States"


def test_new_trial_request_alerts_the_platform_admin(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "auth.emailer.send_trial_request_alert", lambda recipient, **details: sent.append((recipient, details))
    )
    monkeypatch.setenv("MDARIX_TRIAL_ALERT_EMAIL", "admin-alerts@example.invalid")
    email = _request_trial("Alerted Devices")
    assert sent == [
        (
            "admin-alerts@example.invalid",
            {
                "organization": "Alerted Devices",
                "display_name": "Taylor Quality",
                "email": email,
                "profile_lines": PROFILE_LINES,
            },
        )
    ]
    # Repeating the same request does not alert again.
    again = TestClient(app).post(
        "/api/v1/auth/signup",
        json={"email": email, "display_name": "Taylor Quality", "organization": "Alerted Devices", **PROFILE},
    )
    assert again.status_code == 409 and again.json()["detail"]["code"] == "TRIAL_ALREADY_REQUESTED"
    assert len(sent) == 1


def test_a_failing_alert_never_breaks_sign_up(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr("auth.emailer.send_trial_request_alert", boom)
    monkeypatch.setenv("MDARIX_TRIAL_ALERT_EMAIL", "admin-alerts@example.invalid")
    _request_trial("Resilient Devices")  # asserts the sign-up still succeeds
    monkeypatch.setenv("MDARIX_TRIAL_ALERT_EMAIL", "")
    monkeypatch.setattr("auth.emailer.send_trial_request_alert", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    _request_trial("Quiet Devices")  # no alert address configured: nothing is sent


def test_a_trial_request_needs_the_required_answers_and_stores_nothing_without_them():
    email = f"trial-{uuid.uuid4().hex[:10]}@example.invalid"
    base = {"email": email, "display_name": "Taylor Quality", "organization": "Answer Devices"}
    client = TestClient(app)
    for missing, code in (
        ({**PROFILE, "job_title": ""}, "JOB_TITLE_REQUIRED"),
        ({**PROFILE, "country": " "}, "COUNTRY_REQUIRED"),
        ({**PROFILE, "no_patient_data": False}, "NO_PATIENT_DATA_CONFIRMATION_REQUIRED"),
        ({**PROFILE, "device_class": "CLASS_IV"}, "INVALID_DEVICE_CLASS"),
    ):
        refused = client.post("/api/v1/auth/signup", json={**base, **missing})
        assert refused.status_code == 422 and refused.json()["detail"]["code"] == code
    db = SessionLocal()
    try:
        assert db.query(OnboardingRequest).filter(OnboardingRequest.email == email).count() == 0
    finally:
        db.close()


def test_the_review_queue_shows_what_the_requester_told_us():
    email = f"trial-{uuid.uuid4().hex[:10]}@example.invalid"
    answers = {
        **PROFILE,
        "company_size": "201-1000",
        "device_types": "Infusion pumps",
        "device_class": "CLASS_II",
        "markets": ["US", "EU"],
        "complaint_system": "TRACKWISE",
        "complaint_volume": "50_500",
        "trial_data": "ANONYMIZED_EXPORTS",
        "evaluation_goal": "Complaint trending",
    }
    sent = TestClient(app).post(
        "/api/v1/auth/signup",
        json={"email": email, "display_name": "Taylor Quality", "organization": "Profile Devices", **answers},
    )
    assert sent.status_code == 200, sent.text
    queue = authenticated_client().get("/api/v1/platform-admin/trial-requests").json()["items"]
    item = next(row for row in queue if row["email"] == email)
    assert item["profile"]["complaint_system"] == "TRACKWISE" and item["profile"]["markets"] == ["US", "EU"]
    lines = {line["label"]: line["value"] for line in item["profile_lines"]}
    assert lines["Highest device class"] == "Class II"
    assert lines["Markets"] == "United States (FDA), European Union (MDR/IVDR)"
    assert lines["Trial data"] == "Our anonymized exports"


# ------------------------------------------------------------------------------------- the story from the first minute


def test_the_trial_tells_the_whole_story_from_the_first_minute():
    """Every chapter of the quality loop has a finding in the sample data, the trial sees which chapters it acted in,
    and the Platform Admin sees the same progress for every trial."""
    user, approval, _email = _approved_trial_client()
    tenant_key = approval["tenant_key"]

    second_look = user.get("/api/v1/complaints/second-look").json()
    flagged = {item["complaint_identifier"]: item for item in second_look["items"]}
    assert {"SAMPLE-RV-01", "SAMPLE-RV-02", "SAMPLE-RV-03", "SAMPLE-RV-04", "SAMPLE-RV-05"} <= set(flagged)
    assert flagged["SAMPLE-RV-01"]["reasons"][0]["code"] == "CANCELLED"
    assert flagged["SAMPLE-RV-03"]["reasons"][0]["code"] == "NFF_RECURRING"

    readiness = {check["code"]: check for check in user.get("/api/v1/readiness").json()["checks"]}
    assert readiness["REPORTING_CLOCKS"]["state"] != "NOT_SET" and readiness["REPORTING_CLOCKS"]["value"] >= 1
    assert readiness["HARM_CLOSED_WITHOUT_CASE"]["value"] == 1  # SAMPLE-RV-09, closed after a training call
    assert readiness["CAPA_EFFECTIVENESS"]["state"] == "CRITICAL"  # a CAPA closed without a check
    assert readiness["RISK_FILE_INPUT"]["value"] == 3 and readiness["RISK_FILE_INPUT"]["state"] == "CRITICAL"

    story = user.get("/api/v1/trial/story")
    assert story.status_code == 200, story.text
    body = story.json()
    assert [chapter["code"] for chapter in body["chapters"]] == [
        "HIDDEN_COMPLAINTS",
        "REPORTING_CLOCKS",
        "TRENDS_TO_CASES",
        "INVESTIGATE_WITH_AI",
        "DECIDE_AND_SIGN",
        "CAPA_EFFECTIVE",
        "RISK_FILE",
        "SHOW_THE_INSPECTOR",
        "YOUR_DATA",
    ]
    assert body["acted"] == 0 and body["next"] == "HIDDEN_COMPLAINTS"
    chapters = {chapter["code"]: chapter for chapter in body["chapters"]}
    assert chapters["HIDDEN_COMPLAINTS"]["finding"]["value"] >= 5
    assert chapters["INVESTIGATE_WITH_AI"]["finding"]["value"] == 1  # the guided investigation
    # Trials start without AI: the chapter promises what the case page does without it.
    assert chapters["INVESTIGATE_WITH_AI"]["title"] == "Investigate with evidence you can trace"
    assert "AI assistance joins when it is switched on" in chapters["INVESTIGATE_WITH_AI"]["promise"]
    assert chapters["RISK_FILE"]["finding"]["state"] == "CRITICAL"
    # The decision chapter opens the guided investigation's waiting brief.
    assert chapters["DECIDE_AND_SIGN"]["opens"] == {"section": "Investigations", "tab": "Decision Brief"}
    assert chapters["DECIDE_AND_SIGN"]["case"]["id"] and chapters["INVESTIGATE_WITH_AI"]["case"]
    assert chapters["HIDDEN_COMPLAINTS"]["case"] is None
    assert all(chapter["promise"] and chapter["pain"] and chapter["opens"]["section"] for chapter in body["chapters"])

    # A person decides one hidden complaint: the first chapter is acted on.
    record = flagged["SAMPLE-RV-01"]["id"]
    decided = user.post(
        f"/api/v1/complaints/{record}/second-look",
        json={"decision": "CONFIRMED", "reason": "Meets our complaint definition: harm reported"},
    )
    assert decided.status_code == 200, decided.text
    body = user.get("/api/v1/trial/story").json()
    assert body["acted"] == 1 and body["next"] == "REPORTING_CLOCKS"
    assert body["chapters"][0]["acted"] == {"done": True, "count": 1}

    # The Platform Admin sees the trial, its usage and how far into the story it went; the trial user does not.
    assert user.get("/api/v1/platform-admin/trials").status_code in (401, 403)
    overview = authenticated_client().get("/api/v1/platform-admin/trials")
    assert overview.status_code == 200, overview.text
    item = next(entry for entry in overview.json()["items"] if entry["tenant_key"] == tenant_key)
    assert item["story"]["acted"] == ["HIDDEN_COMPLAINTS"] and item["story"]["total"] == 9
    assert item["users"] == {"used": 1, "limit": 3} and item["days_left"] == 30 and item["state"] == "ACTIVE"
    assert item["story"]["last_activity"]
    summary = overview.json()["summary"]
    assert summary["active"] >= 1 and summary["acted"] >= 1 and summary["chapters"]["HIDDEN_COMPLAINTS"] >= 1
    assert [chapter["code"] for chapter in overview.json()["chapters"]][0] == "HIDDEN_COMPLAINTS"


def test_opening_a_case_is_not_investigating_but_starting_its_analysis_is():
    """The case page's automatic first analysis does not tick the investigation chapter; one a person starts does."""
    from backend.app.db.models.foundation import Investigation

    user, approval, _email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    db = SessionLocal()
    try:
        case = (
            db.query(Investigation)
            .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == "SAMPLE-INV-001")
            .one()
        )
        case_id = case.id
    finally:
        db.close()

    def investigated() -> bool:
        chapters = {chapter["code"]: chapter for chapter in user.get("/api/v1/trial/story").json()["chapters"]}
        return chapters["INVESTIGATE_WITH_AI"]["acted"]["done"]

    assert user.post(f"/api/v1/investigations/{case_id}/ai-run", json={"trigger": "AUTO"}).status_code in (200, 202)
    assert investigated() is False
    started = user.post(f"/api/v1/investigations/{case_id}/ai-run", json={"trigger": "MANUAL"})
    assert started.status_code in (200, 202), started.text
    assert investigated() is True


def test_one_trial_user_reviews_the_sample_brief_and_may_sign_its_decision():
    """The guided investigation arrives with its brief written and submitted by the sample author (who cannot sign
    in and holds no seat); the trial user alone reviews it, accepts it for decision and may sign, while the author
    could not: segregation of duties holds."""
    from backend.app.db.models.foundation import Investigation
    from backend.app.db.models.reviews import DecisionBriefVersion
    from backend.app.trial.sample_decision import SAMPLE_AUTHOR_NAME, stage_sample_decision

    user, approval, _email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    db = SessionLocal()
    try:
        case = (
            db.query(Investigation)
            .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == "SAMPLE-INV-001")
            .one()
        )
        case_id = case.id
        brief = db.query(DecisionBriefVersion).filter(DecisionBriefVersion.investigation_id == case_id).one()
        author = db.get(AuthUser, uuid.UUID(brief.submitted_by))
        assert brief.status == "READY_FOR_REVIEW" and brief.created_by == brief.submitted_by
        assert author.display_name == SAMPLE_AUTHOR_NAME and author.status == "DISABLED"
        # Staged once: approving again or refreshing leaves it.
        assert stage_sample_decision(db, tenant_id)["created"] is False
    finally:
        db.close()
    status = user.get("/api/v1/trial/status").json()
    assert status["usage"]["users"] == 1
    assert [member["display_name"] for member in user.get("/api/v1/trial/team").json()["members"]] != []
    assert all(
        member["display_name"] != SAMPLE_AUTHOR_NAME for member in user.get("/api/v1/trial/team").json()["members"]
    )

    base = f"/api/v1/investigations/{case_id}/decision-brief/versions/1"
    started = user.post(f"{base}/start-review", json={})
    assert started.status_code == 200, started.text
    accepted = user.post(
        f"{base}/review", json={"action": "ACCEPT_FOR_DECISION", "comment": "Evidence and scope hold."}
    )
    assert accepted.status_code == 200, accepted.text
    screen = user.get(f"/api/v1/investigations/{case_id}/decision")
    assert screen.status_code == 200, screen.text
    actions = screen.json()["actions"]
    assert actions["can_sign"] is True, actions


def test_the_story_is_added_once_and_the_refresh_leaves_a_trial_with_it_alone():
    import importlib.util

    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.db.models.reportability import ReportabilitySettings
    from backend.app.trial.sample_data import STORY_WINDOWS_BY, seed_story_examples

    _user, approval, _email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    db = SessionLocal()
    try:
        bind_tenant(db, tenant_id)
        assert seed_story_examples(db, tenant_id) == {"created": False}
        windows = db.query(ReportabilitySettings).filter(ReportabilitySettings.tenant_id == tenant_id).one()
        assert windows.updated_by == STORY_WINDOWS_BY and len(windows.windows) == 3
        assert db.query(Complaint).filter(Complaint.tenant_id == tenant_id).count() == 37
    finally:
        db.close()

    spec = importlib.util.spec_from_file_location("refresh_trial_story", "scripts/refresh_trial_story.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    db = SessionLocal()
    try:
        results = {item["tenant"]: item["result"] for item in script.refresh(db, apply=False)}
    finally:
        db.close()
    assert results[approval["tenant_key"]] == "already has the story"


def test_the_trial_finds_the_rise_per_device_and_its_signal_from_the_first_minute():
    """The sample lots carry quantities (md43): the young OrbitCare Rev B is compared with Rev A per unit in the field
    and found significantly higher; the count rule's signal is detected at approval, so the third chapter has work."""
    user, approval, _email = _approved_trial_client()
    board = user.get("/api/v1/triage/trends", params={"group": "version"})
    assert board.status_code == 200, board.text
    orbit = next(item for item in board.json()["items"] if item["name"] == "OrbitCare 300 Infusion Pump (Sample) Rev B")
    assert orbit["result"] == "SIGNIFICANT", orbit
    assert orbit["baseline"] == "PREVIOUS_VERSION" and orbit["baseline_name"].endswith("Rev A")
    assert orbit["basis"] == "UNITS" and orbit["label"] == "Rate significantly higher than the previous version"
    assert "Scaled by the units in the field" in orbit["sentence"]
    assert board.json()["basis"]["units"] >= 1

    chapters = {chapter["code"]: chapter for chapter in user.get("/api/v1/trial/story").json()["chapters"]}
    trends = chapters["TRENDS_TO_CASES"]["finding"]
    assert trends["value"] >= 1 and "waiting for a decision or a case" in trends["text"], trends
    assert chapters["TRENDS_TO_CASES"]["acted"]["done"] is False  # detection is not a person's action

    # A lot's quantity comes in with the lot import, checked before anything is saved.
    bad = "lot_id,product_id,version,quantity\nL-Q1,SAMPLE-ORBIT-300,Rev B,-5\nL-Q2,SAMPLE-ORBIT-300,Rev B,lots\n"
    report = user.post("/api/v1/trial/imports/lots/check", content=bad).json()
    assert not report["ready"] and len(report["issues"]) == 2
    assert "whole number" in report["issues"][0]["message"]
    good = 'lot_id,product_id,version,quantity\nL-Q1,SAMPLE-ORBIT-300,Rev B,"1,250"\n'
    imported = user.post("/api/v1/trial/imports/lots", content=good)
    assert imported.status_code == 200, imported.text
    db = SessionLocal()
    try:
        from backend.app.db.models.foundation import LotBatch

        lot = (
            db.query(LotBatch)
            .filter(LotBatch.tenant_id == uuid.UUID(approval["tenant_id"]), LotBatch.lot_identifier == "L-Q1")
            .one()
        )
        assert lot.quantity == 1250
    finally:
        db.close()


def test_the_inspection_pack_holds_every_record_behind_every_check():
    import hashlib
    import io
    import json
    import zipfile

    user, approval, _email = _approved_trial_client()
    response = user.get("/api/v1/readiness/inspection-pack.zip", params={"period_days": 365})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert "mdarix-inspection-pack-" in response.headers["content-disposition"]
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = archive.namelist()
    assert names[:3] == ["00-README.txt", "01-readiness-summary.pdf", "02-inspection-checks.csv"]
    assert names[-1] == "manifest.json" and len(names) == 12
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["unreadable"] == [] and manifest["checks"]["checks"] == 8
    for entry in manifest["files"]:
        assert hashlib.sha256(archive.read(entry["name"])).hexdigest() == entry["sha256"], entry["name"]
    assert archive.read("01-readiness-summary.pdf").startswith(b"%PDF")

    def rows(name):
        text = archive.read(name).decode("utf-8-sig")
        return text.splitlines()

    hidden = rows("03-hidden-complaints.csv")
    assert hidden[0].startswith("Complaint,Source ID,Product")
    assert any("SAMPLE-RV-01" in line and "Cancelled or rejected" in line for line in hidden)
    assert any("SAMPLE-RV-09" in line for line in rows("06-harm-closed-without-investigation.csv"))
    assert len(rows("10-risk-file-input.csv")) == 4  # the header and the three sample products
    assert any("SAMPLE-CAPA-01" in line for line in rows("09-capas-without-verified-effect.csv"))
    checks = rows("02-inspection-checks.csv")
    assert len(checks) == 9 and any("03-hidden-complaints.csv" in line for line in checks)
    readme = archive.read("00-README.txt").decode("utf-8")
    assert "SHA-256" in readme and "verify against the source records" in readme

    # The export is audited, and handing the inspector a pack is chapter 8 of the trial's story.
    chapters = {chapter["code"]: chapter for chapter in user.get("/api/v1/trial/story").json()["chapters"]}
    assert chapters["SHOW_THE_INSPECTOR"]["acted"]["done"] is True
    assert user.get("/api/v1/readiness/inspection-pack.zip", params={"period_days": 10}).status_code == 422


def test_the_weekly_readiness_email_reaches_the_quality_leads_once_a_week(monkeypatch):
    from backend.app import notifications
    from backend.app.db.data_plane import open_tenant_data_session
    from backend.app.db.models.stage2 import OutboxEvent
    from backend.app.db.tenant_scope import bind_system
    from backend.app.readiness_home import digest

    user, approval, email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    monday = datetime(2026, 10, 19, 8, 0, tzinfo=timezone.utc)
    db = SessionLocal()
    try:
        bind_system(db, "test: weekly readiness email")
        with open_tenant_data_session(tenant_id) as data:
            assert digest.queue_for_tenant(db, data, tenant_id, monday) is True
            db.commit()
            assert digest.queue_for_tenant(db, data, tenant_id, monday) is False  # once a week
        event = (
            db.query(OutboxEvent)
            .filter(OutboxEvent.tenant_id == tenant_id, OutboxEvent.event_name == digest.EVENT)
            .one()
        )
        payload = event.payload
        assert payload["week"] == "2026-W43" and "@" not in str(payload)  # no address in the queue
        content = payload["content"]
        assert content["first"] is True and content["total"] == 8 and content["weakest"]["state"] == "CRITICAL"

        sent = []
        from auth import emailer

        monkeypatch.setattr(
            emailer, "send_readiness_digest", lambda recipient, **details: sent.append((recipient, details)) or "SENT"
        )
        assert notifications.handle_event(db, digest.EVENT, payload) is True
        assert [recipient for recipient, _ in sent] == [email]  # the trial's Leader
        assert sent[0][1]["week"] == "2026-W43" and sent[0][1]["content"]["total"] == 8

        # The next week says what changed (compared with this week's snapshot).
        with open_tenant_data_session(tenant_id) as data:
            assert digest.queue_for_tenant(db, data, tenant_id, datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc))
            db.commit()
        later = (
            db.query(OutboxEvent)
            .filter(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.event_name == digest.EVENT,
                OutboxEvent.payload["week"].as_string() == "2026-W44",
            )
            .one()
        )
        assert later.payload["content"]["first"] is False

        # A quality lead may switch it off for themselves; then nobody of this trial gets it.
        shown = user.get("/api/v1/me/email-preferences").json()
        assert shown == {
            "weekly_readiness": True,
            "weekly_readiness_eligible": True,
            "weekly_readiness_about": shown["weekly_readiness_about"],
        }
        assert (
            user.put("/api/v1/me/email-preferences", json={"weekly_readiness": False}).json()["weekly_readiness"]
            is False
        )
        db.expire_all()
        assert digest.recipients(db, tenant_id) == []
        assert user.put("/api/v1/me/email-preferences", json={"weekly_readiness": True}).status_code == 200
        db.expire_all()
        assert digest.recipients(db, tenant_id) == [email]
    finally:
        db.query(OutboxEvent).filter(OutboxEvent.tenant_id == tenant_id, OutboxEvent.event_name == digest.EVENT).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()


def test_a_trial_books_a_one_to_one_demo_and_mdarix_sees_its_progress(monkeypatch):
    from auth import emailer
    from backend.app.db.models.stage2 import DemoRequest

    alerts = []
    monkeypatch.setenv("MDARIX_DEMO_ALERT_EMAIL", "sales@mdarix.invalid")
    monkeypatch.setattr(
        emailer,
        "send_trial_demo_request_alert",
        lambda recipient, **details: alerts.append((recipient, details)) or "SENT",
    )
    user, approval, email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        assert user.get("/api/v1/trial/demo-request").json() == {"request": None}
        refused = user.post("/api/v1/trial/demo-request", json={"phone": "abc"})
        assert refused.status_code == 422 and refused.json()["detail"]["field"] == "phone"
        booked = user.post(
            "/api/v1/trial/demo-request",
            json={
                "preferred_time": "Tuesday or Wednesday afternoon (IST)",
                "phone": "+91 98450 12345",
                "focus": ["HIDDEN_COMPLAINTS", "RISK_FILE", "NOT_A_CHAPTER"],
                "note": "We have a notified body audit in March.",
            },
        )
        assert booked.status_code == 200, booked.text
        assert booked.json()["status"] == "DEMO_REQUESTED"
        assert booked.json()["request"]["preferred_time"] == "Tuesday or Wednesday afternoon (IST)"
        again = user.post("/api/v1/trial/demo-request", json={})
        assert again.json()["status"] == "ALREADY_REQUESTED"
        assert again.json()["request"]["id"] == booked.json()["request"]["id"]
        assert user.get("/api/v1/trial/demo-request").json()["request"]["status"] == "NEW"

        # The MDARIX team is told, with the organization and how far the trial got.
        assert [recipient for recipient, _ in alerts] == ["sales@mdarix.invalid"]
        details = alerts[0][1]
        assert details["email"] == email and details["organization"] == "Trial Devices Inc"
        assert details["focus"] == (
            "Recover complaints hidden as cancellations or inquiries",
            "Feed post-market data into the risk file",
        )
        assert details["progress"].startswith("0 of 9 story chapters tried, 30 days left")

        admin = authenticated_client()
        listed = admin.get("/api/v1/platform-admin/demo-requests").json()["items"]
        item = next(entry for entry in listed if entry["id"] == booked.json()["request"]["id"])
        assert item["source"] == "TRIAL" and item["organization"] == "Trial Devices Inc"
        assert item["trial_tenant_id"] == str(tenant_id) and item["context"]["chapters_total"] == 9
        assert item["note"] == "We have a notified body audit in March."
        trials = admin.get("/api/v1/platform-admin/trials").json()
        mine = next(entry for entry in trials["items"] if entry["tenant_id"] == str(tenant_id))
        assert mine["demo_request"]["status"] == "NEW" and trials["summary"]["demo_requested"] >= 1
    finally:
        db = SessionLocal()
        try:
            db.query(DemoRequest).filter(DemoRequest.trial_tenant_id == tenant_id).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()


def _forget_exit_requests(tenant_ids):
    from backend.app.db.models.stage2 import TrialExitRequest

    db = SessionLocal()
    try:
        db.query(TrialExitRequest).filter(TrialExitRequest.trial_tenant_id.in_(tenant_ids)).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


def test_the_owner_ends_the_trial_early_and_its_data_is_deleted(monkeypatch):
    """The owner asks to end early with a reason; Platform Admin approves with deletion: the trial ends, everything it
    stored is purged (the demo it booked too), the request and its reason remain, and the owner is emailed."""
    from auth import emailer
    from backend.app.db.models.stage2 import DemoRequest, TrialExitRequest

    sent = []
    monkeypatch.setattr(emailer, "send_trial_ended_early", lambda *args, **kwargs: sent.append((args, kwargs)))
    monkeypatch.setattr(emailer, "send_trial_exit_request_alert", lambda *args, **kwargs: None)
    monkeypatch.setenv("MDARIX_TRIAL_ALERT_EMAIL", "trials@mdarix.invalid")
    user, approval, email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        state = user.get("/api/v1/trial/exit-request").json()
        assert state["is_owner"] is True and state["request"] is None and "MISSING" in state["reasons"]
        assert user.post("/api/v1/trial/demo-request", json={"preferred_time": "Monday"}).status_code == 200

        asked = user.post(
            "/api/v1/trial/exit-request",
            json={"reason_code": "MISSING", "reason": "We need our QMS connected first.", "delete_data": True},
        )
        assert asked.status_code == 200, asked.text
        assert asked.json()["status"] == "REQUESTED"
        again = user.post("/api/v1/trial/exit-request", json={"reason_code": "OTHER"}).json()
        assert again["status"] == "ALREADY_REQUESTED" and again["request"]["reason_code"] == "MISSING"
        # Withdrawn, then asked again; an unknown reason is refused.
        assert user.post("/api/v1/trial/exit-request/withdraw").json()["status"] == "WITHDRAWN"
        assert user.post("/api/v1/trial/exit-request", json={"reason_code": "BORED"}).status_code == 422
        asked = user.post(
            "/api/v1/trial/exit-request",
            json={"reason_code": "MISSING", "reason": "We need our QMS connected first.", "delete_data": True},
        ).json()
        request_id = asked["request"]["id"]

        admin = authenticated_client()
        assert TestClient(app).get("/api/v1/platform-admin/trial-exit-requests").status_code == 401
        listed = admin.get("/api/v1/platform-admin/trial-exit-requests").json()
        item = next(row for row in listed["items"] if row["id"] == request_id)
        assert item["status"] == "PENDING" and item["reason_label"] == "Something we need is missing"
        assert item["requested_by"] and item["days_left"] == 30 and listed["pending"] >= 1

        decided = admin.post(
            f"/api/v1/platform-admin/trial-exit-requests/{request_id}/approve", json={"delete_data": True}
        )
        assert decided.status_code == 200, decided.text
        assert decided.json()["data_deleted"] is True and "notify" not in decided.json()
        assert sent and sent[0][0][0] == email and sent[0][1] == {"data_deleted": True}
        # Decided once only.
        assert (
            admin.post(f"/api/v1/platform-admin/trial-exit-requests/{request_id}/approve", json={}).status_code == 409
        )

        db = SessionLocal()
        try:
            assert db.query(Tenant).filter(Tenant.id == tenant_id).one().status == "ARCHIVED"
            assert db.query(Product).filter(Product.tenant_id == tenant_id).count() == 0
            assert db.query(AuthUser).filter(AuthUser.username == email).count() == 0
            assert db.query(DemoRequest).filter(DemoRequest.trial_tenant_id == tenant_id).count() == 0
            kept = db.query(TrialExitRequest).filter(TrialExitRequest.id == uuid.UUID(request_id)).one()
            assert kept.status == "APPROVED" and kept.data_deleted and kept.reason == "We need our QMS connected first."
        finally:
            db.close()
        assert user.get("/api/v1/trial/status").status_code == 401
    finally:
        _forget_exit_requests([tenant_id])


def test_a_declined_request_keeps_the_trial_and_an_approved_one_can_keep_the_data(monkeypatch):
    """Declining needs a note for the owner and the trial continues; approving without deletion ends the trial, keeps
    the data for the usual 30 days and queues the owner's email; the data can then be deleted early."""
    from auth import emailer
    from backend.app.db.models.stage2 import OutboxEvent
    from backend.app.notifications import queue_trial_reminders

    declined, ended = [], []
    monkeypatch.setattr(emailer, "send_trial_exit_declined", lambda *args, **kwargs: declined.append((args, kwargs)))
    monkeypatch.setattr(emailer, "send_trial_ended_early", lambda *args, **kwargs: ended.append((args, kwargs)))
    monkeypatch.delenv("MDARIX_TRIAL_ALERT_EMAIL", raising=False)
    user, approval, email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    admin = authenticated_client()
    started = datetime.now(timezone.utc)
    try:
        request_id = user.post("/api/v1/trial/exit-request", json={"delete_data": False}).json()["request"]["id"]
        path = f"/api/v1/platform-admin/trial-exit-requests/{request_id}"
        assert admin.post(f"{path}/decline", json={"note": "Call?"}).status_code == 422
        note = "We would like a short call first; could you reply with a time?"
        assert admin.post(f"{path}/decline", json={"note": note}).json()["status"] == "DECLINED"
        assert declined[0][0][0] == email and declined[0][1] == {"note": note}
        shown = user.get("/api/v1/trial/exit-request").json()["request"]
        assert shown["status"] == "DECLINED" and shown["decision_note"] == note
        assert user.get("/api/v1/trial/status").status_code == 200

        request_id = user.post("/api/v1/trial/exit-request", json={"delete_data": False}).json()["request"]["id"]
        path = f"/api/v1/platform-admin/trial-exit-requests/{request_id}"
        decided = admin.post(f"{path}/approve", json={"delete_data": False}).json()
        assert decided["data_deleted"] is False and not ended
        db = SessionLocal()
        try:
            subscription = trial_subscription(db, tenant_id)
            assert subscription.expires_at <= datetime.now(timezone.utc) and subscription.status == "EXPIRED"
            assert db.query(Product).filter(Product.tenant_id == tenant_id).count() == 3
            early = (
                db.query(OutboxEvent)
                .filter(OutboxEvent.tenant_id == tenant_id, OutboxEvent.event_name == "TRIAL_REMINDER")
                .all()
            )
            assert [event.payload.get("early") for event in early] == [True]
            # The scheduler sends no second "trial ended" email.
            queue_trial_reminders(db)
            db.commit()
            assert (
                db.query(OutboxEvent)
                .filter(OutboxEvent.tenant_id == tenant_id, OutboxEvent.event_name == "TRIAL_REMINDER")
                .count()
                == 1
            )
        finally:
            db.close()
        assert user.get("/api/v1/trial/status").status_code == 403

        deleted = admin.post(f"{path}/delete-data")
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["data_deleted"] is True and ended[0][0][0] == email
        assert admin.post(f"{path}/delete-data").status_code == 409
        db = SessionLocal()
        try:
            assert db.query(Product).filter(Product.tenant_id == tenant_id).count() == 0
            # An archived trial gets no more reminders.
            queue_trial_reminders(db)
            db.commit()
            assert db.query(OutboxEvent).filter(OutboxEvent.tenant_id == tenant_id).count() == 0
        finally:
            db.close()
    finally:
        _forget_exit_requests([tenant_id])
        # Reminders this test queued for other trial workspaces in the test database.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM event_outbox WHERE event_name = 'TRIAL_REMINDER' AND occurred_at >= :started "
                    "AND tenant_id IN (SELECT id FROM tenants WHERE tenant_key LIKE :pattern)"
                ),
                {"started": started, "pattern": "TRIAL\\_%"},
            )
