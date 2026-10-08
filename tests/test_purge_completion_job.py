"""The daily purge-completion job and the audit retention date (scheduler.py, enterprise_audit.py)."""

from datetime import datetime, timezone

from backend.app import scheduler
from backend.app.enterprise_audit import retention_until


def _run(monkeypatch, summary: dict, state: dict) -> tuple[dict, list]:
    sent: list = []
    monkeypatch.setattr("backend.app.tenant_purge.complete_pending_purges", lambda db, actor_ref: summary)
    monkeypatch.setattr(scheduler, "send_alert", lambda subject, body: sent.append((subject, body)))
    return scheduler.purge_completion(None, state), sent


def test_the_job_is_registered_daily():
    job = next(job for job in scheduler.JOBS if job.name == "purge-completion")
    assert job.every.total_seconds() == 24 * 3600


def test_nothing_pending_sends_no_alert(monkeypatch):
    state: dict = {}
    result, sent = _run(
        monkeypatch, {"pending": [], "archived": [], "incomplete": [], "skipped": [], "failed": []}, state
    )
    assert sent == [] and result["archived"] == 0 and state["reported_incomplete"] == []


def test_an_incomplete_deletion_alerts_once_until_the_list_changes(monkeypatch):
    stuck = {"pending": [], "archived": [], "incomplete": [{"tenant_id": "t-1"}], "skipped": [], "failed": []}
    state: dict = {}
    _, first = _run(monkeypatch, stuck, state)
    _, second = _run(monkeypatch, stuck, state)
    assert len(first) == 1 and "t-1" in first[0][1] and second == []
    worse = {**stuck, "failed": [{"tenant_id": "t-2", "error": "OSError"}]}
    _, third = _run(monkeypatch, worse, state)
    assert len(third) == 1 and "t-2" in third[0][1]


def test_a_legal_hold_is_skipped_not_reported_as_stuck(monkeypatch):
    held = {"pending": [], "archived": [], "incomplete": [], "skipped": [{"tenant_id": "t-3", "why": "LEGAL_HOLD"}]}
    result, sent = _run(monkeypatch, {**held, "failed": []}, {})
    assert sent == [] and result["skipped"] == 1


def test_audit_retention_is_seven_calendar_years_like_the_database_trigger():
    assert retention_until(datetime(2026, 10, 6, 9, 30, tzinfo=timezone.utc)) == datetime(
        2033, 10, 6, 9, 30, tzinfo=timezone.utc
    )
    # Postgres: '2028-02-29'::timestamptz + interval '7 years' = 2035-02-28.
    assert retention_until(datetime(2028, 2, 29, tzinfo=timezone.utc)) == datetime(2035, 2, 28, tzinfo=timezone.utc)
