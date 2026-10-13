"""Readiness end to end: each inspection check from known records (hidden complaints, backlog past target, reporting
clocks, trends without CAPA or risk review, harm complaints closed without a case, CAPAs without a verified effect,
signals past their triage date), the four home numbers, the management review summary and its PDF (permission, audit),
and organization isolation.

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
from backend.app.db.models.foundation import AuditEvent, AuthUser, Capa, Complaint, Product, TenantMembership
from backend.app.db.models.signals import Signal
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from backend.app.main import app

PASSWORD = "Readiness checks 2026!"
REASON = "From our complaint handling procedure QP-08 rev 4"
NOW = datetime.now(timezone.utc)


def _organization(label: str):
    from backend.app.customer_lifecycle import build_customer_tenant

    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db,
            tenant_key=f"READY_{label}_{uuid.uuid4().hex[:6].upper()}",
            name=f"Readiness {label}",
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
            username=f"ready-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name=f"{role.title()} Ready",
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


def _product(tenant_id) -> str:
    tag = uuid.uuid4().hex[:8].upper()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_identifier=f"RD-P-{tag}",
            name=f"Ready Pump {tag}",
            created_at=NOW,
            updated_at=NOW,
        )
        db.add(product)
        db.commit()
        return str(product.id)


def _complaint(tenant_id, product_id: str, *, days_ago: int, **fields) -> str:
    moment = NOW - timedelta(days=days_ago)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = Complaint(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            complaint_identifier=f"RD-C-{uuid.uuid4().hex[:10].upper()}",
            product_id=uuid.UUID(product_id),
            complaint_timestamp=moment,
            awareness_timestamp=moment,
            recorded_timestamp=moment,
            event_timestamp=moment,
            description=fields.pop("description", "Device stopped during use"),
            status=fields.pop("status", "open"),
            created_at=moment,
            updated_at=moment,
            **fields,
        )
        db.add(row)
        db.commit()
        return str(row.id)


@pytest.fixture(scope="module")
def org():
    from backend.app.trial.retention import purge_trial

    tenant_id = _organization("A")
    other_id = _organization("B")
    clients = {
        "lead": _client(tenant_id, "TRIAGE_LEAD"),
        "investigator": _client(tenant_id, "INVESTIGATOR"),
        "regulatory": _client(tenant_id, "REGULATORY_REVIEWER"),
        "viewer": _client(tenant_id, "VIEWER"),
        "other": _client(other_id, "VIEWER"),
    }
    try:
        yield {"tenant_id": tenant_id, "other_id": other_id, **clients}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:readiness-cleanup")
            purge_trial(db, other_id, "test:readiness-cleanup")


@pytest.fixture(scope="module")
def seeded(org):
    """One known record behind each check."""
    tenant, product = org["tenant_id"], _product(org["tenant_id"])
    fda = org["viewer"].get("/api/v1/complaints/reportability-settings").json()["templates"][0]
    saved = org["regulatory"].put(
        "/api/v1/complaints/reportability-settings", json={"windows": [fda], "lookback_days": 365, "reason": REASON}
    )
    assert saved.status_code == 200, saved.text
    ids = {
        "hidden": _complaint(tenant, product, days_ago=6, status="Cancelled", death=True, country="US"),
        "past_target": _complaint(tenant, product, days_ago=40, country="US"),
        "due_soon": _complaint(tenant, product, days_ago=28, country="US", death=True),
        "harm_closed": _complaint(
            tenant, product, days_ago=20, status="Closed", serious_injury=True, country="Germany"
        ),
    }
    lead = org["lead"]
    signal = lead.post(
        "/api/v1/triage/signals",
        json={
            "title": "Stops during use",
            "product_id": product,
            "complaint_ids": [_complaint(tenant, product, days_ago=3), _complaint(tenant, product, days_ago=4)],
        },
    )
    assert signal.status_code == 201, signal.text
    opened = org["investigator"].post(
        f"/api/v1/triage/signals/{signal.json()['id']}/open-case",
        json={"investigation_question": "Why does the device stop during use?"},
    )
    assert opened.status_code == 201, opened.text
    waiting = lead.post(
        "/api/v1/triage/signals",
        json={"title": "Waiting for triage", "product_id": product, "complaint_ids": []},
    )
    assert waiting.status_code == 201, waiting.text
    with SessionLocal() as db:
        bind_tenant(db, tenant)
        decided = db.query(Signal).filter(Signal.id == uuid.UUID(signal.json()["id"])).one()
        decided.status = "DECISION_RECORDED"  # its case decided, with no CAPA and no risk review
        late = db.query(Signal).filter(Signal.id == uuid.UUID(waiting.json()["id"])).one()
        late.due_at = NOW - timedelta(days=2)
        db.add(
            Capa(
                id=uuid.uuid4(),
                tenant_id=tenant,
                capa_identifier=f"RD-CAPA-{uuid.uuid4().hex[:6]}",
                title="Closed without a check",
                product_id=uuid.UUID(product),
                status="Closed",
                opened_at=NOW - timedelta(days=90),
                due_at=NOW - timedelta(days=30),
                created_at=NOW,
                updated_at=NOW,
            )
        )
        db.commit()
    return {**ids, "product": product, "case_id": opened.json()["investigation"]["id"], "signal": signal.json()["id"]}


def _checks(client) -> dict:
    response = client.get("/api/v1/readiness")
    assert response.status_code == 200, response.text
    return {check["code"]: check for check in response.json()["checks"]}


def test_every_check_reads_the_records_behind_it(org, seeded):
    body = org["viewer"].get("/api/v1/readiness").json()
    assert [check["code"] for check in body["home"]] == [
        "COMPLAINTS_TO_RECHECK",
        "COMPLAINTS_PAST_TARGET",
        "REPORTING_CLOCKS",
        "TRENDS_WITHOUT_ACTION",
    ]
    checks = {check["code"]: check for check in body["checks"]}
    assert (checks["COMPLAINTS_TO_RECHECK"]["value"], checks["COMPLAINTS_TO_RECHECK"]["state"]) == (1, "CRITICAL")
    assert checks["COMPLAINTS_TO_RECHECK"]["items"][0]["id"] == seeded["hidden"]
    assert checks["COMPLAINTS_TO_RECHECK"]["opens"] == {"section": "Complaints", "tab": "Second look"}
    assert (checks["COMPLAINTS_PAST_TARGET"]["value"], checks["COMPLAINTS_PAST_TARGET"]["state"]) == (1, "CRITICAL")
    assert checks["COMPLAINTS_PAST_TARGET"]["items"][0]["id"] == seeded["past_target"]
    clocks = checks["REPORTING_CLOCKS"]
    assert (clocks["value"], clocks["state"], clocks["due_soon"], clocks["overdue"]) == (1, "ATTENTION", 1, 0)
    assert clocks["items"][0]["id"] == seeded["due_soon"]
    trends = checks["TRENDS_WITHOUT_ACTION"]
    assert (trends["value"], trends["state"], trends["decided_without_action"]) == (1, "CRITICAL", 1)
    assert trends["items"][0]["id"] == seeded["signal"]
    harm = checks["HARM_CLOSED_WITHOUT_CASE"]
    assert (harm["value"], harm["state"]) == (1, "CRITICAL") and harm["items"][0]["id"] == seeded["harm_closed"]
    capa = checks["CAPA_EFFECTIVENESS"]
    assert (capa["value"], capa["state"]) == (1, "CRITICAL")
    triage = checks["TRIAGE_OVERDUE"]
    assert (triage["value"], triage["state"]) == (1, "ATTENTION")
    assert all(check["why"] for check in body["checks"])
    # A number never contradicts its state: zero is clear (or not set up), never a finding.
    assert all(check["value"] or check["state"] in ("CLEAR", "NOT_SET") for check in body["checks"])
    # Harm complaints of a product with no risk review: post-market data not in the risk file.
    risk = checks["RISK_FILE_INPUT"]
    assert (risk["value"], risk["state"]) == (1, "CRITICAL") and risk["items"][0]["id"] == seeded["product"]
    assert body["summary"]["checks"] == 8 and body["summary"]["critical"] == 6


def test_a_capa_on_the_decided_case_clears_the_trend_check(org, seeded):
    tenant = org["tenant_id"]
    with SessionLocal() as db:
        bind_tenant(db, tenant)
        db.add(
            Capa(
                id=uuid.uuid4(),
                tenant_id=tenant,
                capa_identifier=f"RD-CAPA-{uuid.uuid4().hex[:6]}",
                title="Fix the stop",
                product_id=uuid.UUID(seeded["product"]),
                investigation_id=uuid.UUID(seeded["case_id"]),
                status="open",
                opened_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        db.commit()
    trends = _checks(org["viewer"])["TRENDS_WITHOUT_ACTION"]
    assert (trends["value"], trends["state"]) == (0, "CLEAR")


def test_the_summary_for_management_review(org, seeded):
    summary = org["viewer"].get("/api/v1/readiness/summary", params={"period_days": 90}).json()
    assert summary["period"]["days"] == 90
    complaints = summary["complaints"]
    assert complaints["received"] == 6 and complaints["closed"] == 1
    assert (complaints["death"], complaints["serious_injury"]) == (2, 1)
    assert summary["reporting"]["windows"] == ["FDA MDR: death, serious injury or malfunction (30 calendar days)"]
    assert summary["trends"]["signals_raised"] == 2
    assert org["viewer"].get("/api/v1/readiness/summary", params={"period_days": 5}).status_code == 422

    assert org["viewer"].get("/api/v1/readiness/summary.pdf").status_code == 403
    pdf = org["lead"].get("/api/v1/readiness/summary.pdf", params={"period_days": 90})
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["content-disposition"].startswith('attachment; filename="mdarix-readiness-summary-')
    assert pdf.content.startswith(b"%PDF")
    from reports.pdf import page_count

    assert page_count(pdf.content) >= 1
    assert b"Readiness today" in pdf.content and b"Reporting to regulatory authorities" in pdf.content
    with SessionLocal() as db:
        bind_system(db, "test: read the audit trail")
        assert (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == org["tenant_id"], AuditEvent.action == "READINESS_SUMMARY_EXPORTED")
            .count()
            == 1
        )


def test_another_organization_sees_none_of_this(org, seeded):
    checks = _checks(org["other"])
    assert all(check["value"] in (0, None) for check in checks.values())
    # Without reporting windows the clocks are "not set up", the finding itself.
    assert checks["REPORTING_CLOCKS"]["state"] == "NOT_SET"
    assert checks["REPORTING_CLOCKS"]["opens"] == {"section": "Complaints", "tab": "Reporting windows"}
    assert org["other"].get("/api/v1/readiness/summary").json()["complaints"]["received"] == 0
