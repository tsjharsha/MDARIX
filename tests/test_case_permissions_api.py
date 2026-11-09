"""0.10.93 (B2) step 4 through the API, with migration tr19: roles on Cases and triage decided on the server, deny by
default, refusals audited, no privilege escalation through a direct API call (spec 6, OD-4); segregation of duties
outside the trial (6.4); the customer contact and its privacy rules (OD-1); the routes that set WAITING_INTERNAL and
VOIDED; an urgent Case is the Complaint at once; the duplicate choice at escalation."""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.models.foundation import AuditEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_intake_triage_api import INTAKE, TRIAGE, _all_no, _ok, _sign
from tests.test_release_c1_0_10_73 import _invite

pytestmark = pytest.mark.db

WORDS = "Hospital reports the monitor screen froze during a transfer; restarted fine."


def _trial(personas):
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    team = {persona: _invite(user, persona, f"{persona.title()} Colleague")[1] for persona in personas}
    return user, tenant_id, team, purge_trial


@pytest.fixture(scope="module")
def desk():
    user, tenant_id, team, purge = _trial(["servicedesk", "investigator"])
    try:
        yield {"user": user, "tenant_id": tenant_id, **team}
    finally:
        with SessionLocal() as db:
            purge(db, tenant_id, "test:case-permissions-cleanup")


@pytest.fixture(scope="module")
def pilot_like():
    user, tenant_id, team, purge = _trial(["executive", "quality"])
    try:
        yield {"user": user, "tenant_id": tenant_id, **team}
    finally:
        with SessionLocal() as db:
            purge(db, tenant_id, "test:case-permissions-cleanup")


def _log(client, **extra):
    return client.post(INTAKE, json={"kind": "CONTACT", "reporter_words": WORDS, "answers": _all_no(), **extra})


def _refusals(tenant_id) -> list[dict]:
    with SessionLocal() as db:
        bind_system(db, "test:case-permissions")
        rows = db.query(AuditEvent).filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == "ACTION_REFUSED")
        return [row.details for row in rows]


def _denied(response) -> bool:
    return response.status_code == 403 and response.json()["detail"]["code"] == "PERMISSION_DENIED"


def test_the_service_desk_logs_checks_and_signs_but_never_triages_or_reviews(desk):  # spec 6.3, OD-4
    agent, tenant_id = desk["servicedesk"], desk["tenant_id"]
    event = _ok(_log(agent, answers=_all_no(Q2="YES", Q4="YES")))
    _ok(agent.put(f"{INTAKE}/{event['id']}/check", json={"answers": _all_no(Q2="YES", Q4="YES"), "seen_version": 1}))
    item = next(entry for entry in _ok(agent.get(TRIAGE))["items"] if entry["id"] == event["id"])
    # A direct API call gets no more than the screens: triage, acknowledge, review are refused and audited.
    assert _denied(agent.post(f"{TRIAGE}/INTAKE/{event['id']}/acknowledge"))
    assert _denied(
        agent.post(
            f"{TRIAGE}/INTAKE/{event['id']}/record", json={"severity": "MINOR", "event_owner": "x", "triage_owner": "x"}
        )
    )
    assert _denied(
        agent.post(
            f"{INTAKE}/{event['id']}/check/review", json={"outcome": "AGREED", "note": "x" * 12, "password": PASSWORD}
        )
    )
    assert item["speed"] == "FAST"
    needs = [entry["needs"] for entry in _refusals(tenant_id)]
    assert ["complaint.triage"] in needs and ["quality.review"] in needs
    signed = _ok(_sign(agent, _ok(agent.get(f"{INTAKE}/{event['id']}")), "COMPLAINT"))
    assert signed["status"] == "ESCALATED"  # escalation is upward: no second person (spec 3.2)


def test_an_investigator_logs_a_case_but_no_longer_classifies_or_triages_it(desk):  # OD-4
    investigator = desk["investigator"]
    event = _ok(_log(investigator))
    assert _denied(investigator.put(f"{INTAKE}/{event['id']}/check", json={"answers": _all_no(), "seen_version": 1}))
    assert _denied(investigator.post(f"{TRIAGE}/INTAKE/{event['id']}/acknowledge"))


def test_the_contact_follows_od1(desk):  # OD-1, CI-43
    owner, agent, investigator, tenant_id = desk["user"], desk["servicedesk"], desk["investigator"], desk["tenant_id"]
    event = _ok(_log(agent))
    url = f"{INTAKE}/{event['id']}/contact"
    named = agent.put(url, json={"organisation": "OrbitCare Clinic (sample)", "name": "A Person"})
    assert named.status_code == 422 and named.json()["detail"]["code"] == "NO_PERSONAL_NAME"
    body = {
        "organisation": "OrbitCare Clinic (sample)",
        "contact_role": "Biomedical engineer",
        "phone": "+1 555 0100",
        "email": "biomed@orbitcare.example",
        "preferred_channel": "EMAIL",
    }
    shown = _ok(agent.put(url, json=body))["contact"]
    assert shown["held"] and shown["phone"] == "+1 555 0100" and shown["preferred_channel"] == "EMAIL"
    hidden = _ok(investigator.get(f"{INTAKE}/{event['id']}"))["contact"]
    assert hidden == {"held": True, "erased": False, "no_contact_reason": None, "label": "Contact held"}
    with SessionLocal() as db:
        bind_system(db, "test:case-permissions")
        audit = (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == "CASE_CONTACT_SET")
            .one()
        )
        assert "phone" not in str(audit.details.values()) or "+1 555" not in str(audit.details)
        assert "contact_phone" in audit.details["fields"]
    assert _denied(agent.post(f"{url}/erase", json={"reason": "Data-subject request received by e-mail."}))
    erased = _ok(owner.post(f"{url}/erase", json={"reason": "Data-subject request received by e-mail."}))["contact"]
    assert erased["erased"] and not erased["held"] and "phone" not in erased


def test_waiting_for_the_internal_team_and_back(desk):  # S-2
    agent = desk["servicedesk"]
    event = _ok(_log(agent))
    url = f"{INTAKE}/{event['id']}/waiting"
    assert (
        _ok(agent.post(url, json={"waiting": True, "reason": "Asked engineering about the freeze log."}))["status"]
        == "WAITING_INTERNAL"
    )
    assert (
        _ok(agent.post(url, json={"waiting": False, "reason": "Engineering answered: firmware known issue."}))["status"]
        == "OPEN"
    )


def test_an_urgent_case_is_the_complaint_at_once_and_a_viewer_cannot_log_one(pilot_like):  # 3.2, 6.3
    owner, viewer = pilot_like["user"], pilot_like["executive"]
    urgent = {"kind": "URGENT", "reporter_words": "Distributor reports a patient death after an alarm failed."}
    event = _ok(owner.post(INTAKE, json=urgent))
    assert event["status"] == "ESCALATED" and event["complaint_id"] and event["escalation"] == "CREATED"
    assert _denied(viewer.post(INTAKE, json=urgent))
    assert _denied(viewer.post(f"{TRIAGE}/escalate", json={"kind": "INTAKE", "id": event["id"], "reason": "x" * 12}))
    assert _denied(viewer.post(INTAKE, json={**urgent, "kind": "CONTACT"}))


def test_outside_the_trial_the_reviewer_and_the_withdrawer_are_other_people(pilot_like, monkeypatch):  # 6.4
    from backend.app.intake import router as intake_router

    monkeypatch.setattr(intake_router, "is_trial", lambda *_: False)
    owner, colleague, tenant_id = pilot_like["user"], pilot_like["quality"], pilot_like["tenant_id"]
    event = _ok(_log(owner, requested="CALIBRATION", answers=_all_no(Q7="YES")))
    reviewed = _ok(_sign(owner, event, "SERVICE_ONLY", reason="Repair asked, no deficiency alleged."))
    assert reviewed["status"] == "IN_REVIEW"
    review = {"outcome": "AGREED", "note": "Checked the call notes again.", "password": PASSWORD}
    same = owner.post(
        f"{INTAKE}/{event['id']}/check/review", json={**review, "resolution_summary": "Repaired on site."}
    )
    assert same.status_code == 403 and same.json()["detail"]["code"] == "REVIEWER_IS_SIGNER"
    assert any(entry.get("why") == "REVIEWER_IS_SIGNER" for entry in _refusals(tenant_id))
    wrong = _ok(_log(owner))
    void = {"reason": "Logged twice by mistake at the desk.", "password": PASSWORD}
    refused = owner.post(f"{INTAKE}/{wrong['id']}/void", json=void)
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "SAME_PERSON"
    voided = _ok(colleague.post(f"{INTAKE}/{wrong['id']}/void", json=void))
    assert voided["status"] == "VOIDED"
    after = colleague.post(f"{INTAKE}/{wrong['id']}/void", json=void)
    assert after.status_code == 409 and after.json()["detail"]["code"] == "CASE_STATE_REFUSED"


def test_escalation_asks_attach_or_create_when_a_likely_duplicate_exists(pilot_like, monkeypatch):  # 2.4, 3.3 step 2
    from backend.app.intake import router as intake_router

    owner = pilot_like["user"]
    complaint = _ok(owner.get("/api/v1/complaints", params={"q": "SAMPLE-RT-01"}))["items"][0]
    candidate = [{"id": complaint["id"], "ref": "SAMPLE-RT-01", "reasons": ["same product"]}]
    monkeypatch.setattr(intake_router, "_likely_complaints", lambda *_: candidate)
    event = _ok(_log(owner, answers=_all_no(Q2="YES")))
    asked = _sign(owner, event, "COMPLAINT")
    assert asked.status_code == 422 and asked.json()["detail"]["code"] == "DUPLICATE_CHOICE_NEEDED"
    assert asked.json()["detail"]["candidates"] == candidate
    attached = _ok(_sign(owner, event, "COMPLAINT", attach_to=complaint["id"]))
    assert attached["escalation"] == "ATTACHED" and attached["complaint_id"] == complaint["id"]
    other = _ok(_log(owner, answers=_all_no(Q2="YES")))
    assert _ok(_sign(owner, other, "COMPLAINT", create_new=True))["escalation"] == "CREATED"
