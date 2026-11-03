"""0.10.85, round D3 "Polish to 9.5" of the approved redesign: the server's part.


- D3.1: every complaint list view is in urgency order: overdue first, then the nearest legal deadline, then the
  nearest other date.
- D3.2: "Reportability: decision needed" leaves out a complaint whose every market is signed, and the Stage reads
  "Report" once the conclusions are signed and a report is still to file (U-13).
"""

from __future__ import annotations

import uuid

import pytest

from tests.test_free_trial import _approved_trial_client
from tests.test_release_c3_0_10_75 import _purge

pytestmark = pytest.mark.db

LIST = "/api/v1/complaints"


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture(scope="module")
def trial():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        _purge(tenant_id)


def _urgency(item: dict) -> tuple:
    """What the list promises, from each row's own dates: overdue first, the nearest legal deadline, the nearest other."""
    due = item["work"]["due"]
    legal = [
        d["due_at"] for d in due if d["category"] in ("REPORTING", "OBLIGATION") and not d["key"].startswith("task:")
    ]
    other = [d["due_at"] for d in due if d["due_at"] not in legal]
    if not due:
        return (2, "~", "~")
    return (0 if any(d["state"] == "OVERDUE" for d in due) else 1, min(legal, default="~"), min(other, default="~"))


@pytest.mark.parametrize(
    "view", ["open", "due-week", "legal-week", "reportability", "waiting-reporter", "overdue", "signed-month"]
)
def test_every_list_view_is_in_urgency_order(trial, view):
    """D3.1: the overdue first, then the nearest legal deadline, in every view (only "open" was before, by its nearest
    date of any kind, so a triage target came before a legal deadline)."""
    items = _ok(trial["user"].get(LIST, params={"view": view, "work": "true", "page_size": 200}))["items"]
    keys = [_urgency(item) for item in items]
    assert keys == sorted(keys), [(item["complaint_identifier"], key) for item, key in zip(items, keys)]


def test_a_complaint_with_every_market_signed_needs_no_decision_and_its_stage_is_report(trial):
    """D3.2, U-13: SAMPLE-RV-07's only market (EU and Northern Ireland) is signed reportable and its report is still
    to file: it is not in "Reportability: decision needed", and its Stage reads "Report"."""
    user = trial["user"]
    event = _ok(user.get("/api/v1/oversight/events/SAMPLE-RV-07"))
    assert event["work"]["markets"] == ["EU_NI"]
    checks = {item["code"]: item["result"] for item in event["checklist"]}
    assert (checks["MARKETS"], checks["OBLIGATIONS"]) == ("PASS", "BLOCKED")
    assert event["work"]["stage"] == "Report"
    assert [stage["label"] for stage in event["stages"]][:2] == ["Triage", "Report"]
    needed = _ok(user.get(LIST, params={"view": "reportability", "work": "true", "page_size": 200}))["items"]
    refs = [item["complaint_identifier"] for item in needed]
    assert "SAMPLE-RV-07" not in refs and refs
    # Every complaint still listed has a market without a signed conclusion; none reads "Report".
    assert all(item["work"]["stage"] != "Report" for item in needed)
    rows = {
        item["complaint_identifier"]: item
        for item in _ok(user.get(LIST, params={"view": "open", "work": "true"}))["items"]
    }
    assert rows["SAMPLE-RV-07"]["work"]["stage"] == "Report"


def test_search_finds_a_complaint_by_any_part_of_its_reference_and_the_customers_own_ids(trial):
    """D3.11, U-20: any part of the reference ("RV-11"), and the customer's own service ticket, serial number or UDI
    for the same complaint."""
    user = trial["user"]
    by_ref = _ok(user.get(LIST, params={"q": "RV-11"}))["items"]
    assert [item["complaint_identifier"] for item in by_ref] == ["SAMPLE-RV-11"]
    by_ticket = _ok(user.get(LIST, params={"q": "svc-24-1107"}))["items"]
    assert "SAMPLE-RV-11" in [item["complaint_identifier"] for item in by_ticket]
