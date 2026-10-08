"""Free-trial requesters hear back: an acknowledgement when they ask, and a polite email when a request is declined.
Neither can fail the request or the decision."""

from sqlalchemy import text

from auth import emailer
from backend.app import notifications
from backend.app.db.session import SessionLocal, engine
from backend.app.db.tenant_scope import bind_system
from backend.app.trial.service import acknowledge_trial_request
from tests.conftest import authenticated_client
from tests.test_free_trial import _request_id, _request_trial


def test_a_declined_requester_is_told_politely_without_the_internal_reason(monkeypatch):
    admin = authenticated_client()
    email = _request_trial("Declined Devices Ltd")
    request_id = _request_id(admin, email)
    declined = admin.post(
        f"/api/v1/platform-admin/trial-requests/{request_id}/decline", json={"reason": "Competitor research"}
    )
    assert declined.status_code == 200 and declined.json()["status"] == "DECLINED"
    with engine.connect() as conn:
        events = conn.execute(
            text("SELECT event_name, payload FROM event_outbox WHERE aggregate_id = :id"), {"id": request_id}
        ).all()
    assert [name for name, _ in events] == ["TRIAL_REQUEST_DECLINED"]
    payload = events[0][1]
    assert payload["request_id"] == request_id and "@" not in str(payload) and "Competitor" not in str(payload)

    sent = []
    monkeypatch.setattr(
        emailer, "send_trial_request_declined", lambda recipient, **kw: sent.append((recipient, kw)) or "SENT"
    )
    db = SessionLocal()
    try:
        bind_system(db, "test: deliver the decline email")
        assert notifications.handle_event(db, "TRIAL_REQUEST_DECLINED", payload)
    finally:
        db.close()
    assert sent == [(email, {"display_name": "Taylor Quality", "organization": "Declined Devices Ltd"})]


def test_the_decline_email_reads_politely(monkeypatch):
    rendered = []
    monkeypatch.setattr(
        emailer, "_send_email", lambda to, subject, body, html=None, reply_to=None: rendered.append(body) or "SENT"
    )
    emailer.send_trial_request_declined("a@example.com", display_name="Dee", organization="Declined Co")
    assert "Thank you for your interest, Dee" in rendered[0] and "not able to offer a trial" in rendered[0]


def test_the_acknowledgement_never_raises(monkeypatch):
    sent = []
    monkeypatch.setattr(
        emailer, "send_trial_request_acknowledgement", lambda recipient, **kw: sent.append((recipient, kw)) or "SENT"
    )
    acknowledge_trial_request("Ack Co", "Ann", "ann@example.invalid")
    assert sent == [("ann@example.invalid", {"display_name": "Ann", "organization": "Ack Co"})]

    def refuse(*_args, **_kwargs):
        raise emailer.EmailDeliveryError("provider down")

    monkeypatch.setattr(emailer, "send_trial_request_acknowledgement", refuse)
    acknowledge_trial_request("Ack Co", "Ann", "ann@example.invalid")  # logged, not raised
