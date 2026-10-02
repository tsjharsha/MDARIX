"""The workspace dashboard: the signed-in user's own quality work, day by day, counts only."""

from fastapi.testclient import TestClient

from backend.app.main import app
from tests.test_business_permissions import _client_with_role

PATH = "/api/v1/analytics/trends"
SERIES = ("signals", "investigations_opened", "investigations_closed", "evidence", "decisions", "ai_runs")


def test_every_series_has_one_row_per_day_and_the_window_is_bounded():
    user = _client_with_role("INVESTIGATOR")
    body = user.get(PATH, params={"days": 14}).json()
    assert body["days"] == 14 and body["scope"] == "TENANT"
    for name in SERIES:
        assert len(body[name]) == 14, name
        assert all(set(row) <= {"date", "count", "completed", "failed"} for row in body[name]), name
    assert user.get(PATH, params={"days": 1000}).json()["days"] == 90
    assert user.get(PATH, params={"days": 1}).json()["days"] == 7


def test_breakdowns_add_up_to_the_tenants_own_totals():
    user = _client_with_role("INVESTIGATOR")
    body = user.get(PATH).json()
    counts = user.get("/api/v1/analytics/command-center").json()["counts"]
    assert sum(row["count"] for row in body["investigations_by_status"]) == counts["investigations"]
    assert sum(row["count"] for row in body["signals_by_status"]) == counts["complaints"]
    assert sum(row["count"] for row in body["evidence_by_reliability"]) == counts["evidence"]
    assert sum(row["count"] for row in body["decisions_by_status"]) == counts["decisions"]


def test_signing_in_is_required():
    assert TestClient(app).get(PATH).status_code == 401
