"""Asking for an MVP conversation from a free trial (backend/app/trial/mvp_request.py), end to end: the request and its
update, the move of the trial data (only once the sample is removed and own data is in), the MDARIX team's alert and
its Platform Admin view, the audit trail and each organization seeing only its own request."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.db.session import engine
from backend.app.main import app
from tests.conftest import authenticated_client
from tests.test_free_trial import _approved_trial_client, _clean_trial_workspaces  # noqa: F401 (module fixture)

EXPECTATIONS = "Find hidden complaints across our two infusion pump lines and show CAPA effectiveness."
EXPORT = (
    "Complaint Number,Product Code,Product Name,Complaint Description,Lot #,Status\n"
    "MVP-0001,MVP-PUMP,Own Pump,Display flickers at start-up,MVP-LOT-1,Open\n"
)


def _forget(tenant_ids) -> None:
    with engine.begin() as connection:
        for tenant_id in tenant_ids:
            connection.execute(text("DELETE FROM trial_mvp_requests WHERE tenant_id = :t"), {"t": str(tenant_id)})


def _audited(tenant_id) -> list[str]:
    with engine.connect() as connection:
        return [
            action
            for (action,) in connection.execute(
                text(
                    "SELECT action FROM audit_events WHERE tenant_id = :t AND entity_type = 'TrialMvpRequest' "
                    "ORDER BY created_at"
                ),
                {"t": str(tenant_id)},
            )
        ]


def test_a_trial_asks_for_an_mvp_conversation_and_mdarix_sees_it(monkeypatch):
    from auth import emailer

    alerts = []
    monkeypatch.setenv("MDARIX_DEMO_ALERT_EMAIL", "sales@mdarix.invalid")
    monkeypatch.setattr(
        emailer,
        "send_trial_mvp_request_alert",
        lambda recipient, **details: alerts.append((recipient, details)) or "SENT",
    )
    user, approval, email = _approved_trial_client()
    other, other_approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    admin = authenticated_client()
    try:
        state = user.get("/api/v1/trial/mvp-request").json()
        assert state["request"] is None
        # The sample is still there: the trial data cannot be moved yet.
        assert state["data_move"]["allowed"] is False and state["data_move"]["reason"] == "SAMPLE_DATA_PRESENT"
        assert state["data_move"]["sample_records"] > 0

        short = user.post("/api/v1/trial/mvp-request", json={"expectations": "MVP"})
        assert short.status_code == 422 and short.json()["detail"]["field"] == "expectations"
        bad_phone = user.post("/api/v1/trial/mvp-request", json={"expectations": EXPECTATIONS, "phone": "abc"})
        assert bad_phone.status_code == 422 and bad_phone.json()["detail"]["field"] == "phone"
        # The server refuses the data move however the screen was bypassed.
        move = user.post("/api/v1/trial/mvp-request", json={"expectations": EXPECTATIONS, "move_trial_data": True})
        assert move.status_code == 422 and move.json()["detail"]["code"] == "MVP_DATA_MOVE_NOT_ALLOWED"
        assert user.get("/api/v1/trial/mvp-request").json()["request"] is None

        asked = user.post(
            "/api/v1/trial/mvp-request",
            json={
                "expectations": EXPECTATIONS,
                "scope": "OrbitCare 300 pumps, made in Pune.\n\nComplaints in TrackWise, lots in SAP.",
                "phone": "+91 98450 12345",
                "contact_preference": "A video call, Tuesday afternoon IST",
            },
        )
        assert asked.status_code == 200, asked.text
        assert asked.json()["status"] == "REQUESTED"
        request = asked.json()["request"]
        assert request["status"] == "NEW" and request["move_trial_data"] is False
        assert request["scope"] == "OrbitCare 300 pumps, made in Pune.\nComplaints in TrackWise, lots in SAP."
        assert request["requested_by"] == "Taylor Quality"

        # One open request per organization: asking again updates it.
        again = user.post("/api/v1/trial/mvp-request", json={"expectations": "Only the hidden complaints, please."})
        assert again.json()["status"] == "UPDATED" and again.json()["request"]["id"] == request["id"]
        shown = user.get("/api/v1/trial/mvp-request").json()["request"]
        assert shown["expectations"] == "Only the hidden complaints, please." and shown["scope"] is None

        # The MDARIX team is told, both times.
        assert [recipient for recipient, _ in alerts] == ["sales@mdarix.invalid", "sales@mdarix.invalid"]
        first, second = alerts[0][1], alerts[1][1]
        assert first["email"] == email and first["organization"] == "Trial Devices Inc"
        assert first["phone"] == "+91 98450 12345" and first["days_left"] == 30 and first["updated"] is False
        assert second["updated"] is True
        assert _audited(tenant_id) == ["TRIAL_MVP_REQUESTED", "TRIAL_MVP_REQUEST_UPDATED"]

        # Another organization sees none of it.
        assert other.get("/api/v1/trial/mvp-request").json()["request"] is None

        # Platform Admin sees it; nobody else does.
        assert TestClient(app).get("/api/v1/platform-admin/mvp-requests").status_code == 401
        assert user.get("/api/v1/platform-admin/mvp-requests").status_code == 403
        listed = admin.get("/api/v1/platform-admin/mvp-requests").json()
        item = next(entry for entry in listed["items"] if entry["id"] == request["id"])
        assert item["organization"] == "Trial Devices Inc" and item["email"] == email
        assert item["tenant_business_id"] == approval["tenant_business_id"] and item["days_left"] == 30
        assert listed["counts"]["NEW"] >= 1

        path = f"/api/v1/platform-admin/mvp-requests/{request['id']}/status"
        assert admin.post(path, json={"status": "LATER"}).status_code == 422
        contacted = admin.post(path, json={"status": "CONTACTED", "note": "Scoping call on Friday"})
        assert contacted.status_code == 200 and contacted.json()["note"] == "Scoping call on Friday"
        assert user.get("/api/v1/trial/mvp-request").json()["request"]["status"] == "CONTACTED"
        # Contacted is still open: asking again still updates the same request.
        assert user.post("/api/v1/trial/mvp-request", json={"expectations": EXPECTATIONS}).json()["status"] == "UPDATED"

        # Once closed, the organization may ask again; the closed one cannot reopen beside it.
        assert admin.post(path, json={"status": "CLOSED"}).status_code == 200
        fresh = user.post("/api/v1/trial/mvp-request", json={"expectations": EXPECTATIONS}).json()
        assert fresh["status"] == "REQUESTED" and fresh["request"]["id"] != request["id"]
        reopened = admin.post(path, json={"status": "NEW"})
        assert reopened.status_code == 409 and reopened.json()["detail"]["code"] == "MVP_REQUEST_OPEN"
        assert "TRIAL_MVP_REQUEST_STATUS_CHANGED" not in _audited(tenant_id)  # audited in the platform's trail
    finally:
        _forget([tenant_id, uuid.UUID(other_approval["tenant_id"])])


def test_trial_data_moves_only_once_the_sample_is_removed_and_own_data_is_in(monkeypatch):
    monkeypatch.delenv("MDARIX_DEMO_ALERT_EMAIL", raising=False)
    monkeypatch.delenv("MDARIX_TRIAL_ALERT_EMAIL", raising=False)
    user, approval, _email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        removed = user.post("/api/v1/trial/sample-data/removal", json={"confirm": True})
        assert removed.status_code == 200, removed.text
        state = user.get("/api/v1/trial/mvp-request").json()["data_move"]
        assert state == {"allowed": False, "reason": "NO_OWN_DATA", "sample_records": 0, "own_records": 0}
        refused = user.post("/api/v1/trial/mvp-request", json={"expectations": EXPECTATIONS, "move_trial_data": True})
        assert refused.status_code == 422

        assert user.post("/api/v1/trial/imports/complaints", content=EXPORT).status_code == 200
        state = user.get("/api/v1/trial/mvp-request").json()["data_move"]
        assert state["allowed"] is True and state["reason"] is None and state["own_records"] >= 1
        asked = user.post("/api/v1/trial/mvp-request", json={"expectations": EXPECTATIONS, "move_trial_data": True})
        assert asked.status_code == 200, asked.text
        assert asked.json()["request"]["move_trial_data"] is True
    finally:
        _forget([tenant_id])


def test_only_a_trial_workspace_asks_for_an_mvp():
    admin = authenticated_client()
    response = admin.get("/api/v1/trial/mvp-request")
    assert response.status_code == 404 and response.json()["detail"]["code"] == "NOT_A_TRIAL_WORKSPACE"
    asked = admin.post("/api/v1/trial/mvp-request", json={"expectations": EXPECTATIONS})
    assert asked.status_code == 404
