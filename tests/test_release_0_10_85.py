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


def test_records_name_complaints_and_investigations_by_the_customers_reference(trial):
    """D3.12: Records' readiness lists named complaints "CMP000029"; the customer's own reference reads now; the
    trial's scale note says its version in words."""
    import re

    from backend.app.decision_guides.router import SCALE_NOTE

    checks = _ok(trial["user"].get("/api/v1/readiness"))["checks"]
    refs = [item.get("ref") for check in checks for item in check.get("items", []) if item.get("ref")]
    assert refs and not [ref for ref in refs if re.fullmatch(r"(CMP|INV)\d{6}", ref)]
    assert "scale-starter-1" not in SCALE_NOTE


def test_a_list_page_reads_each_kind_of_record_once_with_the_same_values(trial):
    """D3.13: complaint_work and the events list read the checklist facts of a page at once (facts_many); the values
    are those of the one-complaint read, for every complaint of the trial."""
    from backend.app.db.models.foundation import Complaint
    from backend.app.db.session import SessionLocal
    from backend.app.oversight import closure

    db = SessionLocal()
    try:
        complaints = db.query(Complaint).filter(Complaint.tenant_id == trial["tenant_id"]).all()
        many = closure.facts_many(db, trial["tenant_id"], complaints)
        assert len(many) == len(complaints) > 20
        for complaint in complaints:
            one = closure.facts(db, trial["tenant_id"], complaint)
            batch = many[str(complaint.id)]
            assert closure.checklist(batch) == closure.checklist(one), complaint.complaint_identifier
            assert closure.stage_line(batch, closure.checklist(batch), None) == closure.stage_line(
                one, closure.checklist(one), None
            )
            for key in ("intakes", "obligations", "snapshots", "dispositions", "decisions", "requests", "capas"):
                assert {getattr(row, "id", row) for row in batch[key]} == {getattr(row, "id", row) for row in one[key]}
            assert {case.id for case in batch["cases"]} == {case.id for case in one["cases"]}
    finally:
        db.close()


def test_the_removal_preview_asks_the_database_a_few_times_not_once_per_table_and_key(trial):
    """D3.13: Getting started and Import read the sample removal's preview (2 to 13 s on a busy local stack); its plan
    asked about 300 queries. The same rows now come from a few UNION ALL rounds."""
    from sqlalchemy import event

    from backend.app.db.session import SessionLocal
    from backend.app.trial import sample_removal

    db = SessionLocal()
    seen = []
    listener = lambda *args: seen.append(1)  # noqa: E731
    event.listen(db.get_bind(), "before_cursor_execute", listener)
    try:
        planned = sample_removal.plan(db, trial["tenant_id"])
        assert planned["rows"]["complaints"]
        assert len(seen) < 40, len(seen)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listener)
        db.close()


def test_one_request_reads_the_triage_list_once_per_kind(trial, monkeypatch):
    """D3.13: one list page read the whole triage list up to seven times (the watch, every complaint's checklist, the
    story); it is kept on the request's session for a few seconds and dropped on any write."""
    from backend.app.intake import service

    calls = []
    real = service._triage
    monkeypatch.setattr(service, "_triage", lambda *args, **kwargs: calls.append(1) or real(*args, **kwargs))
    _ok(trial["user"].get(LIST, params={"view": "open", "work": "true", "page_size": 50}))
    assert 0 < len(calls) <= 3, len(calls)


def test_the_story_steps_carry_the_owners_names_and_the_report_path_one_word():
    """The owner's ten step names (4 Nov 2026, a vertical list); the report's status path keeps one word per stage."""
    from backend.app.authority_reports.rules import STAGES
    from backend.app.trial.one_story import STEPS

    assert [label for _, label in STEPS] == [
        "Review the case",
        "Classify service or complaint",
        "Triage",
        "Assess reportability",
        "Sign the conclusion",
        "Prepare the report",
        "Complete and approve",
        "Record the submission",
        "Review records",
        "Explore trends",
    ]
    assert [label for _, label in STAGES if len(label.split()) != 1] == []


def test_the_triage_list_reads_for_a_day_as_well_as_a_moment(trial):
    """The readiness checks' watch passes a day: the triage list raised AttributeError ('date' has no 'date'), and the
    "Reported in window" check read nothing."""
    from datetime import date

    from backend.app.db.session import SessionLocal
    from backend.app.intake import service

    db = SessionLocal()
    try:
        assert service.triage(db, None, trial["tenant_id"], "all", date.today())["items"] is not None
    finally:
        db.close()
