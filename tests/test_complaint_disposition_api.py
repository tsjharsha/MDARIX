"""Complaint disposition through the API (T-G36, T-G36T, T-G36R, T-U13, T-G39), with migration tr02's table: each
branch on the trial's sample complaints (the routine path, a second service-level close and the recurring matter, the
known issue, the escalation by trigger), the practice training, versions, a trigger met at signing and after signing,
classification Unknown kept, the trend by resolution, Readiness, tenant isolation, and sample removal."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.models.complaint_disposition import ComplaintDisposition
from backend.app.db.models.foundation import AuditEvent, Complaint, Investigation, SignedApprovalRecord
from backend.app.db.models.market_assessment import ComplaintClassification, ComplaintMarketAssessment
from backend.app.db.session import RuntimeSessionLocal, SessionLocal, runtime_role_active
from backend.app.db.tenant_scope import bind_system, bind_tenant
from tests.test_free_trial import PASSWORD, _approved_trial_client

pytestmark = pytest.mark.db

BOARD = "/api/v1/complaints/dispositions"
TRAINING = "/api/v1/signer-training"
WHY = "Same failure and lot as the open investigation; added as a contributing complaint."
RECORD = {
    "troubleshooting": "Alarm check and filter inspection over the phone with the therapist.",
    "correction_type": "USER_INSTRUCTED",
    "correction": "User instructed to re-seat the filter in its housing.",
    "result": "Alarm cleared, device in use.",
    "service_ticket": "DIST-REF-2231",
    "no_investigation_rationale": "User-correctable seating fault, cleared at service level; no harm; no product "
    "defect indicated; trended under ISO 13485:2016 8.2.2.",
}


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    items = user.get(f"{BOARD}?page_size=100").json()["items"]
    ids = {item["complaint_identifier"]: item["id"] for item in items}
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        for row in db.query(Complaint.complaint_identifier, Complaint.id).filter(Complaint.tenant_id == tenant_id):
            ids.setdefault(row.complaint_identifier, str(row.id))
    try:
        yield {"user": user, "tenant_id": tenant_id, "ids": ids}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:disposition-cleanup")


def _url(complaint_id: str, tail: str = "") -> str:
    return f"/api/v1/complaints/{complaint_id}/disposition{tail}"


def _acknowledge(client) -> None:
    for document in client.get(f"{TRAINING}?documents=DISPOSITION_RULES,CODING_CRITERIA").json()["documents"]:
        done = client.post(
            f"{TRAINING}/{document['code']}/acknowledge",
            json={"version": document["version"], "statement": document["statement"]},
        )
        assert done.status_code == 200, done.text


def _sign(client, complaint_id: str, branch: str, screen: dict | None = None, **extra):
    screen = screen or client.get(_url(complaint_id)).json()
    classification = screen["classification"]
    body = {
        "branch": branch,
        "classification": {
            "use_environment": classification["use_environment"],
            "use_environment_text": classification["use_environment_text"],
            "user_type": classification["user_type"],
            "user_type_text": classification["user_type_text"],
        },
        "seen_triggers": screen["trigger_codes"],
        "seen_version": screen["version"],
        "routine": screen["routine"]["offered"],
        "opened_at": screen["opened_at"],
        "password": PASSWORD,
    }
    if branch == "SERVICE_LEVEL":
        body.update({"service_record": RECORD, "attribution": "USE_RELATED"})
    body.update(extra)
    return client.post(_url(complaint_id, "/sign"), json=body)


def _backlog_ids(client) -> set[str]:
    found = client.get("/api/v1/complaints/backlog?page_size=100").json()["items"]
    return {item["id"] for item in found}


def _readiness(client) -> dict:
    return {check["code"]: check for check in client.get("/api/v1/readiness").json()["checks"]}


def test_the_sample_example_is_signed_three_weeks_ago_by_the_sample_author(trial):
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        (row,) = (
            db.query(ComplaintDisposition)
            .filter(
                ComplaintDisposition.tenant_id == trial["tenant_id"],
                ComplaintDisposition.source_system == "MDARIX_SAMPLE",
            )
            .all()
        )
    assert row.branch == "SERVICE_LEVEL" and row.attribution == "DEVICE_RELATED"
    assert row.signed_at < datetime.now(timezone.utc) - timedelta(days=19)


def test_the_routine_complaint_closes_at_service_level_on_one_screen_with_one_signature(trial):
    user, rt01 = trial["user"], trial["ids"]["SAMPLE-RT-01"]
    screen = user.get(_url(rt01)).json()
    assert screen["routine"]["offered"] is True and screen["trigger_codes"] == []
    assert [item["market"] for item in screen["routine"]["markets"]] == ["US", "EU_NI"]
    assert screen["reportability"]["on_watch"] is False and screen["candidates"] == []
    proposed = screen["classification"]
    assert proposed["state"] == "PROPOSED" and proposed["use_environment"] == "INTENSIVE_CARE_UNIT"
    assert (
        proposed["user_type"] == "HEALTHCARE_PROFESSIONAL"
        and screen["coding_criteria"]["version"] == "coding-starter-1"
    )
    assert screen["practice_label"].startswith("Practice record") and screen["training_required"] is True
    assert rt01 in _backlog_ids(user)

    # The practice training on the disposition rules and the coding criteria comes first (a trial's rule).
    untrained = _sign(user, rt01, "SERVICE_LEVEL", screen)
    assert untrained.status_code == 409 and untrained.json()["detail"]["code"] == "TRAINING_REQUIRED"
    assert {doc["code"] for doc in untrained.json()["detail"]["missing"]} == {"DISPOSITION_RULES", "CODING_CRITERIA"}
    _acknowledge(user)
    # The attribution is required, and undetermined needs its reason; "Other" needs its text.
    assert _sign(user, rt01, "SERVICE_LEVEL", screen, attribution=None).status_code == 422
    undetermined = _sign(user, rt01, "SERVICE_LEVEL", screen, attribution="UNDETERMINED")
    assert undetermined.status_code == 422 and "Undetermined" in undetermined.json()["detail"]["message"]
    other = _sign(
        user, rt01, "SERVICE_LEVEL", screen, classification={"use_environment": "OTHER", "user_type": "PATIENT"}
    )
    assert other.status_code == 422 and '"other" use environment' in other.json()["detail"]["message"]
    no_rationale = _sign(
        user, rt01, "SERVICE_LEVEL", screen, service_record={**RECORD, "no_investigation_rationale": ""}
    )
    assert no_rationale.status_code == 422 and "8.2.2" in no_rationale.json()["detail"]["message"]
    assert _sign(user, rt01, "ESCALATED_BY_TRIGGER", screen, rationale="No trigger is met here").status_code == 422
    bad = _sign(user, rt01, "SERVICE_LEVEL", screen, password="not the password")
    assert bad.status_code == 403

    signed = _sign(user, rt01, "SERVICE_LEVEL", screen)
    assert signed.status_code == 200, signed.text
    current = signed.json()["current"]
    assert current["branch"] == "SERVICE_LEVEL" and current["version"] == 1 and current["routine_path"] is True
    assert (
        current["attribution"] == "USE_RELATED" and current["service_record"]["clause"] == "ISO 13485:2016 clause 8.2.2"
    )
    assert current["service_record"]["service_ticket"] == "DIST-REF-2231" and current["hands_on_seconds"] is not None
    assert current["answers"]["TRIGGER"]["answer"] == "NO" and current["answers"]["SERVICE_LEVEL"]["answer"] == "YES"
    classification = signed.json()["classification"]
    assert classification["state"] == "CONFIRMED" and classification["coding_criteria_version"] == "coding-starter-1"
    assert classification["use_environment"] == "INTENSIVE_CARE_UNIT" and classification["version"] == 2
    assert rt01 not in _backlog_ids(user)
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        record = db.get(SignedApprovalRecord, uuid.UUID(current["signed_record_id"]))
        assert record.object_type == "ComplaintDisposition" and record.decision == "SERVICE_LVL"
        assert "not reportable on the routine basis" in record.signature_meaning
        markets = (
            db.query(ComplaintMarketAssessment)
            .filter(
                ComplaintMarketAssessment.tenant_id == trial["tenant_id"],
                ComplaintMarketAssessment.complaint_id == uuid.UUID(rt01),
            )
            .order_by(ComplaintMarketAssessment.market)
            .all()
        )
        assert [(row.market, row.question_set, row.conclusion) for row in markets] == [
            ("EU_NI", "ROUTINE-BASIS", "NOT_REPORTABLE"),
            ("US", "ROUTINE-BASIS", "NOT_REPORTABLE"),
        ]
        assert {row.signed_record_id for row in markets} == {record.id}
        bind_system(db, "test: the audit trail")
        actions = [
            row.details
            for row in db.query(AuditEvent).filter(
                AuditEvent.entity_id == uuid.UUID(rt01), AuditEvent.action == "COMPLAINT_DISPOSITION_SIGNED"
            )
        ]
        assert len(actions) == 1 and actions[0]["version"] == 1 and actions[0]["market_conclusions"] == ["US", "EU_NI"]

    # A signed disposition is never edited: a change is version 2, with its reason, and version 1 stays visible.
    screen = user.get(_url(rt01)).json()
    again = _sign(user, rt01, "SERVICE_LEVEL", screen, attribution="DEVICE_RELATED")
    assert again.status_code == 422 and "why it changes" in again.json()["detail"]["message"]
    stale = _sign(user, rt01, "SERVICE_LEVEL", {**screen, "version": 0}, change_reason="The filter housing was cracked")
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "SIGNED_MEANWHILE"
    changed = _sign(
        user,
        rt01,
        "SERVICE_LEVEL",
        screen,
        attribution="DEVICE_RELATED",
        change_reason="The filter housing was found cracked",
    )
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert body["current"]["version"] == 2 and body["current"]["attribution"] == "DEVICE_RELATED"
    assert [(row["version"], row["superseded"]) for row in body["history"]] == [(1, True)]


def test_a_source_value_off_the_list_stays_unknown_and_two_cable_closes_raise_the_recurring_matter(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    rt02 = trial["ids"]["SAMPLE-RT-02"]
    _acknowledge(user)
    screen = user.get(_url(rt02)).json()
    assert screen["classification"]["use_environment"] == "UNKNOWN"
    assert screen["classification"]["source_values"]["use_environment"] == "Step-down unit"
    assert _readiness(user)["RECURRING_SERVICE_LEVEL"]["value"] == 0  # RT-03 alone, signed by the sample author
    signed = _sign(
        user,
        rt02,
        "SERVICE_LEVEL",
        screen,
        attribution="DEVICE_RELATED",
        service_record={**RECORD, "correction_type": "PART_REPLACED", "correction": "Replaced the SpO2 cable"},
        classification={"use_environment": "HOSPITAL_WARD", "user_type": "HEALTHCARE_PROFESSIONAL"},
    )
    assert signed.status_code == 200, signed.text
    coded = signed.json()["classification"]
    assert coded["use_environment"] == "HOSPITAL_WARD" and coded["source_values"]["use_environment"] == "Step-down unit"
    recurring = _readiness(user)["RECURRING_SERVICE_LEVEL"]
    assert recurring["value"] == 1 and "PulseWatch" in recurring["items"][0]["ref"]
    assert recurring["items"][0]["label"].startswith("2 service-level resolutions in 30 days")

    # The trend by resolution: both cable closes, hospital ward, device-related; the counts match the dispositions.
    trend = user.get(f"{BOARD}/trend?group=use_environment&attribution=DEVICE_RELATED").json()
    ward = next(item for item in trend["items"] if item["key"] == ["Hospital ward"])
    assert ward["service_level"] == 2 and trend["totals"]["service_level"] == 3  # RT-01 v2 too (ICU)
    by_problem = user.get(f"{BOARD}/trend?group=problem").json()
    cable = next(item for item in by_problem["items"] if item["key"][1] == "CABLE_WEAR")
    assert cable["service_level"] == 2 and cable["complaints"] == 2
    signed_board = user.get(f"{BOARD}?show=signed").json()
    assert signed_board["summary"]["by_branch"]["SERVICE_LEVEL"] == by_problem["totals"]["service_level"]
    assert all(item["disposition"]["signed_by"] for item in signed_board["items"])

    # The next cable-wear complaint fires RECURRENCE until a case covers it.
    rt03 = trial["ids"]["SAMPLE-RT-03"]
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        template = db.get(Complaint, uuid.UUID(rt03))
        third = Complaint(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            complaint_identifier="OWN-CABLE-3",
            product_id=template.product_id,
            product_version_id=template.product_version_id,
            description="SpO2 cable frayed again at the connector.",
            problem_code="CABLE_WEAR",
            status="open",
            patient_involved=False,
            malfunction=False,
            complaint_timestamp=datetime.now(timezone.utc),
            source_system="TRIAL_UPLOAD",
            source_identifier="OWN-CABLE-3",
            source_timestamp=datetime.now(timezone.utc),
            effective_timestamp=datetime.now(timezone.utc),
            recorded_timestamp=datetime.now(timezone.utc),
            ingestion_timestamp=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(third)
        db.commit()
        third_id = str(third.id)
    screen = user.get(_url(third_id)).json()
    assert screen["trigger_codes"] == ["RECURRENCE"] and screen["routine"]["offered"] is False
    fact = screen["triggers"][0]
    assert fact["field"] == "service_level_resolutions" and fact["value"] == 2
    refused = _sign(user, third_id, "SERVICE_LEVEL", screen)
    assert refused.status_code == 422 and "other branches are refused" in refused.json()["detail"]["message"]


def test_the_known_issue_joins_the_open_case_through_a_new_scope_version(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    rt04 = trial["ids"]["SAMPLE-RT-04"]
    _acknowledge(user)
    screen = user.get(_url(rt04)).json()
    # The pressure-alarm signal exists, but SAMPLE-INV-001 covers it: no RECURRENCE, no NEW_FAILURE_MODE.
    assert screen["trigger_codes"] == []
    (case,) = screen["candidates"]
    assert case["identifier"] == "SAMPLE-INV-001" and "same product and problem code" in case["match"]
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        cases_before = db.query(Investigation).filter(Investigation.tenant_id == tenant_id).count()
    wrong = _sign(user, rt04, "KNOWN_ISSUE", screen, case_id=str(uuid.uuid4()), rationale=WHY)
    assert wrong.status_code == 422
    # Choosing service level while a case matches needs the reason it is not that issue.
    assert _sign(user, rt04, "SERVICE_LEVEL", screen).status_code == 422
    signed = _sign(user, rt04, "KNOWN_ISSUE", screen, case_id=case["id"], rationale=WHY)
    assert signed.status_code == 200, signed.text
    current = signed.json()["current"]
    assert current["branch"] == "KNOWN_ISSUE" and current["attribution"] is None
    assert current["investigation_ref"] == case["ref"]
    scope = user.get(f"/api/v1/investigations/{case['id']}/scope").json()
    assert rt04 in {item["id"] for item in scope["current"]["included_complaints"]}
    assert "contributing complaint" in (scope["versions"][0]["change_reason"] or "")
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        assert db.query(Investigation).filter(Investigation.tenant_id == tenant_id).count() == cases_before
    assert rt04 not in _backlog_ids(user)


def test_the_battery_shutdown_escalates_by_its_trigger_and_stays_on_the_watch(trial):
    user = trial["user"]
    rt05 = trial["ids"]["SAMPLE-RT-05"]
    _acknowledge(user)
    screen = user.get(_url(rt05)).json()
    assert screen["trigger_codes"] == ["NEW_FAILURE_MODE"] and screen["routine"]["offered"] is False
    fact = screen["triggers"][0]
    assert (
        fact["field"] == "problem_code"
        and fact["value"] == "BATTERY_SHUTDOWN"
        and "not recorded before" in fact["fact"]
    )
    assert screen["reportability"]["on_watch"] is True
    refused = _sign(user, rt05, "SERVICE_LEVEL", screen)
    assert refused.status_code == 422 and "trigger is met" in refused.json()["detail"]["message"]
    assert _sign(user, rt05, "KNOWN_ISSUE", screen, rationale=WHY).status_code == 422
    routine = _sign(user, rt05, "ESCALATED_BY_TRIGGER", {**screen, "routine": {"offered": True}}, rationale="x" * 12)
    assert routine.status_code == 409 and routine.json()["detail"]["code"] == "ROUTINE_NOT_OFFERED"
    signed = _sign(
        user,
        rt05,
        "ESCALATED_BY_TRIGGER",
        screen,
        rationale="Unexplained shutdown on battery of a respiratory controller; product investigation needed.",
        classification={"use_environment": "AMBULANCE", "user_type": "HEALTHCARE_PROFESSIONAL"},
    )
    assert signed.status_code == 200, signed.text
    body = signed.json()
    current = body["current"]
    assert current["branch"] == "ESCALATED_BY_TRIGGER" and current["triggers"][0]["code"] == "NEW_FAILURE_MODE"
    assert current["investigation_ref"] and current["answers"]["SERVICE_LEVEL"]["answer"] == "REFUSED"
    # The disposition never replaces the reportability assessment: its markets are still due.
    assert body["reportability"]["on_watch"] is True and body["reportability"]["settled"] is False
    case = user.get(f"/api/v1/investigations/{current['investigation_id']}/scope").json()
    assert [item["id"] for item in case["current"]["included_complaints"]] == [rt05]
    due = _readiness(user)["DISPOSITIONS_DUE"]
    assert due["escalated"] >= 1 and any("NEW_FAILURE_MODE" in item["label"] for item in due["items"])


def test_a_trigger_met_since_the_screen_opened_refuses_the_signature_and_one_met_after_signing_is_listed(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    _acknowledge(user)
    rv08 = trial["ids"]["SAMPLE-RV-08"]
    screen = user.get(_url(rv08)).json()
    assert "INJURY" in screen["trigger_codes"]
    late = _sign(
        user, rv08, "ESCALATED_BY_TRIGGER", {**screen, "trigger_codes": []}, rationale="Patient outcome unknown"
    )
    assert late.status_code == 409 and late.json()["detail"]["code"] == "TRIGGER_MET_SINCE_OPENED"
    assert {item["code"] for item in late.json()["detail"]["triggers"]} >= {"INJURY"}

    # RT-01 closed at service level; its record later shows a serious injury: a disposition to review.
    rt01 = trial["ids"]["SAMPLE-RT-01"]
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.get(Complaint, uuid.UUID(rt01)).serious_injury = True
        db.commit()
    due = _readiness(user)["DISPOSITIONS_DUE"]
    assert due["to_review"] >= 1 and due["state"] == "CRITICAL"
    assert any(item["id"] == rt01 and "after signing" in item["label"] for item in due["items"])


def test_another_organization_cannot_read_dispositions_and_removal_and_purge_cover_them(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    from tests.test_reporting_capa_api import _client, _organization

    other_id = _organization("DX")
    rt01 = trial["ids"]["SAMPLE-RT-01"]
    assert _client(other_id, "LEADER").get(_url(rt01)).status_code == 404
    if runtime_role_active():
        for tenant, expected in ((uuid.uuid4(), 0), (tenant_id, True)):
            runtime = RuntimeSessionLocal()
            try:
                bind_tenant(runtime, tenant)
                count = runtime.query(ComplaintDisposition).filter(ComplaintDisposition.tenant_id == tenant_id).count()
                assert (count > 0) == bool(expected)
            finally:
                runtime.close()
    story = user.get("/api/v1/trial/story").json()
    chapter = next(item for item in story["chapters"] if item["code"] == "ROUTINE_COMPLAINTS")
    assert chapter["number"] == 1 and chapter["acted"]["count"] >= 3  # RT-01 (twice), RT-02, RT-04, RT-05
    serious = next(item for item in story["chapters"] if item["code"] == "REPORTING_CLOCKS")
    assert serious["acted"]["count"] == 0  # the routine path's market conclusions count in chapter 1 only

    # The management review summary counts the dispositions by branch and the escalations by trigger.
    summary = user.get("/api/v1/readiness/summary").json()["dispositions"]
    assert summary["by_branch"]["KNOWN_ISSUE"] == 1 and summary["by_trigger"]["NEW_FAILURE_MODE"] == 1
    assert summary["by_branch"]["SERVICE_LEVEL"] >= 3 and summary["routine"] >= 2

    removed = user.post("/api/v1/trial/sample-data/removal", json={"confirm": True})
    assert removed.status_code == 200, removed.text
    assert "ROUTINE_COMPLAINTS" in removed.json()["chapters_kept"]
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        left = {
            row.complaint_id
            for row in db.query(ComplaintDisposition).filter(ComplaintDisposition.tenant_id == tenant_id)
        }
        own = {
            row.id
            for row in db.query(Complaint.id).filter(
                Complaint.tenant_id == tenant_id, Complaint.source_system == "TRIAL_UPLOAD"
            )
        }
        assert left <= own  # only work on the organization's own complaints stays
        assert (
            db.query(ComplaintClassification)
            .filter(ComplaintClassification.tenant_id == tenant_id, ComplaintClassification.source_system.isnot(None))
            .count()
            == 0
        )
        assert (
            db.query(SignedApprovalRecord)
            .filter(
                SignedApprovalRecord.tenant_id == tenant_id,
                SignedApprovalRecord.object_type == "ComplaintDisposition",
                SignedApprovalRecord.object_id.notin_([row.id for row in db.query(ComplaintDisposition.id)] or [None]),
            )
            .count()
            == 0
        )
        assert (
            db.query(Complaint)
            .filter(Complaint.complaint_identifier == "SAMPLE-RT-01", Complaint.tenant_id == tenant_id)
            .count()
            == 0
        )
    from backend.app.tenant_export import _tables
    from backend.app.trial.retention import TRIAL_DATA_TABLES

    with SessionLocal() as db:
        bind_system(db, "test: tables an export and the purge cover")
        assert "complaint_dispositions" in {table for _, table in _tables(db)}
    assert "complaint_dispositions" in TRIAL_DATA_TABLES


def test_an_organization_outside_a_trial_signs_without_the_practice_acknowledgement():
    from backend.app.trial.retention import purge_trial
    from tests.test_reporting_capa_api import PASSWORD as ORG_PASSWORD
    from tests.test_reporting_capa_api import _client, _complaint, _organization, _product

    tenant_id = _organization("DS")
    try:
        leader = _client(tenant_id, "LEADER", "Lee Leader")
        complaint = _complaint(tenant_id, _product(tenant_id), country="US", problem_code=None, patient_involved=False)
        screen = leader.get(_url(complaint)).json()
        assert screen["training_required"] is False and screen["practice_label"] is None
        assert screen["routine"]["offered"] is True
        signed = _sign(leader, complaint, "SERVICE_LEVEL", screen, password=ORG_PASSWORD)
        assert signed.status_code == 200, signed.text
        assert signed.json()["current"]["branch"] == "SERVICE_LEVEL"
        assert leader.get(f"{BOARD}?show=signed").json()["summary"]["signed"] == 1
        viewer = _client(tenant_id, "VIEWER")
        assert _sign(viewer, complaint, "SERVICE_LEVEL", screen, password=ORG_PASSWORD).status_code == 403
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:disposition-org-cleanup")
