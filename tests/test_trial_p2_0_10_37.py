"""Release 0.10.37: P2 findings of the pre-launch review taken on the trial maintenance line.

- FUN-07: a reply to the support team's email about a problem report reaches the reporter (Reply-To).
- NEW-3: browser error reports sent before sign-in are deleted 90 days after they arrive (trial-retention job).
- FUN-09: on a MULTI deployment the configuration check requires MDARIX_TRIAL_ALERT_EMAIL (tests/test_config_check.py).
- UX-15: the case workspace's "latest saved result" reads answer 200 with nothing saved when asked ?missing=empty.
- UX-26: the trial status names when the person first signed in and, for a colleague, who invited them.
"""

import uuid
from datetime import datetime, timedelta, timezone

from auth import emailer
from backend.app import client_errors
from backend.app.db.models.pilot_support import ClientErrorReport
from backend.app.db.models.foundation import AuthUser
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from backend.app.support_api import deliver_problem_report
from backend.app.trial import retention
from tests.test_decision_brief import _product
from tests.test_free_trial import _approved_trial_client, _clean_trial_workspaces  # noqa: F401 (module fixture)
from tests.test_support_problems import client_in_tenant, two_active_tenants
from tests.test_trial_self_admin import _trial_with_colleague


# ------------------------------------------------------------------- FUN-07: a reply reaches the reporter


def test_a_reply_to_the_problem_report_email_goes_to_the_person_who_reported_it(monkeypatch):
    tenant = two_active_tenants()[0]
    client, _user_id, email = client_in_tenant(tenant)
    created = client.post(
        "/api/v1/support/problems", json={"summary": "Export stalls", "details": "The export never finishes."}
    )
    assert created.status_code == 201, created.text
    sent = []
    monkeypatch.setenv("MDARIX_SUPPORT_EMAIL", "support@example.test")
    monkeypatch.setattr(
        emailer,
        "_send_email",
        lambda to, subject, text, html=None, reply_to=None: (
            sent.append({"to": to, "reply_to": reply_to, "text": text}) or "SENT"
        ),
    )
    with SessionLocal() as db:
        bind_system(db, "test: deliver the report")
        assert deliver_problem_report(db, {"report_id": created.json()["id"]}) == "SENT"
    assert sent[0]["to"] == "support@example.test"
    # Before 0.10.37 the Reply-To fell back to the support address itself, so a reply never reached the customer.
    assert sent[0]["reply_to"] == email
    assert f"Reply to this email to answer {email}." in sent[0]["text"]
    assert "Platform Admin, Operations, Problem reports" in sent[0]["text"]


def test_the_reply_to_header_is_the_reporter_and_other_alerts_keep_the_support_address(monkeypatch):
    captured = {}

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, **kwargs):
            pass

        def login(self, *args):
            pass

        def send_message(self, message):
            captured.setdefault("messages", []).append(message)

    for name, value in {
        "MDARIX_SMTP_HOST": "smtp.example.test",
        "MDARIX_SMTP_USERNAME": "mailer",
        "MDARIX_SMTP_PASSWORD": "secret",
        "MDARIX_SMTP_FROM": "MDARIX <no-reply@example.test>",
        "MDARIX_SMTP_VERIFIED_DOMAIN": "example.test",
        "MDARIX_SUPPORT_EMAIL": "support@example.test",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(emailer.smtplib, "SMTP", FakeSMTP)
    assert emailer.send_operations_alert("ops@example.test", "Problem", "Body", reply_to="asha@orbit.example") == "SENT"
    assert emailer.send_operations_alert("ops@example.test", "Dead letters", "Body") == "SENT"
    first, second = captured["messages"]
    assert first["Reply-To"] == "asha@orbit.example"
    assert second["Reply-To"] == emailer.company().support_email


# ------------------------------------------------------------------- NEW-3: error reports sent before sign-in


def _error_report(tenant_id, age: timedelta) -> uuid.UUID:
    row_id = uuid.uuid4()
    with SessionLocal() as db:
        if tenant_id is None:
            bind_system(db, "test: an error report sent before sign-in")
        else:
            bind_tenant(db, tenant_id)
        db.add(
            ClientErrorReport(
                id=row_id,
                tenant_id=tenant_id,
                path="/signin",
                message="TypeError: x is undefined",
                user_agent="test",
                created_at=datetime.now(timezone.utc) - age,
            )
        )
        db.commit()
    return row_id


def _exists(row_id) -> bool:
    with SessionLocal() as db:
        bind_system(db, "test: read error reports")
        return db.get(ClientErrorReport, row_id) is not None


def test_error_reports_sent_before_sign_in_are_deleted_after_90_days_and_organization_ones_are_kept():
    tenant = two_active_tenants()[0]
    old_anonymous = _error_report(None, timedelta(days=91))
    exactly_due = _error_report(None, timedelta(days=90, minutes=1))
    recent_anonymous = _error_report(None, timedelta(days=89))
    old_of_an_organization = _error_report(tenant.id, timedelta(days=200))
    with SessionLocal() as db:
        deleted = client_errors.delete_anonymous_reports(db)
    assert deleted >= 2
    assert not _exists(old_anonymous) and not _exists(exactly_due)
    assert _exists(recent_anonymous)
    # Filed under an organization: deleted with the organization's data, never by age.
    assert _exists(old_of_an_organization)
    assert client_errors.ANONYMOUS_RETENTION_DAYS == 90


def test_the_daily_retention_run_deletes_them_and_says_how_many():
    old_anonymous = _error_report(None, timedelta(days=120))
    with SessionLocal() as db:
        bind_system(db, "test: the retention run")
        result = retention.run_retention(db, "test")
    assert result["error_reports_deleted"] >= 1
    assert not _exists(old_anonymous)


# ------------------------------------------------------------------- UX-15: nothing saved yet answers 200 on request

LATEST = {
    "hypotheses": ("hypothesis_set", "HYPOTHESIS_SET_NOT_FOUND"),
    "challenges": ("challenge_set", "CHALLENGE_SET_NOT_FOUND"),
    "unknowns": ("unknown_set", "UNKNOWN_SET_NOT_FOUND"),
    "failure-chains": ("failure_chain_set", "FAILURE_CHAIN_SET_NOT_FOUND"),
    "briefs/latest": ("brief", "BRIEF_NOT_FOUND"),
}


def test_a_new_case_reads_nothing_saved_as_200_when_asked_and_404_otherwise():
    owner, approval, _email = _approved_trial_client()
    product_id, complaint_id = _product(uuid.UUID(approval["tenant_id"]))
    made = owner.post(
        "/api/v1/investigations",
        json={
            "product_id": product_id,
            "investigation_question": "Why do the occlusion alarms rise on Rev B?",
            "complaint_ids": [complaint_id],
            "assign_to_me": True,
        },
    )
    assert made.status_code == 201, made.text
    base = f"/api/v1/investigations/{made.json()['id']}"
    for path, (field, code) in LATEST.items():
        # The API's answer is unchanged for every other caller.
        missing = owner.get(f"{base}/{path}")
        assert missing.status_code == 404 and missing.json()["detail"]["code"] == code, (path, missing.text)
        # The case workspace asks for "nothing saved" as an empty answer, so the browser logs no error.
        empty = owner.get(f"{base}/{path}", params={"missing": "empty"})
        assert empty.status_code == 200, (path, empty.text)
        assert empty.json() == {field: None, "persisted": False}, path
    # The analysis read answers AI's off state in a trial, saved or not (RCA-D13: tests/test_r1_analysis_off.py).
    for params in ({}, {"missing": "empty"}):
        off = owner.get(f"{base}/analysis/latest", params=params)
        assert off.status_code == 200 and off.json()["state"] == "AI_OFF" and off.json()["analysis"] is None
    # A case of another organization stays out of reach: its brief read is still 404 with the parameter.
    other = owner.get(f"/api/v1/investigations/{uuid.uuid4()}/briefs/latest", params={"missing": "empty"})
    assert other.status_code == 404


# ------------------------------------------------------------------- UX-26: who the person is in the trial


def test_the_trial_status_names_when_the_person_joined_and_who_invited_a_colleague():
    owner, approval, owner_email, colleague, email = _trial_with_colleague()
    mine = owner.get("/api/v1/trial/status").json()["me"]
    assert mine["invited_by"] is None and mine["organization"] == "Trial Devices Inc"
    theirs = colleague.get("/api/v1/trial/status").json()["me"]
    assert theirs["invited_by"] == "Taylor Quality"
    assert theirs["organization"] == "Trial Devices Inc"
    # When they first signed in: just now, so the feedback prompt waits (frontend Feedback.tsx readyForFeedback).
    joined = datetime.fromisoformat(theirs["joined_at"])
    assert datetime.now(timezone.utc) - joined < timedelta(minutes=5)
    with SessionLocal() as db:
        bind_system(db, "test: the colleague's account")
        user = db.query(AuthUser).filter(AuthUser.username == email).one()
        assert joined >= user.created_at
