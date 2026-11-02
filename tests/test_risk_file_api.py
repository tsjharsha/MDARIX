"""Post-market data and the risk file end to end: each product's state from known records (not reviewed, reviewed,
no risks in MDARIX, quiet), each risk with the risk reviews that assessed it, the readiness check, the state rules for
open and overdue reassessments, organization isolation and validation.

Everything runs in fresh organizations of their own (on the shared plane), deleted at the end.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from auth.durable import persist_session
from auth.service import _hash
from backend.app.db.models.foundation import (
    AuthUser,
    Complaint,
    InvestigationComplaint,
    Product,
    Risk,
    TenantMembership,
)
from backend.app.db.models.reviews import CaseReview
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.main import app
from backend.app.post_market import risk_file

PASSWORD = "Risk file input 2026!"
NOW = datetime.now(timezone.utc)
BOARD = "/api/v1/post-market/risk-file"


def _organization(label: str):
    from backend.app.customer_lifecycle import build_customer_tenant

    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db,
            tenant_key=f"RISKFILE_{label}_{uuid.uuid4().hex[:6].upper()}",
            name=f"Risk file {label}",
            status="ACTIVE",
            now=NOW,
        )
        db.add(customer)
        db.add(tenant)
        db.commit()
        return tenant.id


def _client(tenant_id, role: str) -> TestClient:
    with SessionLocal() as db:
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=f"riskfile-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name=f"{role.title()} Riskfile",
            company="Test",
            password_hash=_hash(PASSWORD),
            role=role,
            status="ACTIVE",
            email_verified=True,
            created_at=NOW,
            updated_at=NOW,
        )
        db.add(user)
        db.flush()
        db.add(
            TenantMembership(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=user.id,
                status="ACTIVE",
                is_default=True,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        db.commit()
        token = secrets.token_urlsafe(32)
        persist_session(db, token, user.id, tenant_id)
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    return client


@pytest.fixture(scope="module")
def org():
    from backend.app.trial.retention import purge_trial

    tenant_id = _organization("A")
    other_id = _organization("B")
    try:
        yield {
            "tenant_id": tenant_id,
            "investigator": _client(tenant_id, "INVESTIGATOR"),
            "viewer": _client(tenant_id, "VIEWER"),
            "other": _client(other_id, "VIEWER"),
        }
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:risk-file-cleanup")
            purge_trial(db, other_id, "test:risk-file-cleanup")


def _product(tenant_id, name: str, risks: int = 0) -> tuple[str, list[str]]:
    tag = uuid.uuid4().hex[:6].upper()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_identifier=f"RF-P-{tag}",
            name=f"{name} {tag}",
            created_at=NOW,
            updated_at=NOW,
        )
        db.add(product)
        db.flush()
        risk_ids = []
        for index in range(risks):
            risk = Risk(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                risk_identifier=f"RF-R-{tag}-{index}",
                product_id=product.id,
                description=f"Hazard {index}: delayed therapy",
                created_at=NOW,
                updated_at=NOW,
            )
            db.add(risk)
            risk_ids.append(str(risk.id))
        db.commit()
        return str(product.id), risk_ids


def _complaint(tenant_id, product_id: str, *, days_ago: int = 10, **flags) -> str:
    moment = NOW - timedelta(days=days_ago)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = Complaint(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            complaint_identifier=f"RF-C-{uuid.uuid4().hex[:10].upper()}",
            product_id=uuid.UUID(product_id),
            complaint_timestamp=moment,
            event_timestamp=moment,
            description="Therapy interrupted",
            status="open",
            created_at=moment,
            updated_at=moment,
            **flags,
        )
        db.add(row)
        db.commit()
        return str(row.id)


def _reviewed(org, product_id: str, complaint_id: str, risk_ids: list[str], outcome="NO_CHANGE_REQUIRED"):
    case = org["investigator"].post(
        "/api/v1/investigations",
        json={
            "product_id": product_id,
            "investigation_question": "Does this harm change the risk file?",
            "complaint_ids": [complaint_id],
        },
    )
    assert case.status_code in (200, 201), case.text
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        case_id = (
            db.query(InvestigationComplaint.investigation_id)
            .filter(InvestigationComplaint.complaint_id == uuid.UUID(complaint_id))
            .scalar()
        )
        db.add(
            CaseReview(
                tenant_id=org["tenant_id"],
                investigation_id=case_id,
                review_type="RISK",
                status="COMPLETED",
                requested_by="test",
                outcome=outcome,
                rationale="Assessed against the risk register",
                assessed={"risk_ids": risk_ids, "markets": [], "notes": None},
                completed_at=NOW - timedelta(days=2),
            )
        )
        db.commit()
    return case.json()


def test_each_product_shows_whether_its_field_data_reached_the_risk_file(org):
    tenant = org["tenant_id"]
    unreviewed, _ = _product(tenant, "Unreviewed Pump", risks=2)
    _complaint(tenant, unreviewed, serious_injury=True)
    reviewed, risks = _product(tenant, "Reviewed Pump", risks=2)
    harm = _complaint(tenant, reviewed, death=True)
    case = _reviewed(org, reviewed, harm, [risks[0]])
    no_register, _ = _product(tenant, "Unregistered Pump", risks=0)
    _reviewed(org, no_register, _complaint(tenant, no_register, malfunction=True), [])
    quiet, _ = _product(tenant, "Quiet Pump", risks=1)
    _complaint(tenant, quiet)  # no harm, no malfunction

    board = org["viewer"].get(BOARD).json()
    states = {item["product"]["id"]: item["state"] for item in board["items"]}
    assert states[unreviewed] == "NOT_REVIEWED"
    assert states[reviewed] == "REVIEWED"
    assert states[no_register] == "NO_RISK_REGISTER"
    assert states[quiet] == "QUIET"
    assert board["items"][0]["product"]["id"] == unreviewed  # the most urgent first
    assert board["summary"]["not_reviewed"] == 1 and board["summary"]["reviewed"] == 1
    item = next(entry for entry in board["items"] if entry["product"]["id"] == reviewed)
    assert item["post_market"]["harm"] == 1 and item["risk_file"]["risk_reviews"] == 1
    assert (item["risk_file"]["risks"], item["risk_file"]["risks_assessed"]) == (2, 1)

    detail = org["viewer"].get(f"{BOARD}/{reviewed}").json()
    by_id = {risk["id"]: risk for risk in detail["risks"]}
    assert by_id[risks[0]]["assessed"][0]["case"] == case["business_id"]
    assert by_id[risks[1]]["assessed"] == []
    assert detail["risks"][0]["id"] == risks[1]  # risks never assessed first
    assert detail["reviews"][0]["risks_assessed"] == 1

    readiness = {check["code"]: check for check in org["viewer"].get("/api/v1/readiness").json()["checks"]}
    risk_check = readiness["RISK_FILE_INPUT"]
    assert (risk_check["value"], risk_check["state"]) == (2, "CRITICAL")
    assert risk_check["opens"].items() >= {"section": "Records", "tab": "Risk file input"}.items()
    assert {entry["id"] for entry in risk_check["items"]} == {unreviewed, no_register}


def test_isolation_and_validation(org):
    product, _ = _product(org["tenant_id"], "Private Pump")
    assert org["other"].get(f"{BOARD}/{product}").status_code == 404
    assert all(item["product"]["id"] != product for item in org["other"].get(BOARD).json()["items"])
    assert org["viewer"].get(BOARD, params={"period_days": 30}).status_code == 422
    assert org["viewer"].get(f"{BOARD}/{uuid.uuid4()}").status_code == 404


@pytest.mark.parametrize(
    "facts,state",
    [
        ({"matters": True, "reviewed": False, "overdue": 1, "open_count": 1, "risks": 3}, "NOT_REVIEWED"),
        ({"matters": True, "reviewed": True, "overdue": 1, "open_count": 1, "risks": 3}, "REASSESSMENT_OVERDUE"),
        ({"matters": False, "reviewed": False, "overdue": 0, "open_count": 2, "risks": 3}, "REASSESSMENT_OPEN"),
        ({"matters": True, "reviewed": True, "overdue": 0, "open_count": 0, "risks": 0}, "NO_RISK_REGISTER"),
        ({"matters": True, "reviewed": True, "overdue": 0, "open_count": 0, "risks": 3}, "REVIEWED"),
        ({"matters": False, "reviewed": False, "overdue": 0, "open_count": 0, "risks": 0}, "QUIET"),
    ],
)
def test_the_state_rules(facts, state):
    assert risk_file.state_of(**facts) == state
