"""0.10.73, Release C part C1: the shell, personas and team.

- "Viewing as": the trial owner's persona is kept on the server and opens the next sign-in; only the owner changes it
  (a colleague gets 403 PERSONA_LOCKED); it changes what they see, never what they may sign.
- A colleague's persona is their real role, set by the owner at the invitation and changed only by the owner.
- The 3-user trial limit is gone: a safety cap of 50 (MDARIX_TRIAL_USER_CAP), said plainly when reached.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from access_control.personas import WORKSPACE_PERSONAS, persona_for_role
from backend.app.db.models.foundation import AuditEvent, AuthUser
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from tests.test_free_trial import PASSWORD, _activation_token, _approved_trial_client

pytestmark = pytest.mark.db

TEAM = "/api/v1/trial/team"
MOCKUP_TABS = {
    "admin": ["home", "complaints", "trees", "reports", "investigations", "trends", "products", "records", "team"],
    "quality": ["home", "complaints", "reports", "investigations", "trends", "products", "records"],
    "regulatory": ["home", "complaints", "trees", "reports", "records"],
    "handler": ["home", "complaints"],
    "investigator": ["home", "investigations", "trends", "products"],
    "risk": ["home", "investigations", "products", "records"],
    "decision": ["home", "complaints", "reports", "records"],
    "executive": ["home", "trends", "products", "records"],
}


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


def _sign_in(email: str) -> TestClient:
    client = TestClient(app)
    _ok(client.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD}))
    return client


def _invite(owner: TestClient, persona: str | None, name: str = "Rahul Colleague"):
    email = f"c1-{uuid.uuid4().hex[:8]}@example.invalid"
    body = {"email": email, "display_name": name, **({"persona": persona} if persona else {})}
    invited = _ok(owner.post(TEAM, json=body))
    colleague = TestClient(app)
    _ok(
        colleague.post(
            "/api/v1/auth/activate-account", json={"token": _activation_token(invited, email), "password": PASSWORD}
        )
    )
    _ok(colleague.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD}))
    return invited, colleague, email


def _role(user_id: str) -> str:
    with SessionLocal() as db:
        bind_system(db, "test: a colleague's role")
        return db.get(AuthUser, uuid.UUID(user_id)).role


def _audits(tenant_id: str, action: str) -> list[AuditEvent]:
    with SessionLocal() as db:
        bind_system(db, "test: persona audit")
        return (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == uuid.UUID(tenant_id), AuditEvent.action == action)
            .order_by(AuditEvent.created_at)
            .all()
        )


def test_the_personas_match_the_approved_design_and_each_persona_is_a_real_role():
    assert {persona.code: list(persona.tabs) for persona in WORKSPACE_PERSONAS} == MOCKUP_TABS
    roles = {persona.code: persona.role for persona in WORKSPACE_PERSONAS}
    assert roles == {
        "admin": "LEADER",
        "quality": "LEADER",
        "regulatory": "REGULATORY_REVIEWER",
        "handler": "TRIAGE_LEAD",
        "investigator": "INVESTIGATOR",
        "risk": "RISK_REVIEWER",
        "decision": "APPROVER",
        "executive": "VIEWER",
    }
    # Each colleague persona's role reads back as that persona (Admin is the owner's own: Leader reads as Quality).
    assert all(persona_for_role(role) == code for code, role in roles.items() if code not in ("admin",))
    # Only Admin has the Team tab.
    assert [code for code, tabs in MOCKUP_TABS.items() if "team" in tabs] == ["admin"]


def test_a_fresh_trial_owner_opens_on_admin_and_the_choice_persists_across_sign_in():
    owner, approval, email = _approved_trial_client()
    context = _ok(owner.get("/api/v1/session/context"))
    assert (context["persona"], context["persona_locked"]) == ("admin", False)
    assert context["persona_tabs"] == MOCKUP_TABS["admin"]
    assert [item["code"] for item in context["persona_options"]] == list(MOCKUP_TABS)

    switched = _ok(owner.post("/api/v1/me/persona", json={"persona": "regulatory"}))
    assert switched["persona"] == "regulatory" and switched["persona_tabs"] == MOCKUP_TABS["regulatory"]
    # A new sign-in (another device) opens on it.
    again = _ok(_sign_in(email).get("/api/v1/session/context"))
    assert again["persona"] == "regulatory" and again["persona_label"] == "Regulatory Leader"
    # The view changed; the role did not.
    assert again["active_role"] == context["active_role"]
    assert again["business_permissions"] == context["business_permissions"]
    events = _audits(approval["tenant_id"], "PERSONA_VIEW_CHANGED")
    assert [(e.details["previous_persona"], e.details["persona"], e.details["role_changed"]) for e in events] == [
        ("admin", "regulatory", False)
    ]
    # The same persona again changes nothing; an unknown one is refused.
    _ok(owner.post("/api/v1/me/persona", json={"persona": "regulatory"}))
    assert len(_audits(approval["tenant_id"], "PERSONA_VIEW_CHANGED")) == 1
    assert owner.post("/api/v1/me/persona", json={"persona": "superuser"}).status_code == 422


def test_a_colleague_s_role_follows_the_persona_and_they_cannot_change_it():
    owner, approval, _ = _approved_trial_client()
    invited, colleague, _ = _invite(owner, "regulatory")
    assert (invited["persona"], invited["role"]) == ("regulatory", "REGULATORY_REVIEWER")
    assert _role(invited["id"]) == "REGULATORY_REVIEWER"
    context = _ok(colleague.get("/api/v1/session/context"))
    assert (context["persona"], context["persona_locked"]) == ("regulatory", True)
    assert context["persona_tabs"] == MOCKUP_TABS["regulatory"]
    assert "regulatory.approve" in context["business_permissions"]  # the Regulatory Leader may approve reports
    refused = colleague.post("/api/v1/me/persona", json={"persona": "admin"})
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "PERSONA_LOCKED"
    assert _ok(colleague.get("/api/v1/session/context"))["persona"] == "regulatory"
    # A colleague cannot change anyone's persona either, nor be given the owner's Admin.
    member = next(item for item in _ok(owner.get(TEAM))["members"] if item["id"] == invited["id"])
    assert (member["persona"], member["persona_locked"]) == ("regulatory", True)
    owner_row = next(item for item in _ok(owner.get(TEAM))["members"] if item["is_owner"])
    assert (owner_row["persona"], owner_row["persona_locked"]) == ("admin", False)
    assert colleague.post(f"{TEAM}/{invited['id']}/persona", json={"persona": "decision"}).status_code == 403
    assert owner.post(f"{TEAM}/{invited['id']}/persona", json={"persona": "admin"}).status_code == 422
    assert owner.post(f"{TEAM}/{owner_row['id']}/persona", json={"persona": "decision"}).status_code == 409

    # The owner changes it: the role follows at once, audited with what it was.
    changed = _ok(owner.post(f"{TEAM}/{invited['id']}/persona", json={"persona": "decision"}))
    assert (changed["persona"], changed["role"]) == ("decision", "APPROVER")
    after = _ok(colleague.get("/api/v1/session/context"))
    assert after["persona"] == "decision" and "decision.sign" in after["business_permissions"]
    trail = [
        (e.details["how"], e.details["previous_role"], e.details["role"])
        for e in _audits(approval["tenant_id"], "TRIAL_PERSONA_ASSIGNED")
    ]
    assert trail == [("invited", None, "REGULATORY_REVIEWER"), ("changed", "REGULATORY_REVIEWER", "APPROVER")]


def test_a_colleague_invited_without_a_persona_keeps_leader_as_before():
    owner, _, _ = _approved_trial_client()
    invited, colleague, _ = _invite(owner, None)
    assert _role(invited["id"]) == "LEADER"
    assert _ok(colleague.get("/api/v1/session/context"))["persona"] == "quality"


def test_switching_persona_never_changes_a_signing_check():
    """The owner's market sign route answers the same under every persona; a View-only colleague is refused by the
    role, whatever they view as, until the owner gives them a role that may sign."""
    owner, approval, _ = _approved_trial_client()
    complaint = _ok(owner.get("/api/v1/oversight/events/SAMPLE-RV-11"))["event"]["complaint_id"]
    sign = f"/api/v1/complaints/{complaint}/market-assessments/US/sign"
    body = {"conclusion": "REPORTABLE", "version": 1, "saved_at": "2026-01-01T00:00:00+00:00", "password": "x"}
    answers = set()
    for persona in MOCKUP_TABS:
        _ok(owner.post("/api/v1/me/persona", json={"persona": persona}))
        response = owner.post(sign, json=body)
        answers.add((response.status_code, response.json()["detail"]["code"]))
    assert len(answers) == 1 and next(iter(answers))[0] != 200, answers

    invited, viewer, _ = _invite(owner, "executive", "Esha Executive")
    refused = viewer.post(sign, json=body)
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "PERMISSION_DENIED"
    assert viewer.post("/api/v1/me/persona", json={"persona": "regulatory"}).status_code == 403
    assert viewer.post(sign, json=body).status_code == 403
    _ok(owner.post(f"{TEAM}/{invited['id']}/persona", json={"persona": "regulatory"}))
    # Now the role may sign: the route reaches the same check the owner's did.
    now = viewer.post(sign, json=body)
    assert (now.status_code, now.json()["detail"]["code"]) == next(iter(answers))


def test_the_fourth_person_is_invited_and_the_cap_of_fifty_is_said_plainly(monkeypatch):
    owner, approval, _ = _approved_trial_client()
    for index in range(3):
        _ok(
            owner.post(
                TEAM, json={"email": f"c1-{index}-{uuid.uuid4().hex[:6]}@example.invalid", "display_name": f"P {index}"}
            )
        )
    roster = _ok(owner.get(TEAM))
    assert roster["seats_used"] == 4 and roster["limit"] == 50
    assert _ok(owner.get("/api/v1/trial/status"))["limits"]["users"] == 50
    # The cap holds at its setting (here 5, so the test stays quick): the sixth is refused, in plain words.
    monkeypatch.setenv("MDARIX_TRIAL_USER_CAP", "5")
    _ok(owner.post(TEAM, json={"email": f"c1-5-{uuid.uuid4().hex[:6]}@example.invalid", "display_name": "P 5"}))
    full = owner.post(TEAM, json={"email": f"c1-6-{uuid.uuid4().hex[:6]}@example.invalid", "display_name": "P 6"})
    assert full.status_code == 409 and full.json()["detail"]["code"] == "TRIAL_USER_LIMIT_REACHED"
    assert "5 people, its safety limit" in full.json()["detail"]["message"]
    # A setting that is not a whole number from 1 falls back to 50.
    monkeypatch.setenv("MDARIX_TRIAL_USER_CAP", "lots")
    assert _ok(owner.get(TEAM))["limit"] == 50


def test_the_free_trial_plan_reads_the_cap_and_the_refresh_is_idempotent():
    from backend.app.db.models.foundation import FeatureEntitlement, PlanDefinition
    from backend.app.trial.service import FREE_TRIAL_PLAN, refresh_plan_limits

    _approved_trial_client()  # the plan exists
    with SessionLocal() as db:
        bind_system(db, "test: the trial plan before 0.10.73")
        plan = db.query(PlanDefinition).filter(PlanDefinition.code == FREE_TRIAL_PLAN).first()
        saved = (
            plan.description,
            {row.id: dict(row.limits or {}) for row in db.query(FeatureEntitlement).filter_by(plan_id=plan.id)},
        )
        plan.description = "30-day evaluation: sample data, CSV templates, up to 3 users."
        for row in db.query(FeatureEntitlement).filter_by(plan_id=plan.id):
            row.limits = {**(row.limits or {}), "licensed_users_limit": 3}
        db.commit()
        try:
            dry = refresh_plan_limits(db, apply=False)
            assert dry and plan.description.endswith("up to 3 users.")
            assert refresh_plan_limits(db, apply=True) == dry
            db.commit()
            assert plan.description.endswith("up to 50 people.")
            assert refresh_plan_limits(db, apply=False) == []
        finally:
            plan.description = saved[0]
            for row in db.query(FeatureEntitlement).filter_by(plan_id=plan.id):
                row.limits = saved[1][row.id]
            db.commit()


def test_a_pilot_user_gets_their_role_s_screens_locked():
    from tests.conftest import authenticated_client

    admin = authenticated_client()
    context = _ok(admin.get("/api/v1/session/context"))
    assert context["persona_locked"] is True
    assert admin.post("/api/v1/me/persona", json={"persona": "executive"}).status_code == 403
