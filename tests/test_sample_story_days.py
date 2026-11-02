"""A sample that tells one story (0.10.64, quality plan stage 3: J2, J19, J29, J30, J31, D).

The "done when" of stage 3: a trial opened on day 0, 7, 15 or 29 tells the same story. Time passing is simulated by
moving every stored time of the trial back (the audit trail and sign-in sessions excepted), then doing what opening
the trial does: the hourly jobs (the sample's clock, the reporting reminders, the signals) and the screens' own
reminder sweep. My Work, the bell, Triage, Reportability, Trends, Readiness and Oversight then say the same as on
day 0. On 0.10.63 day 0 already showed 12 alerts (an "overdue" QMS task among them), and day 7 showed RV-06 overdue.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from backend.app.oversight.rules import zone_info

import pytest
from sqlalchemy import text

from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_market_assessment_api import _acknowledge, _answers, _market, _save, _sign, _url

pytestmark = pytest.mark.db

KEPT = {"audit_events", "auth_sessions", "auth_users", "authentication_events", "mfa_challenges"}
# The flagship (sample_data.FLAGSHIP): a malfunction with no harm whose recurrence could cause a serious injury.
FLAGSHIP_US = dict(US1="NO", US2A="NO", US2B="NO", US2C="NO", US3="NO", US4="YES", US5="YES", US6="NO")
FLAGSHIP_IN = dict(IN1="NO", IN2A="NO", IN2B="NO", IN2C="NO", IN2D="NO", IN2E="NO", IN2F="NO", IN3="NO")


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:sample-story-days-cleanup")


@pytest.fixture
def fresh():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:sample-story-days-cleanup")


def _age(tenant_id, days: int) -> None:
    """``days`` pass: every stored time and date of the trial moves back (its request's sample anchor too)."""
    from backend.app.db.models.stage2 import OnboardingRequest
    from backend.app.trial.sample_clock import ANCHOR

    with SessionLocal() as db:
        columns = db.execute(
            text(
                "SELECT c.table_name, c.column_name, c.data_type FROM information_schema.columns c "
                "JOIN information_schema.columns t ON t.table_name = c.table_name AND t.column_name = 'tenant_id' "
                "AND t.table_schema = 'public' WHERE c.table_schema = 'public' "
                "AND c.data_type IN ('date', 'timestamp with time zone', 'timestamp without time zone')"
            )
        ).all()
        for table, column, kind in columns:
            if table in KEPT:
                continue
            by = "make_interval(days => :days)" if kind != "date" else "CAST(:days AS integer)"
            db.execute(
                text(f'UPDATE {table} SET "{column}" = "{column}" - {by} WHERE tenant_id = :tenant'),
                {"days": days, "tenant": tenant_id},
            )
        request = db.query(OnboardingRequest).filter(OnboardingRequest.tenant_id == tenant_id).one()
        anchor = datetime.fromisoformat(request.profile[ANCHOR])
        request.profile = {**request.profile, ANCHOR: (anchor - timedelta(days=days)).isoformat()}
        db.commit()


def _open(tenant_id) -> dict:
    """What opening the trial runs: the hourly jobs for it (sample clock, reporting reminders, signals)."""
    from backend.app.reportability.reminders import sweep_reportability
    from backend.app.signals.hooks import seed_demo_signals
    from backend.app.trial.sample_clock import keep_current

    with SessionLocal() as control, SessionLocal() as data:
        bind_tenant(data, tenant_id)
        moved = keep_current(control, data, tenant_id)
        sweep_reportability(data, tenant_id)
        data.commit()
        seed_demo_signals(data, tenant_id)
    return moved


def _story(user) -> dict:
    """What each screen says, in a form two days can be compared by."""
    bell = _ok(user.get("/api/v1/oversight/alerts"))
    triage = _ok(user.get("/api/v1/triage"))["items"]
    watch = _ok(user.get("/api/v1/complaints/reportability?show=all&page_size=100"))["items"]
    trends = _ok(user.get("/api/v1/triage/trends"))
    readiness = _ok(user.get("/api/v1/readiness"))
    oversight = _ok(user.get("/api/v1/oversight"))
    chapters = _ok(user.get("/api/v1/trial/story"))["chapters"]

    def first(item):
        deadline = (item.get("deadlines") or [{}])[0]
        return f"{item['ref']}|{deadline.get('market')}|{deadline.get('state')}|{deadline.get('days_left')}"

    return {
        "bell": sorted(f"{i['ref']}|{i['category']}|{i['state']}|{i['tier']}|{i['reason']}" for i in bell["items"]),
        "bell_unread": bell["unread"],
        "my_work": _ok(user.get("/api/v1/tasks/summary"))["counts"],
        "triage": sorted(first(item) for item in triage),
        "watch": sorted(
            f"{i['complaint_identifier']}|{(i.get('binding') or {}).get('state')}|"
            f"{(i.get('binding') or {}).get('days_left')}"
            for i in watch
        ),
        "trends": sorted(f"{g['name']}|{g['result']}|{g['sentence']}" for g in trends["items"]),
        "readiness": [f"{c['code']}|{c['state']}|{c['value']}" for c in readiness["checks"]],
        "oversight": sorted(f"{i['ref']}|{i['category']}|{i['state']}" for i in oversight["items"]),
        "events": oversight["event_counts"],
        "next_steps": [f"{c['code']}|{(c.get('finding') or {}).get('text')}" for c in chapters],
    }


@pytest.mark.unit
def test_a_stage_never_needed_reads_not_needed():
    from types import SimpleNamespace

    from backend.app.oversight import closure

    found = {"complaint": SimpleNamespace(status="open"), "cases": []}
    items = [
        {"code": "TRIAGE", "result": closure.PASS},
        {"code": "MARKETS", "result": closure.NOT_REQUIRED},
        {"code": "DECISION", "result": closure.BLOCKED},
    ]
    stages = {stage["code"]: stage["state"] for stage in closure.stage_line(found, items, None)}
    # 0.10.63 ticked the market assessment and the investigation as done although neither was ever needed (J29).
    assert stages == {
        "TRIAGE": "DONE",
        "MARKETS": "NOT_NEEDED",
        "INVESTIGATION": "NOT_NEEDED",
        "DECISION": "CURRENT",
        "READY": "OPEN",
        "CLOSED": "LATER",
    }


def test_the_flagship_is_reportable_in_the_us_in_30_days_and_not_in_india(trial):
    """The third scenario, "Is this reportable, and by when, in the US and India?", on the flagship complaint
    (suspected inaccurate measurement, no reported harm, service required): triage first, then each market's guide."""
    user, tenant_id = trial["user"], trial["tenant_id"]
    flagship = next(
        item
        for item in _ok(user.get("/api/v1/complaints/reportability?show=all&page_size=100"))["items"]
        if item["complaint_identifier"] == "SAMPLE-RV-11"
    )
    # A triage item names the complaint by its own reference since 0.10.66 (one ID per complaint), not its MDARIX ID.
    triage = next(item for item in _ok(user.get("/api/v1/triage"))["items"] if item["ref"] == "SAMPLE-RV-11")
    roles = {deadline["market"]: deadline["role"] for deadline in triage["deadlines"]}
    assert roles["US"] == "OWN" and roles["IN"] == "IF_ALSO"
    complaint = flagship["id"]
    from backend.app.db.models.foundation import Complaint

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        aware = db.get(Complaint, uuid.UUID(complaint)).awareness_timestamp
    us_day = aware.astimezone(zone_info("America/New_York")).date()

    _acknowledge(user, "US")
    us = _save(user, complaint, "US", _answers(**FLAGSHIP_US), harm_level="NEGLIGIBLE")
    assert us["evaluation"]["suggested"] == "REPORTABLE" and us["evaluation"]["report_type"] == "US_30_DAY"
    assert _sign(user, complaint, "US", us, "REPORTABLE", password=PASSWORD).status_code == 200
    signed = _market(_ok(user.get(_url(complaint))), "US")["current"]
    # Expected: a 30-calendar-day malfunction report (21 CFR 803.50), due 30 days after the awareness day in New York.
    assert signed["conclusion"] == "REPORTABLE" and signed["due_on"] == (us_day + timedelta(days=30)).isoformat()

    _acknowledge(user, "IN")
    india = _save(user, complaint, "IN", _answers(**FLAGSHIP_IN), harm_level="NEGLIGIBLE")
    # Expected: no adverse event (nobody was harmed), so not reportable in India, and no Indian deadline.
    assert india["evaluation"]["suggested"] == "NOT_REPORTABLE"
    done = _sign(
        user,
        complaint,
        "IN",
        india,
        "NOT_REPORTABLE",
        password=PASSWORD,
        reason="No adverse event: nobody was harmed, a malfunction only.",
    )
    assert done.status_code == 200, done.text
    assert _market(done.json(), "IN")["current"]["conclusion"] == "NOT_REPORTABLE"
    # The US conclusion is an escalation trigger: the disposition opens a case for the investigation.
    disposition = _ok(user.get(f"/api/v1/complaints/{complaint}/disposition"))
    assert "REPORTABLE" in disposition["trigger_codes"]

    # A person worked on the sample: its clock stops (signed records are never re-dated) until the story restarts.
    from backend.app.trial.sample_clock import keep_current

    _age(tenant_id, 3)
    with SessionLocal() as control, SessionLocal() as data:
        bind_tenant(data, tenant_id)
        assert keep_current(control, data, tenant_id)["why"] == "WORKED_ON"
    preview = _ok(user.get("/api/v1/trial/sample-data/removal"))
    assert preview["clock_stopped"] and preview["own_records"] == 0
    assert user.post("/api/v1/trial/sample-data/restart", json={}).status_code == 422
    restarted = _ok(user.post("/api/v1/trial/sample-data/restart", json={"confirm": True}))
    assert restarted["status"] == "SAMPLE_RESTARTED"
    fresh = _market(_ok(user.get(_url(_flagship_id(user)))), "US")
    assert fresh["current"] is None  # the practice conclusion went with the old sample
    assert not _ok(user.get("/api/v1/trial/sample-data/removal"))["clock_stopped"]


def _flagship_id(user) -> str:
    return next(
        item["id"]
        for item in _ok(user.get("/api/v1/complaints/reportability?show=all&page_size=100"))["items"]
        if item["complaint_identifier"] == "SAMPLE-RV-11"
    )


@pytest.mark.unit
def test_the_screens_count_the_chapters_the_story_has():
    """J19: Getting started's loading fallback, the trial guide and the user guide say as many chapters as the story
    serves (they said 9 beside 10 before 0.10.63); one number, checked here against the server's list."""
    import re
    from pathlib import Path

    from backend.app.trial import story

    root = Path(__file__).resolve().parents[1] / "frontend" / "src"
    constant = re.search(r"STORY_CHAPTERS = (\d+);", (root / "features/help/trialGuide.ts").read_text("utf-8"))
    assert int(constant.group(1)) == len(story.CHAPTERS) == 10
    words = {10: "ten"}[len(story.CHAPTERS)]
    assert f"each of the {words} chapters" in (root / "features/help/userGuide.ts").read_text("utf-8")


def test_day_0_is_calm_and_the_same_story_is_told_on_day_7_15_and_29(fresh):
    user, tenant_id = fresh["user"], fresh["tenant_id"]
    _open(tenant_id)
    day0 = _story(user)
    # Day 0 holds only the story's alerts: RV-08's overdue reply (to the trial owner alone) and the two triage steps.
    assert day0["bell"] == [
        "SAMPLE-RV-08|COMMUNICATION|OVERDUE|ESCALATION|NO_ONE_ELSE",
        "SAMPLE-RV-11|TRIAGE|DUE_SOON|REMINDER|NO_OWNER",
        "SAMPLE-URG-01|TRIAGE|DUE_SOON|REMINDER|NO_OWNER",
    ], day0["bell"]
    assert day0["bell_unread"] == 3
    # Every story deadline is ahead of the reader except RV-09's, the finished late example.
    assert [row for row in day0["watch"] if "|OVERDUE|" in row] == ["SAMPLE-RV-09|OVERDUE|-10"]
    # The OrbitCare rise is significant; RV-09 (signed ready to close before it was closed) is "Closed" (J30).
    assert any("SIGNIFICANT" in row for row in day0["trends"])
    assert day0["events"]["CLOSED"] == 1
    passed = 0
    for day in (7, 15, 29):
        _age(tenant_id, day - passed)
        passed = day
        moved = _open(tenant_id)
        assert moved["moved"], moved
        assert _story(user) == day0, f"day {day}"
