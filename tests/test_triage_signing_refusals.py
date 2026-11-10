"""B2's signing routes on a Case and its triage refuse a wrong or missing authenticator code with the signature's own
code (SIGNATURE_CODE_INVALID, never MFA_REQUIRED), audit the refusal and change nothing (0.10.62 J1 applied to the
0.10.93 routes: test_signing_code_refusals.py lists them).

``/confirm`` (routine triage in one click) carries no credential, so a downgrade or later awareness there always
stops at SIGNATURE_NEEDED; ``/confirm-qms`` saves through the same function as ``/record``, tested here."""

# ruff: noqa: F811 (``trial`` is the shared fixture, imported)
from __future__ import annotations

import pytest

from backend.app.db.models.stage2 import LoginThrottle
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_free_trial import PASSWORD
from tests.test_intake_triage_api import INTAKE, TRIAGE, _all_no
from tests.test_mfa_mvp import _enroll
from tests.test_triage_two_speeds_api import _actions, _find, _log, _ok, _save, _url, trial  # noqa: F401 (fixture)

pytestmark = pytest.mark.db


def _refused_twice(client, url: str, body: dict, people: list[str]) -> None:
    """A wrong code, then none: both refused as the signature's, never as the sign-in's second factor."""
    wrong = client.post(url, json={**body, "mfa_code": "000000"})
    assert wrong.status_code == 403, wrong.text
    assert wrong.json()["detail"]["code"] == "SIGNATURE_CODE_INVALID"
    assert wrong.json()["detail"]["message"].startswith("That code didn't match")  # the typed code reached the check
    missing = client.post(url, json=body)
    assert missing.status_code == 403 and missing.json()["detail"]["code"] == "SIGNATURE_CODE_INVALID"
    assert missing.json()["detail"]["message"] == "Enter the current code from your authenticator app."
    with SessionLocal() as db:  # wrong codes count on the sign throttle: start each route afresh
        bind_system(db, "test: clear the sign throttle")
        db.query(LoginThrottle).filter(LoginThrottle.identifier.in_([f"sign:{ref}" for ref in people])).delete()
        db.commit()


def test_b2_signing_routes_refuse_a_wrong_or_missing_code_and_change_nothing(trial, monkeypatch):
    from backend.app.intake import router as intake_router
    from tests.test_release_c1_0_10_73 import _invite

    user, tenant_id, me = trial["user"], trial["tenant_id"], trial["me"]
    _enroll(user)
    _, colleague, _ = _invite(user, "quality", "Second Reviewer")
    _enroll(colleague)
    other = next(person["id"] for person in _ok(user.get(TRIAGE))["people"] if person["id"] != me)
    people = [me, other]
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_FOR_SIGNATURES", "true")

    # /record: lowering a fast-track triage in a one-person trial is signed by the person.
    event = _log(user, answers=_all_no(Q2="YES", Q4="YES"))
    _ok(_save(user, _find(user, f"INTAKE:{event['id']}"), me, severity="SERIOUS", backup_owner=other))
    saved = _find(user, f"INTAKE:{event['id']}")
    body = {
        "severity": "MINOR",
        "event_owner": me,
        "triage_owner": me,
        "backup_owner": other,
        "immediate_action": "Pump taken out of use at the clinic.",
        "containment": ["OUT_OF_USE"],
        "seen_version": saved["record"]["version"],
        "change_reason": "Physician confirmed a bruise, no lasting harm.",
        "password": PASSWORD,
    }
    _refused_twice(user, _url(saved), body, people)
    assert _find(user, f"INTAKE:{event['id']}")["record"]["severity"] == "SERIOUS"

    # /exclude-threat: a possible public health threat, excluded with a reason, the password and the code.
    event = _log(user, answers=_all_no(Q2="YES", Q4="YES"))
    _ok(_save(user, _find(user, f"INTAKE:{event['id']}"), me, public_health_threat=True, backup_owner=other))
    item = _find(user, f"INTAKE:{event['id']}")
    reason = {"reason": "Single device, lot checked: no wider risk.", "password": PASSWORD}
    _refused_twice(user, _url(item, "exclude-threat"), reason, people)
    assert _find(user, f"INTAKE:{event['id']}")["record"]["public_health_threat"]

    # /downgrades/{task}: outside the trial the second person signs the requested downgrade.
    monkeypatch.setattr(intake_router, "is_trial", lambda *_: False)
    event = _log(user, answers=_all_no(Q2="YES", Q4="YES"))
    _ok(_save(user, _find(user, f"INTAKE:{event['id']}"), me, severity="CRITICAL", backup_owner=other))
    saved = _find(user, f"INTAKE:{event['id']}")
    lower = {"severity": "MINOR", "backup_owner": other, "change_reason": "Only a bruise, per the GP."}
    asked = _save(user, saved, me, **lower)
    assert asked.status_code == 409 and asked.json()["detail"]["code"] == "SECOND_PERSON_NEEDED"
    decide = f"{TRIAGE}/downgrades/{asked.json()['detail']['task_id']}"
    approve = {"decision": "APPROVE", "reason": "Checked the GP letter: a bruise.", "password": PASSWORD}
    _refused_twice(colleague, decide, approve, people)
    assert _find(user, f"INTAKE:{event['id']}")["record"]["severity"] == "CRITICAL"
    monkeypatch.setattr(intake_router, "is_trial", lambda *_: True)

    # /void: a Case entered in error is withdrawn, signed.
    event = _log(user)
    void = {"reason": "Logged twice by the service desk.", "password": PASSWORD}
    _refused_twice(user, f"{INTAKE}/{event['id']}/void", void, people)
    assert _ok(user.get(f"{INTAKE}/{event['id']}"))["status"] != "VOIDED"

    attempts = {row.details.get("attempt") for row in _actions(tenant_id, "SIGNATURE_MFA_FAILED")}
    assert {"TRIAGE_DOWNGRADE", "TRIAGE_THREAT", "CASE_VOID"} <= attempts
    assert len(_actions(tenant_id, "SIGNATURE_MFA_FAILED")) == 8  # every refusal audited
