"""0.10.96 (B3 group B, B1): the US follow-up chain, against the database.

The trial's finished US example (SAMPLE-RV-09, accepted and FDA-valid since A9) is the initial report: its follow-ups
are numbered 1, 2, 3 without gaps, one open at a time, each with the initial's number, an H2 type, and a 30-day clock;
FDA's request for information becomes a follow-up; a re-signed conclusion supersedes an approved, unsent follow-up."""

# ruff: noqa: F811 (``trial`` is the shared fixture, imported)
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.app.db.models.authority_reports import ReportObligation
from backend.app.db.models.market_assessment import ComplaintMarketAssessment
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_authority_reports_api import REPORTS, _ok, trial  # noqa: F401 (a fixture)
from tests.test_release_0_10_96 import _sample_us, _us_report

pytestmark = pytest.mark.db


def _rv09(trial) -> dict:
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        report, _ = _sample_us(db, trial["tenant_id"])
        report_id = str(report.id)
    return _ok(trial["user"].get(f"{REPORTS}/{report_id}"))


def _create(trial, **body):
    rv09 = _rv09(trial)
    payload = {"received_on": date.today().isoformat(), "what_is_new": "The returned device was evaluated.", **body}
    return trial["user"].post(f"{REPORTS}/{rv09['id']}/follow-ups", json=payload)


def _accept(trial, detail: dict) -> dict:
    """FDA's Ack3 says accepted."""
    attempt = detail["submissions"][0]["id"]
    return _ok(
        trial["user"].post(
            f"{REPORTS}/{detail['id']}/submissions/{attempt}/evidence",
            json={"kind": "ACK3", "outcome": "ACCEPTED", "received_at": datetime.now(timezone.utc).isoformat(),
                  "note": "Ack3 passed"},
        )
    )  # fmt: skip


def _send_and_submit(trial, report_id: str, accept: bool = True) -> dict:
    """Send for approval, a colleague approves, the eMDR submission recorded (and, by default, FDA accepts it)."""
    from tests.test_reporting_capa_api import PASSWORD as COLLEAGUE_PASSWORD

    user = trial["user"]
    pending = _ok(user.post(f"{REPORTS}/{report_id}/snapshots"))["pending_snapshot"]["id"]
    approved = _ok(
        trial["colleague"].post(
            f"{REPORTS}/{report_id}/snapshots/{pending}/approve", json={"password": COLLEAGUE_PASSWORD}
        )
    )
    assert approved["state"] == "APPROVED", approved["state"]
    submitted = _ok(
        user.post(
            f"{REPORTS}/{report_id}/submissions",
            json={
                "route": "EMDR",
                "submitted_at": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
                "content_note": "The eMDR file as sent through the ESG.",
                "no_differences": True,
                "file": {"name": "copy.txt", "content_type": "text/plain", "data": "Y29weQ=="},
            },
        )
    )
    return _accept(trial, submitted) if accept else submitted


def _value(detail: dict, field_id: str):
    return next(item for part in detail["sections"] for item in part["fields"] if item["id"] == field_id)["value"]


def test_b3_a_follow_up_keeps_the_initial_report_number(trial):
    user, rv09 = trial["user"], _rv09(trial)
    assert rv09["state"] == "ACCEPTED"
    first = _create(trial, narrative="Evaluation found the alarm speaker below its specified output.")
    assert first.status_code == 200, first.text
    detail = first.json()
    assert detail["kind"] == "RESPONSE" and detail["parent_id"] == rv09["id"] and detail["follow_up"] == 1
    assert detail["form"]["version"] == rv09["form"]["version"]
    assert _value(detail, "MFR_REPORT") == _value(rv09, "MFR_REPORT") == _value(detail, "G8")
    assert _value(detail, "G6") == "30-day; Follow-up #1"
    assert _value(detail, "B5") == "Evaluation found the alarm speaker below its specified output."
    # The page's "what changed since the last report sent": only what the file sends, here the new narrative.
    assert [line.split(":")[0] for line in detail["emdr"]["changed"]] == ["B5 Describe event or problem"]
    refused = user.put(f"{REPORTS}/{detail['id']}/fields/MFR_REPORT", json={"value": "1234567-2026-00099"})
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "FOLLOWS_INITIAL"
    # G6 is the chain's: never typed on a follow-up, and never "Follow-up #n" typed on an initial report.
    g6 = user.put(f"{REPORTS}/{detail['id']}/fields/G6", json={"value": "30-day; Follow-up #3"})
    assert g6.status_code == 422 and g6.json()["detail"]["code"] == "FOLLOWS_CHAIN"
    draft = _us_report(trial["tenant_id"])
    typed = user.put(f"{REPORTS}/{draft}/fields/G6", json={"value": "30-day; Follow-up #1"})
    assert typed.status_code == 422 and typed.json()["detail"]["code"] == "NOT_A_FOLLOW_UP", typed.text
    _ok(user.put(f"{REPORTS}/{draft}/fields/G6", json={"value": "30-day; Initial"}))
    # The chain on the initial report, and the list's "Follow-up #1".
    chain = _ok(user.get(f"{REPORTS}/{rv09['id']}"))["responses"]
    assert [(row["id"], row["follow_up"]) for row in chain] == [(detail["id"], 1)]
    listed = [row for row in _ok(user.get(REPORTS))["items"] if row["id"] == detail["id"]]
    assert listed and listed[0]["follow_up"] == 1


def test_b3_a_follow_up_without_an_h2_tick_cannot_be_sent(trial):
    user = trial["user"]
    (follow,) = _rv09(trial)["responses"]
    url = f"{REPORTS}/{follow['id']}"
    refused = user.post(f"{url}/snapshots")
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "H2_REQUIRED", refused.text
    wrong = user.put(f"{url}/fields/H2", json={"value": "Something else"})
    assert wrong.status_code == 422 and wrong.json()["detail"]["code"] == "NOT_A_CHOICE"
    ticked = _ok(user.put(f"{url}/fields/H2", json={"value": "Device evaluation; Additional information"}))
    h2 = next(item for part in ticked["sections"] for item in part["fields"] if item["id"] == "H2")
    assert h2["value"] == "Device evaluation; Additional information" and h2["editable"]


def test_b3_the_next_follow_up_waits_until_the_last_is_submitted(trial):
    (follow,) = _rv09(trial)["responses"]
    refused = _create(trial, h2=["Correction"])
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "FOLLOW_UP_OPEN"
    submitted = _send_and_submit(trial, follow["id"], accept=False)
    assert submitted["state"] == "SUBMITTED_PENDING"
    # Sent but not yet accepted: FDA may still reject it, so the next waits (review B3-Z 1).
    pending = _create(trial, h2=["Correction"])
    assert pending.status_code == 409 and pending.json()["detail"]["code"] == "FOLLOW_UP_OPEN"
    assert _accept(trial, submitted)["state"] == "ACCEPTED"
    second = _create(trial, h2=["Correction"])
    assert second.status_code == 200, second.text
    assert second.json()["follow_up"] == 2 and _value(second.json(), "G6") == "30-day; Follow-up #2"


def test_b3_re_signing_supersedes_an_approved_follow_up(trial):
    """Audit fix 4 for the chain: a conclusion signed again ends the approval of an unsubmitted follow-up."""
    from backend.app.reportability.assessment_router import _settle_open_reports
    from tests.test_reporting_capa_api import PASSWORD as COLLEAGUE_PASSWORD

    user, rv09 = trial["user"], _rv09(trial)
    second = next(row for row in rv09["responses"] if row["follow_up"] == 2 and row["state"] == "DRAFT")
    pending = _ok(user.post(f"{REPORTS}/{second['id']}/snapshots"))["pending_snapshot"]["id"]
    _ok(
        trial["colleague"].post(
            f"{REPORTS}/{second['id']}/snapshots/{pending}/approve", json={"password": COLLEAGUE_PASSWORD}
        )
    )
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        initial = db.get(ReportObligation, uuid.UUID(rv09["id"]))
        # The US conclusion signed again, as not reportable: a follow-up may still be sent, on the new conclusion.
        held = db.get(ReportObligation, uuid.UUID(second["id"])).assessment_id
        # A real row stands in for the new version (the key needs one); everything is rolled back below.
        other = db.query(ComplaintMarketAssessment.id).filter(ComplaintMarketAssessment.id != held).first()[0]
        signed = SimpleNamespace(id=other, conclusion="NOT_REPORTABLE", report_type=None, due_on=None, version=9)
        ctx = SimpleNamespace(user_id=uuid.uuid4(), correlation_id=None)
        _settle_open_reports(
            db, ctx, trial["tenant_id"], initial.complaint_id, "US", signed, datetime.now(timezone.utc)
        )
        db.flush()
        follow = db.get(ReportObligation, uuid.UUID(second["id"]))
        assert follow.state == "DRAFT" and follow.due_on.isoformat() == second["due_on"]  # its own clock stays
        assert follow.assessment_id == other
        assert db.get(ReportObligation, initial.id).state == "ACCEPTED"  # the submitted initial never changes
        db.rollback()  # the test's conclusion is not real: nothing is kept
    after = _ok(user.get(f"{REPORTS}/{second['id']}"))
    assert after["state"] == "APPROVED"  # rolled back


def test_b3_an_unsent_follow_up_is_cancelled_with_a_reason_and_frees_the_chain(trial):
    user, rv09 = trial["user"], _rv09(trial)
    first = next(row for row in rv09["responses"] if row["follow_up"] == 1)
    second = next(row for row in rv09["responses"] if row["follow_up"] == 2)
    assert second["state"] == "APPROVED"  # approved, never sent: it blocks the chain
    url = f"{REPORTS}/{second['id']}/cancel"
    short = user.post(url, json={"reason": "No"})
    assert short.status_code == 422 and short.json()["detail"]["code"] == "REASON_REQUIRED"
    for other, code in ((rv09["id"], "NOT_A_FOLLOW_UP"), (first["id"], "ALREADY_SENT")):
        refused = user.post(f"{REPORTS}/{other}/cancel", json={"reason": "Raised in error by the team."})
        assert refused.status_code == 409 and refused.json()["detail"]["code"] == code, refused.text
    done = _ok(user.post(url, json={"reason": "Raised in error by the team."}))
    assert done["state"] == "CANCELLED" and done["state_label"] == "Cancelled before it was sent"
    assert done["cancelled_reason"] == "Raised in error by the team."
    assert {row["state"] for row in done["snapshots"]} == {"SUPERSEDED"}  # its approval ends
    again = _ok(user.get(f"{REPORTS}/{rv09['id']}"))
    assert again["state"] == "ACCEPTED"  # the initial never changes
    assert next(row for row in again["responses"] if row["id"] == first["id"])["state"] == "ACCEPTED"
    with SessionLocal() as db:
        from backend.app.db.models.foundation import AuditEvent

        bind_tenant(db, trial["tenant_id"])
        (event,) = (
            db.query(AuditEvent)
            .filter(AuditEvent.entity_id == uuid.UUID(second["id"]), AuditEvent.action == "REPORT_CANCELLED")
            .all()
        )
        assert event.details["reason"] == "Raised in error by the team."
        assert event.details["state_before"] == "APPROVED"


def test_b3_follow_up_numbers_run_1_2_3_without_gaps(trial):
    # The follow-up cancelled above, before it was sent, takes no number: the next one is #2 again.
    again = _create(trial, h2=["Correction"])
    assert again.status_code == 200, again.text
    assert again.json()["follow_up"] == 2
    _send_and_submit(trial, again.json()["id"])
    third = _create(trial, h2=["Additional information"])
    assert third.status_code == 200 and third.json()["follow_up"] == 3
    numbers = [row["follow_up"] for row in _rv09(trial)["responses"]]
    assert numbers == [1, 2, 2, 3]  # the cancelled one reads its would-be number; the sent ones run 1, 2, 3
    _ok(trial["user"].post(f"{REPORTS}/{third.json()['id']}/cancel", json={"reason": "Not needed after all."}))


def test_b3_an_fda_request_becomes_a_follow_up_ticking_response_to_fda_request(trial):
    rv09 = _rv09(trial)
    due = (date.today() + timedelta(days=10)).isoformat()
    found = trial["user"].post(
        f"{REPORTS}/{rv09['id']}/requests",
        json={"request_text": "FDA asks for the device evaluation result.", "received_on": date.today().isoformat(),
              "due_on": due},
    )  # fmt: skip
    assert found.status_code == 200, found.text
    detail = found.json()
    assert detail["form"]["version"] == rv09["form"]["version"] and detail["follow_up"] == 3
    assert _value(detail, "H2") == "Response to FDA request" and detail["deadline"]["due_on"] == due
    assert detail["request"]["text"] == "FDA asks for the device evaluation result."


def _request(trial, rv09: dict, text: str, due: date):
    return trial["user"].post(
        f"{REPORTS}/{rv09['id']}/requests",
        json={"request_text": text, "received_on": date.today().isoformat(), "due_on": due.isoformat()},
    )


def test_b3_an_fda_request_while_a_follow_up_is_open_is_recorded_on_it(trial):
    """Owner decision 1 after run 4: no 409 for a request; it is kept on the open follow-up, H2 ticked, audited."""
    from backend.app.db.models.foundation import AuditEvent
    from tests.test_reporting_capa_api import PASSWORD as COLLEAGUE_PASSWORD

    user, rv09 = trial["user"], _rv09(trial)
    third = next(row for row in rv09["responses"] if row["follow_up"] == 3 and row["state"] == "DRAFT")
    url = f"{REPORTS}/{third['id']}"
    _ok(user.put(f"{url}/fields/H2", json={"value": "Device evaluation"}))
    # Approved, not sent: the request is kept and its date counts, but the frozen file is not changed (no H2 tick).
    pending = _ok(user.post(f"{url}/snapshots"))["pending_snapshot"]["id"]
    _ok(trial["colleague"].post(f"{url}/snapshots/{pending}/approve", json={"password": COLLEAGUE_PASSWORD}))
    sooner = date.today() + timedelta(days=5)
    found = _request(trial, rv09, "FDA also asks for the lot history.", sooner)
    assert found.status_code == 200, found.text
    held = found.json()
    assert held["id"] == third["id"] and held["follow_up"] == 3 and held["state"] == "APPROVED"  # no new follow-up
    assert _value(held, "H2") == "Device evaluation"
    assert held["deadline"]["due_on"] == sooner.isoformat()  # due by the earlier date
    (kept,) = held["fda_requests"]
    assert kept["text"] == "FDA also asks for the lot history." and kept["h2_ticked"] is False
    assert kept["received_on"] == date.today().isoformat() and kept["due_on"] == sooner.isoformat()
    assert len(_rv09(trial)["responses"]) == len(rv09["responses"])
    # Reopened to a draft: the next request ticks H2 "Response to FDA request"; a later date never moves it back.
    _ok(user.post(f"{url}/reopen", json={"reason": "Answer FDA's request in this follow-up."}))
    found = _request(trial, rv09, "FDA asks for the service records too.", date.today() + timedelta(days=20))
    assert found.status_code == 200, found.text
    detail = found.json()
    assert detail["id"] == third["id"] and detail["state"] == "DRAFT"
    assert _value(detail, "H2") == "Device evaluation; Response to FDA request"
    assert detail["deadline"]["due_on"] == sooner.isoformat()
    assert [row["h2_ticked"] for row in detail["fda_requests"]] == [False, True]
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        events = (
            db.query(AuditEvent)
            .filter(AuditEvent.entity_id == uuid.UUID(third["id"]), AuditEvent.action == "REPORT_REQUEST_ATTACHED")
            .order_by(AuditEvent.chain_seq)
            .all()
        )
        assert [(row.old_values["H2"], row.new_values["H2"]) for row in events] == [
            ("Device evaluation", "Device evaluation"),
            ("Device evaluation", "Device evaluation; Response to FDA request"),
        ]
        assert events[0].new_values["due_on"] == sooner.isoformat() and events[0].details["state"] == "APPROVED"
        assert events[1].details["request_text"] == "FDA asks for the service records too."
        asked = (
            db.query(AuditEvent)
            .filter(AuditEvent.entity_id == uuid.UUID(rv09["id"]), AuditEvent.action == "REPORT_INFORMATION_REQUESTED")
            .order_by(AuditEvent.chain_seq)
            .all()
        )
        assert [(row.details["response"], row.details["attached"]) for row in asked[-2:]] == [(third["id"], True)] * 2


def test_b3_a_follow_ups_frozen_file_sends_only_what_changed(trial):
    """B2 against the database: follow-up #1's approved file is FDA's follow-up shape, with only what is new."""
    from backend.app.authority_reports import emdr, emdr_pdf

    first = next(row for row in _rv09(trial)["responses"] if row["follow_up"] == 1)
    detail = _ok(trial["user"].get(f"{REPORTS}/{first['id']}"))
    snapshot = next(row["id"] for row in detail["snapshots"] if row["state"] == "APPROVED")
    found = trial["user"].get(f"{REPORTS}/{first['id']}/emdr.xml", params={"snapshot": snapshot})
    assert found.status_code == 200, found.text
    assert emdr.validate(found.content) == []
    read = emdr_pdf.read(found.content)
    assert "C53579" in read["G6"] and read["G6 follow-up #"] == ["1"]
    assert sorted(read["H2"]) == ["C53586", "C53588"]
    assert read["B5"] == ["Evaluation found the alarm speaker below its specified output."]
    assert read["G8"] == [_value(_rv09(trial), "MFR_REPORT")]
    for block in ("D2 procode", "B1", "H1", "H6 clinical", "G1 email", "B4"):
        assert block not in read, block  # unchanged since the initial report: FDA keeps it
