"""0.10.75, Release C part C3: decision trees and authority reports for the US and India.

- On the new navigation, signing a market conclusion as reportable creates exactly one report for the market (FDA
  3500A, MvPI MDAE), pre-filled from the complaint, the product, the organization and the tree; a draft creates none;
  a later signed "not reportable" cancels an unsubmitted report with its reason, audited; reportable again reopens it.
- The status path (created, mandatory fields complete, sent for approval, approved and PDF ready, submitted,
  acknowledged) and the mandatory-fields meter come from the form; Send for approval waits for every mandatory field.
- The approver is never the preparer, or (working alone in a trial) the practice label shows; the PDF comes only after
  approval, with the approval on its own last page.
- The classic navigation (every pilot today) keeps its rules; the sample's reports fit the path; the refresh gives a
  running trial the report of a conclusion signed before the upgrade, once.
- The Decision trees tab: each market's tree with its version, status and test matrix result, and each complaint's
  path: question, answer, clause, outcome.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.authority_reports import rules
from backend.app.db.models.foundation import AuditEvent
from backend.app.db.session import SessionLocal
from backend.app.main import app
from tests.report_fill import fill
from tests.conftest import authenticated_client
from tests.test_flagship_walkthrough import _answers_from_record
from tests.test_free_trial import PASSWORD, _activation_token, _approved_trial_client
from tests.test_market_assessment_api import _acknowledge, _save, _sign
from tests.test_sample_story_days import FLAGSHIP_US

pytestmark = pytest.mark.db

REPORTS = "/api/v1/reports"
TREES = "/api/v1/decision-trees"


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


def _purge(tenant_id) -> None:
    from backend.app.trial.retention import purge_trial

    with SessionLocal() as db:
        purge_trial(db, tenant_id, "test:release-c3-cleanup")


def _classic(tenant_id) -> None:
    admin = authenticated_client()
    found = _ok(admin.get(f"/api/v1/platform-admin/tenants/{tenant_id}"))
    tenant = found.get("tenant", found)
    _ok(
        admin.patch(
            f"/api/v1/platform-admin/tenants/{tenant_id}",
            json={
                "navigation": "classic",
                "reason": "test: the classic navigation keeps its rules",
                "lock_version": tenant["lock_version"],
            },
        )
    )


def _flagship(user) -> str:
    """SAMPLE-RV-11 triaged and the US training acknowledged, ready for its US assessment: its id."""
    complaint = _ok(user.get("/api/v1/oversight/events/SAMPLE-RV-11"))["event"]["complaint_id"]
    person = _ok(user.get("/api/v1/triage"))["people"][0]["id"]
    _ok(
        user.post(
            f"/api/v1/triage/COMPLAINT/{complaint}/record",
            json={
                "severity": "NEGLIGIBLE",
                "event_owner": person,
                "triage_owner": person,
                "immediate_action": "Out of use, sent for service.",
            },
        )
    )
    _acknowledge(user, "US")
    return complaint


@pytest.fixture(scope="module")
def trial():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    complaint = _flagship(user)
    try:
        yield {"user": user, "tenant_id": tenant_id, "complaint": complaint}
    finally:
        _purge(tenant_id)


def _us_answers(user, complaint, recurs: bool = True) -> tuple[dict, str]:
    detail = _ok(user.get(f"/api/v1/complaints/{complaint}/market-assessments"))
    answers, _ = _answers_from_record(detail, "US", FLAGSHIP_US)
    if not recurs:
        # "Would it cause or contribute to a death or serious injury if it recurred?": No. Not reportable.
        answers["US5"] = {**answers["US5"], "answer": "NO", "rationale": "Test: the reading error cannot recur unseen."}
    return answers, detail["severity_level"]


def _sign_us(user, complaint, conclusion: str, recurs: bool = True):
    answers, level = _us_answers(user, complaint, recurs)
    saved = _save(user, complaint, "US", answers, harm_level=level)
    return _sign(user, complaint, "US", saved, conclusion, password=PASSWORD)


def _reports(user, complaint) -> list[dict]:
    return [item for item in _ok(user.get(REPORTS, params={"complaint_id": complaint}))["items"] if item["id"]]


def _audit(tenant_id, action: str) -> list[AuditEvent]:
    with SessionLocal() as db:
        return db.query(AuditEvent).filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == action).all()


def test_signing_reportable_creates_exactly_one_report_and_a_draft_creates_none(trial):
    user, complaint = trial["user"], trial["complaint"]
    answers, level = _us_answers(user, complaint)
    saved = _save(user, complaint, "US", answers, harm_level=level)
    # A draft conclusion: no report (the list may name the market as owed, never as a report).
    assert _reports(user, complaint) == []
    _ok(_sign(user, complaint, "US", saved, "REPORTABLE", password=PASSWORD))
    (report,) = _reports(user, complaint)
    assert (report["market"], report["state"], report["stage"]) == ("US", "DRAFT", "CREATED")
    assert report["form_title"] == "Form FDA 3500A worksheet (eMDR)"
    assert 0 < report["mandatory"]["filled"] < report["mandatory"]["total"]
    detail = _ok(user.get(f"{REPORTS}/{report['id']}"))
    # Pre-filled from the complaint, the product, the organization and the tree, each with its source.
    filled = {item["id"]: item for section in detail["sections"] for item in section["fields"] if item["value"]}
    assert {"B1", "B5", "D1", "D2B"} <= set(filled) and all(filled[key]["source"] for key in ("B1", "B5", "D1"))
    assert [stage["label"] for stage in detail["stages"]] == [label for _, label in rules.STAGES]
    assert [stage["state"] for stage in detail["stages"]][:2] == ["CURRENT", "LATER"]
    assert detail["preparers"] and detail["mandatory"]["missing"]
    # This complaint's (0.10.76: the sample's SAMPLE-RV-07 has its own, made when the sample was staged).
    created = [
        e
        for e in _audit(trial["tenant_id"], "REPORT_CREATED_FROM_CONCLUSION")
        if e.details["complaint_id"] == complaint
    ]
    assert len(created) == 1
    # Signing reportable again (a new version) keeps the one report.
    _ok(_sign_us(user, complaint, "REPORTABLE"))
    assert [item["id"] for item in _reports(user, complaint)] == [report["id"]]


def test_send_for_approval_stays_blocked_until_every_mandatory_field_is_filled(trial):
    user, complaint = trial["user"], trial["complaint"]
    (report,) = _reports(user, complaint)
    refused = user.post(f"{REPORTS}/{report['id']}/snapshots")
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "MANDATORY_FIELDS_MISSING"
    missing = refused.json()["detail"]["missing"]
    assert missing == _ok(user.get(f"{REPORTS}/{report['id']}"))["mandatory"]["missing"]
    fill(user, REPORTS, report["id"], missing[:-1])
    still = user.post(f"{REPORTS}/{report['id']}/snapshots")
    assert still.status_code == 422 and still.json()["detail"]["missing"] == missing[-1:]
    detail = fill(user, REPORTS, report["id"], missing[-1:])
    assert detail["stage"] == "COMPLETE" and detail["mandatory"]["missing"] == []
    detail = _ok(user.post(f"{REPORTS}/{report['id']}/snapshots"))
    assert detail["stage"] == "APPROVAL" and detail["pending_snapshot"]


def test_the_pdf_comes_only_after_approval_and_alone_the_practice_label_shows(trial):
    user, complaint = trial["user"], trial["complaint"]
    (report,) = _reports(user, complaint)
    detail = _ok(user.get(f"{REPORTS}/{report['id']}"))
    pending = detail["pending_snapshot"]["id"]
    for query in ({}, {"snapshot": pending}):
        refused = user.get(f"{REPORTS}/{report['id']}/worksheet.pdf", params=query)
        assert refused.status_code == 409 and refused.json()["detail"]["code"] == "APPROVE_FIRST"
    # Working alone in the trial: the preparer approves the practice report, and the practice label shows.
    assert detail["approval"]["same_person"] and detail["approval"]["may_approve"]
    assert detail["practice_label"] and "Not your regulatory record" in detail["practice_label"]
    # The list view "Waiting for my approval" holds it (in a trial, one's own as practice).
    assert "my-approval" in next(item for item in _reports(user, complaint))["views"]
    detail = _ok(user.post(f"{REPORTS}/{report['id']}/snapshots/{pending}/approve", json={"password": PASSWORD}))
    assert (detail["state"], detail["stage"], detail["stage_label"]) == ("APPROVED", "APPROVED", "Approved")
    snapshot = detail["approved_snapshot"]
    assert snapshot["same_person"]
    pdf = user.get(f"{REPORTS}/{report['id']}/worksheet.pdf", params={"snapshot": snapshot["id"]})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_a_colleague_approves_a_report_prepared_by_someone_else():
    owner, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        mail = f"c3-approver-{uuid.uuid4().hex[:6]}@example.invalid"
        invited = _ok(
            owner.post(
                "/api/v1/trial/team", json={"email": mail, "display_name": "Rahul Colleague", "persona": "regulatory"}
            )
        )
        colleague = TestClient(app)
        _ok(
            colleague.post(
                "/api/v1/auth/activate-account", json={"token": _activation_token(invited, mail), "password": PASSWORD}
            )
        )
        _ok(colleague.post("/api/v1/auth/signin", json={"email": mail, "password": PASSWORD}))
        complaint = _flagship(owner)
        _ok(_sign_us(owner, complaint, "REPORTABLE"))
        (report,) = _reports(owner, complaint)
        fill(owner, REPORTS, report["id"], _ok(owner.get(f"{REPORTS}/{report['id']}"))["mandatory"]["missing"])
        detail = _ok(owner.post(f"{REPORTS}/{report['id']}/snapshots"))
        # The preparer may not approve once a colleague may: no practice approval, the colleague named.
        assert not detail["approval"]["may_approve"] and detail["approval"]["approvers"] == ["Rahul Colleague"]
        refused = owner.post(
            f"{REPORTS}/{report['id']}/snapshots/{detail['pending_snapshot']['id']}/approve",
            json={"password": PASSWORD},
        )
        assert refused.status_code == 403
        theirs = _ok(colleague.get(f"{REPORTS}/{report['id']}"))
        assert theirs["approval"]["may_approve"] and not theirs["approval"]["same_person"]
        assert "my-approval" in _reports(colleague, complaint)[0]["views"]
        done = _ok(
            colleague.post(
                f"{REPORTS}/{report['id']}/snapshots/{theirs['pending_snapshot']['id']}/approve",
                json={"password": PASSWORD},
            )
        )
        assert done["approved_snapshot"]["approved_by"] == "Rahul Colleague"
        assert done["approved_snapshot"]["approved_by"] not in done["preparers"]
        assert not done["approved_snapshot"]["same_person"]
    finally:
        _purge(tenant_id)


def test_a_not_reportable_re_sign_cancels_the_unsubmitted_report_and_reportable_reopens_it(trial):
    user, complaint, tenant_id = trial["user"], trial["complaint"], trial["tenant_id"]
    (report,) = _reports(user, complaint)
    assert report["state"] == "APPROVED"  # approved, not yet submitted: still cancellable
    _ok(_sign_us(user, complaint, "NOT_REPORTABLE", recurs=False))
    (cancelled,) = _reports(user, complaint)
    assert (cancelled["id"], cancelled["state"], cancelled["stage"], cancelled["views"]) == (
        report["id"],
        "CANCELLED",
        None,
        [],
    )
    detail = _ok(user.get(f"{REPORTS}/{report['id']}"))
    assert "says not reportable" in detail["cancelled_reason"] and detail["next_step"].startswith("Nothing")
    assert all(row["state"] == "SUPERSEDED" for row in detail["snapshots"])
    (event,) = _audit(tenant_id, "REPORT_CANCELLED")
    assert event.details["reason"] == detail["cancelled_reason"] and event.details["state_before"] == "APPROVED"
    # Nothing is owed: no deadline of it on Oversight, and the complaint's checklist does not wait for it.
    items = _ok(user.get("/api/v1/oversight", params={"show": "all"}))["items"]
    assert not any(item["key"] == f"obligation:{report['id']}" for item in items)
    # Reportable again: the same report, a draft once more (one report per market per complaint).
    _ok(_sign_us(user, complaint, "REPORTABLE"))
    (again,) = _reports(user, complaint)
    assert (again["id"], again["state"]) == (report["id"], "DRAFT")
    assert len(_audit(tenant_id, "REPORT_REOPENED_BY_CONCLUSION")) == 1


def test_the_sample_reports_fit_the_status_path(trial):
    items = {item["complaint_ref"]: item for item in _ok(trial["user"].get(REPORTS))["items"] if item["id"]}
    us, india = items["SAMPLE-RV-09"], items["SAMPLE-RV-10"]
    assert (us["state"], us["stage"], us["stage_label"]) == ("ACCEPTED", "ACKNOWLEDGED", "Acknowledged")
    assert us["views"] == [] or us["views"] == ["submitted-month"]
    # 0.10.81: sent back for correction, it is neither complete nor submitted this month.
    assert (india["state"], india["stage"], india["stage_label"]) == (
        "CORRECTION_REQUIRED",
        "CREATED",
        "Draft: correction required",
    )
    assert india["mandatory"]["filled"] == india["mandatory"]["total"] and india["views"] == ["open"]


def test_the_classic_navigation_keeps_its_rules_and_the_refresh_adds_the_report_once():
    from backend.app.trial import reports_0_10_75

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        _classic(tenant_id)
        complaint = _flagship(user)
        _ok(_sign_us(user, complaint, "REPORTABLE"))
        # Classic: nothing created on signing; the worksheet is started by a person, approval asked with fields
        # missing, and the working draft downloads, as before.
        assert _reports(user, complaint) == []
        started = _ok(user.post(REPORTS, json={"complaint_id": complaint, "market": "US"}))
        assert started["mandatory"]["missing"]
        assert user.get(f"{REPORTS}/{started['id']}/worksheet.pdf").content.startswith(b"%PDF")
        _ok(user.post(f"{REPORTS}/{started['id']}/snapshots"))
        # A trial moved to the new navigation with a conclusion signed before the upgrade and no report: the refresh
        # adds it once (dry run first), as the signing would have.
        with SessionLocal() as db:
            from backend.app.db.models.authority_reports import ReportObligation
            from backend.app.db.models.foundation import Tenant
            from backend.app.db.tenant_scope import bind_tenant

            bind_tenant(db, tenant_id)
            db.query(ReportObligation).filter(ReportObligation.id == uuid.UUID(started["id"])).delete()
            db.get(Tenant, tenant_id).navigation = "new"
            db.commit()
            assert reports_0_10_75.refresh(db, tenant_id, apply=False) == 1
            assert reports_0_10_75.refresh(db, tenant_id, apply=True) == 1
            db.commit()
            assert reports_0_10_75.refresh(db, tenant_id, apply=False) == 0
        (report,) = _reports(user, complaint)
        assert (report["state"], report["stage"]) == ("DRAFT", "CREATED")
    finally:
        _purge(tenant_id)


def test_the_decision_trees_show_each_market_and_the_path_a_complaint_took(trial):
    user = trial["user"]
    trees = _ok(user.get(TREES))
    by_market = {tree["market"]: tree for tree in trees["markets"]}
    assert {"US", "IN"} <= set(by_market)
    us = by_market["US"]
    # The sample's own US guide version 2 is approved and in use (its version 3 is a draft): the tree shows it.
    assert (us["status"], us["version"]) == ("APPROVED", 2) and us["version_label"].startswith(
        "Your version 2 · approved"
    )
    assert (by_market["IN"]["status"], by_market["IN"]["version"]) == ("STARTER", 1)
    assert "consultant" in by_market["IN"]["version_label"]
    assert us["tests"]["total"] > 0 and us["tests"]["passed"] == us["tests"]["total"]
    assert [question["id"] for question in us["questions"]][:3] == ["US1", "US2A", "US2B"]
    assert all(question["clause"] for question in us["questions"])
    walked = {item["ref"]: item for item in trees["complaints"]}
    assert "US" in walked["SAMPLE-RV-09"]["signed"] and "IN" in walked["SAMPLE-RV-10"]["signed"]
    path = _ok(user.get(TREES, params={"complaint_id": walked["SAMPLE-RV-09"]["id"]}))["paths"]["US"]
    answers = {node["id"]: node["answer"] for node in path["nodes"]}
    assert (answers["US1"], answers["US2C"], answers["US4"], answers["US5"]) == ("NO", "YES", "YES", "YES")
    assert all(node["clause"] for node in path["nodes"])
    assert (
        path["outcome"]["code"] == "REPORTABLE" and path["outcome"]["signed"] and path["outcome"]["report_type_label"]
    )
    assert path["report"] and path["has_form"]
    # An unknown complaint is refused; another organization's is not found either.
    assert user.get(TREES, params={"complaint_id": str(uuid.uuid4())}).status_code == 404


@pytest.mark.parametrize(
    ("state", "missing", "pending", "stage"),
    [
        ("DRAFT", 3, False, "CREATED"),
        ("DRAFT", 0, False, "COMPLETE"),
        ("DRAFT", 0, True, "APPROVAL"),
        ("CORRECTION_REQUIRED", 0, False, "CREATED"),
        ("CORRECTION_REQUIRED", 0, True, "APPROVAL"),
        ("APPROVED", 0, False, "APPROVED"),
        ("SUBMITTED_PENDING", 0, False, "SUBMITTED"),
        ("SUBMITTED_NO_ACK", 0, False, "SUBMITTED"),
        ("ACCEPTED", 0, False, "ACKNOWLEDGED"),
        ("FOLLOW_UP_DUE", 0, False, "ACKNOWLEDGED"),
        ("COMPLETE", 0, False, "ACKNOWLEDGED"),
        ("CANCELLED", 0, False, None),
    ],
)
def test_each_state_has_its_place_on_the_status_path(state, missing, pending, stage):
    view = rules.stage_view(state, missing, pending)
    assert view["stage"] == stage
    states = [item["state"] for item in view["stages"]]
    if stage is None:
        assert states == ["LATER"] * 6 and view["stage_label"] == "Cancelled: not reportable"
    elif stage == "ACKNOWLEDGED":
        assert states == ["DONE"] * 6
    else:
        at = [code for code, _ in rules.STAGES].index(stage)
        assert states == ["DONE"] * at + ["CURRENT"] + ["LATER"] * (5 - at)


def test_an_approved_reports_approval_stands_on_its_own_last_page():
    from backend.app.authority_reports import render
    from reports.pdf import PAGE_BREAK

    view = {
        "form": {
            "title": "Form FDA 3500A worksheet (eMDR)",
            "version": "Form FDA 3500A (09/2025)",
            "authority": "FDA",
            "source_document": "Form FDA 3500A",
            "clauses": [],
        },
        "complaint": {"ref": "SAMPLE-RV-11", "product_name": "PulseWatch 410", "version": "Rev A"},
        "market_label": "United States",
        "state_label": "Approved snapshot",
        "deadline": {"due_label": "Tue 1 Dec 2026, 23:59 IST", "due_on": "2026-12-01", "provisional": False},
        "starter_mark": "Starter text.",
        "never_submits": "MDARIX never submits.",
        "practice_label": None,
        "sections": [
            {
                "code": "B",
                "title": "B. Adverse event or product problem",
                "note": None,
                "fields": [
                    {
                        "number": "B5",
                        "label": "Describe event or problem",
                        "value": "SpO2 read high",
                        "status_label": "From record",
                        "source": None,
                        "by": None,
                    }
                ],
            }
        ],
        "snapshot": {"version": 1, "state": "APPROVED"},
        "signature": {
            "signer_name": "Rahul Colleague",
            "signer_role": "Regulatory Reviewer",
            "signed_at": "2026-11-03T10:00:00",
            "meaning": "I approve snapshot 1.",
            "record_business_id": "SIG000001",
            "record_id": "x",
            "content_fingerprint": "f" * 64,
        },
    }
    lines = render.lines(view)
    at = lines.index(("Approval", "heading"))
    assert lines[at - 1] == ("", PAGE_BREAK) and lines.index(("Source records", "heading")) < at
    assert lines[at + 1][0].startswith("Approved by Rahul Colleague") and len(lines) == at + 5
    pages = render.render_pdf(view, "Medisynth Devices (Sample)").count(b"/Type /Page ")
    draft = render.render_pdf({**view, "signature": None, "snapshot": None}, "Medisynth Devices (Sample)").count(
        b"/Type /Page "
    )
    assert (pages, draft) == (2, 1)
