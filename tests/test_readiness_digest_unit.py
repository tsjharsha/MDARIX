"""The weekly readiness email's rules, without a database (backend/app/readiness_home/digest.py, auth/emailer.py):
the week, when it may go, what changed, the weakest link and the email's words."""

from __future__ import annotations

from datetime import date, datetime, timezone

from backend.app.readiness_home import digest


def _check(code: str, state: str, value, detail: str = "", why: str = "") -> dict:
    return {"code": code, "title": code.title(), "state": state, "value": value, "detail": detail, "why": why}


READINESS = {
    "as_of": "2026-10-19",
    "checks": [
        _check(
            "COMPLAINTS_TO_RECHECK",
            "CRITICAL",
            5,
            "1 of 5 records to recheck reports a death or serious injury",
            "Hidden complaints.",
        ),
        _check("COMPLAINTS_PAST_TARGET", "CLEAR", 0),
        _check("REPORTING_CLOCKS", "ATTENTION", 2),
        _check("TRENDS_WITHOUT_ACTION", "CLEAR", 0),
        _check("RISK_FILE_INPUT", "CRITICAL", 3),
        _check("HARM_CLOSED_WITHOUT_CASE", "CLEAR", 0),
        _check("CAPA_EFFECTIVENESS", "ATTENTION", 1),
        _check("TRIAGE_OVERDUE", "CLEAR", 0),
    ],
}


def test_the_week_and_when_the_digest_may_go():
    assert digest.iso_week(date(2026, 10, 19)) == "2026-W43"
    assert digest.iso_week(date(2027, 1, 1)) == "2026-W53"
    assert not digest.due(datetime(2026, 10, 19, 5, 59, tzinfo=timezone.utc))  # Monday before 06:00
    assert digest.due(datetime(2026, 10, 19, 6, 0, tzinfo=timezone.utc))
    assert digest.due(datetime(2026, 10, 20, 1, 0, tzinfo=timezone.utc))  # any later day of the week


def test_the_loop_in_story_order_and_the_weakest_link_first_in_the_worst_state():
    content = digest.compose(READINESS, None)
    assert [station["code"] for station in content["stations"]] == [code for code, _ in digest.LOOP]
    assert (content["clear"], content["total"]) == (4, 8)
    assert content["weakest"]["code"] == "COMPLAINTS_TO_RECHECK"
    assert content["weakest"]["label"] == "Hidden complaints found"
    assert content["weakest"]["why"] == "Hidden complaints."
    assert content["first"] is True and content["changes"] == []
    clear = {"checks": [_check(code, "CLEAR", 0) for code, _ in digest.LOOP]}
    assert digest.compose(clear, None)["weakest"] is None


def test_what_changed_since_last_week_in_loop_order():
    previous = digest.snapshot(READINESS)
    previous["COMPLAINTS_TO_RECHECK"] = {"state": "CRITICAL", "value": 7}
    previous["RISK_FILE_INPUT"] = {"state": "ATTENTION", "value": 3}
    previous["TRIAGE_OVERDUE"] = {"state": "ATTENTION", "value": 2}
    content = digest.compose(READINESS, previous)
    assert content["first"] is False
    assert content["changes"] == [
        "Hidden complaints found: 7 to 5",
        "Trends triaged: Needs attention to Clear (2 to 0)",
        "Risk file fed: Needs attention to Critical (3 to 3)",
    ]
    assert digest.compose(READINESS, digest.snapshot(READINESS))["changes"] == []


def test_only_a_person_who_switched_it_off_is_left_out():
    class Person:
        def __init__(self, preferences):
            self.email_preferences = preferences

    assert digest.wants_digest(Person({}))
    assert digest.wants_digest(Person({"weekly_readiness": True}))
    assert not digest.wants_digest(Person({"weekly_readiness": False}))
    assert digest.wants_digest(Person(None))


def test_the_email_says_the_loop_the_weakest_link_and_what_changed(monkeypatch):
    from auth import emailer

    sent = {}
    monkeypatch.setattr(emailer, "_send", lambda recipient, message, **_: sent.update(message=message) or "SENT")
    previous = digest.snapshot(READINESS)
    previous["COMPLAINTS_TO_RECHECK"] = {"state": "CRITICAL", "value": 7}
    content = digest.compose(READINESS, previous)
    assert (
        emailer.send_readiness_digest("q@acme.invalid", organization="Acme", week="2026-W43", content=content) == "SENT"
    )
    message = sent["message"]
    assert message.subject == "Your quality loop this week: 4 of 8 inspection checks clear (2026-W43)"
    assert message.paragraphs[0] == "4 of 8 inspection checks are clear in Acme this week."
    assert message.paragraphs[1].startswith("Weakest link: Hidden complaints found, critical (5).")
    assert "What changed since last week:" in message.paragraphs
    assert message.items == ("Hidden complaints found: 7 to 5",)
    assert ("Hidden complaints found", "5 · Critical") in message.details
    assert message.button[1].endswith("/app/readiness")
    assert "switch off the weekly readiness email under My Account" in message.reason
    first = digest.compose(READINESS, None)
    emailer.send_readiness_digest("q@acme.invalid", organization="Acme", week="2026-W43", content=first)
    assert "first weekly readiness email" in sent["message"].paragraphs[0]
    text, html = emailer.render(sent["message"])
    assert "Hidden complaints found" in text and "Hidden complaints found" in html
