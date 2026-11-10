"""Reporting and CAPA end to end: the reporting windows (set by the organization, versioned), the reportability watch
(clocks against those windows, missing answers, what it leaves out, most urgent first), a person's decision with its
timeliness and the audit trail, a case's completed regulatory review settling a complaint, the reminder sweep, and the
CAPA effectiveness check (the board, the recurrence, planning and re-planning, the signed result with its signature
record, rounds, permissions) and organization isolation.

Everything runs in fresh organizations of their own (on the shared plane), deleted at the end.
"""

from __future__ import annotations

import secrets
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from datetime import time as clock_time

import pytest
from fastapi.testclient import TestClient

from auth import totp
from auth.durable import persist_session
from auth.service import _hash
from backend.app.db.models.capa_effectiveness import CapaEffectivenessCheck
from backend.app.db.models.foundation import (
    AuditEvent,
    AuthUser,
    Capa,
    Complaint,
    InvestigationComplaint,
    Product,
    SignedApprovalRecord,
    TenantMembership,
)
from backend.app.db.models.reviews import CaseReview
from backend.app.db.models.workflow import WorkflowTask
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from backend.app.main import app
from backend.app.reportability import rules as watch_rules

PASSWORD = "Reporting and CAPA 2026!"
REASON = "From our complaint handling procedure QP-08 rev 4"
WATCH = "/api/v1/complaints/reportability"
SETTINGS = "/api/v1/complaints/reportability-settings"
BOARD = "/api/v1/capas/effectiveness"
TODAY = datetime.now(timezone.utc).date()


def _organization(label: str):
    from backend.app.customer_lifecycle import build_customer_tenant

    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db,
            tenant_key=f"REPORTING_{label}_{uuid.uuid4().hex[:6].upper()}",
            name=f"Reporting and CAPA {label}",
            status="ACTIVE",
            now=datetime.now(timezone.utc),
        )
        db.add(customer)
        db.add(tenant)
        db.commit()
        return tenant.id


def _client(tenant_id, role: str, name: str | None = None) -> TestClient:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=f"reporting-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name=name or f"{role.title()} Reporting",
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
        "regulatory": _client(tenant_id, "REGULATORY_REVIEWER", "Rita Regulatory"),
        "approver": _client(tenant_id, "APPROVER", "Alex Approver"),
        "reviewer": _client(tenant_id, "REVIEWER", "Quinn Quality"),
        "investigator": _client(tenant_id, "INVESTIGATOR"),
        "viewer": _client(tenant_id, "VIEWER"),
        "admin": _client(tenant_id, "CUSTOMER_ADMIN"),
        "other": _client(other_id, "REGULATORY_REVIEWER"),
    }
    try:
        yield {"tenant_id": tenant_id, "other_id": other_id, **clients}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:reporting-capa-cleanup")
            purge_trial(db, other_id, "test:reporting-capa-cleanup")


@pytest.fixture(scope="module")
def windows(org):
    """The FDA 30-day and EU 15-day templates, saved by the regulatory reviewer."""
    settings = org["viewer"].get(SETTINGS).json()
    chosen = [settings["templates"][0], settings["templates"][1]]
    saved = org["regulatory"].put(SETTINGS, json={"windows": chosen, "lookback_days": 365, "reason": REASON})
    assert saved.status_code == 200, saved.text
    return saved.json()


def _product(tenant_id) -> str:
    now = datetime.now(timezone.utc)
    tag = uuid.uuid4().hex[:8].upper()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_identifier=f"RCP-P-{tag}",
            name=f"Report Pump {tag}",
            created_at=now,
            updated_at=now,
        )
        db.add(product)
        db.commit()
        return str(product.id)


def _complaint(tenant_id, product_id: str, *, aware_days_ago: int = 5, **fields) -> str:
    now = datetime.now(timezone.utc)
    # Noon UTC of that day: the same day in New York, Brussels, London and India, so a market's day count (0.10.63,
    # awareness taken in the market's time zone) does not depend on the hour the suite runs.
    aware = (
        now
        if not aware_days_ago
        else datetime.combine((now - timedelta(days=aware_days_ago)).date(), clock_time(12), timezone.utc)
    )
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = Complaint(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            complaint_identifier=f"RCP-C-{uuid.uuid4().hex[:10].upper()}",
            product_id=uuid.UUID(product_id),
            complaint_timestamp=fields.pop("received", aware),
            awareness_timestamp=fields.pop("awareness", aware),
            recorded_timestamp=fields.pop("recorded", aware),
            description=fields.pop("description", "Pump alarm during therapy"),
            status=fields.pop("status", "open"),
            created_at=now,
            updated_at=now,
            **fields,
        )
        db.add(row)
        db.commit()
        return str(row.id)


def _items(response) -> list[dict]:
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _ids(response) -> list[str]:
    return [item["id"] for item in _items(response)]


def _actions(tenant_id, entity_id) -> list[str]:
    with SessionLocal() as db:
        bind_system(db, "test: read the audit trail")
        return [
            row.action
            for row in db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.entity_id == uuid.UUID(str(entity_id)))
            .order_by(AuditEvent.created_at)
        ]


# ------------------------------------------------------------------------------------------- reporting windows


def test_the_organization_enters_its_own_windows(org, windows):
    assert [window["name"] for window in windows["windows"]] == [
        watch_rules.TEMPLATES[0]["name"],
        watch_rules.TEMPLATES[1]["name"],
    ]
    assert windows["configured"] is True and windows["version"] == 1
    # Each window keeps its template's regulatory basis (backend/app/standards.py).
    assert [window["basis"] for window in windows["windows"]] == [["CFR803_50", "CFR803_53"], ["MDR_87"]]
    assert windows["updated_by_name"] == "Rita Regulatory"
    body = {"windows": windows["windows"], "lookback_days": 365, "reason": REASON}
    assert org["investigator"].put(SETTINGS, json=body).status_code == 403
    assert org["reviewer"].put(SETTINGS, json=body).status_code == 403
    same = org["regulatory"].put(SETTINGS, json=body)
    assert same.status_code == 422 and same.json()["detail"]["code"] == "NOTHING_TO_CHANGE"
    bad = org["regulatory"].put(SETTINGS, json={**body, "windows": [{**windows["windows"][0], "triggers": []}]})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "WINDOWS_INVALID"
    assert org["regulatory"].put(SETTINGS, json={**body, "reason": "short"}).status_code == 422
    # Another organization has none.
    assert org["other"].get(SETTINGS).json()["configured"] is False


# ------------------------------------------------------------------------------------------- the watch


def test_the_watch_runs_clocks_against_the_windows_most_urgent_first(org, windows):
    tenant, product = org["tenant_id"], _product(org["tenant_id"])
    overdue = _complaint(tenant, product, aware_days_ago=40, country="US", malfunction=True)
    due_soon = _complaint(tenant, product, aware_days_ago=28, country="USA", death=True, serious_injury=False)
    running = _complaint(tenant, product, aware_days_ago=3, country="France", serious_injury=True)
    no_window = _complaint(tenant, product, aware_days_ago=3, country="Japan", death=True)
    follow_up = _complaint(tenant, product, aware_days_ago=2, country="US", patient_involved=True)
    _complaint(tenant, product, aware_days_ago=10, country="US", status="Cancelled", death=True)
    _complaint(tenant, product, aware_days_ago=10, country="US")  # reports nothing
    _complaint(tenant, product, aware_days_ago=400, country="US", death=True)  # before the look-back

    response = org["viewer"].get(WATCH, params={"product_id": product})
    assert _ids(response) == [overdue, due_soon, running, no_window, follow_up]
    items = {item["id"]: item for item in response.json()["items"]}
    assert items[overdue]["state"] == "OVERDUE" and items[overdue]["binding"]["days_left"] == -10
    assert items[due_soon]["state"] == "DUE_SOON" and items[due_soon]["binding"]["days_left"] == 2
    assert items[due_soon]["binding"]["window"] == watch_rules.TEMPLATES[0]["name"]
    assert items[due_soon]["binding"]["basis"] == ["CFR803_50", "CFR803_53"]
    assert items[running]["state"] == "RUNNING" and items[running]["binding"]["days"] == 15
    assert items[no_window]["state"] == "NO_WINDOW" and items[no_window]["clocks"] == []
    assert items[follow_up]["state"] == "FOLLOW_UP"
    assert [flag["code"] for flag in items[follow_up]["follow_ups"]] == ["PATIENT_OUTCOME"]
    assert items[overdue]["aware_source"] == "AWARENESS_DATE" and items[overdue]["days_since_aware"] == 40
    summary = response.json()["summary"]
    assert (summary["open"], summary["overdue"], summary["due_soon"], summary["running"]) == (5, 1, 1, 3)
    assert (summary["no_window"], summary["follow_up"], summary["held_on_second_look"]) == (1, 1, 1)
    assert _ids(org["viewer"].get(WATCH, params={"product_id": product, "show": "overdue"})) == [overdue]
    assert _ids(org["viewer"].get(WATCH, params={"product_id": product, "show": "follow_up"})) == [follow_up]


def _earlier_decision(org, complaint_id: str, reported_on: date, reference: str) -> None:
    """A filed report recorded by the single-decision route before it closed (0.10.95): as that route stored it, bound
    to the complaint's window then."""
    from backend.app.db.models.reportability import ComplaintReportability

    (item,) = [i for i in org["viewer"].get(WATCH, params={"show": "all"}).json()["items"] if i["id"] == complaint_id]
    binding = item["binding"]
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        db.add(
            ComplaintReportability(
                tenant_id=uuid.UUID(str(org["tenant_id"])),
                complaint_id=uuid.UUID(complaint_id),
                window_name=binding["window"],
                due_on=date.fromisoformat(binding["due_date"]),
                decision="REPORTED",
                rationale="Death: an MDR was filed under 21 CFR 803",
                report_reference=reference,
                reported_on=reported_on,
                decided_by=str(uuid.uuid4()),
                decided_at=datetime.now(timezone.utc),
            )
        )
        db.commit()


def test_the_single_decision_route_is_closed_and_earlier_decisions_are_still_read(org, windows):
    tenant, product = org["tenant_id"], _product(org["tenant_id"])
    due_soon = _complaint(tenant, product, aware_days_ago=28, country="US", death=True)
    overdue = _complaint(tenant, product, aware_days_ago=35, country="US", malfunction=True)
    path = f"/api/v1/complaints/{due_soon}/reportability"
    reported = {
        "decision": "REPORTED",
        "rationale": "Death: an MDR was filed under 21 CFR 803",
        "report_reference": "MDR-3004-2026-00017",
        "reported_on": (TODAY - timedelta(days=1)).isoformat(),
    }
    for role in ("viewer", "investigator", "reviewer", "admin"):
        assert org[role].post(path, json=reported).status_code == 403, role
    # Reportability is decided on the signed market assessment (0.10.95, code audit 9 and owner decision 10 Nov).
    for body in (reported, {"decision": "NOT_REPORTABLE", "rationale": "Death unrelated to the device per autopsy"}):
        refused = org["regulatory"].post(path, json=body)
        assert refused.status_code == 409 and refused.json()["detail"]["code"] == "SIGNED_ASSESSMENT_REQUIRED"
        assert "Record the filing" in refused.json()["detail"]["message"]
    assert _actions(tenant, due_soon) == []

    _earlier_decision(org, due_soon, TODAY - timedelta(days=1), "MDR-3004-2026-00017")
    _earlier_decision(org, overdue, TODAY - timedelta(days=1), "MDR-3004-2026-00018")
    response = org["viewer"].get(WATCH, params={"product_id": product})
    assert _ids(response) == []
    summary = response.json()["summary"]
    assert (summary["decided"], summary["decided_in_window"], summary["decided_late"]) == (2, 1, 1)
    decided = {
        i["id"]: i["decision"]
        for i in org["viewer"].get(WATCH, params={"product_id": product, "show": "decided"}).json()["items"]
    }
    assert (decided[due_soon]["on_time"], decided[overdue]["on_time"]) == (True, False)
    assert decided[due_soon]["report_reference"] == "MDR-3004-2026-00017"


def test_a_completed_regulatory_review_of_its_case_settles_a_complaint(org, windows):
    tenant, product = org["tenant_id"], _product(org["tenant_id"])
    settled = _complaint(tenant, product, aware_days_ago=5, country="US", serious_injury=True)
    reporting = _complaint(tenant, product, aware_days_ago=5, country="US", malfunction=True)
    for complaint, outcome in ((settled, "NO_REPORTABILITY_CONCERN_IDENTIFIED"), (reporting, "REPORTING_REQUIRED")):
        case = org["investigator"].post(
            "/api/v1/investigations",
            json={
                "product_id": product,
                "investigation_question": "Is this complaint reportable to the FDA?",
                "complaint_ids": [complaint],
            },
        )
        assert case.status_code in (200, 201), case.text
        with SessionLocal() as db:
            bind_tenant(db, tenant)
            case_id = (
                db.query(InvestigationComplaint.investigation_id)
                .filter(InvestigationComplaint.complaint_id == uuid.UUID(complaint))
                .scalar()
            )
            db.add(
                CaseReview(
                    tenant_id=tenant,
                    investigation_id=case_id,
                    review_type="REGULATORY",
                    status="COMPLETED",
                    requested_by="test",
                    outcome=outcome,
                    rationale="Reviewed against the MDR decision tree",
                    completed_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
    items = {
        item["id"]: item for item in _items(org["viewer"].get(WATCH, params={"product_id": product, "show": "all"}))
    }
    assert items[settled]["state"] == "DECIDED" and items[settled]["settled_by_case"] is True
    assert items[settled]["case"]["review"]["outcome"] == "NO_REPORTABILITY_CONCERN_IDENTIFIED"
    # "Reporting required" does not stop the clock: the report still has to be recorded as filed.
    assert items[reporting]["state"] == "RUNNING" and items[reporting]["settled_by_case"] is False


def test_the_sweep_reminds_the_regulatory_reviewers_and_settles_their_tasks(org, windows):
    from backend.app.reportability.reminders import sweep_reportability

    tenant, product = org["tenant_id"], _product(org["tenant_id"])
    urgent = _complaint(tenant, product, aware_days_ago=29, country="US", death=True)
    calm = _complaint(tenant, product, aware_days_ago=1, country="US", malfunction=True)

    def tasks_of(complaint: str) -> list[WorkflowTask]:
        with SessionLocal() as db:
            bind_tenant(db, tenant)
            return (
                db.query(WorkflowTask)
                .filter(
                    WorkflowTask.task_type == "REPORTABILITY_DECISION",
                    WorkflowTask.source_entity_id == uuid.UUID(complaint),
                )
                .all()
            )

    def sweep() -> dict:
        with SessionLocal() as db:
            bind_tenant(db, tenant)
            done = sweep_reportability(db, tenant)
            db.commit()
            return done

    sweep()
    created = tasks_of(urgent)
    assert len(created) == 1 and created[0].assigned_role == "REGULATORY_REVIEWER"
    assert created[0].priority == "CRITICAL" and created[0].investigation_id is None
    assert tasks_of(calm) == []
    sweep()  # idempotent
    assert len(tasks_of(urgent)) == 1
    # A decision on record ends the reminder at the next sweep.
    _earlier_decision(org, urgent, TODAY, "MDR-3004-2026-00019")
    sweep()
    assert [task.status for task in tasks_of(urgent)] == ["COMPLETED"]


# ------------------------------------------------------------------------------------------- CAPA effectiveness


def _capa(tenant_id, product_id: str | None, case_id=None, *, status="open", due_days_ago=30, check_in=None) -> str:
    now = datetime.now(timezone.utc)
    tag = uuid.uuid4().hex[:8].upper()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = Capa(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            capa_identifier=f"RCP-CAPA-{tag}",
            title=f"Replace the occlusion sensor {tag}",
            action_type="CORRECTIVE",
            product_id=uuid.UUID(product_id) if product_id else None,
            investigation_id=case_id,
            status=status,
            opened_at=now - timedelta(days=due_days_ago + 30),
            due_at=now - timedelta(days=due_days_ago),
            effectiveness_check_at=(now + timedelta(days=check_in)) if check_in is not None else None,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        return str(row.id)


def _case_with(org, product: str, complaints: list[str]):
    case = org["investigator"].post(
        "/api/v1/investigations",
        json={
            "product_id": product,
            "investigation_question": "Why do occlusion alarms recur on this pump?",
            "complaint_ids": complaints,
        },
    )
    assert case.status_code in (200, 201), case.text
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        return (
            db.query(InvestigationComplaint.investigation_id)
            .filter(InvestigationComplaint.complaint_id == uuid.UUID(complaints[0]))
            .scalar()
        )


def test_the_board_shows_every_capa_needing_a_check(org):
    tenant, product = org["tenant_id"], _product(org["tenant_id"])
    open_capa = _capa(tenant, product)
    closed = _capa(tenant, product, status="Closed")
    imported = _capa(tenant, product, check_in=5)
    cancelled = _capa(tenant, product, status="Cancelled")
    body = org["viewer"].get(BOARD, params={"show": "all", "page_size": 200}).json()
    items = {item["capa"]["id"]: item for item in body["items"]}
    assert cancelled not in items
    assert items[open_capa]["state"] == "NOT_PLANNED" and items[open_capa]["closed_without_check"] is False
    assert items[closed]["state"] == "NOT_PLANNED" and items[closed]["closed_without_check"] is True
    assert items[imported]["state"] == "DUE_SOON" and items[imported]["plan_source"] == "SOURCE_SYSTEM"
    assert items[imported]["days_left"] == 5
    attention = [item["capa"]["id"] for item in org["viewer"].get(BOARD, params={"page_size": 200}).json()["items"]]
    assert attention.index(imported) < attention.index(closed) < attention.index(open_capa)
    assert body["summary"]["closed_without_check"] >= 1 and body["summary"]["date_from_source"] >= 1
    assert open_capa not in [item["capa"]["id"] for item in org["other"].get(BOARD).json()["items"]]
    assert org["other"].get(f"/api/v1/capas/{open_capa}/effectiveness").status_code == 404


def test_a_check_is_planned_reminded_signed_and_repeated_after_a_failure(org, monkeypatch):
    tenant, product = org["tenant_id"], _product(org["tenant_id"])
    measured = TODAY - timedelta(days=30)
    before = [_complaint(tenant, product, aware_days_ago=days, problem_code="OCC") for days in (35, 45, 50)]
    _complaint(tenant, product, aware_days_ago=10, problem_code="OCC")  # since the action
    _complaint(tenant, product, aware_days_ago=10, problem_code="OTHER")  # another problem: not counted
    case_id = _case_with(org, product, before)
    capa_id = _capa(tenant, product, case_id, due_days_ago=30)
    url = f"/api/v1/capas/{capa_id}/effectiveness"

    detail = org["viewer"].get(url).json()
    assert detail["state"] == "NOT_PLANNED" and detail["can_plan"] is True and detail["can_sign"] is False
    recurrence = detail["recurrence"]
    assert recurrence["available"] is True and recurrence["problem_codes"] == ["OCC"]
    assert recurrence["measured_from"] == measured.isoformat()
    assert (recurrence["before"]["complaints"], recurrence["since"]["complaints"]) == (3, 1)
    assert recurrence["direction"] == "FEWER"
    assert "OCC" in detail["suggestion"]["criteria"]

    plan = {
        "criteria": "No more than one occlusion complaint in the 90 days after the new sensor",
        "planned_on": (TODAY + timedelta(days=10)).isoformat(),
        "measured_from": measured.isoformat(),
    }
    assert org["viewer"].put(f"{url}/plan", json=plan).status_code == 403
    planned = org["investigator"].put(f"{url}/plan", json=plan)
    assert planned.status_code == 200, planned.text
    assert planned.json()["state"] == "DUE_SOON" and planned.json()["check"]["round"] == 1

    def reminders(status: str | None = None) -> list[WorkflowTask]:
        with SessionLocal() as db:
            bind_tenant(db, tenant)
            query = db.query(WorkflowTask).filter(
                WorkflowTask.task_type == "EFFECTIVENESS_CHECK", WorkflowTask.source_entity_id == uuid.UUID(capa_id)
            )
            return query.filter(WorkflowTask.status == status).all() if status else query.all()

    assert [task.assigned_role for task in reminders()] == ["REVIEWER"]
    unexplained = org["investigator"].put(
        f"{url}/plan", json={**plan, "planned_on": (TODAY + 12 * timedelta(days=1)).isoformat()}
    )
    assert unexplained.status_code == 422 and unexplained.json()["detail"]["code"] == "REASON_REQUIRED"
    replanned = org["investigator"].put(
        f"{url}/plan", json={**plan, "planned_on": (TODAY + timedelta(days=12)).isoformat(), "reason": REASON}
    )
    assert replanned.status_code == 200 and replanned.json()["check"]["plan_version"] == 2
    assert len(reminders("CANCELLED")) == 1 and len(reminders("NEW")) == 1

    sign = {"result": "NOT_EFFECTIVE", "summary": "Two occlusion complaints since the change", "plan_version": 2}
    assert org["investigator"].post(f"{url}/result", json={**sign, "password": PASSWORD}).status_code == 403
    stale = org["reviewer"].post(f"{url}/result", json={**sign, "plan_version": 1, "password": PASSWORD})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "PLAN_CHANGED"
    wrong = org["reviewer"].post(f"{url}/result", json={**sign, "password": "not the password"})
    assert wrong.status_code == 403 and wrong.json()["detail"]["code"] == "INVALID_REAUTHENTICATION"
    signed = org["reviewer"].post(f"{url}/result", json={**sign, "password": PASSWORD})
    assert signed.status_code == 200, signed.text
    check = signed.json()["check"]
    assert signed.json()["state"] == "NOT_EFFECTIVE" and check["signed_by"] == "Quinn Quality"
    assert check["evidence"]["since"]["complaints"] == 1 and len(check["content_fingerprint"]) == 64
    assert len(reminders("COMPLETED")) == 1
    with SessionLocal() as db:
        bind_system(db, "test: read the signature")
        record = (
            db.query(SignedApprovalRecord)
            .filter(SignedApprovalRecord.id == uuid.UUID(_signature_id(tenant, capa_id)))
            .one()
        )
        assert record.object_type == "CapaEffectivenessCheck" and record.decision == "INEFFECTIVE"
        assert record.content_fingerprint == check["content_fingerprint"] and record.signer_role == "REVIEWER"
    again = org["reviewer"].post(f"{url}/result", json={**sign, "password": PASSWORD})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "NO_PLANNED_CHECK"

    # After a failure, the next round; with authenticator codes required, the approver signs it effective.
    second = org["investigator"].put(
        f"{url}/plan", json={**plan, "planned_on": (TODAY + timedelta(days=40)).isoformat()}
    )
    assert second.status_code == 200 and second.json()["check"]["round"] == 2
    assert second.json()["state"] == "SCHEDULED"
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_FOR_SIGNATURES", "true")
    body = {"result": "EFFECTIVE", "summary": "No occlusion complaints since round two", "plan_version": 1}
    no_code = org["approver"].post(f"{url}/result", json={**body, "password": PASSWORD})
    assert no_code.status_code == 403 and no_code.json()["detail"]["code"] == "SIGNATURE_MFA_NOT_SET_UP"
    secret = org["approver"].post("/api/v1/auth/mfa/enroll").json()["secret"]
    enrolled = org["approver"].post("/api/v1/auth/mfa/verify-enrollment", json={"code": totp.current_code(secret)})
    assert enrolled.status_code == 200, enrolled.text
    code = totp.code_at(secret, int(time.time() // 30) + 1)
    effective = org["approver"].post(f"{url}/result", json={**body, "password": PASSWORD, "mfa_code": code})
    assert effective.status_code == 200, effective.text
    assert effective.json()["state"] == "EFFECTIVE" and len(effective.json()["rounds"]) == 2
    done = org["investigator"].put(f"{url}/plan", json=plan)
    assert done.status_code == 409 and done.json()["detail"]["code"] == "CHECK_DONE"
    assert _actions(tenant, capa_id).count("CAPA_EFFECTIVENESS_SIGNED") == 2
    assert {"CAPA_EFFECTIVENESS_PLANNED", "CAPA_EFFECTIVENESS_REPLANNED"} <= set(_actions(tenant, capa_id))


def _signature_id(tenant_id, capa_id: str) -> str:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = (
            db.query(CapaEffectivenessCheck)
            .filter(CapaEffectivenessCheck.capa_id == uuid.UUID(capa_id))
            .order_by(CapaEffectivenessCheck.round.desc())
            .first()
        )
        return str(row.signature_id)


def test_a_capa_without_a_product_cannot_be_measured_and_a_cancelled_one_cannot_be_planned(org):
    tenant = org["tenant_id"]
    bare = _capa(tenant, None)
    assert org["viewer"].get(f"/api/v1/capas/{bare}/effectiveness").json()["recurrence"]["available"] is False
    cancelled = _capa(tenant, _product(tenant), status="Rejected")
    plan = {
        "criteria": "No recurrence for ninety days",
        "planned_on": (TODAY + timedelta(days=30)).isoformat(),
        "measured_from": TODAY.isoformat(),
    }
    refused = org["investigator"].put(f"/api/v1/capas/{cancelled}/effectiveness/plan", json=plan)
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "CAPA_NOT_ACTIVE"
    late = org["investigator"].put(
        f"/api/v1/capas/{bare}/effectiveness/plan",
        json={**plan, "measured_from": (TODAY + timedelta(days=31)).isoformat()},
    )
    assert late.status_code == 422 and late.json()["detail"]["code"] == "PLAN_INVALID"
    assert date.fromisoformat(plan["planned_on"]) > TODAY


def test_a_case_regulatory_review_shows_each_complaint_s_reporting_clock(org, windows):
    from backend.app.case_reviews.service import regulatory_context
    from backend.app.db.models.foundation import Investigation

    tenant, product = org["tenant_id"], _product(org["tenant_id"])
    death = _complaint(tenant, product, aware_days_ago=5, country="US", death=True)
    quiet = _complaint(tenant, product, aware_days_ago=5, country="US")
    case = org["investigator"].post(
        "/api/v1/investigations",
        json={
            "product_id": product,
            "investigation_question": "Is this death reportable to the FDA?",
            "complaint_ids": [death, quiet],
        },
    )
    assert case.status_code in (200, 201), case.text
    with SessionLocal() as db:
        bind_tenant(db, tenant)
        row = db.query(Investigation).filter(Investigation.id == uuid.UUID(case.json()["id"])).one()
        clocks = regulatory_context(db, row)["reporting_clocks"]
    assert [item["complaint"]["id"] for item in clocks] == [death]  # the quiet complaint starts no clock
    assert clocks[0]["state"] == "RUNNING" and clocks[0]["binding"]["days_left"] == 25
    assert clocks[0]["binding"]["window"] == watch_rules.TEMPLATES[0]["name"] and clocks[0]["decision"] is None
