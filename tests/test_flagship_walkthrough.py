"""0.10.69, quality plan stage 8: the flagship story is done without the menu, and nothing is typed twice.

"Is this reportable, and by when, in the US and India?" on SAMPLE-RV-11 (PulseWatch 410, SpO2 reading high, nobody
harmed), from the entrance tile to "ready to close": US reportable with its 30-day report, India not reportable. Each
step is the main button of the screen the previous step left the person on: the complaint page's next action (the
server's ``summary.next_action``), the screen it opens, and the next step at its end (stage 8, 8.7). The test fails
when a step's main button does not open the place where the next step is done (a list to search, the menu).

The second person the brief and the decision need (the author never reviews or signs) works from their own My work:
the review task is the first assigned to them.

``WALK`` is the walk-through as the report lists it (screen, main button); ``FIELDS`` the field-source table: every
field the person fills along the flagship and scenario 2, and where its value comes from. The test asserts each
prefilled value against its source.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.session import SessionLocal
from backend.app.oversight.rules import zone_info
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_market_assessment_api import _acknowledge, _answers, _market, _save, _sign
from tests.test_reporting_capa_api import PASSWORD as COLLEAGUE_PASSWORD
from tests.test_reporting_capa_api import _client
from tests.test_sample_story_days import FLAGSHIP_IN, FLAGSHIP_US

pytestmark = pytest.mark.db

EVENT = "/api/v1/oversight/events/SAMPLE-RV-11"
REPORTS = "/api/v1/reports"

# (step, the screen it is done on, its main button) — the frontend's own labels (entrance.ts, the screens).
WALK = [
    ("Entrance", "Getting started (the entrance)", "Is this reportable, and by when, in the US and India?"),
    # 0.10.72 (B3): the triage panel is on the complaint page itself; no button opens the triage list first.
    ("Triage", "Complaint page › Summary, its triage panel", "Save the triage record"),
    ("US market", "Complaint page › Summary", "Assess the United States (FDA) market"),
    ("US market", "Complaints › Reporting, the US assessment", "Save and sign"),
    ("India market", "The same assessment's next step", "Assess India (CDSCO) too"),
    ("India market", "Complaints › Reporting, the India assessment", "Save and sign"),
    # 0.10.75 (C3): signing the US conclusion reportable created the report; the next step opens it on its own page.
    ("US report", "Next step", "Complete the United States (FDA) report (draft)"),
    ("US report", "Reports › the report (show only missing)", "Send for approval"),
    ("US report", "The approver's My work (the trial owner alone: the same screen)", "Approve"),
    ("US report", "Reports › the report", "Mark as submitted"),
    ("US report", "Reports › the report: the acknowledgement", "Record the evidence"),
    ("Disposition", "Next step", "Sign the disposition"),
    ("Disposition", "My work › Queues, the complaint's disposition", "Sign"),
    ("Investigation", "Next step", "Sign the investigation's decision"),
    ("Investigation", "Investigation › Evidence (progress line: Next), the complaint's own record", "Record review"),
    ("Investigation", "Investigation › Decisions & actions (Next: Risk and regulatory review)", "Record outcome"),
    ("Investigation", "Investigation › Decisions & actions (Next: Investigation brief)", "Compose the brief"),
    ("Investigation", "Same section", "Submit for quality review"),
    ("Investigation", "The colleague's My work: the review task", "Accept"),
    ("Investigation", "Same section, below the brief", "Sign decision"),
    ("Ready to close", "Next step: the complaint page › Decisions & actions", "Sign ready to close"),
]

# (journey, field, screen, where its value comes from; "entered" when the person enters a new fact)
FIELDS = [
    ("flagship", "Severity", "Triage", "entered: the first time the harm is judged"),
    ("flagship", "Event owner, triage owner", "Triage", "prefilled: the person (the only colleague)"),
    ("flagship", "Immediate action", "Triage", "entered"),
    ("flagship", "Awareness time", "Triage", "prefilled: the complaint's awareness"),
    ("flagship", "Harm level (US, India)", "Market assessment", "prefilled: the triage record's severity"),
    (
        "flagship",
        "Factual answers (death, serious injury, malfunction)",
        "Market assessment",
        "prefilled: the complaint record's fields, each confirmed by the person (0.10.72)",
    ),
    (
        "flagship",
        "Judgement answers (causation, recurrence, remedial action, unexpected) and the conclusion",
        "Market assessment",
        "entered: the person's judgement, never prefilled",
    ),
    ("flagship", "Worksheet fields from the record", "Report worksheet", "prefilled: complaint, product, assessment"),
    ("flagship", "Manufacturer report number (front page)", "Report worksheet", "entered"),
    ("flagship", "G8 manufacturer report number", "Report worksheet", "prefilled: the worksheet's front page"),
    ("flagship", "G2 report source", "Report worksheet", "entered (no classification yet)"),
    ("flagship", "Other must-have fields (procode, 510(k), manufacturer, IMDRF codes)", "Report worksheet", "entered"),
    ("flagship", "Submission: route, time, copy", "Report", "entered: what was submitted outside MDARIX"),
    ("flagship", "User type", "Disposition", "prefilled: the worksheet's report source (G2)"),
    ("flagship", "Why the investigation is needed", "Disposition", "entered"),
    ("flagship", "Investigation question", "Investigation", "prefilled: the complaint's words and the trigger"),
    ("flagship", "Evidence", "Investigation", "prefilled: the complaint's own record, linked"),
    ("flagship", "Problem statement", "Decision Brief", "prefilled: the investigation's question"),
    (
        "flagship",
        "Proposed conclusion, rationale, attribution",
        "Brief and decision",
        "entered: the person's judgement",
    ),
    ("rising", "Trend to review", "Trends", "prefilled: the trend check's rise (Rev B, per unit)"),
    ("rising", "Investigation question, complaints", "Open an investigation", "prefilled: the trend's complaints"),
    ("rising", "Suspect factor", "Lot impact", "prefilled: the factor most of the investigation's lots share"),
]


# The walk's action count (0.10.72, Release B): each main button, each answer the person enters (choose it and type its
# rationale: two actions) and each suggestion from the record they confirm (one action). 0.10.71: 22 buttons and 16
# entered answers, 54 actions.
ACTIONS_BEFORE = 54


def _answers_from_record(detail: dict, market: str, wanted: dict) -> tuple[dict, int]:
    """The market's answers as the person gives them: the record's suggestions confirmed (each must be the walk's own
    answer), the rest entered with a rationale. Returns the answers and the actions they took."""
    item = _market(detail, market)
    suggested, answers, actions = item["suggestions"], {}, 0
    for question, answer in wanted.items():
        offer = suggested.get(question)
        if offer:
            assert offer["answer"] == answer, (question, offer)
            answers[question] = {
                "answer": answer,
                "rationale": offer["source"],
                "evidence": [offer["evidence"]],
                "confirmed": True,
            }
            actions += 1
        else:
            answers.update(_answers(**{question: answer}))
            actions += 2
    return answers, actions


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    from tests.code_lists import ensure_loaded

    ensure_loaded()  # the IMDRF terms and FDA's codes (0.10.77)

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id, "colleague": _client(tenant_id, "LEADER", "Rahul Colleague")}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:flagship-walkthrough-cleanup")


def _next(user) -> tuple[str | None, dict | None, dict]:
    view = _ok(user.get(EVENT))
    action = view["summary"]["next_action"]
    return (action["label"], action["opens"]["target"], view) if action else (None, None, view)


def test_the_flagship_from_the_entrance_to_ready_to_close_by_each_screens_main_button(trial):
    user, colleague = trial["user"], trial["colleague"]
    # The entrance tile opens the complaint's own page (entrance.ts; vitest entrance.test.tsx checks the place).
    label, target, view = _next(user)
    complaint = view["event"]["complaint_id"]
    me = _ok(user.get("/api/v1/triage"))["people"]

    # 1. Triage: the next action names this complaint's triage panel, which its page shows inline (0.10.72, B3).
    assert label == "Complete the triage record"  # 0.10.72: on the page, no longer "(on the triage list)"
    assert target["record"] == {"kind": "complaint", "id": complaint} and target["tab"] == "Triage"
    owner = next(person["id"] for person in me if person["name"] != "Rahul Colleague")
    _ok(
        user.post(
            f"/api/v1/triage/COMPLAINT/{complaint}/record",
            json={
                "severity": "NEGLIGIBLE",
                "event_owner": owner,
                "triage_owner": owner,
                "immediate_action": "Monitor out of use and sent for service.",
            },
        )
    )

    # 2. The US market: the harm level is not asked again; it starts from the triage record.
    label, target, _ = _next(user)
    assert label == "Assess the United States (FDA) market"
    assert target["record"]["id"] == complaint and target["tab"] == "Reportability"
    detail = _ok(user.get(f"/api/v1/complaints/{complaint}/market-assessments"))
    assert (detail["severity_level"], detail["severity_source"]) == ("NEGLIGIBLE", "The triage record")
    _acknowledge(user, "US")
    # The factual questions arrive from the complaint record; causation, recurrence and remedial action never do.
    assert sorted(_market(detail, "US")["suggestions"]) == ["US1", "US2A", "US2B", "US2C", "US4"]
    answers, actions = _answers_from_record(detail, "US", FLAGSHIP_US)
    us = _save(user, complaint, "US", answers, harm_level=detail["severity_level"])
    assert us["evaluation"]["report_type"] == "US_30_DAY"
    assert _sign(user, complaint, "US", us, "REPORTABLE", password=PASSWORD).status_code == 200
    from backend.app.db.models.foundation import Complaint
    from backend.app.db.tenant_scope import bind_tenant

    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        aware = db.get(Complaint, uuid.UUID(complaint)).awareness_timestamp
    signed = _market(_ok(user.get(f"/api/v1/complaints/{complaint}/market-assessments")), "US")["current"]
    assert signed["due_on"] == (aware.astimezone(zone_info("America/New_York")).date() + timedelta(days=30)).isoformat()

    # 3. India, the story's second market (the assessment's next step, "Assess India (CDSCO) too"): not reportable.
    origins = {key: entry["origin"] for key, entry in signed["answers"].items()}
    assert origins == {
        **dict.fromkeys(["US1", "US2A", "US2B", "US2C", "US4"], "CONFIRMED"),
        **dict.fromkeys(["US3", "US5", "US6"], "ENTERED"),
    }
    # The audit trail keeps the same origins (0.10.72, B1).
    from backend.app.db.models.foundation import AuditEvent
    from backend.app.db.tenant_scope import bind_system

    with SessionLocal() as db:
        bind_system(db, "test: the signed assessment's audit")
        audit = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.tenant_id == trial["tenant_id"], AuditEvent.action == "COMPLAINT_MARKET_CONCLUSION_SIGNED"
            )
            .one()
        )
        assert audit.details["answer_origins"] == origins
    _acknowledge(user, "IN")
    assert sorted(_market(detail, "IN")["suggestions"]) == ["IN2A", "IN2B", "IN2D", "IN2F"]
    answers, more = _answers_from_record(detail, "IN", FLAGSHIP_IN)
    actions += more
    india = _save(user, complaint, "IN", answers, harm_level=detail["severity_level"])
    assert india["evaluation"]["suggested"] == "NOT_REPORTABLE"
    reason = "No adverse event: nobody was harmed, a malfunction only."
    assert _sign(user, complaint, "IN", india, "NOT_REPORTABLE", password=PASSWORD, reason=reason).status_code == 200
    # India is assessed, but the event's market stays the United States: the complaint's Markets field (0.10.70).
    assert _ok(user.get(EVENT))["work"]["markets"] == ["US"]

    # 4. The US report, created when the US conclusion was signed reportable (0.10.75, C3): the next step opens it;
    # G8 is never typed twice.
    label, target, _ = _next(user)
    assert label == "Complete the United States (FDA) report (draft)"
    assert target["record"]["id"] == complaint and target["tab"] == "Reports"
    (started,) = [item for item in _ok(user.get(REPORTS, params={"complaint_id": complaint}))["items"] if item["id"]]
    report = _ok(user.get(f"{REPORTS}/{started['id']}"))
    missing = [f["id"] for s in report["sections"] for f in s["fields"] if f["status"] == "MUST_HAVE"]
    assert "G8" in missing  # until the front page's number is entered
    values = {"MFR_REPORT": "1234567-2026-00011", "G2": "Health professional"}
    for field in [item for item in missing if item != "G8"]:
        report = _ok(user.put(f"{REPORTS}/{report['id']}/fields/{field}", json={"value": values.get(field, "Entered")}))
    # 0.10.77: the device problem code is suggested from the approved mapping (with its FDA code) and confirmed.
    (problem,) = [f for s in report["sections"] for f in s["fields"] if f["status"] == "SUGGESTED"]
    assert (problem["id"], problem["suggestion"]) == ("H6_PROBLEM", "A090807 High Readings (FDA 2459)")
    report = _ok(user.put(f"{REPORTS}/{report['id']}/fields/H6_PROBLEM", json={"confirmed": True}))
    g8 = next(f for s in report["sections"] for f in s["fields"] if f["id"] == "G8")
    assert (g8["value"], g8["status"], g8["source"]["label"]) == (
        "1234567-2026-00011",
        "FROM_RECORD",
        "This worksheet's front page",
    )
    assert not [f for s in report["sections"] for f in s["fields"] if f["status"] == "MUST_HAVE"]
    asked = _ok(user.post(f"{REPORTS}/{report['id']}/snapshots"))
    # The colleague may approve: the approval is a task in their My work, its first.
    task = _ok(colleague.get("/api/v1/tasks", params={"view": "assigned"}))["items"][0]
    assert task["title"].startswith("Approve snapshot 1 of the Form FDA 3500A")
    _ok(
        colleague.post(
            f"{REPORTS}/{report['id']}/snapshots/{asked['pending_snapshot']['id']}/approve",
            json={"password": COLLEAGUE_PASSWORD},
        )
    )
    sent = _ok(
        user.post(
            f"{REPORTS}/{report['id']}/submissions",
            json={
                "route": "EMDR",
                "submitted_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
                "content_note": "As submitted.",
                "no_differences": True,
            },
        )
    )
    _ok(
        user.post(
            f"{REPORTS}/{report['id']}/submissions/{sent['submissions'][0]['id']}/evidence",
            json={
                "kind": "ACK3",
                "outcome": "ACCEPTED",
                "received_at": datetime.now(timezone.utc).isoformat(),
                "note": "Acknowledgement 3: accepted",
            },
        )
    )

    # 5. The disposition: the user type comes from the worksheet's report source; the trigger escalates.
    label, target, _ = _next(user)
    assert label == "Sign the disposition"
    assert target["record"] == {"kind": "disposition", "id": complaint}
    from tests.test_complaint_disposition_api import _acknowledge as acknowledge_disposition
    from tests.test_complaint_disposition_api import _sign as sign_disposition

    acknowledge_disposition(user)
    screen = _ok(user.get(f"/api/v1/complaints/{complaint}/disposition"))
    assert screen["classification"]["user_type"] == "HEALTHCARE_PROFESSIONAL"
    assert "report worksheet G2" in screen["classification"]["source_values"]["user_type"]
    assert "REPORTABLE" in screen["trigger_codes"]
    # One word per thing (0.10.70): every trigger's fact and definition says "investigation", never "case".
    for text in [item["fact"] for item in screen["triggers"]] + [
        rule["definition"] for rule in screen["trigger_rules"]
    ]:
        assert not re.search(r"(cases?|signals?)", text), text
    rationale = "Reportable in the US: a product investigation of the reading error."
    disposition = _ok(sign_disposition(user, complaint, "ESCALATED_BY_TRIGGER", screen, rationale=rationale))
    case_id = disposition["current"]["investigation_id"]

    # 6. The investigation: the next step opens THIS investigation's decision (it opened the list before 0.10.69).
    label, target, _ = _next(user)
    assert label == "Sign the investigation's decision"
    assert target["record"] == {"kind": "case", "id": case_id} and target["tab"] == "Decision"
    resolved = _ok(user.get("/api/v1/workspace/context/resolve", params={"investigation": case_id}))
    assert resolved["investigation_id"] == case_id
    case = f"/api/v1/investigations/{case_id}"
    scope = _ok(user.get(f"{case}/scope"))["current"]
    # The question in words: the complaint's own words and the triggers, no codes, no doubled "escalated" (0.10.70).
    assert (
        scope["question"].startswith("Biomedical engineering checked a monitor")
        and "REPORTABLE" not in scope["question"]
    )
    assert "Escalated from complaint SAMPLE-RV-11 by the triggers reportable outcome, new failure mode." in (
        " ".join(scope["question"].split())
    )
    assert "trigger met:" not in scope["question"]
    # Items 9 and 10 (0.10.70): the product's investigation list, which the investigation page's context reads, holds
    # this investigation with its question, owner, due date and its own version (Rev A, the flagship's), so the page
    # never shows a previously opened version or the first investigation of the list.
    listed = _ok(user.get(f"/api/v1/products/{resolved['product_id']}/investigations"))
    row = next(item for item in listed if item["id"] == case_id)
    assert row["investigation_question"] == scope["question"]
    assert row["owner_ref"] and row["due_at"]
    assert row["version_identifier"] == "Rev A"
    orbit = _ok(user.get("/api/v1/workspace/context/resolve", params={"investigation": "SAMPLE-INV-001"}))
    orbit_row = next(
        item
        for item in _ok(user.get(f"/api/v1/products/{orbit['product_id']}/investigations"))
        if item["id"] == orbit["investigation_id"]
    )
    assert orbit_row["version_identifier"] == "Rev B"
    # Readiness names the escalation's triggers in words, not codes (0.10.70).
    due = {check["code"]: check for check in _ok(user.get("/api/v1/readiness"))["checks"]}["DISPOSITIONS_DUE"]
    assert "Escalated: reportable outcome, new failure mode" in [item["label"] for item in due["items"]]
    # The complaint's own record is the first evidence: the person reviews it, nothing is typed again.
    (item,) = _ok(user.get(f"{case}/evidence-inventory"))["items"]
    assert item["evidence"]["source_reference"] == "Complaint SAMPLE-RV-11"
    _ok(
        user.post(
            f"{case}/evidence/{item['evidence']['id']}/review",
            json={"review_status": "ACCEPTED", "relationship": "SUPPORTING", "reason": "The engineer's own check."},
        )
    )
    review = _ok(user.post(f"{case}/reviews", json={"review_type": "REGULATORY", "reason": "A malfunction."}), 201)
    _ok(user.post(f"/api/v1/case-reviews/{review['id']}/start", json={}))
    _ok(
        user.post(
            f"/api/v1/case-reviews/{review['id']}/complete",
            json={
                "outcome": "REPORTABILITY_ASSESSMENT_COMPLETE",
                "rationale": "US reportable and filed; India not reportable.",
                "assessed": {},
            },
        )
    )
    brief = f"{case}/decision-brief"
    composed = _ok(user.post(brief, json={"use_ai_draft": False}), 201)
    # The problem statement is the investigation's question (it started empty with AI off).
    assert composed["narrative"]["problem_statement"] == " ".join(scope["question"].split())
    _ok(
        user.put(
            f"{brief}/draft",
            json={
                "problem_statement": composed["narrative"]["problem_statement"],
                "proposed_conclusion": "The SpO2 sensor drifted high on this unit; service replaces it.",
                "recommended_actions": ["Replace the sensor in service"],
                "author_notes": "",
            },
        )
    )
    _ok(user.post(f"{brief}/submit", json={}))
    # The colleague's My work: the brief's review task.
    _ok(colleague.post(f"{brief}/versions/1/start-review", json={}))
    _ok(colleague.post(f"{brief}/versions/1/review", json={"action": "ACCEPT_FOR_DECISION", "comment": "Holds."}))
    decision = _ok(colleague.get(f"{case}/decision"))["brief"]
    signed = colleague.post(
        f"{case}/decision/sign",
        json={
            "brief_version_id": decision["id"],
            "brief_content_hash": decision["content_hash"],
            "outcome": "ACCEPT_CONCLUSION",
            "rationale": "The sensor drift explains the reading; service replaces the sensor.",
            "root_cause_attribution": "DEVICE_RELATED",
            "residual_unknowns_acknowledged": True,
            "password": COLLEAGUE_PASSWORD,
        },
    )
    assert signed.status_code == 200, signed.text

    # 7. Ready to close: nothing open; the event owner signs.
    label, target, view = _next(user)
    assert label is None and view["state"] == "READY_TO_SIGN", view["checklist"]
    ready = _ok(user.post(f"/api/v1/oversight/events/{complaint}/ready", json={"password": PASSWORD, "reason": ""}))
    assert ready["ready"]["state"] == "READY"
    # The action count drops: the market answers took 23 actions instead of 32.
    assert actions == 23
    # 0.10.72: 21 main buttons (triage on the page) and 23 answer actions: 44 actions instead of 54.
    assert (len(WALK), len(WALK) + actions) == (21, 44)
    assert len(WALK) + actions < ACTIONS_BEFORE


def test_a_finished_sample_event_asks_for_nothing_and_an_old_one_is_signed_again(trial):
    """Item 4 (0.10.70): SAMPLE-RV-09, closed in the QMS after its ready to close was signed, asks for no next step;
    its ready to close was signed over an empty checklist before (the root cause: the sample's seeding), so it read
    "Sign the disposition" and "changed since signed". It is now signed with its checklist as it stood and its reason,
    the day after its US report was accepted. A trial seeded before is signed again by the refresh, once."""
    from backend.app.db.models.foundation import SignedApprovalRecord
    from backend.app.db.models.oversight import EventClosure
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.oversight import closure
    from backend.app.trial.sample_calm import RV09_REASON, _rv09, rerecord_rv09

    user = trial["user"]
    view = _ok(user.get("/api/v1/oversight/events/SAMPLE-RV-09"))
    assert view["state"] == "CLOSED" and view["summary"]["next_action"] is None
    assert not view["changed_since_signed"]
    assert not [stage for stage in view["stages"] if stage["state"] == "CURRENT"]
    assert (view["ready"]["state"], view["ready"]["reason"]) == ("READY_WITH_REASON", RV09_REASON)
    entries = view["decision_record"]["entries"]
    ready = next(entry for entry in entries if entry["kind"] == "Ready to close in the QMS")
    assert all(entry["signed_at"] <= ready["signed_at"] for entry in entries if entry["kind"].startswith("Market"))
    # The list and My work read the same next step: none.
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        complaint = _rv09(db, trial["tenant_id"])
        row = db.query(EventClosure).filter(EventClosure.complaint_id == complaint.id).one()
        # As seeded before 0.10.70: "checklist clear" over an empty checklist.
        row.ready_state, row.ready_reason = "READY", None
        row.content_fingerprint = closure.fingerprint(complaint.id, [])
        row_id, record_id = row.id, row.signed_record_id
        db.commit()
    assert _ok(user.get("/api/v1/oversight/events/SAMPLE-RV-09"))["summary"]["next_action"]["label"] == (
        "Sign the disposition"
    )
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        assert rerecord_rv09(db, trial["tenant_id"]) == 1  # the dry run changes nothing
        assert rerecord_rv09(db, trial["tenant_id"], apply=True) == 1
        db.commit()
        assert rerecord_rv09(db, trial["tenant_id"], apply=True) == 0
        signed = db.get(SignedApprovalRecord, record_id)
        assert signed.content_fingerprint == db.get(EventClosure, row_id).content_fingerprint
    again = _ok(user.get("/api/v1/oversight/events/SAMPLE-RV-09"))
    assert again["summary"]["next_action"] is None and not again["changed_since_signed"]


def test_a_complaint_in_an_investigation_is_decided_there(trial):
    """Item 8 (0.10.70): the OrbitCare complaints in SAMPLE-INV-001's scope read stage "Investigation" and asked "Sign
    the disposition"; their next step is the investigation's decision, on that investigation."""
    view = _ok(trial["user"].get("/api/v1/oversight/events/SAMPLE-ORBIT-300-CMP-007"))
    action = view["summary"]["next_action"]
    assert action["label"] == "Sign the investigation's decision"
    assert action["opens"]["target"]["record"]["kind"] == "case"
    assert next(stage for stage in view["stages"] if stage["state"] == "CURRENT")["code"] == "INVESTIGATION"


@pytest.mark.unit
def test_the_walk_and_the_field_sources_are_listed():
    assert (
        WALK[0][2] == "Is this reportable, and by when, in the US and India?" and WALK[-1][2] == "Sign ready to close"
    )
    assert all(
        source.split(":")[0] in ("entered", "prefilled", "entered (no classification yet)") for *_, source in FIELDS
    )
