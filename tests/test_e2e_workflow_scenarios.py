"""Phase 7: the 25 scenarios of the workflow blueprint, end to end through the real HTTP API.

Each scenario drives the API as the people of a small medical-device company would: a Triage Lead, a Quality
Investigator, a Risk Reviewer, a Regulatory Reviewer, a Quality Reviewer and an Authorized Decision Maker (six
distinct accounts), plus one person who holds three workflow roles, a colleague investigator, a viewer and a customer
administrator. A second organization (with a leader who holds every permission) checks that nothing crosses over.
Both organizations are fresh (on the shared plane) and are deleted at the end.

Records that only arrive from outside the API (products, complaints and evidence from an import or a connector) are
written to the database directly, and so is time passing (a due date in the past), the way the other workflow tests
do it. Everything a person does goes through the API.

The Trust & Audit views of a case (``/api/v1/investigations/{id}/trust/...``: timeline, replay, ai-runs, integrity,
export; backend/app/case_audit) are read through ``_trust`` and ``_timeline`` below.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import with_signing_plan
from fastapi.testclient import TestClient

from auth.durable import persist_session
from auth.service import _hash
from backend.app.db.models.decision_outcomes import DecisionFollowUp, ImpactAssessment
from backend.app.db.models.foundation import (
    AIExecution,
    AuditEvent,
    AuthUser,
    Complaint,
    Decision,
    Evidence,
    Investigation,
    Product,
    ProductVersion,
    TenantMembership,
)
from backend.app.db.models.reviews import DecisionBriefVersion
from backend.app.db.models.signals import InvestigationSignal, Signal, SignalComplaint, SignalEvent
from backend.app.db.models.stage3 import SupplierEvidenceRequest
from backend.app.db.models.workflow import WorkflowTask
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.main import app

PASSWORD = "End to end workflow 2026!"
REASON = "Reason recorded for the audit trail"
QUESTION = "Why do occlusion alarms rise after release B?"
RATIONALE = "The bench test reproduces the sensor drift of release B; the conclusion holds"
REVIEW_RATIONALE = "Checked against the risk file and the reporting rules of every market in scope"
RETURN_COMMENT = "The pressure logs of the returned pumps must be in the brief"
SUPERSEDE_REASON = "The late field report changes the conclusion; this decision replaces the earlier one"
GRANT_REASON = "Small team: one person triages, reviews quality and decides"
NARRATIVE = {
    "problem_statement": "Occlusion alarms rose after release B without occlusions",
    "proposed_conclusion": "Sensor drift in release B is the best supported explanation",
    "recommended_actions": ["Replace the occlusion sensor", "Retrain the field service team"],
}

# The six workflow roles, one distinct person each, then the people the other scenarios need.
SIX = ("lead", "investigator", "risk", "regulatory", "quality", "decider")
PEOPLE = (
    ("lead", "TRIAGE_LEAD"),
    ("investigator", "INVESTIGATOR"),
    ("risk", "RISK_REVIEWER"),
    ("regulatory", "REGULATORY_REVIEWER"),
    ("quality", "REVIEWER"),
    ("decider", "APPROVER"),
    ("multi", "INVESTIGATOR"),
    ("self_approver", "INVESTIGATOR"),
    ("colleague", "INVESTIGATOR"),
    ("viewer", "VIEWER"),
    ("admin", "CUSTOMER_ADMIN"),
)
# Additional workflow roles granted by the customer administrator (through the API) when the organization is set up.
EXTRA_ROLES = {
    "multi": ("TRIAGE_LEAD", "REVIEWER", "APPROVER"),
    "self_approver": ("REVIEWER", "APPROVER"),
}
TRUST_ENDPOINTS = ("timeline", "replay", "ai-runs", "integrity", "export")
UUID_TEXT = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


# ------------------------------------------------------------------------------------------- organizations, people


# Intelligence records without a business identifier of their own (backend/app/case_intelligence/rules.py).
UNNUMBERED_OBJECTS = {"HYPOTHESIS_EVIDENCE", "FAILURE_CHAIN_LINK", "OBSERVATION"}


def _organization(prefix: str):
    from backend.app.customer_lifecycle import build_customer_tenant

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db,
            tenant_key=f"{prefix}_{uuid.uuid4().hex[:8].upper()}",
            name="End-to-end workflow",
            status="ACTIVE",
            now=now,
        )
        db.add(customer)
        db.add(tenant)
        db.commit()  # registers the organization on the shared plane (migration md20)
        with_signing_plan(db, tenant)  # the plan and decision rules every organization has
        return tenant.id


def _purge(tenant_id) -> None:
    from backend.app.trial.retention import purge_trial

    with SessionLocal() as db:
        purge_trial(db, tenant_id, "test:e2e-workflow-cleanup")


def _client(tenant_id, role: str, name: str) -> tuple[TestClient, str]:
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=f"e2e-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name=f"{name} E2E",
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
        user_id = str(user.id)
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    return client, user_id


@pytest.fixture(scope="module")
def org():
    """A fresh organization with the six workflow roles held by six people, a person holding three workflow roles
    (Investigator + Triage Lead, Quality Reviewer, Decision Maker), an investigator who also holds the reviewer and
    decision-maker roles (for segregation of duties), a colleague investigator, a viewer and a customer administrator;
    and a second organization with a leader (every permission)."""
    tenant_id = _organization("E2E")
    other_id = _organization("E2E_OTHER")
    try:
        people = {name: _client(tenant_id, role, name.replace("_", " ").title()) for name, role in PEOPLE}
        admin, _ = people["admin"]
        for name, roles in EXTRA_ROLES.items():
            granted = admin.put(
                f"/api/v1/admin/identity/users/{people[name][1]}/roles",
                json={"additional_roles": list(roles), "reason": GRANT_REASON},
            )
            assert granted.status_code == 200, granted.text
        outsider = _client(other_id, "LEADER", "Outsider")
        yield {"tenant_id": tenant_id, "other_id": other_id, "outsider": outsider, **people}
    finally:
        _purge(tenant_id)
        _purge(other_id)


# --------------------------------------------------------------------------- records from outside the API (imports)


def _seed(
    tenant_id,
    *,
    complaints: int = 1,
    problem: str | None = "OCCLUSION",
    versions: tuple[str, ...] = ("Rev A",),
    flags: list[dict] | None = None,
    days_ago: int = 3,
) -> dict:
    """A product with its versions and ``complaints`` complaints on the first version (``flags[i]`` adds columns to
    complaint i: serious_injury, malfunction, death, country), as an import would record them."""
    now = datetime.now(timezone.utc)
    tag = uuid.uuid4().hex[:8].upper()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_identifier=f"E2E-P-{tag}",
            name=f"E2E Pump {tag}",
            created_at=now,
            updated_at=now,
        )
        db.add(product)
        db.flush()
        version_ids = []
        for identifier in versions:
            version = ProductVersion(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                product_id=product.id,
                version_identifier=identifier,
                created_at=now,
                updated_at=now,
            )
            db.add(version)
            db.flush()
            version_ids.append(str(version.id))
        extra = list(flags or [])
        complaint_ids = [
            _complaint(
                db,
                tenant_id,
                product.id,
                version_ids[0],
                problem,
                days_ago,
                **(extra[index] if index < len(extra) else {}),
            )
            for index in range(complaints)
        ]
        db.commit()
        return {
            "product_id": str(product.id),
            "product_business_id": product.business_id,
            "version_id": version_ids[0],
            "version_ids": version_ids,
            "complaint_ids": complaint_ids,
            "problem": problem,
        }


def _complaint(db, tenant_id, product_id, version_id, problem, days_ago: int, **flags) -> str:
    now = datetime.now(timezone.utc)
    row = Complaint(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        complaint_identifier=f"E2E-C-{uuid.uuid4().hex[:10].upper()}",
        product_id=uuid.UUID(str(product_id)),
        product_version_id=uuid.UUID(str(version_id)) if version_id else None,
        event_timestamp=now - timedelta(days=days_ago),
        complaint_timestamp=now - timedelta(days=max(days_ago - 1, 0)),
        description="Occlusion alarm without an occlusion",
        problem_code=problem,
        status="open",
        created_at=now,
        updated_at=now,
        **flags,
    )
    db.add(row)
    db.flush()
    return str(row.id)


def _add_complaint(tenant_id, seed: dict, **flags) -> str:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        complaint_id = _complaint(db, tenant_id, seed["product_id"], seed["version_id"], seed["problem"], 1, **flags)
        db.commit()
        return complaint_id


def _evidence(tenant_id, *, case_id=None, title: str = "Bench test of the occlusion sensor", at=None) -> dict:
    """Evidence as a connector or an import records it (on the case when ``case_id`` is given)."""
    now = datetime.now(timezone.utc)
    received = at or now
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = Evidence(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            evidence_identifier=f"E2E-EV-{uuid.uuid4().hex[:10].upper()}",
            investigation_id=uuid.UUID(str(case_id)) if case_id else None,
            evidence_type="TEST_REPORT",
            title=title,
            source_system="Lab records",
            source_identifier=f"LAB-{uuid.uuid4().hex[:6]}",
            source_timestamp=received - timedelta(days=1),
            ingestion_timestamp=received,
            recorded_timestamp=received,
            content="Occlusion alarm reproduced at 4 psi on 3 of 10 pumps.",
            created_at=received,
            updated_at=received,
        )
        db.add(row)
        db.commit()
        return {"id": str(row.id), "business_id": row.business_id, "identifier": row.evidence_identifier}


# ----------------------------------------------------------------------------------------------- database readers


def _get(tenant_id, model, **filters):
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        found = db.query(model).filter_by(**filters).one()
        db.expunge(found)
        return found


def _all(tenant_id, model, *criteria, order_by=None) -> list:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        query = db.query(model).filter(model.tenant_id == tenant_id, *criteria)
        if order_by is not None:
            query = query.order_by(order_by)
        rows = query.all()
        db.expunge_all()
        return rows


def _update(tenant_id, model, *criteria, **values) -> None:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.query(model).filter(model.tenant_id == tenant_id, *criteria).update(values, synchronize_session=False)
        db.commit()


def _case_row(tenant_id, case_id) -> Investigation:
    return _get(tenant_id, Investigation, id=uuid.UUID(str(case_id)))


def _tasks(tenant_id, *, source_id=None, case_id=None, task_type: str | None = None) -> list[WorkflowTask]:
    criteria = []
    if source_id is not None:
        criteria.append(WorkflowTask.source_entity_id == uuid.UUID(str(source_id)))
    if case_id is not None:
        criteria.append(WorkflowTask.investigation_id == uuid.UUID(str(case_id)))
    if task_type:
        criteria.append(WorkflowTask.task_type == task_type)
    return _all(tenant_id, WorkflowTask, *criteria, order_by=WorkflowTask.created_at)


def _audit_actions(tenant_id, entity_id) -> list[str]:
    return [
        row.action
        for row in _all(
            tenant_id, AuditEvent, AuditEvent.entity_id == uuid.UUID(str(entity_id)), order_by=AuditEvent.created_at
        )
    ]


def _audits(tenant_id, entity_id, action: str) -> list[AuditEvent]:
    return _all(
        tenant_id,
        AuditEvent,
        AuditEvent.entity_id == uuid.UUID(str(entity_id)),
        AuditEvent.action == action,
        order_by=AuditEvent.created_at,
    )


def _username(tenant_id, user_id) -> str:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return db.query(AuthUser.username).filter(AuthUser.id == uuid.UUID(str(user_id))).scalar()


# ---------------------------------------------------------------------------------------------------- API helpers


def _code(response) -> str | None:
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return None
    return detail.get("code") if isinstance(detail, dict) else None


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


def _signal(client, seed: dict, title: str, *, complaint_ids=None, **extra) -> dict:
    made = client.post(
        "/api/v1/triage/signals",
        json={
            "title": title,
            "product_id": seed["product_id"],
            "product_version_id": seed["version_id"],
            "complaint_ids": seed["complaint_ids"] if complaint_ids is None else complaint_ids,
            **extra,
        },
    )
    return _ok(made, 201)


def _triage(client, signal_id, action: str, body: dict | None = None):
    return client.post(f"/api/v1/triage/signals/{signal_id}/{action}", json=body or {})


def _signal_detail(client, signal_id) -> dict:
    return _ok(client.get(f"/api/v1/triage/signals/{signal_id}"))


def _needs_case(client, seed: dict, title: str, *, complaint_ids=None) -> dict:
    """A signal triaged as needing an investigation."""
    signal = _signal(client, seed, title, complaint_ids=complaint_ids)
    marked = _triage(client, signal["id"], "disposition", {"disposition": "INVESTIGATION_REQUIRED", "reason": REASON})
    assert _ok(marked)["status"] == "INVESTIGATION_REQUIRED"
    return signal


def _run_detection(client) -> dict:
    body = _ok(client.post("/api/v1/triage/rules/run"))
    assert set(body) >= {"created", "updated", "monitor_reopened"}
    return body


def _open_case(client, seed: dict, complaint_ids=None, *, assign_to_me: bool = True) -> dict:
    made = client.post(
        "/api/v1/investigations",
        json={
            "product_id": seed["product_id"],
            "investigation_question": QUESTION,
            "complaint_ids": seed["complaint_ids"] if complaint_ids is None else complaint_ids,
            "assign_to_me": assign_to_me,
        },
    )
    return _ok(made, 201)


def _review_evidence(client, case_id, evidence_id, *, status="ACCEPTED", relationship="SUPPORTING", **extra) -> dict:
    response = client.post(
        f"/api/v1/investigations/{case_id}/evidence/{evidence_id}/review",
        json={"review_status": status, "relationship": relationship, **extra},
    )
    return _ok(response)


def _intel(case_id) -> str:
    return f"/api/v1/investigations/{case_id}/intelligence"


def _hypothesis(client, case_id, statement: str, *, status: str | None = None, evidence_id=None) -> dict:
    """A hypothesis a person adds, judged ``status`` and supported by ``evidence_id`` when given."""
    made = _ok(client.post(f"{_intel(case_id)}/hypotheses", json={"statement": statement, "rationale": REASON}), 201)
    if status:
        made = _judge(client, case_id, made["id"], status)
    if evidence_id:
        _link(client, case_id, made["id"], evidence_id, "SUPPORTING")
    return made


def _judge(client, case_id, hypothesis_id, status: str) -> dict:
    response = client.post(
        f"{_intel(case_id)}/hypotheses/{hypothesis_id}/status", json={"human_status": status, "reason": REASON}
    )
    return _ok(response)


def _link(client, case_id, hypothesis_id, evidence_id, relation: str) -> dict:
    response = client.post(
        f"{_intel(case_id)}/hypotheses/{hypothesis_id}/evidence",
        json={"evidence_id": evidence_id, "relation": relation, "rationale": REASON},
    )
    return _ok(response, 201)


def _readiness(client, case_id) -> dict:
    body = _ok(client.get(f"/api/v1/investigations/{case_id}/readiness"))
    return {check["key"]: check for check in body["checks"]}


def _ready_case(org, author: str = "investigator", *, seed: dict | None = None) -> dict:
    """A case ``author`` opened (one complaint, medium priority: no risk or regulatory review required) whose evidence
    is reviewed and whose leading hypothesis a person judged strongly supported. Returns the case with
    ``_evidence`` and ``_hypothesis``."""
    tenant_id = org["tenant_id"]
    client, _ = org[author]
    seed = seed or _seed(tenant_id)
    case = _open_case(client, seed, seed["complaint_ids"][:1])
    _make_ready(org, author, case)
    return case


def _make_ready(org, author: str, case: dict) -> dict:
    tenant_id = org["tenant_id"]
    client, _ = org[author]
    bench = _evidence(tenant_id, case_id=case["id"])
    _review_evidence(client, case["id"], bench["id"], reason="The bench test reproduces the alarm")
    hypothesis = _hypothesis(
        client,
        case["id"],
        "The occlusion sensor of release B drifts under load",
        status="STRONGLY_SUPPORTED",
        evidence_id=bench["id"],
    )
    case["_evidence"] = bench
    case["_hypothesis"] = hypothesis
    return case


def _brief(case_id) -> str:
    return f"/api/v1/investigations/{case_id}/decision-brief"


def _decision(case_id) -> str:
    return f"/api/v1/investigations/{case_id}/decision"


def _submit(org, case_id, author: str = "investigator") -> dict:
    """Compose the next version of the brief, write its narrative and send it to quality review."""
    client, _ = org[author]
    _ok(client.post(_brief(case_id), json={}), 201)
    _ok(client.put(_brief(case_id) + "/draft", json=NARRATIVE))
    return _ok(client.post(_brief(case_id) + "/submit", json={"comment": "Ready for quality review"}))


def _accept(org, case_id, version: int = 1, reviewer: str = "quality") -> dict:
    client, _ = org[reviewer]
    accepted = _ok(client.post(_brief(case_id) + f"/versions/{version}/review", json={"action": "ACCEPT_FOR_DECISION"}))
    assert accepted["status"] == "APPROVED_FOR_DECISION"
    return accepted


def _approved(org, author: str = "investigator") -> tuple[dict, dict]:
    """A ready case whose brief version 1 ``author`` wrote and the quality reviewer approved for decision."""
    case = _ready_case(org, author)
    _submit(org, case["id"], author)
    return case, _accept(org, case["id"])


def _sign_body(brief: dict, **changes) -> dict:
    body = {
        "brief_version_id": brief["id"],
        "brief_content_hash": brief["content_hash"],
        "outcome": "ACCEPT_CONCLUSION",
        "rationale": RATIONALE,
        "root_cause_attribution": "DEVICE_RELATED",
        "root_cause_category": "MATERIAL",
        "password": PASSWORD,
    }
    body.update(changes)
    return body


def _sign(client, case_id, brief: dict, **changes):
    return client.post(_decision(case_id) + "/sign", json=_sign_body(brief, **changes))


def _decided(org, author: str = "investigator", **changes) -> tuple[dict, dict, dict]:
    """An approved case signed by the decision maker: ``(case, brief, signed record)``."""
    case, brief = _approved(org, author)
    record = _ok(_sign(org["decider"][0], case["id"], brief, **changes))
    assert record["verification"]["status"] == "VALID"
    return case, brief, record


def _record(client, decision_id) -> dict:
    return _ok(client.get(f"/api/v1/decisions/{decision_id}/record"))


def _governance_status(client, decision_id) -> str:
    response = client.get(f"/api/v1/governance/decisions/{decision_id}/signature-verification")
    return _ok(response)["verification_status"]


def _ai_off(org) -> dict:
    """The customer administrator switches AI processing off for the organization (audited), and every signed-in
    person's AI status says so."""
    admin, _ = org["admin"]
    settings = _ok(
        admin.put(
            "/api/v1/admin/ai-settings",
            json={"ai_processing_allowed": False, "reason": "Pilot runs without AI until the contract is signed"},
        )
    )
    assert settings["ai_processing_allowed"] is False
    status = _ok(org["investigator"][0].get("/api/v1/ai/status"))
    # Switched off; a server without any AI service says that first (switching on would change nothing).
    expected = "AI_DISABLED" if status["available"] else "PROVIDER_UNAVAILABLE"
    assert status["enabled"] is False and status["reason_code"] == expected and status["message"]
    return status


# ------------------------------------------------------------------------------------- Trust & Audit (Phase 7 API)


def _trust(client, case_id, name: str, **params):
    """One Trust & Audit view of a case."""
    return client.get(f"/api/v1/investigations/{case_id}/trust/{name}", params=params or None)


def _timeline(client, case_id) -> tuple[list[dict], dict[str, int]]:
    """Every item of the case's trust timeline (oldest first, all pages) and the count of items by category."""
    items: list[dict] = []
    page, categories = 1, {}
    while True:
        body = _ok(_trust(client, case_id, "timeline", page=page, page_size=200))
        assert set(body) >= {"items", "total", "categories", "page", "page_size"}, sorted(body)
        items.extend(body["items"])
        categories = body["categories"]
        if len(items) >= body["total"] or not body["items"]:
            break
        page += 1
    assert items and all(
        {"at", "category", "event", "title", "actor", "object", "origin"} <= set(item) for item in items
    )
    times = [datetime.fromisoformat(item["at"]) for item in items if item["at"]]
    assert times == sorted(times), "The timeline is not oldest first"
    return items, categories


def _first(events: list[dict], marker) -> int:
    """Index of the first event that mentions ``marker`` (text, or a compiled pattern); -1 when none does."""
    for index, event in enumerate(events):
        text = json.dumps(event, default=str)
        if marker.search(text) if isinstance(marker, re.Pattern) else marker in text:
            return index
    return -1


def _uuid_only_objects(value, path: str = "$") -> list[str]:
    """Places in a JSON value where a record is named by its UUID alone: a bare UUID string in a list, or an object
    holding a UUID value with no business id, label, name or title beside it."""
    found: list[str] = []
    if isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, str) and UUID_TEXT.match(item):
                found.append(f"{path}[{index}]")
            else:
                found.extend(_uuid_only_objects(item, f"{path}[{index}]"))
    elif isinstance(value, dict):
        has_uuid = any(isinstance(item, str) and UUID_TEXT.match(item) for item in value.values())
        readable = any(
            isinstance(item, str)
            and item.strip()
            and not UUID_TEXT.match(item)
            and (
                key.endswith(("business_id", "label", "name", "title", "summary", "description"))
                or key in {"text", "message", "action", "event_type", "kind", "category"}
            )
            for key, item in value.items()
        )
        if has_uuid and not readable:
            found.append(path)
        for key, item in value.items():
            found.extend(_uuid_only_objects(item, f"{path}.{key}"))
    return found


def _secrets(org) -> list[str]:
    """What must never appear in an audit view: the people's password and password hashes, and their session
    tokens."""
    names = [name for name, _ in PEOPLE]
    tokens = [org[name][0].cookies.get("mdarix_session") for name in names]
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        hashes = [
            row[0]
            for row in db.query(AuthUser.password_hash).filter(
                AuthUser.id.in_([uuid.UUID(org[name][1]) for name in names])
            )
        ]
    return [PASSWORD, *(item for item in tokens + hashes if item)]


# ============================================================================================ 1. the golden path


@pytest.fixture(scope="module")
def golden(org):
    """Scenario 1, walked once by six distinct people through the API: a signal triaged into a case, its scope, its
    evidence reviewed and an evidence request answered, people's judgements, risk and regulatory reviews, brief
    version 1 returned and version 2 accepted, a signed decision with a CAPA follow-up, and the case closed with its
    criteria met. Scenarios 1, 18 and 24 read what it left."""
    tenant_id = org["tenant_id"]
    lead, _ = org["lead"]
    investigator, investigator_id = org["investigator"]
    risk, risk_id = org["risk"]
    regulatory, regulatory_id = org["regulatory"]
    quality, _ = org["quality"]
    decider, decider_id = org["decider"]
    started = datetime.now(timezone.utc)
    seed = _seed(
        tenant_id,
        complaints=3,
        problem="GOLDEN OCCLUSION",
        flags=[{"serious_injury": True, "country": "DE"}, {"malfunction": True, "country": "US"}, {"country": "FR"}],
    )

    # The Triage Lead raises the signal, triages it and opens a case for the investigator.
    signal = _signal(lead, seed, "Occlusion alarms without an occlusion", description="Three reports in a week")
    assert signal["status"] == "NEW" and signal["complaint_count"] == 3 and signal["business_id"].startswith("SIG")
    assert _ok(_triage(lead, signal["id"], "start"))["status"] == "TRIAGE"
    raised = _ok(_triage(lead, signal["id"], "priority", {"priority": "HIGH", "reason": "A serious injury reported"}))
    assert raised["confirmed_priority"] == "HIGH"
    marked = _triage(lead, signal["id"], "disposition", {"disposition": "INVESTIGATION_REQUIRED", "reason": REASON})
    assert _ok(marked)["status"] == "INVESTIGATION_REQUIRED"
    opened = _ok(
        _triage(
            lead,
            signal["id"],
            "create-investigation",
            {"investigation_question": QUESTION, "assignee_user_id": investigator_id},
        ),
        201,
    )
    case = opened["investigation"]
    case_id = case["id"]
    assert case["business_id"].startswith("INV") and case["complaints_linked"] == 3
    assert case["owner"]["id"] == investigator_id and opened["signal"]["status"] == "INVESTIGATION_OPEN"
    row = _case_row(tenant_id, case_id)
    assert row.workflow_state == "OPEN" and row.priority == "HIGH"

    # The investigator takes the case and widens its scope.
    (task,) = _tasks(tenant_id, case_id=case_id, task_type="INVESTIGATION")
    assert task.status == "ASSIGNED" and str(task.assigned_user_id) == investigator_id
    assert _ok(investigator.post(f"/api/v1/tasks/{task.id}/accept"))["status"] == "ACCEPTED"
    assert _case_row(tenant_id, case_id).workflow_state == "IN_PROGRESS"
    scope = _ok(
        investigator.put(
            f"/api/v1/investigations/{case_id}/scope",
            json={
                "question": QUESTION,
                "included_complaint_ids": seed["complaint_ids"],
                "product_version_ids": [seed["version_id"]],
                "markets": ["EU", "US"],
                "objectives": "Find why the occlusion alarms rise",
                "change_reason": "Markets and objectives agreed at the kick-off",
            },
        )
    )
    assert scope["scope"]["version"] == 2 and scope["scope"]["markets"] == ["EU", "US"]
    policy = _ok(investigator.get(f"/api/v1/investigations/{case_id}/reviews/policy"))
    assert policy["risk"]["required"] is True and policy["regulatory"]["required"] is True

    # Evidence: the bench test is reviewed; the pressure logs are asked of the risk reviewer, answered, accepted.
    bench = _evidence(tenant_id, case_id=case_id)
    reviewed = _review_evidence(investigator, case_id, bench["id"], reason="The bench test reproduces the alarm")
    assert reviewed["link"]["review_status"] == "ACCEPTED" and reviewed["link"]["relationship"] == "SUPPORTING"
    request = _ok(
        investigator.post(
            f"/api/v1/investigations/{case_id}/evidence-requests",
            json={
                "kind": "INTERNAL",
                "title": "Pressure logs of the returned pumps",
                "requested_items": ["Pressure log export"],
                "rationale": "Needed to compare the alarms with the line pressure",
                "priority": "HIGH",
                "due_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
                "recipient_user_id": risk_id,
            },
        ),
        201,
    )
    assert request["status"] == "OPEN" and request["business_id"].startswith("EVR")
    assert _readiness(investigator, case_id)["no_blocking_request"]["result"] == "BLOCKED"
    path = f"/api/v1/evidence-requests/{request['id']}"
    assert _ok(risk.post(f"{path}/acknowledge"))["status"] == "ACKNOWLEDGED"
    answered = _ok(risk.post(f"{path}/respond", json={"note": "Pressure logs attached: 4 psi offset on 3 pumps"}))
    assert answered["status"] == "RECEIVED"
    accepted_answer = _ok(
        investigator.post(
            f"{path}/review",
            json={"accept": True, "review_status": "ACCEPTED", "relationship": "SUPPORTING", "evidence_type": "log"},
        )
    )
    assert accepted_answer["status"] == "REVIEWED"
    logs = accepted_answer["evidence"]["evidence"]
    checks = _readiness(investigator, case_id)
    assert checks["no_blocking_request"]["result"] == "PASS" and checks["evidence_reviewed"]["result"] == "PASS"

    # Intelligence: people's judgements, an answered question and an observation.
    leading = _hypothesis(
        investigator,
        case_id,
        "Sensor drift in release B raises false occlusion alarms",
        status="STRONGLY_SUPPORTED",
        evidence_id=bench["id"],
    )
    _link(investigator, case_id, leading["id"], logs["id"], "SUPPORTING")
    alternative = _hypothesis(
        investigator, case_id, "Users set the occlusion limit too low on the ward", status="WEAKLY_SUPPORTED"
    )
    unknown = _ok(
        investigator.post(
            f"{_intel(case_id)}/unknowns",
            json={"description": "Did the returned pumps run release B?", "evidence_needed": "Device history records"},
        ),
        201,
    )
    resolved = investigator.post(
        f"{_intel(case_id)}/unknowns/{unknown['id']}/status",
        json={"status": "resolved", "reason": "The device history records show release B on every pump"},
    )
    assert _ok(resolved)["status"] == "resolved"
    _ok(
        investigator.post(
            f"{_intel(case_id)}/observations",
            json={
                "evidence_id": bench["id"],
                "statement": "Alarm at 4 psi without an occlusion",
                "epistemic_type": "FACT",
                "rationale": REASON,
            },
        ),
        201,
    )

    # Risk and regulatory reviews, required by policy, done by their reviewers.
    reviews = {}
    for review_type, reviewer, outcome in (
        ("RISK", risk, "NO_CHANGE_REQUIRED"),
        ("REGULATORY", regulatory, "NO_REPORTABILITY_CONCERN_IDENTIFIED"),
    ):
        made = _ok(
            investigator.post(
                f"/api/v1/investigations/{case_id}/reviews",
                json={"review_type": review_type, "reason": "Required by the review policy"},
            ),
            201,
        )
        assert made["required_by_policy"] is True and made["status"] == "REQUESTED"
        assert _ok(reviewer.post(f"/api/v1/case-reviews/{made['id']}/start"))["status"] == "IN_PROGRESS"
        done = _ok(
            reviewer.post(
                f"/api/v1/case-reviews/{made['id']}/complete", json={"outcome": outcome, "rationale": REVIEW_RATIONALE}
            )
        )
        assert done["status"] == "COMPLETED" and done["outcome"] == outcome
        reviews[review_type] = done
    assert reviews["RISK"]["reviewer"]["id"] == risk_id and reviews["REGULATORY"]["reviewer"]["id"] == regulatory_id
    checks = _readiness(investigator, case_id)
    assert checks["risk_review"]["result"] == "PASS" and checks["regulatory_review"]["result"] == "PASS"

    # The Decision Brief: version 1 returned by the quality reviewer, version 2 accepted.
    first = _submit(org, case_id)
    assert first["version"] == 1 and first["status"] == "READY_FOR_REVIEW"
    assert first["content"]["leading_hypothesis"]["business_id"] == leading["business_id"]
    returned = _ok(
        quality.post(
            _brief(case_id) + "/versions/1/review", json={"action": "RETURN_FOR_EVIDENCE", "comment": RETURN_COMMENT}
        )
    )
    assert returned["status"] == "RETURNED" and _case_row(tenant_id, case_id).workflow_state == "IN_PROGRESS"
    second = _ok(investigator.post(_brief(case_id), json={}), 201)
    assert second["version"] == 2 and second["business_id"] != first["business_id"]
    edited = {"problem_statement": NARRATIVE["problem_statement"] + "; the pressure logs confirm the offset"}
    _ok(investigator.put(_brief(case_id) + "/draft", json=edited))
    assert _ok(investigator.post(_brief(case_id) + "/submit", json={}))["status"] == "READY_FOR_REVIEW"
    approved = _accept(org, case_id, 2)
    assert _case_row(tenant_id, case_id).workflow_state == "READY_FOR_DECISION"

    # The decision maker signs, with a CAPA as follow-up.
    signed = _ok(_sign(decider, case_id, approved, follow_ups=[{"action_type": "CAPA_REQUIRED"}]))
    decision = signed["decision"]
    assert signed["verification"]["status"] == "VALID" and decision["decision_status"] == "SIGNED"
    assert decision["decided_by_user_id"] == decider_id and decision["decided_under_role"] == "APPROVER"
    assert decision["brief_version_id"] == approved["id"]
    (follow_up,) = signed["follow_ups"]
    assert follow_up["action_type"] == "CAPA_REQUIRED" and follow_up["assignee_user_id"] == investigator_id
    assert _case_row(tenant_id, case_id).workflow_state == "DECIDED"

    # The case closes once its closure criteria are met.
    check = _ok(investigator.get(f"/api/v1/investigations/{case_id}/closure-check"))
    assert check["applies"] is True and check["can_close"] is True, check
    closed = _ok(
        investigator.patch(
            f"/api/v1/investigations/{case_id}",
            json={"status": "closed", "reason": "Decision signed; the CAPA is tracked in the quality system"},
        )
    )
    assert closed["status"] == "closed" and closed["workflow_state"] == "CLOSED"
    return {
        "started": started,
        "finished": datetime.now(timezone.utc),
        "seed": seed,
        "signal": signal,
        "case_id": case_id,
        "case_business_id": case["business_id"],
        "bench": bench,
        "logs": logs,
        "request": request,
        "leading": leading,
        "alternative": alternative,
        "unknown": unknown,
        "reviews": reviews,
        "brief_v1": first,
        "brief_v2": approved,
        "decision": decision,
        "follow_up": follow_up,
    }


def test_01_golden_path_with_six_distinct_users(org, golden):
    tenant_id = org["tenant_id"]
    ids = {name: org[name][1] for name in SIX}
    assert len(set(ids.values())) == 6
    case_id, investigator = golden["case_id"], org["investigator"][0]

    # Each step is recorded under the person and role that did it.
    events = _signal_detail(investigator, golden["signal"]["id"])["events"]
    roles = {event["event_type"]: event["actor_role"] for event in events}
    assert {key: roles.get(key) for key in ("CREATED", "TRIAGE_STARTED", "PRIORITY_SET", "DISPOSITIONED")} == {
        "CREATED": "TRIAGE_LEAD",
        "TRIAGE_STARTED": "TRIAGE_LEAD",
        "PRIORITY_SET": "TRIAGE_LEAD",
        "DISPOSITIONED": "TRIAGE_LEAD",
    }
    assert roles["INVESTIGATION_CREATED"] == "TRIAGE_LEAD"
    v1 = _ok(investigator.get(_brief(case_id) + "/versions/1"))
    v2 = _ok(investigator.get(_brief(case_id) + "/versions/2"))
    assert v1["status"] == "RETURNED" and v1["content_hash"] == golden["brief_v1"]["content_hash"]
    assert v1["hash_verified"] is True and v2["status"] == "APPROVED_FOR_DECISION"
    assert [(item["action"], item["actor_role"]) for item in v1["review_actions"]] == [
        ("START_REVIEW", "REVIEWER"),
        ("RETURN_FOR_EVIDENCE", "REVIEWER"),
    ]
    assert v2["submitted_by_name"] == "Investigator E2E" and v2["reviewed_by_name"] == "Quality E2E"
    record = _record(investigator, golden["decision"]["id"])
    assert record["verification"]["status"] == "VALID" and record["signature"]["signer_name"] == "Decider E2E"
    assert record["decision"]["brief_business_id"] == golden["brief_v2"]["business_id"]
    assert _get(tenant_id, Signal, id=uuid.UUID(golden["signal"]["id"])).status == "CLOSED"
    assert _case_row(tenant_id, case_id).workflow_state == "CLOSED"
    follow_up = _get(tenant_id, DecisionFollowUp, id=uuid.UUID(golden["follow_up"]["id"]))
    assert follow_up.status == "OPEN"  # the CAPA outlives the case

    # The audit trail holds every step, in the order it happened.
    ordered = [
        "SIGNAL_CREATED",
        "SIGNAL_TRIAGE_STARTED",
        "SIGNAL_DISPOSITIONED",
        "SIGNAL_INVESTIGATION_CREATED",
        "INVESTIGATION_SCOPE_CHANGED",
        "EVIDENCE_REVIEWED",
        "EVIDENCE_REQUESTED",
        "EVIDENCE_REQUEST_RESPONDED",
        "EVIDENCE_REQUEST_REVIEWED",
        "INTELLIGENCE_STATUS_CHANGED",
        "CASE_REVIEW_COMPLETED",
        "BRIEF_SUBMITTED",
        "BRIEF_RETURN_FOR_EVIDENCE",
        "BRIEF_ACCEPT_FOR_DECISION",
        "CASE_DECISION_SIGNED",
        "INVESTIGATION_CLOSED",
    ]
    rows = _all(
        tenant_id,
        AuditEvent,
        AuditEvent.action.in_(ordered),
        AuditEvent.created_at >= golden["started"],
        AuditEvent.created_at <= golden["finished"],
        order_by=AuditEvent.created_at,
    )
    first_seen: dict[str, datetime] = {}
    for row in rows:
        first_seen.setdefault(row.action, row.created_at)
    assert [action for action in ordered if action not in first_seen] == []
    times = [first_seen[action] for action in ordered]
    assert times == sorted(times), list(zip(ordered, times))

    # The trust timeline of the case shows each step in order.
    timeline, _ = _timeline(investigator, case_id)
    markers = [
        ("signal", golden["signal"]["business_id"]),
        ("case", golden["case_business_id"]),
        ("evidence", golden["bench"]["business_id"]),
        ("evidence request", golden["request"]["business_id"]),
        ("hypothesis", golden["leading"]["business_id"]),
        ("risk review", golden["reviews"]["RISK"]["business_id"]),
        ("regulatory review", golden["reviews"]["REGULATORY"]["business_id"]),
        ("brief v1", golden["brief_v1"]["business_id"]),
        ("brief v2", golden["brief_v2"]["business_id"]),
        ("decision", golden["decision"]["business_id"]),
    ]
    positions = [(name, _first(timeline, marker)) for name, marker in markers]
    assert [name for name, index in positions if index < 0] == [], positions
    assert [index for _, index in positions] == sorted(index for _, index in positions), positions
    follow_up_at = _first(timeline, golden["follow_up"]["business_id"])
    assert follow_up_at >= positions[-2][1], (follow_up_at, positions)
    closing = [
        index
        for index, event in enumerate(timeline)
        if index >= positions[-1][1] and re.search(r"clos", json.dumps(event, default=str), re.IGNORECASE)
    ]
    assert closing, "The timeline does not show the case closing after the decision"


# ============================================================================== 2. a small company: several roles


def test_02_one_person_holds_three_workflow_roles_and_acts_under_each(org):
    tenant_id = org["tenant_id"]
    multi, multi_id = org["multi"]
    decider, _ = org["decider"]
    session = _ok(multi.get("/api/v1/session/context"))
    assert [(role["code"], role["source"]) for role in session["roles"]] == [
        ("INVESTIGATOR", "account"),
        ("TRIAGE_LEAD", "additional"),
        ("REVIEWER", "additional"),
        ("APPROVER", "additional"),
    ]
    assert {"signal.triage", "quality.review", "decision.sign", "investigation.work"} <= set(
        session["business_permissions"]
    )

    # As Triage Lead the person raises and triages a signal; as Investigator opens the case and writes its brief.
    seed = _seed(tenant_id, problem="SMALL TEAM")
    signal = _needs_case(multi, seed, "Alarm reports from a small customer")
    opened = _ok(
        _triage(
            multi,
            signal["id"],
            "create-investigation",
            {"investigation_question": QUESTION, "assignee_user_id": multi_id},
        ),
        201,
    )
    case = opened["investigation"]
    roles = {event["event_type"]: event["actor_role"] for event in _signal_detail(multi, signal["id"])["events"]}
    assert roles["CREATED"] == "TRIAGE_LEAD" and roles["DISPOSITIONED"] == "TRIAGE_LEAD"
    assert roles["INVESTIGATION_CREATED"] == "INVESTIGATOR"
    assert _case_row(tenant_id, case["id"]).workflow_state == "IN_PROGRESS"
    _make_ready(org, "multi", case)
    _submit(org, case["id"], "multi")
    own = _get(tenant_id, DecisionBriefVersion, investigation_id=uuid.UUID(case["id"]), version=1)
    assert own.created_role == "INVESTIGATOR" and own.submitted_by == multi_id

    # Holding the Quality Reviewer and Decision Maker roles does not let them review or sign what they wrote.
    for response in (
        multi.post(_brief(case["id"]) + "/versions/1/start-review", json={}),
        multi.post(_brief(case["id"]) + "/versions/1/review", json={"action": "ACCEPT_FOR_DECISION"}),
    ):
        assert response.status_code == 403 and _code(response) == "SOD_DENIED", response.text
    brief = _accept(org, case["id"])
    refused = _sign(multi, case["id"], brief)
    assert refused.status_code == 403 and _code(refused) == "SOD_DENIED", refused.text
    assert "SOD_DENIED" in _audit_actions(tenant_id, case["id"])
    actions = _ok(multi.get(_decision(case["id"])))["actions"]
    assert actions["can_sign"] is False and actions["reason"]
    assert _all(tenant_id, Decision, Decision.investigation_id == uuid.UUID(case["id"])) == []
    assert _ok(_sign(decider, case["id"], brief))["decision"]["decided_under_role"] == "APPROVER"

    # On a colleague's brief the same person reviews as Quality Reviewer and decides as Decision Maker.
    other = _ready_case(org, "investigator")
    _submit(org, other["id"])
    reviewed = _ok(multi.post(_brief(other["id"]) + "/versions/1/review", json={"action": "ACCEPT_FOR_DECISION"}))
    assert [(item["action"], item["actor_role"]) for item in reviewed["review_actions"]] == [
        ("START_REVIEW", "REVIEWER"),
        ("ACCEPT_FOR_DECISION", "REVIEWER"),
    ]
    signed = _ok(_sign(multi, other["id"], reviewed))
    assert signed["decision"]["decided_by_user_id"] == multi_id
    assert signed["decision"]["decided_under_role"] == "APPROVER"
    stored = _get(tenant_id, Decision, id=uuid.UUID(signed["decision"]["id"]))
    assert stored.decided_under_role == "APPROVER" and str(stored.decided_by_user_id) == multi_id


# =============================================================================== 3. monitor, no investigation


def test_03_a_new_signal_is_monitored_without_an_investigation_and_comes_back(org):
    tenant_id = org["tenant_id"]
    lead, _ = org["lead"]
    seed = _seed(tenant_id, complaints=3, problem="MONITOR DRIP", days_ago=2)
    created = _run_detection(lead)
    (signal,) = _ok(lead.get("/api/v1/triage/signals", params={"product_id": seed["product_id"]}))["items"]
    assert signal["business_id"] in created["created"] and signal["origin"] == "THRESHOLD_RULE"
    assert _ok(_triage(lead, signal["id"], "start"))["status"] == "TRIAGE"

    trigger = "Two more complaints of the same kind within a month"
    review = (datetime.now(timezone.utc).date() + timedelta(days=14)).isoformat()
    missing = _triage(lead, signal["id"], "disposition", {"disposition": "MONITOR", "reason": REASON})
    assert missing.status_code == 422 and _code(missing) == "MONITOR_DETAILS_REQUIRED"
    monitored = _ok(
        _triage(
            lead,
            signal["id"],
            "disposition",
            {"disposition": "MONITOR", "reason": REASON, "monitor_review_date": review, "monitor_trigger": trigger},
        )
    )
    assert monitored["status"] == "MONITOR" and monitored["investigations"] == []
    assert monitored["disposition"]["monitor_review_date"] == review
    assert monitored["disposition"]["monitor_trigger"] == trigger
    (task,) = _tasks(tenant_id, source_id=signal["id"], task_type="SIGNAL_TRIAGE")
    assert task.status == "COMPLETED" and task.completion_outcome == "MONITOR"
    due = _ok(lead.get("/api/v1/triage/signals", params={"review_due": "true", "page_size": 200}))
    assert signal["id"] not in [item["id"] for item in due["items"]]

    # Nothing new: detection leaves it monitored.
    assert signal["business_id"] not in _run_detection(lead)["monitor_reopened"]
    assert _get(tenant_id, Signal, id=uuid.UUID(signal["id"])).status == "MONITOR"

    # A later complaint of the same kind sends it back to triage, still without an investigation.
    _add_complaint(tenant_id, seed)
    assert signal["business_id"] in _run_detection(lead)["monitor_reopened"]
    back = _signal_detail(lead, signal["id"])
    assert back["status"] == "TRIAGE" and back["complaint_count"] == 4 and back["investigations"] == []
    assert "MONITOR_TRIGGERED" in [event["event_type"] for event in back["events"]]
    assert [task.status for task in _tasks(tenant_id, source_id=signal["id"], task_type="SIGNAL_TRIAGE")] == [
        "COMPLETED",
        "NEW",
    ]
    assert _all(tenant_id, InvestigationSignal, InvestigationSignal.signal_id == uuid.UUID(signal["id"])) == []


# ================================================================================ 4. duplicate and merge


def test_04_a_duplicate_and_a_merge_keep_their_lineage_and_delete_nothing(org):
    tenant_id = org["tenant_id"]
    lead, _ = org["lead"]
    seed = _seed(tenant_id, complaints=3, problem="BATTERY DRAIN")
    first, second, third = (
        _signal(lead, seed, title, complaint_ids=[complaint])
        for title, complaint in zip(
            ("Battery drains early", "Battery drains overnight", "Battery empty after use"), seed["complaint_ids"]
        )
    )
    no_canonical = _triage(lead, second["id"], "disposition", {"disposition": "DUPLICATE", "reason": REASON})
    assert no_canonical.status_code == 422 and _code(no_canonical) == "CANONICAL_REQUIRED"
    duplicate = _ok(
        _triage(
            lead,
            second["id"],
            "disposition",
            {"disposition": "DUPLICATE", "reason": REASON, "canonical_signal_id": first["id"]},
        )
    )
    assert duplicate["status"] == "DUPLICATE"
    assert duplicate["canonical"] == {"id": first["id"], "business_id": first["business_id"]}
    merged = _ok(_triage(lead, first["id"], "merge", {"source_signal_ids": [third["id"]], "reason": REASON}))
    assert {(item["business_id"], item["status"]) for item in merged["merged_from"]} == {
        (second["business_id"], "DUPLICATE"),
        (third["business_id"], "MERGED"),
    }
    assert merged["complaint_count"] == 2
    # A signal that is no longer open cannot be merged again.
    again = _triage(lead, first["id"], "merge", {"source_signal_ids": [second["id"]], "reason": REASON})
    assert again.status_code == 409 and _code(again) == "SIGNAL_STATE_CONFLICT"

    # Nothing was deleted: every signal is still there with its complaints and its history.
    for source, status in ((second, "DUPLICATE"), (third, "MERGED")):
        detail = _signal_detail(lead, source["id"])
        assert detail["status"] == status and detail["canonical"]["business_id"] == first["business_id"]
        assert detail["complaint_count"] == 1 and detail["events"][0]["event_type"] == "CREATED"
    rows = _all(tenant_id, Signal, Signal.product_id == uuid.UUID(seed["product_id"]))
    assert {str(row.id) for row in rows} == {first["id"], second["id"], third["id"]}
    links = _all(tenant_id, SignalComplaint, SignalComplaint.signal_id.in_([row.id for row in rows]))
    by_signal: dict[str, int] = {}
    for link in links:
        by_signal[str(link.signal_id)] = by_signal.get(str(link.signal_id), 0) + 1
    assert by_signal == {first["id"]: 2, second["id"]: 1, third["id"]: 1}
    for item in (first, second, third):
        assert "SIGNAL_CREATED" in _audit_actions(tenant_id, item["id"])
    assert "SIGNAL_MERGED" in _audit_actions(tenant_id, third["id"])


# ======================================================================= 5. one signal, several investigations


def test_05_one_signal_opens_several_investigations(org):
    tenant_id = org["tenant_id"]
    lead, _ = org["lead"]
    investigator, investigator_id = org["investigator"]
    seed = _seed(tenant_id, complaints=2, problem="TUBING KINK")
    signal = _needs_case(lead, seed, "Tubing kinks under the clamp")
    first = _ok(
        _triage(
            investigator,
            signal["id"],
            "create-investigation",
            {"investigation_question": QUESTION, "assignee_user_id": investigator_id},
        ),
        201,
    )
    second = _ok(
        _triage(
            investigator,
            signal["id"],
            "create-investigation",
            {"investigation_question": "Is the supplier lot of the tubing involved?"},
        ),
        201,
    )
    cases = {first["investigation"]["id"], second["investigation"]["id"]}
    assert len(cases) == 2 and len(second["signal"]["investigations"]) == 2
    assert {item["id"] for item in _signal_detail(lead, signal["id"])["investigations"]} == cases
    links = _all(tenant_id, InvestigationSignal, InvestigationSignal.signal_id == uuid.UUID(signal["id"]))
    assert {str(link.investigation_id) for link in links} == cases
    for case_id in cases:
        scope = _ok(investigator.get(f"/api/v1/investigations/{case_id}/scope"))["current"]
        assert {item["id"] for item in scope["included_complaints"]} == set(seed["complaint_ids"])
    (queued,) = _tasks(tenant_id, case_id=second["investigation"]["id"], task_type="INVESTIGATION")
    assert queued.status == "NEW" and queued.assigned_user_id is None and queued.assigned_role == "INVESTIGATOR"

    # The signal stays open while one of its cases is.
    path = "/api/v1/investigations/{}"
    _ok(lead.patch(path.format(first["investigation"]["id"]), json={"status": "closed", "reason": REASON}))
    assert _get(tenant_id, Signal, id=uuid.UUID(signal["id"])).status == "INVESTIGATION_OPEN"
    _ok(lead.patch(path.format(second["investigation"]["id"]), json={"status": "closed", "reason": REASON}))
    assert _get(tenant_id, Signal, id=uuid.UUID(signal["id"])).status == "CLOSED"


# ======================================================================= 6. several signals, one investigation


def test_06_several_signals_become_one_investigation(org):
    tenant_id = org["tenant_id"]
    lead, _ = org["lead"]
    investigator, investigator_id = org["investigator"]
    seed = _seed(tenant_id, complaints=3, problem="PRESSURE DRIFT")
    first, second, third = seed["complaint_ids"]
    main = _needs_case(lead, seed, "Pressure readings drift", complaint_ids=[first])
    also_a = _signal(lead, seed, "Pressure alarm at start-up", complaint_ids=[second])
    also_b = _signal(lead, seed, "Pressure alarm after priming", complaint_ids=[third])
    elsewhere = _signal(lead, _seed(tenant_id, problem="PRESSURE DRIFT"), "Pressure drift on another pump")
    mismatch = _triage(
        investigator,
        main["id"],
        "create-investigation",
        {"investigation_question": QUESTION, "also_signal_ids": [elsewhere["id"]]},
    )
    assert mismatch.status_code == 422 and _code(mismatch) == "PRODUCT_MISMATCH"

    opened = _ok(
        _triage(
            investigator,
            main["id"],
            "create-investigation",
            {
                "investigation_question": QUESTION,
                "assignee_user_id": investigator_id,
                "also_signal_ids": [also_a["id"], also_b["id"]],
                "complaint_ids": seed["complaint_ids"],
            },
        ),
        201,
    )
    case = opened["investigation"]
    assert case["complaints_linked"] == 3
    links = _all(tenant_id, InvestigationSignal, InvestigationSignal.investigation_id == uuid.UUID(case["id"]))
    assert {str(link.signal_id) for link in links} == {main["id"], also_a["id"], also_b["id"]}
    for item in (main, also_a, also_b):
        detail = _signal_detail(lead, item["id"])
        assert detail["status"] == "INVESTIGATION_OPEN", item["business_id"]
        assert case["id"] in [entry["id"] for entry in detail["investigations"]]
    scope = _ok(investigator.get(f"/api/v1/investigations/{case['id']}/scope"))["current"]
    assert {item["id"] for item in scope["included_complaints"]} == set(seed["complaint_ids"])
    assert _get(tenant_id, Signal, id=uuid.UUID(elsewhere["id"])).status == "NEW"


# ================================================================================ 7. reassigning the investigator


def test_07_reassigning_the_case_task_with_a_reason_moves_the_case_owner(org):
    tenant_id = org["tenant_id"]
    lead, _ = org["lead"]
    investigator, investigator_id = org["investigator"]
    colleague, colleague_id = org["colleague"]
    _, viewer_id = org["viewer"]
    case = _open_case(investigator, _seed(tenant_id))
    (task,) = _tasks(tenant_id, case_id=case["id"], task_type="INVESTIGATION")
    assert task.status == "ACCEPTED" and str(task.assigned_user_id) == investigator_id
    path = f"/api/v1/tasks/{task.id}/reassign"
    why = "Investigator on leave for three weeks; the colleague knows the pump"

    refused = investigator.post(path, json={"reason": why, "assignee_user_id": colleague_id})
    assert refused.status_code == 403 and _code(refused) == "PERMISSION_DENIED"
    assert lead.post(path, json={"reason": "short", "assignee_user_id": colleague_id}).status_code == 422
    ineligible = lead.post(path, json={"reason": why, "assignee_user_id": viewer_id})
    assert ineligible.status_code == 422 and _code(ineligible) == "ASSIGNEE_NOT_ELIGIBLE"

    moved = _ok(lead.post(path, json={"reason": why, "assignee_user_id": colleague_id}))
    assert moved["status"] == "ASSIGNED" and moved["assigned_user"]["id"] == colleague_id
    assert _case_row(tenant_id, case["id"]).owner_ref == _username(tenant_id, colleague_id)
    (owner_change,) = _audits(tenant_id, case["id"], "INVESTIGATION_UPDATED")
    assert why in owner_change.reason and task.business_id in owner_change.reason
    assert owner_change.old_values == {"owner": _username(tenant_id, investigator_id)}
    assert owner_change.new_values == {"owner": _username(tenant_id, colleague_id)}
    events = _ok(colleague.get(f"/api/v1/tasks/{task.id}"))["events"]
    assert events[-1]["event_type"] == "REASSIGNED" and events[-1]["reason"] == why
    assert events[-1]["actor_role"] == "TRIAGE_LEAD"

    def assigned(client) -> list[str]:
        items = _ok(client.get("/api/v1/tasks", params={"view": "assigned", "page_size": 200}))["items"]
        return [item["id"] for item in items]

    assert str(task.id) in assigned(colleague) and str(task.id) not in assigned(investigator)
    assert _ok(colleague.post(f"/api/v1/tasks/{task.id}/accept"))["status"] == "ACCEPTED"
    assert _case_row(tenant_id, case["id"]).workflow_state == "IN_PROGRESS"


# ================================================================================= 8. an overdue evidence request


def test_08_an_overdue_evidence_request_is_listed_overdue_and_escalated(org):
    tenant_id = org["tenant_id"]
    investigator, investigator_id = org["investigator"]
    colleague, colleague_id = org["colleague"]
    quality, _ = org["quality"]
    case = _open_case(investigator, _seed(tenant_id))
    _ok(investigator.patch(f"/api/v1/investigations/{case['id']}", json={"reason": REASON, "priority": "CRITICAL"}))
    request = _ok(
        investigator.post(
            f"/api/v1/investigations/{case['id']}/evidence-requests",
            json={
                "kind": "INTERNAL",
                "title": "Batch record for lot KS-5521",
                "requested_items": ["Batch record"],
                "rationale": "Needed to check the sensor batch",
                "priority": "HIGH",
                "due_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                "recipient_user_id": colleague_id,
            },
        ),
        201,
    )
    assert request["overdue"] is False
    path = f"/api/v1/evidence-requests/{request['id']}"

    # Its due date passes.
    past = datetime.now(timezone.utc) - timedelta(days=2)
    _update(tenant_id, SupplierEvidenceRequest, SupplierEvidenceRequest.id == uuid.UUID(request["id"]), due_at=past)
    _update(tenant_id, WorkflowTask, WorkflowTask.source_entity_id == uuid.UUID(request["id"]), due_at=past)
    assert _ok(investigator.get(path))["overdue"] is True
    received = _ok(
        colleague.get("/api/v1/evidence-requests", params={"box": "received", "investigation_id": case["id"]})
    )
    (listed,) = [item for item in received["items"] if item["id"] == request["id"]]
    assert listed["overdue"] is True

    # The escalation shows in My Work of both people, the case readiness and the dashboards.
    (response_task,) = _tasks(tenant_id, source_id=request["id"], task_type="EVIDENCE_RESPONSE")
    (waiting_task,) = _tasks(tenant_id, source_id=request["id"], task_type="EVIDENCE_REQUEST")
    assert str(waiting_task.assigned_user_id) == investigator_id

    def overdue(client) -> list[str]:
        items = _ok(client.get("/api/v1/tasks", params={"view": "overdue", "page_size": 200}))["items"]
        assert all(item["overdue"] for item in items)
        return [item["id"] for item in items]

    assert str(response_task.id) in overdue(colleague) and str(waiting_task.id) in overdue(investigator)
    assert _ok(colleague.get("/api/v1/tasks/summary"))["counts"]["overdue"] >= 1
    assert _ok(investigator.get("/api/v1/tasks/summary"))["counts"]["overdue"] >= 1
    checks = _readiness(investigator, case["id"])
    assert checks["no_blocking_request"]["result"] == "BLOCKED"
    mine = _ok(investigator.get("/api/v1/investigations/mine/summary"))
    assert mine["counts"]["requests_waiting"] >= 1
    assert [item["open_requests"] for item in mine["cases"] if item["id"] == case["id"]] == [1]
    blocked = _ok(quality.get("/api/v1/decision-briefs/summary"))["blocked"]
    (card,) = [item for item in blocked if item["investigation"]["business_id"] == case["business_id"]]
    assert "no_blocking_request" in {item["key"] for item in card["blocking"]}

    # Once answered it is no longer overdue and its task leaves the overdue list.
    assert _ok(colleague.post(f"{path}/respond", json={"note": "Batch record attached"}))["status"] == "RECEIVED"
    assert _ok(investigator.get(path))["overdue"] is False
    assert str(response_task.id) not in overdue(colleague)


# ======================================================================= 9. contradicting evidence, new leader


def test_09_contradicting_evidence_changes_the_leading_hypothesis(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    case = _ready_case(org)
    case_id, first = case["id"], case["_hypothesis"]
    alternative = _hypothesis(
        investigator, case_id, "Tubing from the new supplier kinks under the clamp", status="PARTIALLY_SUPPORTED"
    )
    draft = _ok(investigator.post(_brief(case_id), json={}), 201)
    assert draft["content"]["leading_hypothesis"]["business_id"] == first["business_id"]
    assert alternative["business_id"] in [item["business_id"] for item in draft["content"]["alternative_hypotheses"]]

    # A field return analysis contradicts the leading hypothesis and supports the alternative.
    returns = _evidence(tenant_id, case_id=case_id, title="Field return analysis of the pumps")
    _review_evidence(
        investigator,
        case_id,
        returns["id"],
        relationship="CONTRADICTING",
        reason="No drift on any of the returned pumps",
    )
    _link(investigator, case_id, first["id"], returns["id"], "CONTRADICTING")
    _link(investigator, case_id, alternative["id"], returns["id"], "SUPPORTING")
    contradictions = _ok(investigator.get(f"{_intel(case_id)}/contradictions"))
    assert contradictions["counts"]["hypothesis_links"] >= 1 and contradictions["counts"]["case_evidence"] >= 1
    assert _readiness(investigator, case_id)["contradictions_documented"]["result"] == "PENDING"

    # People judge again; the brief follows their judgement, never the AI's.
    assert _judge(investigator, case_id, first["id"], "CONTRADICTED")["human_status"] == "CONTRADICTED"
    assert (
        _judge(investigator, case_id, alternative["id"], "STRONGLY_SUPPORTED")["human_status"] == "STRONGLY_SUPPORTED"
    )
    assert _readiness(investigator, case_id)["contradictions_documented"]["result"] == "PASS"
    refreshed = _ok(investigator.post(_brief(case_id) + "/draft/refresh"))
    content = refreshed["content"]
    assert content["leading_hypothesis"]["business_id"] == alternative["business_id"]
    assert content["leading_hypothesis"]["human_status"] == "STRONGLY_SUPPORTED"
    others = {item["business_id"]: item for item in content["alternative_hypotheses"]}
    assert others[first["business_id"]]["human_status"] == "CONTRADICTED"
    # The brief judges evidence against the leading explanation, each piece once (0.10.72): the field returns, which
    # contradicted the first explanation, support the alternative that now leads, and say so through its link.
    by_evidence = {item["evidence_business_id"]: item for item in content["supporting_evidence"]}
    assert by_evidence[returns["business_id"]]["hypothesis_business_id"] == alternative["business_id"]
    assert returns["business_id"] not in {item["evidence_business_id"] for item in content["contradicting_evidence"]}
    assert refreshed["content_hash"] != draft["content_hash"] and refreshed["hash_verified"] is True

    _ok(investigator.put(_brief(case_id) + "/draft", json=NARRATIVE))
    submitted = _ok(investigator.post(_brief(case_id) + "/submit", json={}))
    assert submitted["content"]["leading_hypothesis"]["business_id"] == alternative["business_id"]


# ============================================================================== 10. AI unavailable, work goes on


def test_10_with_ai_switched_off_the_workflow_is_completed_by_hand(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    decider, _ = org["decider"]
    status = _ai_off(org)
    assert status["manual_paths"]["hypotheses"] is True and status["manual_paths"]["ask"] == "record-based answers"
    assert "AI_PROCESSING_SETTING_CHANGED" in _audit_actions(tenant_id, tenant_id)

    seed = _seed(tenant_id)
    case = _open_case(investigator, seed, seed["complaint_ids"][:1])
    case_id = case["id"]
    bench = _evidence(tenant_id, case_id=case_id)
    _review_evidence(investigator, case_id, bench["id"], reason="The bench test reproduces the alarm")
    hypothesis = _hypothesis(
        investigator,
        case_id,
        "The occlusion sensor of release B drifts under load",
        status="STRONGLY_SUPPORTED",
        evidence_id=bench["id"],
    )
    assert hypothesis["origin"] == "HUMAN"
    unknown = _ok(
        investigator.post(f"{_intel(case_id)}/unknowns", json={"description": "Which firmware ran on the pumps?"}),
        201,
    )
    assert unknown["origin"] == "HUMAN"
    _ok(
        investigator.post(
            f"{_intel(case_id)}/unknowns/{unknown['id']}/status",
            json={"status": "resolved", "reason": "The service log names release B on every pump"},
        )
    )
    chain = _ok(
        investigator.post(
            f"{_intel(case_id)}/failure-chains",
            json={
                "name": "Sensor drift to false alarm",
                "nodes": ["Release B firmware", "Sensor offset of 4 psi", "Occlusion alarm without occlusion"],
                "links": [
                    {
                        "from_index": 0,
                        "to_index": 1,
                        "state": "SUPPORTED",
                        "evidence_id": bench["id"],
                        "rationale": REASON,
                    },
                    {"from_index": 1, "to_index": 2, "state": "HYPOTHESIZED"},
                ],
            },
        ),
        201,
    )
    assert chain["origin"] == "HUMAN"
    observation = _ok(
        investigator.post(
            f"{_intel(case_id)}/observations",
            json={"evidence_id": bench["id"], "statement": "Alarm at 4 psi", "epistemic_type": "FACT"},
        ),
        201,
    )
    assert observation["origin"] == "HUMAN" and observation["epistemic_type"] == "FACT"
    analysis = _readiness(investigator, case_id)["analysis_run"]
    assert analysis["result"] == "PASS" and analysis["rationale"].startswith("People recorded")

    # No AI draft is offered; the brief is written, reviewed and decided without any AI run.
    no_draft = investigator.post(_brief(case_id), json={"use_ai_draft": True})
    assert no_draft.status_code == 409 and _code(no_draft) == "AI_DRAFT_NOT_AVAILABLE"
    submitted = _submit(org, case_id)
    ai = submitted["content"]["ai_assistance"]
    assert (
        ai["executions"] == []
        and ai["statement"] == "No AI was used in this investigation. People made the judgements."
    )
    brief = _accept(org, case_id)
    signed = _ok(_sign(decider, case_id, brief))
    assert signed["decision"]["ai_execution_refs"] == [] and signed["verification"]["status"] == "VALID"
    assert _all(tenant_id, AIExecution, AIExecution.investigation_id == uuid.UUID(case_id)) == []
    assert _ok(_trust(investigator, case_id, "ai-runs"))["counts"]["total"] == 0
    assert _case_row(tenant_id, case_id).workflow_state == "DECIDED"


# ===================================================================== 11. risk review asks for more evidence


def test_11_a_risk_review_asking_for_more_evidence_blocks_submission_until_a_new_one_completes(org):
    tenant_id = org["tenant_id"]
    investigator, investigator_id = org["investigator"]
    risk, _ = org["risk"]
    case = _ready_case(org)
    case_id = case["id"]
    _ok(investigator.patch(f"/api/v1/investigations/{case_id}", json={"reason": REASON, "priority": "HIGH"}))
    policy = _ok(investigator.get(f"/api/v1/investigations/{case_id}/reviews/policy"))
    assert policy["risk"]["required"] is True and policy["regulatory"]["required"] is False
    _ok(investigator.post(_brief(case_id), json={}), 201)
    _ok(investigator.put(_brief(case_id) + "/draft", json=NARRATIVE))

    def review(outcome: str) -> dict:
        made = _ok(investigator.post(f"/api/v1/investigations/{case_id}/reviews", json={"review_type": "RISK"}), 201)
        _ok(risk.post(f"/api/v1/case-reviews/{made['id']}/start"))
        done = risk.post(
            f"/api/v1/case-reviews/{made['id']}/complete", json={"outcome": outcome, "rationale": REVIEW_RATIONALE}
        )
        return _ok(done)

    first = review("ADDITIONAL_EVIDENCE_REQUIRED")
    assert first["outcome_label"] == "Additional evidence required"
    (follow_up,) = _tasks(tenant_id, source_id=first["id"], task_type="FOLLOW_UP")
    assert follow_up.is_return is True and str(follow_up.assigned_user_id) == investigator_id
    check = _readiness(investigator, case_id)["risk_review"]
    assert check["result"] == "BLOCKED" and "A new risk review must be completed" in check["rationale"]
    refused = investigator.post(_brief(case_id) + "/submit", json={})
    assert refused.status_code == 409 and _code(refused) == "BRIEF_NOT_READY"
    assert "risk_review" in {item["key"] for item in refused.json()["detail"]["blocking"]}
    assert _get(tenant_id, DecisionBriefVersion, investigation_id=uuid.UUID(case_id), version=1).status == "DRAFT"

    second = review("NO_CHANGE_REQUIRED")
    assert _readiness(investigator, case_id)["risk_review"]["result"] == "PASS"
    submitted = _ok(investigator.post(_brief(case_id) + "/submit", json={}))
    assert submitted["status"] == "READY_FOR_REVIEW"
    assert submitted["content"]["risk_review"]["review"]["business_id"] == second["business_id"]
    assert submitted["content"]["risk_review"]["review"]["outcome"] == "NO_CHANGE_REQUIRED"


# ============================================================================ 12. regulatory review by market


@pytest.mark.skip(reason="Later release: regulatory reviews that differ by market are not built yet")
def test_12_a_regulatory_review_differs_by_market():
    """Expected once built: a case whose scope covers the EU and the US gets one regulatory assessment per market
    (reportable in one, not in the other); the brief shows each market's outcome and the decision records both.
    Today one regulatory review covers every market of the case (its context lists the complaints by market)."""


# ============================================================================== 13. quality returns the brief


def test_13_the_quality_reviewer_returns_the_brief_and_version_2_follows_with_version_1_unchanged(org):
    tenant_id = org["tenant_id"]
    investigator, investigator_id = org["investigator"]
    quality, _ = org["quality"]
    case = _ready_case(org)
    case_id = case["id"]
    first = _submit(org, case_id)
    assert _ok(quality.post(_brief(case_id) + "/versions/1/start-review", json={}))["status"] == "UNDER_REVIEW"
    no_comment = quality.post(_brief(case_id) + "/versions/1/review", json={"action": "RETURN_FOR_EVIDENCE"})
    assert no_comment.status_code == 422
    returned = _ok(
        quality.post(
            _brief(case_id) + "/versions/1/review", json={"action": "RETURN_FOR_EVIDENCE", "comment": RETURN_COMMENT}
        )
    )
    assert returned["status"] == "RETURNED" and returned["review_actions"][-1]["comment"] == RETURN_COMMENT
    (follow_up,) = _tasks(tenant_id, source_id=first["id"], task_type="FOLLOW_UP")
    assert follow_up.is_return is True and str(follow_up.assigned_user_id) == investigator_id
    assert "BRIEF_RETURN_FOR_EVIDENCE" in _audit_actions(tenant_id, first["id"])
    assert _case_row(tenant_id, case_id).workflow_state == "IN_PROGRESS"

    second = _ok(investigator.post(_brief(case_id), json={}), 201)
    assert second["version"] == 2 and second["narrative"]["problem_statement"] == NARRATIVE["problem_statement"]
    _ok(investigator.put(_brief(case_id) + "/draft", json={"proposed_conclusion": "Sensor drift, confirmed by logs"}))
    _ok(investigator.post(_brief(case_id) + "/submit", json={}))
    versions = {item["version"]: item["status"] for item in _ok(investigator.get(_brief(case_id)))["versions"]}
    assert versions == {1: "RETURNED", 2: "READY_FOR_REVIEW"}
    (follow_up,) = _tasks(tenant_id, source_id=first["id"], task_type="FOLLOW_UP")
    assert follow_up.status == "COMPLETED" and follow_up.completion_outcome == "RESUBMITTED"
    _accept(org, case_id, 2)

    # Version 1 is exactly what was returned.
    v1 = _ok(investigator.get(_brief(case_id) + "/versions/1"))
    assert v1["status"] == "RETURNED" and v1["content_hash"] == first["content_hash"] and v1["hash_verified"] is True
    assert v1["content"] == first["content"] and v1["narrative"] == first["narrative"]
    assert v1["narrative"]["proposed_conclusion"] == NARRATIVE["proposed_conclusion"]


# ============================================================================ 14. decision maker returns the case


def test_14_the_decision_maker_returns_the_case_without_signing(org):
    tenant_id = org["tenant_id"]
    investigator, investigator_id = org["investigator"]
    decider, _ = org["decider"]
    case, brief = _approved(org)
    path = _decision(case["id"]) + "/return"
    body = {"brief_version_id": brief["id"], "comment": "The bench test of lot 7 must be in the brief"}

    refused = investigator.post(path, json=body)
    assert refused.status_code == 403 and _code(refused) == "PERMISSION_DENIED"
    assert decider.post(path, json={**body, "comment": "short"}).status_code == 422
    returned = _ok(decider.post(path, json=body))
    assert returned["brief"]["status"] == "RETURNED" and returned["actions"]["can_sign"] is False
    assert _case_row(tenant_id, case["id"]).workflow_state == "IN_PROGRESS"
    assert "CASE_DECISION_RETURNED" in _audit_actions(tenant_id, case["id"])
    returns = [task for task in _tasks(tenant_id, case_id=case["id"], task_type="FOLLOW_UP") if task.is_return]
    assert returns and str(returns[-1].assigned_user_id) == investigator_id
    (approval,) = _tasks(tenant_id, case_id=case["id"], task_type="DECISION_APPROVAL")
    assert approval.status == "COMPLETED" and approval.completion_outcome == "RETURNED"
    assert _all(tenant_id, Decision, Decision.investigation_id == uuid.UUID(case["id"])) == []
    assert _all(tenant_id, DecisionFollowUp, DecisionFollowUp.investigation_id == uuid.UUID(case["id"])) == []
    stale = _sign(decider, case["id"], brief)
    assert stale.status_code == 409 and _code(stale) == "STALE_BRIEF"
    assert _ok(investigator.get(_brief(case["id"])))["actions"]["can_compose"] is True


# ============================================================================== 15. signing with re-authentication


def test_15_a_signature_needs_re_authentication_and_verifies(org):
    tenant_id = org["tenant_id"]
    decider, decider_id = org["decider"]
    case, brief = _approved(org)

    wrong = _sign(decider, case["id"], brief, password="Not the password 1")
    assert wrong.status_code == 403 and _code(wrong) == "INVALID_REAUTHENTICATION"
    assert "Not the password" not in wrong.text and PASSWORD not in wrong.text
    assert "SIGNATURE_REAUTHENTICATION_FAILED" in _audit_actions(tenant_id, case["id"])
    details = json.dumps([row.details for row in _audits(tenant_id, case["id"], "SIGNATURE_REAUTHENTICATION_FAILED")])
    assert "Not the password" not in details
    assert _all(tenant_id, Decision, Decision.investigation_id == uuid.UUID(case["id"])) == []

    signed = _ok(_sign(decider, case["id"], brief))
    signature = signed["signature"]
    assert signature["status"] == "SIGNED" and signature["signer_name"] == "Decider E2E"
    assert re.fullmatch(r"[0-9a-f]{64}", signature["fingerprint_full"])
    assert signature["signature_meaning"] == (
        f"I, Decider E2E, Authorized Decision Maker, have reviewed Decision Brief {brief['business_id']} version 1 "
        "and decide: Accept the conclusion"
    )
    assert signed["verification"]["status"] == "VALID"
    assert {item["key"]: item["ok"] for item in signed["verification"]["checks"]} == {
        "fingerprint": True,
        "signature": True,
        "brief_hash": True,
        "snapshot": True,
        "authority": True,
        "separation": True,
    }
    decision = signed["decision"]
    assert decision["decided_by_user_id"] == decider_id and decision["brief_content_hash"] == brief["content_hash"]
    record = _record(org["viewer"][0], decision["id"])  # anyone in the organization reads and verifies it
    assert record["verification"]["status"] == "VALID"
    assert all(item["ok"] for item in record["verification"]["checks"])
    assert _governance_status(decider, decision["id"]) == "VALID"
    assert "CASE_DECISION_SIGNED" in _audit_actions(tenant_id, decision["id"])


# ======================================================================== 16. unauthorized people cannot decide


def test_16_people_without_decision_authority_cannot_decide(org):
    tenant_id = org["tenant_id"]
    case, brief = _approved(org)
    for name, code in (
        ("colleague", "APPROVAL_AUTHORITY_DENIED"),
        ("viewer", "APPROVAL_AUTHORITY_DENIED"),
        ("quality", "APPROVAL_AUTHORITY_DENIED"),
        ("admin", "ADMINISTRATOR_CANNOT_SIGN"),
    ):
        client, _ = org[name]
        refused = _sign(client, case["id"], brief)
        assert refused.status_code == 403 and _code(refused) == code, (name, refused.text)
        actions = _ok(client.get(_decision(case["id"])))["actions"]
        assert actions["can_sign"] is False and actions["reason"], name
    for name in ("colleague", "viewer"):
        client, _ = org[name]
        queue = client.get("/api/v1/decisions/queue")
        assert queue.status_code == 403 and _code(queue) == "PERMISSION_DENIED", name
        sent_back = client.post(
            _decision(case["id"]) + "/return", json={"brief_version_id": brief["id"], "comment": RETURN_COMMENT}
        )
        assert sent_back.status_code == 403 and _code(sent_back) == "PERMISSION_DENIED", name
    actions = set(_audit_actions(tenant_id, case["id"]))
    assert {"APPROVAL_AUTHORITY_DENIED", "ADMINISTRATOR_CANNOT_SIGN"} <= actions
    assert _all(tenant_id, Decision, Decision.investigation_id == uuid.UUID(case["id"])) == []
    assert _case_row(tenant_id, case["id"]).workflow_state == "READY_FOR_DECISION"


# ================================================================== 17. no self-approval under strict SoD


def test_17_an_investigator_with_every_role_cannot_approve_their_own_brief(org):
    tenant_id = org["tenant_id"]
    me, me_id = org["self_approver"]
    roles = [role["code"] for role in _ok(me.get("/api/v1/session/context"))["roles"]]
    assert roles == ["INVESTIGATOR", "REVIEWER", "APPROVER"]
    case = _ready_case(org, "self_approver")
    _submit(org, case["id"], "self_approver")
    base = _brief(case["id"])

    for response in (
        me.post(base + "/versions/1/start-review", json={}),
        me.post(base + "/versions/1/review", json={"action": "ACCEPT_FOR_DECISION"}),
    ):
        assert response.status_code == 403 and _code(response) == "SOD_DENIED", response.text
    page = _ok(me.get(base))
    assert page["actions"]["can_review"] is False and page["actions"]["can_start_review"] is False
    (review_task,) = _tasks(tenant_id, case_id=case["id"], task_type="QUALITY_REVIEW")
    assert review_task.assigned_user_id is None

    brief = _accept(org, case["id"])
    refused = _sign(me, case["id"], brief)
    assert refused.status_code == 403 and _code(refused) == "SOD_DENIED", refused.text
    assert "SOD_DENIED" in _audit_actions(tenant_id, case["id"])
    actions = _ok(me.get(_decision(case["id"])))["actions"]
    assert actions["can_sign"] is False and actions["reason"]
    assert _all(tenant_id, Decision, Decision.investigation_id == uuid.UUID(case["id"])) == []
    # Another authorized person decides.
    assert _ok(_sign(org["decider"][0], case["id"], brief))["decision"]["decided_by_user_id"] != me_id


# ======================================================================== 18. another organization's records


def test_18_another_organizations_records_are_not_found(org, golden):
    tenant_id = org["tenant_id"]
    outsider, _ = org["outsider"]
    case_id = golden["case_id"]
    case_tasks = _tasks(tenant_id, case_id=case_id)
    assert case_tasks
    reads = [
        f"/api/v1/investigations/{case_id}/scope",
        f"/api/v1/investigations/{case_id}/readiness",
        f"/api/v1/investigations/{case_id}/evidence-inventory",
        f"/api/v1/investigations/{case_id}/reviews",
        f"/api/v1/investigations/{case_id}/decision-brief",
        f"/api/v1/investigations/{case_id}/decision-brief/versions/1",
        f"/api/v1/investigations/{case_id}/decision",
        f"/api/v1/investigations/{case_id}/follow-ups",
        f"/api/v1/investigations/{case_id}/closure-check",
        f"{_intel(case_id)}/hypotheses",
        f"/api/v1/triage/signals/{golden['signal']['id']}",
        f"/api/v1/case-reviews/{golden['reviews']['RISK']['id']}",
        f"/api/v1/decisions/{golden['decision']['id']}/record",
        f"/api/v1/follow-ups/{golden['follow_up']['id']}",
        f"/api/v1/evidence-requests/{golden['request']['id']}",
        *(f"/api/v1/tasks/{task.id}" for task in case_tasks),
    ]
    for path in reads:
        response = outsider.get(path)
        assert response.status_code == 404, (path, response.status_code, response.text)
        assert golden["case_business_id"] not in response.text, path
    for name in TRUST_ENDPOINTS:
        response = _trust(outsider, case_id, name)
        assert response.status_code == 404, (name, response.status_code, response.text)
    writes = [
        outsider.post(_decision(case_id) + "/sign", json=_sign_body(golden["brief_v2"])),
        outsider.post(_brief(case_id) + "/versions/2/start-review", json={}),
        outsider.post(f"/api/v1/case-reviews/{golden['reviews']['RISK']['id']}/start"),
        outsider.post(f"/api/v1/tasks/{case_tasks[0].id}/claim"),
        _triage(outsider, golden["signal"]["id"], "start"),
        outsider.post(f"{_intel(case_id)}/hypotheses", json={"statement": "Someone else's hypothesis here"}),
    ]
    for response in writes:
        assert response.status_code == 404, response.text
    resolve = outsider.get("/api/v1/workspace/context/resolve", params={"investigation": golden["case_business_id"]})
    assert resolve.status_code == 404
    listed = _ok(outsider.get("/api/v1/triage/signals", params={"q": golden["signal"]["business_id"]}))
    assert golden["signal"]["id"] not in [item["id"] for item in listed["items"]]
    everything = _ok(outsider.get("/api/v1/case-reviews", params={"box": "all", "page_size": 200}))["items"]
    assert golden["reviews"]["RISK"]["id"] not in {item["id"] for item in everything}

    # And the other way round: the second organization's case is not found here.
    other_seed = _seed(org["other_id"])
    theirs = _open_case(outsider, other_seed)
    investigator, _ = org["investigator"]
    for path in (
        f"/api/v1/investigations/{theirs['id']}/scope",
        f"/api/v1/investigations/{theirs['id']}/decision-brief",
        f"/api/v1/investigations/{theirs['id']}/decision",
    ):
        assert investigator.get(path).status_code == 404, path
    assert _trust(investigator, theirs["id"], "timeline").status_code == 404


# ================================================================================ 19. late evidence after signing


def test_19_late_evidence_asks_for_an_impact_assessment_and_a_new_decision_supersedes(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    decider, _ = org["decider"]
    case, brief, signed = _decided(org)
    case_id, first = case["id"], signed["decision"]
    before = _get(tenant_id, Decision, id=uuid.UUID(first["id"]))

    late = _evidence(tenant_id, title="Field report received after the decision")
    linked = _ok(
        investigator.post(
            f"/api/v1/investigations/{case_id}/evidence-links",
            json={"evidence_ids": [late["id"]], "reason": "Field report received after the decision"},
        )
    )
    assert linked["linked"] == 1
    (assessment,) = _ok(investigator.get(f"/api/v1/investigations/{case_id}/impact-assessments"))["items"]
    assert assessment["status"] == "OPEN" and assessment["trigger"] == "EVIDENCE_LINKED"
    assert assessment["decision"]["id"] == first["id"] and assessment["evidence"]["id"] == late["id"]
    assert _record(investigator, first["id"])["verification"]["status"] == "VALID"
    assert _case_row(tenant_id, case_id).workflow_state == "DECIDED"

    material = _ok(
        investigator.post(
            f"/api/v1/impact-assessments/{assessment['id']}/complete",
            json={
                "conclusion": "MATERIAL_IMPACT",
                "rationale": "The report shows a second failure mode never assessed",
            },
        )
    )
    assert material["case_reopened"] is True and material["workflow_state"] == "IN_PROGRESS"
    after = _get(tenant_id, Decision, id=uuid.UUID(first["id"]))
    for field in ("decision_status", "outcome", "rationale", "decided_at", "superseded_by_decision_id"):
        assert getattr(after, field) == getattr(before, field), field
    assert "DECISION_UNDER_RECONSIDERATION" in _audit_actions(tenant_id, first["id"])
    assert _get(tenant_id, ImpactAssessment, id=uuid.UUID(assessment["id"])).status == "COMPLETED"

    # The investigator takes the report into a new brief; it is reviewed and a new decision supersedes the first.
    _review_evidence(
        investigator, case_id, late["id"], relationship="CONTRADICTING", reason="A second failure mode is reported"
    )
    assert len(_ok(investigator.get(f"/api/v1/investigations/{case_id}/impact-assessments"))["items"]) == 1
    second_brief = _ok(investigator.post(_brief(case_id), json={}), 201)
    assert second_brief["version"] == 2
    _ok(investigator.post(_brief(case_id) + "/submit", json={}))
    assert _ok(investigator.get(_brief(case_id) + "/versions/1"))["status"] == "SUPERSEDED"
    approved = _accept(org, case_id, 2)
    required = _sign(decider, case_id, approved)
    assert required.status_code == 409 and _code(required) == "SUPERSEDE_REQUIRED"
    second = _ok(
        _sign(decider, case_id, approved, supersedes_decision_id=first["id"], supersede_reason=SUPERSEDE_REASON)
    )
    assert second["decision"]["supersedes_decision_id"] == first["id"] and second["verification"]["status"] == "VALID"
    old = _record(investigator, first["id"])
    assert old["decision"]["decision_status"] == "SUPERSEDED" and old["superseded_by"]["id"] == second["decision"]["id"]
    assert old["verification"]["status"] == "VALID"  # superseding never breaks the earlier signature
    assert old["decision"]["rationale"] == RATIONALE and old["decision"]["outcome"] == "ACCEPT_CONCLUSION"
    assert _case_row(tenant_id, case_id).workflow_state == "DECIDED"
    # Replayed at the first signature, the late report had not arrived; the evidence has changed since.
    then = _ok(_trust(investigator, case_id, "replay", decision_id=first["id"]))
    assert then["decision"]["business_id"] == first["business_id"] and then["decision"]["status_now"] == "SUPERSEDED"
    assert late["business_id"] not in json.dumps(then["evidence"]["known_then"])
    assert late["business_id"] in json.dumps(then["evidence"]["arrived_later"])
    assert then["integrity"]["changed_since"] is True
    impact = [item for item in _timeline(investigator, case_id)[0] if item["category"] == "IMPACT"]
    impact_business_id = _get(tenant_id, ImpactAssessment, id=uuid.UUID(assessment["id"])).business_id
    assert impact and any(item["object"]["business_id"] == impact_business_id for item in impact)


# ================================================================================ 20. reopening a closed case


def test_20_a_closed_case_is_reopened_with_an_authorized_reason(org):
    tenant_id = org["tenant_id"]
    investigator, investigator_id = org["investigator"]
    case, _, signed = _decided(org)
    path = f"/api/v1/investigations/{case['id']}"
    assert _ok(investigator.get(path + "/closure-check"))["can_close"] is True
    closed = _ok(investigator.patch(path, json={"status": "closed", "reason": "Decision signed, nothing open"}))
    assert closed["workflow_state"] == "CLOSED" and closed["closed_at"]

    frozen = investigator.patch(path, json={"reason": REASON, "priority": "LOW"})
    assert frozen.status_code == 409 and _code(frozen) == "INVESTIGATION_CLOSED"
    why = "A regulator asked for the case to be looked at again"
    for name in ("viewer", "risk"):
        refused = org[name][0].patch(path, json={"status": "open", "reason": why})
        assert refused.status_code == 403 and _code(refused) == "PERMISSION_DENIED", name
    assert investigator.patch(path, json={"status": "open", "reason": "short"}).status_code == 422
    assert _case_row(tenant_id, case["id"]).workflow_state == "CLOSED"

    reopened = _ok(investigator.patch(path, json={"status": "open", "reason": why}))
    assert reopened["status"] == "open" and reopened["workflow_state"] == "IN_PROGRESS"
    assert reopened["closed_at"] is None
    (audit,) = _audits(tenant_id, case["id"], "INVESTIGATION_REOPENED")
    assert audit.reason == why and audit.actor_ref == investigator_id
    assert audit.old_values["status"] == "closed" and audit.new_values["status"] == "open"
    # The signed decision is untouched and still verifies.
    record = _record(investigator, signed["decision"]["id"])
    assert record["decision"]["decision_status"] == "SIGNED" and record["verification"]["status"] == "VALID"
    tasks = _tasks(tenant_id, case_id=case["id"], task_type="INVESTIGATION")
    assert any(task.status in ("ASSIGNED", "ACCEPTED", "NEW") for task in tasks)


# ================================================================================ 21. superseding a decision


def test_21_a_new_signed_decision_supersedes_the_old_one_and_both_verify(org):
    tenant_id = org["tenant_id"]
    decider, _ = org["decider"]
    case, brief, first = _decided(org)
    first_id = first["decision"]["id"]
    required = _sign(decider, case["id"], brief, outcome="CLOSE_NO_FURTHER_ACTION")
    assert required.status_code == 409 and _code(required) == "SUPERSEDE_REQUIRED"
    short = _sign(
        decider,
        case["id"],
        brief,
        outcome="CLOSE_NO_FURTHER_ACTION",
        supersedes_decision_id=first_id,
        supersede_reason="short",
    )
    assert short.status_code == 422 and _code(short) == "DECISION_INVALID"
    second = _ok(
        _sign(
            decider,
            case["id"],
            brief,
            outcome="CLOSE_NO_FURTHER_ACTION",
            supersedes_decision_id=first_id,
            supersede_reason=SUPERSEDE_REASON,
        )
    )
    second_id = second["decision"]["id"]
    assert second["decision"]["supersedes_decision_id"] == first_id and second["supersedes"]["id"] == first_id
    assert second["supersedes"]["business_id"] == first["decision"]["business_id"]

    old = _record(decider, first_id)
    assert old["decision"]["decision_status"] == "SUPERSEDED" and old["superseded_by"]["id"] == second_id
    assert old["superseded_by"]["business_id"] == second["decision"]["business_id"]
    stored = _get(tenant_id, Decision, id=uuid.UUID(first_id))
    assert stored.supersede_reason == SUPERSEDE_REASON and stored.superseded_at is not None
    for decision_id in (first_id, second_id):
        assert _record(decider, decision_id)["verification"]["status"] == "VALID"
        assert _governance_status(decider, decision_id) == "VALID"
    assert "CASE_DECISION_SUPERSEDED" in _audit_actions(tenant_id, first_id)
    screen = _ok(decider.get(_decision(case["id"])))
    assert screen["current_decision"]["id"] == second_id
    assert [item["id"] for item in screen["decisions"]] == [second_id, first_id]
    integrity = _ok(_trust(decider, case["id"], "integrity"))
    assert integrity["summary"]["signatures"] == 2 and integrity["summary"]["signatures_invalid"] == 0
    assert {item["decision_id"] for item in integrity["signatures"]} == {first_id, second_id}


# ======================================================================== 22. workspace context alignment


def test_22_changing_the_product_version_clears_what_no_longer_fits_the_workspace_context(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    lead, _ = org["lead"]
    seed = _seed(tenant_id, versions=("Rev A", "Rev B"))
    other = _seed(tenant_id, versions=("X1",))
    version_a, version_b = seed["version_ids"]
    signal = _signal(lead, seed, "Context alignment signal")
    case = _open_case(investigator, seed)
    path = "/api/v1/workspace/context"
    try:
        full = _ok(
            investigator.put(
                path,
                json={
                    "product_id": seed["product_id"],
                    "product_version_id": version_a,
                    "signal_id": signal["id"],
                    "investigation_id": case["id"],
                },
            )
        )
        assert (full["product_id"], full["product_version_id"]) == (seed["product_id"], version_a)
        assert full["signal_id"] == signal["id"] and full["investigation_id"] == case["id"]
        assert full["investigation_business_id"] == case["business_id"] and full["product_business_id"]

        # Another version of the same product: the signal and the case no longer fit and are cleared.
        moved = _ok(investigator.put(path, json={"product_id": seed["product_id"], "product_version_id": version_b}))
        assert (moved["product_id"], moved["product_version_id"]) == (seed["product_id"], version_b)
        assert moved["signal_id"] is None and moved["investigation_id"] is None
        assert moved["context_version"] > full["context_version"]

        # A case wins over another product named with it; a version of another product is dropped.
        aligned = _ok(investigator.put(path, json={"product_id": other["product_id"], "investigation_id": case["id"]}))
        assert aligned["product_id"] == seed["product_id"] and aligned["investigation_id"] == case["id"]
        dropped = _ok(
            investigator.put(path, json={"investigation_id": case["id"], "product_version_id": other["version_id"]})
        )
        assert dropped["product_id"] == seed["product_id"] and dropped["product_version_id"] is None
        assert dropped["investigation_id"] == case["id"]

        # Without a case, a version of another product is refused; another product clears everything below it.
        refused = investigator.put(
            path, json={"product_id": seed["product_id"], "product_version_id": other["version_id"]}
        )
        assert refused.status_code == 404 and _code(refused) == "PRODUCT_VERSION_NOT_FOUND"
        switched = _ok(investigator.put(path, json={"product_id": other["product_id"]}))
        assert switched["product_id"] == other["product_id"]
        assert switched["product_version_id"] is None and switched["investigation_id"] is None
        assert switched["signal_id"] is None

        # Another organization's records are not found.
        their_seed = _seed(org["other_id"])
        theirs = _open_case(org["outsider"][0], their_seed)
        foreign = investigator.put(path, json={"investigation_id": theirs["id"]})
        assert foreign.status_code == 404 and _code(foreign) == "INVESTIGATION_NOT_FOUND"
        foreign_product = investigator.put(path, json={"product_id": their_seed["product_id"]})
        assert foreign_product.status_code == 404 and _code(foreign_product) == "PRODUCT_NOT_FOUND"
    finally:
        investigator.post(path + "/reset")


# ============================================================================== 23. merge keeps provenance


def test_23_a_signal_merge_preserves_the_provenance_of_complaints_and_events(org):
    tenant_id = org["tenant_id"]
    lead, lead_id = org["lead"]
    investigator, investigator_id = org["investigator"]
    seed = _seed(tenant_id, complaints=3, problem="SENSOR PROVENANCE")
    own, merged_a, merged_b = seed["complaint_ids"]
    canonical = _signal(lead, seed, "Sensor reads high after release B", complaint_ids=[own])
    source = _signal(lead, seed, "Sensor offset at start-up", complaint_ids=[merged_a, merged_b])
    merged = _ok(_triage(lead, canonical["id"], "merge", {"source_signal_ids": [source["id"]], "reason": REASON}))
    assert {item["id"]: item["added_how"] for item in merged["complaints"]} == {
        own: "MANUAL",
        merged_a: "MERGE",
        merged_b: "MERGE",
    }
    assert merged["complaint_count"] == 3 and merged["events"][-1]["event_type"] == "MERGED_FROM"
    assert merged["events"][-1]["actor_role"] == "TRIAGE_LEAD"

    # The source keeps its own complaints, as first linked, and says where it went.
    kept = _signal_detail(lead, source["id"])
    assert {item["id"]: item["added_how"] for item in kept["complaints"]} == {merged_a: "MANUAL", merged_b: "MANUAL"}
    assert kept["status"] == "MERGED" and kept["events"][-1]["event_type"] == "MERGED_INTO"
    links = _all(
        tenant_id, SignalComplaint, SignalComplaint.complaint_id.in_([uuid.UUID(merged_a), uuid.UUID(merged_b)])
    )
    assert sorted((str(link.signal_id), link.added_how) for link in links) == sorted(
        [(source["id"], "MANUAL"), (source["id"], "MANUAL"), (canonical["id"], "MERGE"), (canonical["id"], "MERGE")]
    )
    assert all(link.added_by == lead_id for link in links)

    def history(signal_id) -> list[SignalEvent]:
        return _all(
            tenant_id, SignalEvent, SignalEvent.signal_id == uuid.UUID(signal_id), order_by=SignalEvent.created_at
        )

    into = history(source["id"])[-1]
    assert into.event_type == "MERGED_INTO" and into.reason == REASON and into.actor_ref == lead_id
    assert into.details["canonical_business_id"] == canonical["business_id"]
    came = history(canonical["id"])[-1]
    assert came.event_type == "MERGED_FROM" and came.details["source_business_ids"] == [source["business_id"]]
    assert came.details["complaints_added"] == 2
    for item in (canonical, source):
        assert "SIGNAL_MERGED" in _audit_actions(tenant_id, item["id"])
    assert [task.status for task in _tasks(tenant_id, source_id=source["id"], task_type="SIGNAL_TRIAGE")] == [
        "SUPERSEDED"
    ]

    # The provenance carries into the case opened from the merged signal.
    marked = _triage(lead, canonical["id"], "disposition", {"disposition": "INVESTIGATION_REQUIRED", "reason": REASON})
    _ok(marked)
    opened = _ok(
        _triage(
            investigator,
            canonical["id"],
            "create-investigation",
            {"investigation_question": QUESTION, "assignee_user_id": investigator_id},
        ),
        201,
    )
    assert opened["investigation"]["complaints_linked"] == 3


# ============================================================================== 24. the trust timeline as a record


def test_24_the_trust_timeline_reconstructs_every_material_action(org, golden):
    tenant_id = org["tenant_id"]
    investigator, investigator_id = org["investigator"]
    case_id = golden["case_id"]
    timeline, categories = _timeline(investigator, case_id)
    text = json.dumps(timeline, default=str)

    # Every category of material action scenario 1 used is in the timeline, each record named by its business id.
    assert {
        "SIGNAL",
        "CASE",
        "SCOPE",
        "TASK",
        "EVIDENCE",
        "REQUEST",
        "INTELLIGENCE",
        "REVIEW",
        "BRIEF",
        "DECISION",
        "SIGNATURE",
        "FOLLOW_UP",
    } <= set(categories), categories
    assert sum(categories.values()) == len(timeline)
    records = {
        "signal": golden["signal"]["business_id"],
        "investigation": golden["case_business_id"],
        "evidence": golden["bench"]["business_id"],
        "evidence request": golden["request"]["business_id"],
        "evidence from the request": golden["logs"]["business_id"],
        "leading hypothesis": golden["leading"]["business_id"],
        "alternative hypothesis": golden["alternative"]["business_id"],
        "unknown": golden["unknown"]["business_id"],
        "risk review": golden["reviews"]["RISK"]["business_id"],
        "regulatory review": golden["reviews"]["REGULATORY"]["business_id"],
        "brief version 1": golden["brief_v1"]["business_id"],
        "brief version 2": golden["brief_v2"]["business_id"],
        "decision": golden["decision"]["business_id"],
        "follow-up": golden["follow_up"]["business_id"],
    }
    assert [name for name, business_id in records.items() if business_id not in text] == []
    assert re.search(r"clos", text, re.IGNORECASE), "The timeline does not show the case closing"
    # Each item says when, what and who in words; records carry business ids, never an id alone; nothing secret.
    for item in timeline:
        assert item["at"] and item["title"] and item["category"] and item["origin"] in {"HUMAN", "AI", "SYSTEM"}
        # Hypotheses, unknowns and failure chains are numbered; their evidence links, chain links and observations
        # are not (they are shown with the record they belong to). No object is ever shown by a bare id (below).
        if item["object"] is not None and item["object"]["type"] not in UNNUMBERED_OBJECTS:
            assert item["object"]["business_id"], item
    names = {(item["actor"] or {}).get("name") for item in timeline}
    assert {"Lead E2E", "Investigator E2E", "Risk E2E", "Regulatory E2E", "Quality E2E", "Decider E2E"} <= names
    assert _uuid_only_objects(timeline) == []
    assert [value[:6] + "..." for value in _secrets(org) if value in text] == []
    secret_keys = re.compile(r"pass|token|secret|session", re.IGNORECASE)
    assert not [key for item in timeline for key in item["details"] if secret_keys.search(key)]
    # Filters: one category, one person.
    only = _ok(_trust(investigator, case_id, "timeline", types="DECISION,SIGNATURE", page_size=200))
    assert only["items"] and {item["category"] for item in only["items"]} <= {"DECISION", "SIGNATURE"}
    by_decider = _ok(_trust(investigator, case_id, "timeline", actor="Decider E2E", page_size=200))
    assert by_decider["items"] and all(item["actor"]["name"] == "Decider E2E" for item in by_decider["items"])

    # The replay at signing: what was known when the decision was signed.
    replay = _ok(_trust(investigator, case_id, "replay"))
    assert replay["investigation"]["business_id"] == golden["case_business_id"]
    assert replay["decision"]["business_id"] == golden["decision"]["business_id"]
    assert replay["decision"]["signer"]["name"] == "Decider E2E" and replay["snapshot"]["available"] is True
    known = json.dumps(replay["evidence"]["known_then"])
    assert golden["bench"]["business_id"] in known and golden["logs"]["business_id"] in known
    assert replay["integrity"]["changed_since"] is False and replay["limitations"]
    # No AI ran on this case; every signature and brief fingerprint verifies.
    runs = _ok(_trust(investigator, case_id, "ai-runs"))
    assert runs["items"] == [] and runs["counts"]["total"] == 0
    integrity = _ok(_trust(investigator, case_id, "integrity"))
    assert integrity["summary"] == {"signatures": 1, "signatures_invalid": 0, "briefs_unverified": 0}
    (signature,) = integrity["signatures"]
    assert signature["status"] == "VALID" and signature["decision_business_id"] == golden["decision"]["business_id"]
    assert {item["business_id"] for item in integrity["brief_hashes"]} == {
        golden["brief_v1"]["business_id"],
        golden["brief_v2"]["business_id"],
    }
    assert integrity["audit_chain"]["status"] in {"VALID", "NOT_CHECKED"}, integrity["audit_chain"]

    # The audited export: the same record as a file, its SHA-256 in the audit trail, nothing secret.
    exported = _trust(investigator, case_id, "export")
    assert exported.status_code == 200, exported.text
    digest = hashlib.sha256(exported.content).hexdigest()
    assert exported.headers["X-Content-SHA256"] == digest
    document = exported.json()
    assert document["investigation"]["business_id"] == golden["case_business_id"]
    assert len(document["timeline"]) == len(timeline) and document["integrity"]["summary"]["signatures_invalid"] == 0
    assert [value[:6] + "..." for value in _secrets(org) if value in exported.text] == []
    (audit,) = [row for row in _audits(tenant_id, case_id, "CASE_AUDIT_EXPORTED") if row.details["sha256"] == digest]
    assert audit.actor_ref == investigator_id and audit.details["format"] == "JSON"
    csv_export = _trust(investigator, case_id, "export", format="csv")
    assert csv_export.status_code == 200 and golden["decision"]["business_id"] in csv_export.text
    refused = _trust(org["viewer"][0], case_id, "export")
    assert refused.status_code == 403 and _code(refused) == "PERMISSION_DENIED"


# ======================================================== 25. AI output: sources, limitations, contradictions


def test_25_ask_with_ai_off_answers_from_the_records_with_sources_limitations_and_labels(org, monkeypatch):
    from genai.provider import GenAIProvider, GenAIUnavailable

    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    _ai_off(org)
    case = _ready_case(org)
    case_id, bench = case["id"], case["_evidence"]
    fact = "Occlusion sensor read 4 psi high in 3 of 10 bench runs"
    _ok(
        investigator.post(
            f"{_intel(case_id)}/observations",
            json={"evidence_id": bench["id"], "statement": fact, "epistemic_type": "FACT", "rationale": REASON},
        ),
        201,
    )
    field = _evidence(tenant_id, case_id=case_id, title="Field service note")
    limitation = "Only the first page of the note is legible"
    _review_evidence(
        investigator,
        case_id,
        field["id"],
        status="ACCEPTED_WITH_LIMITATION",
        relationship="CONTRADICTING",
        limitation=limitation,
        reason="The note reports normal readings on the day of the alarm",
    )
    needed = "Device history record of the returned lot"
    unknown = _ok(
        investigator.post(
            f"{_intel(case_id)}/unknowns",
            json={"description": "Which lot did the returned pump come from?", "evidence_needed": needed},
        ),
        201,
    )

    # With AI switched off a configured provider refuses for the organization; Ask answers from the records.
    def refuse(self, *args, **kwargs):
        raise GenAIUnavailable("GENAI_DISABLED_FOR_ORGANIZATION")

    monkeypatch.setattr(GenAIProvider, "complete", refuse)
    asked = _ok(
        investigator.post(
            "/api/v1/stage3/interactions",
            json={"prompt": "Why do occlusion alarms occur?", "investigation_id": case_id},
        )
    )
    assert asked["status"] == "REFUSED" and asked["code"] == "GENAI_DISABLED_FOR_ORGANIZATION"
    structured = asked["structured"]
    assert structured["ai_used"] is False and structured["reason_code"] == "AI_DISABLED"
    assert "records only" in structured["ai_note"] and structured["summary"]
    assert structured["summary_origin"] == "SYSTEM"
    for key in (
        "known_facts",
        "supporting_evidence",
        "contradicting_evidence",
        "unknowns",
        "missing_evidence",
        "limitations",
        "next_steps",
        "sources",
    ):
        assert key in structured, key

    facts = {item["statement"]: item for item in structured["known_facts"]}
    assert fact in facts and facts[fact]["epistemic_type"] == "FACT" and facts[fact]["origin"] == "HUMAN"
    source = facts[fact]["sources"][0]
    assert source["kind"] == "evidence" and source["business_id"] == bench["business_id"]
    assert source["evidence_identifier"] == bench["identifier"]
    assert any(
        "supports the hypothesis" in item["statement"]
        and item["origin"] == "HUMAN"
        and item["hypothesis_business_id"] == case["_hypothesis"]["business_id"]
        for item in structured["supporting_evidence"]
    )
    assert any("reviewed as contradicting" in item["statement"] for item in structured["contradicting_evidence"])
    unknowns = {item["statement"]: item for item in structured["unknowns"]}
    assert unknowns["Which lot did the returned pump come from?"]["business_id"] == unknown["business_id"]
    assert all(item["status"] in {"open", "in_progress"} for item in unknowns.values())
    missing = [item for item in structured["missing_evidence"] if item["statement"] == needed]
    assert missing and missing[0]["unknown_business_id"] == unknown["business_id"]
    assert any(limitation in text for text in structured["limitations"])
    for key in ("known_facts", "supporting_evidence", "contradicting_evidence", "unknowns", "missing_evidence"):
        for item in structured[key]:
            assert item["origin"] in {"HUMAN", "SYSTEM"}, (key, item)  # nothing is labelled AI: no model answered
            assert item["statement"].strip()[:1] not in "{[", (key, item)

    # The conversation keeps the structured answer.
    listed = _ok(investigator.get("/api/v1/stage3/interactions"))
    kept = next(entry for entry in listed if entry["id"] == asked["interaction_id"])
    assert kept["structured"] == structured
