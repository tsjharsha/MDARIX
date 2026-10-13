"""Complaint review end to end: the second look (what it flags and in which order), a person's decision and its
revision with the audit trail, the backlog board (open complaints in no signal and no case, against the target),
a confirmed record joining the backlog, the organization's settings, permissions and organization isolation.

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
from backend.app.db.models.foundation import AuditEvent, AuthUser, Complaint, Product, TenantMembership
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.main import app

PASSWORD = "Complaint review 2026!"
REASON = "Reviewed the record against our complaint definition"
SECOND_LOOK = "/api/v1/complaints/second-look"
BACKLOG = "/api/v1/complaints/backlog"
SETTINGS = "/api/v1/complaints/review-settings"


def _organization(label: str):
    from backend.app.customer_lifecycle import build_customer_tenant

    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db,
            tenant_key=f"REVIEW_{label}_{uuid.uuid4().hex[:6].upper()}",
            name=f"Complaint review {label}",
            status="ACTIVE",
            now=datetime.now(timezone.utc),
        )
        db.add(customer)
        db.add(tenant)
        db.commit()
        return tenant.id


def _client(tenant_id, role: str) -> TestClient:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=f"review-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name=f"{role.title()} Review",
            company="Test",
            password_hash=_hash(PASSWORD),
            role=role,
            status="ACTIVE",
            email_verified=True,
            created_at=now,
            updated_at=now,
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
                created_at=now,
                updated_at=now,
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
    clients = {
        "lead": _client(tenant_id, "TRIAGE_LEAD"),
        "investigator": _client(tenant_id, "INVESTIGATOR"),
        "viewer": _client(tenant_id, "VIEWER"),
        "admin": _client(tenant_id, "CUSTOMER_ADMIN"),
        "other_lead": _client(other_id, "TRIAGE_LEAD"),
    }
    try:
        yield {"tenant_id": tenant_id, "other_id": other_id, **clients}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:complaint-review-cleanup")
            purge_trial(db, other_id, "test:complaint-review-cleanup")


def _product(tenant_id) -> str:
    now = datetime.now(timezone.utc)
    tag = uuid.uuid4().hex[:8].upper()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_identifier=f"REV-P-{tag}",
            name=f"Review Pump {tag}",
            created_at=now,
            updated_at=now,
        )
        db.add(product)
        db.commit()
        return str(product.id)


def _complaint(tenant_id, product_id: str, *, days_ago: int = 5, description: str = "Casing colour", **fields) -> str:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = Complaint(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            complaint_identifier=f"REV-C-{uuid.uuid4().hex[:10].upper()}",
            product_id=uuid.UUID(product_id),
            complaint_timestamp=now - timedelta(days=days_ago),
            description=description,
            status=fields.pop("status", "open"),
            created_at=now,
            updated_at=now,
            **fields,
        )
        db.add(row)
        db.commit()
        return str(row.id)


def _ids(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


def test_the_second_look_flags_hidden_complaints_most_serious_first(org):
    tenant, product = org["tenant_id"], _product(org["tenant_id"])
    death = _complaint(tenant, product, status="Cancelled", death=True, days_ago=10)
    choking = _complaint(tenant, product, complaint_type="Inquiry", description="Patient was choking on the tube")
    _complaint(tenant, product, status="Cancelled")  # cancelled, but nothing suggests a complaint
    nff = [_complaint(tenant, product, status="closed", problem_code="NFF", days_ago=days) for days in (20, 40, 60)]
    _complaint(tenant, product, death=True)  # an ordinary open complaint: not a second-look record

    response = org["viewer"].get(SECOND_LOOK, params={"product_id": product})
    ids = _ids(response)
    assert ids[0] == death
    assert set(ids) == {death, choking, *nff}
    body = response.json()
    assert body["summary"]["to_review"] == 5
    assert body["summary"]["with_harm"] == 1
    assert body["summary"]["by_reason"] == {"CANCELLED": 1, "INQUIRY": 1, "NFF_RECURRING": 3}
    first = body["items"][0]
    assert first["reasons"][0]["label"] == "Cancelled or rejected (status: Cancelled)"
    assert first["signs"] == [{"code": "DEATH", "label": "Death reported"}]
    assert first["decision"] is None
    flagged = next(item for item in body["items"] if item["id"] == choking)
    assert flagged["words"] == ["choking"]


def test_a_person_decides_and_may_revise_with_the_audit_trail(org):
    tenant, product = org["tenant_id"], _product(org["tenant_id"])
    record = _complaint(tenant, product, status="Void", serious_injury=True)
    ordinary = _complaint(tenant, product, serious_injury=True)
    path = f"/api/v1/complaints/{record}/second-look"
    confirm = {"decision": "CONFIRMED", "reason": REASON}

    assert org["viewer"].post(path, json=confirm).status_code == 403
    assert org["admin"].post(path, json=confirm).status_code == 403
    short = org["investigator"].post(path, json={"decision": "CONFIRMED", "reason": "yes"})
    assert short.status_code == 422
    unknown = org["investigator"].post(path, json={"decision": "MAYBE", "reason": REASON})
    assert unknown.status_code == 422

    decided = org["investigator"].post(path, json=confirm)
    assert decided.status_code == 200, decided.text
    assert decided.json()["decision"]["decision"] == "CONFIRMED"
    assert decided.json()["decision"]["decided_by"] == "Investigator Review"
    again = org["investigator"].post(path, json=confirm)
    assert again.status_code == 422 and again.json()["detail"]["code"] == "NOTHING_TO_CHANGE"
    revised = org["lead"].post(path, json={"decision": "DISMISSED", "reason": "A duplicate of a record already open"})
    assert revised.status_code == 200
    assert revised.json()["decision"]["decision"] == "DISMISSED"

    assert record not in _ids(org["viewer"].get(SECOND_LOOK, params={"product_id": product}))
    decided_list = org["viewer"].get(SECOND_LOOK, params={"product_id": product, "state": "decided"}).json()
    assert [item["id"] for item in decided_list["items"]] == [record]
    assert decided_list["items"][0]["decision"]["reason"] == "A duplicate of a record already open"

    with SessionLocal() as db:
        bind_tenant(db, tenant)
        actions = [
            row.action
            for row in db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant, AuditEvent.entity_id == uuid.UUID(record))
            .order_by(AuditEvent.created_at)
        ]
    assert "COMPLAINT_SECOND_LOOK_DECIDED" in actions and "COMPLAINT_SECOND_LOOK_REVISED" in actions

    not_flagged = org["investigator"].post(f"/api/v1/complaints/{ordinary}/second-look", json=confirm)
    assert not_flagged.status_code == 409 and not_flagged.json()["detail"]["code"] == "NOT_ON_SECOND_LOOK"
    missing = org["investigator"].post(f"/api/v1/complaints/{uuid.uuid4()}/second-look", json=confirm)
    assert missing.status_code == 404


def test_the_backlog_board_shows_open_complaints_in_no_signal_and_no_case(org):
    tenant, product = org["tenant_id"], _product(org["tenant_id"])
    old = _complaint(tenant, product, days_ago=40)
    due = _complaint(tenant, product, days_ago=26)
    fresh = _complaint(tenant, product, days_ago=3)
    _complaint(tenant, product, status="Closed", days_ago=50)
    cancelled = _complaint(tenant, product, status="Cancelled", death=True, days_ago=50)
    inquiry = _complaint(tenant, product, complaint_type="Service request", days_ago=50)
    in_signal = _complaint(tenant, product, days_ago=45)
    in_case = _complaint(tenant, product, days_ago=45)
    signal = org["lead"].post(
        "/api/v1/triage/signals",
        json={"title": "Backlog test signal", "product_id": product, "complaint_ids": [in_signal]},
    )
    assert signal.status_code == 201, signal.text
    case = org["investigator"].post(
        "/api/v1/investigations",
        json={
            "product_id": product,
            "investigation_question": "Why do these complaints recur?",
            "complaint_ids": [in_case],
        },
    )
    assert case.status_code in (200, 201), case.text

    response = org["viewer"].get(BACKLOG, params={"product_id": product})
    assert _ids(response) == [old, due, fresh]
    body = response.json()
    assert [item["state"] for item in body["items"]] == ["PAST_TARGET", "DUE_SOON", "ON_TRACK"]
    assert body["items"][0]["days_past_target"] == 10
    assert body["summary"]["target_days"] == 30
    assert body["summary"]["open_unlinked"] == 3
    assert (body["summary"]["past_target"], body["summary"]["due_soon"], body["summary"]["on_track"]) == (1, 1, 1)
    assert body["summary"]["oldest_days"] == 40
    assert {band["band"]: band["count"] for band in body["summary"]["bands"]} == {
        "0-30": 2,
        "31-60": 1,
        "61-90": 0,
        "90+": 0,
    }
    assert _ids(org["viewer"].get(BACKLOG, params={"product_id": product, "show": "past_target"})) == [old]

    # Confirmed on the second look, the cancelled record is a complaint: it joins the backlog, past its target.
    confirmed = org["lead"].post(
        f"/api/v1/complaints/{cancelled}/second-look", json={"decision": "CONFIRMED", "reason": REASON}
    )
    assert confirmed.status_code == 200
    items = org["viewer"].get(BACKLOG, params={"product_id": product}).json()["items"]
    joined = next(item for item in items if item["id"] == cancelled)
    assert joined["confirmed_on_second_look"] is True and joined["state"] == "PAST_TARGET"
    assert inquiry not in [item["id"] for item in items]


def test_the_organization_sets_its_target_and_words(org):
    tenant, product = org["tenant_id"], _product(org["tenant_id"])
    record = _complaint(tenant, product, status="Void", description="Casing discoloured after cleaning", days_ago=12)
    assert org["viewer"].get(SETTINGS).json()["backlog_target_days"] == 30
    change = {"backlog_target_days": 10, "second_look_words": ["Discoloured", " discoloured "], "reason": REASON}
    try:
        assert org["viewer"].put(SETTINGS, json=change).status_code == 403
        assert org["investigator"].put(SETTINGS, json=change).status_code == 403
        changed = org["lead"].put(SETTINGS, json=change)
        assert changed.status_code == 200, changed.text
        settings = changed.json()
        assert settings["backlog_target_days"] == 10 and settings["second_look_words"] == ["discoloured"]
        assert settings["custom_words"] is True and settings["version"] == 1
        assert settings["updated_by_name"] == "Triage_Lead Review"
        assert org["viewer"].get(SETTINGS).json()["updated_by_name"] == "Triage_Lead Review"
        same = org["lead"].put(SETTINGS, json=change)
        assert same.status_code == 422 and same.json()["detail"]["code"] == "NOTHING_TO_CHANGE"
        empty = org["lead"].put(SETTINGS, json={**change, "second_look_words": []})
        assert empty.status_code == 422 and empty.json()["detail"]["code"] == "WORDS_INVALID"
        assert org["lead"].put(SETTINGS, json={**change, "backlog_target_days": 0}).status_code == 422

        # The organization's words flag the record; the default words did not.
        assert record in _ids(org["viewer"].get(SECOND_LOOK, params={"product_id": product}))
    finally:
        reset = org["lead"].put(
            SETTINGS, json={"backlog_target_days": 30, "second_look_words": None, "reason": "Back to the defaults"}
        )
        assert reset.status_code == 200
        assert reset.json()["custom_words"] is False and reset.json()["version"] == 2


def test_another_organization_sees_and_decides_nothing_of_this_one(org):
    tenant, product = org["tenant_id"], _product(org["tenant_id"])
    record = _complaint(tenant, product, status="Cancelled", death=True)
    assert record not in _ids(org["other_lead"].get(SECOND_LOOK))
    assert record not in _ids(org["other_lead"].get(BACKLOG))
    refused = org["other_lead"].post(
        f"/api/v1/complaints/{record}/second-look", json={"decision": "DISMISSED", "reason": REASON}
    )
    assert refused.status_code == 404
