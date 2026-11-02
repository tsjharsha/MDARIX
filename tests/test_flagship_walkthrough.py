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
    ("Triage", "Complaint page › Summary", "Complete the triage record (on the triage list)"),
    ("Triage", "Complaints › To triage, the complaint's triage panel", "Save the triage record"),
    ("US market", "Complaint page › Summary", "Assess the United States (FDA) market"),
    ("US market", "Complaints › Reporting, the US assessment", "Save and sign"),
    ("India market", "The same assessment's next step", "Assess India (CDSCO) too"),
    ("India market", "Complaints › Reporting, the India assessment", "Save and sign"),
    ("US report", "Next step", "Start the United States (FDA) report"),
    ("US report", "Complaints › Reporting, the worksheet (show only missing)", "Ask for approval"),
    ("US report", "The approver's My work (the trial owner alone: the same screen)", "Approve"),
    ("US report", "Complaints › Reporting, the report", "Mark as submitted"),
    ("US report", "Complaints › Reporting, the report: the acceptance", "Record the evidence"),
    ("Disposition", "Next step", "Sign the disposition"),
    ("Disposition", "My work › Queues, the complaint's disposition", "Sign"),
    ("Investigation", "Next step", "Sign the investigation decision on the case"),
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
    ("flagship", "Answers to each market's questions", "Market assessment", "entered: the market's own questions"),
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


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

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

    # 1. Triage: the main button opens this complaint's triage panel, not the list.
    assert label == "Complete the triage record (on the triage list)"
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
    us = _save(user, complaint, "US", _answers(**FLAGSHIP_US), harm_level=detail["severity_level"])
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
    _acknowledge(user, "IN")
    india = _save(user, complaint, "IN", _answers(**FLAGSHIP_IN), harm_level=detail["severity_level"])
    assert india["evaluation"]["suggested"] == "NOT_REPORTABLE"
    reason = "No adverse event: nobody was harmed, a malfunction only."
    assert _sign(user, complaint, "IN", india, "NOT_REPORTABLE", password=PASSWORD, reason=reason).status_code == 200

    # 4. The US report: the worksheet opens on this complaint's reports; G8 is never typed twice.
    label, target, _ = _next(user)
    assert label == "Start the United States (FDA) report"
    assert target["record"]["id"] == complaint and target["tab"] == "Reports"
    report = _ok(user.post(REPORTS, json={"complaint_id": complaint, "market": "US"}))
    missing = [f["id"] for s in report["sections"] for f in s["fields"] if f["status"] == "MUST_HAVE"]
    assert "G8" in missing  # until the front page's number is entered
    values = {"MFR_REPORT": "1234567-2026-00011", "G2": "Health professional"}
    for field in [item for item in missing if item != "G8"]:
        report = _ok(user.put(f"{REPORTS}/{report['id']}/fields/{field}", json={"value": values.get(field, "Entered")}))
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
    rationale = "Reportable in the US: a product investigation of the reading error."
    disposition = _ok(sign_disposition(user, complaint, "ESCALATED_BY_TRIGGER", screen, rationale=rationale))
    case_id = disposition["current"]["investigation_id"]

    # 6. The investigation: the next step opens THIS investigation's decision (it opened the list before 0.10.69).
    label, target, _ = _next(user)
    assert label == "Sign the investigation decision on the case"
    assert target["record"] == {"kind": "case", "id": case_id} and target["tab"] == "Decision"
    resolved = _ok(user.get("/api/v1/workspace/context/resolve", params={"investigation": case_id}))
    assert resolved["investigation_id"] == case_id
    case = f"/api/v1/investigations/{case_id}"
    scope = _ok(user.get(f"{case}/scope"))["current"]
    # The question in words: the complaint's own words and the trigger, no codes.
    assert (
        scope["question"].startswith("Biomedical engineering checked a monitor")
        and "REPORTABLE" not in scope["question"]
    )
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


@pytest.mark.unit
def test_the_walk_and_the_field_sources_are_listed():
    assert (
        WALK[0][2] == "Is this reportable, and by when, in the US and India?" and WALK[-1][2] == "Sign ready to close"
    )
    assert all(
        source.split(":")[0] in ("entered", "prefilled", "entered (no classification yet)") for *_, source in FIELDS
    )
