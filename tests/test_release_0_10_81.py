"""0.10.81: the Critical, High and Medium findings of the functional review of 0.10.79.

- F1: re-signing a market conclusion with another report type moves the open report with it (type, due date,
  provisional flag), audited; a submitted report is never changed, only flagged.
- F10: an imported blank received date stays blank; the clock counts from the event date, named so.
- F3, F4, F9: a missing country or awareness date is asked for, provisional, and blocks signing; contradictory
  import rows are flagged.
- F6: report fields take dates and codes only; a bad stored value is flagged.
- F12: the EU and GB MIR forms never pre-fill 1.2d or 3.2c.
- F7: report fields, product identity, registrations and responsible parties are audited before and after.
- F11: a cancelled report reads Cancelled, not MET; a reopened one drops its cancellation note (kept in the audit).
- Security F3: a download named in any script answers with an ASCII name and the UTF-8 one.
- F5: every trial has every market's starter windows (new ones at approval, running ones through the refresh), so a
  Great Britain or Canada complaint gets its market assessment and clock.
"""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.models.foundation import AuditEvent
from backend.app.db.session import SessionLocal
from tests.test_flagship_walkthrough import _answers_from_record
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_market_assessment_api import _save, _sign
from tests.test_release_c3_0_10_75 import _flagship, _purge, _reports
from tests.test_sample_story_days import FLAGSHIP_US

pytestmark = pytest.mark.db

REPORTS = "/api/v1/reports"


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


def _audit(tenant_id, action: str) -> list[AuditEvent]:
    with SessionLocal() as db:
        return (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == action)
            .order_by(AuditEvent.created_at)
            .all()
        )


@pytest.fixture(scope="module")
def trial():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    complaint = _flagship(user)
    try:
        yield {"user": user, "tenant_id": tenant_id, "complaint": complaint}
    finally:
        _purge(tenant_id)


def _sign_us(user, complaint, remedial: str):
    detail = _ok(user.get(f"/api/v1/complaints/{complaint}/market-assessments"))
    answers, _ = _answers_from_record(detail, "US", {**FLAGSHIP_US, "US6": remedial})
    saved = _save(user, complaint, "US", answers, harm_level=detail["severity_level"])
    signed = _ok(_sign(user, complaint, "US", saved, "REPORTABLE", password=PASSWORD))
    return next(item for item in signed["markets"] if item["market"] == "US")["current"]


def test_f1_a_re_signed_shorter_report_type_moves_the_open_report_and_a_submitted_one_is_only_flagged(trial):
    user, complaint, tenant_id = trial["user"], trial["complaint"], trial["tenant_id"]
    first = _sign_us(user, complaint, "NO")
    (report,) = _reports(user, complaint)
    assert report["due_on"] == first["due_on"]
    # Remedial action needed: the 5-work-day report (21 CFR 803.53), due earlier.
    second = _sign_us(user, complaint, "YES")
    assert second["due_on"] < first["due_on"]
    detail = _ok(user.get(f"{REPORTS}/{report['id']}"))
    assert (detail["report_type"], detail["deadline"]["due_on"], detail["deadline"]["provisional"]) == (
        "US_5_WORK_DAY",
        second["due_on"],
        False,
    )
    assert detail["assessment"]["version"] == second["version"] and detail["conclusion_changed"] is None
    (event,) = _audit(tenant_id, "REPORT_RETYPED_BY_CONCLUSION")
    assert event.old_values == {"report_type": "US_30_DAY", "due_on": first["due_on"], "provisional": False}
    assert event.new_values == {"report_type": "US_5_WORK_DAY", "due_on": second["due_on"], "provisional": False}
    # Submitted: a later conclusion never changes it; it is flagged so a follow-up report can be considered.
    from backend.app.db.models.authority_reports import ReportObligation
    from backend.app.db.tenant_scope import bind_tenant

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.get(ReportObligation, uuid.UUID(report["id"])).state = "SUBMITTED_PENDING"
        db.commit()
    _sign_us(user, complaint, "NO")
    detail = _ok(user.get(f"{REPORTS}/{report['id']}"))
    assert (detail["report_type"], detail["deadline"]["due_on"]) == ("US_5_WORK_DAY", second["due_on"])
    assert "consider a follow-up report" in detail["conclusion_changed"]
    (flagged,) = _audit(tenant_id, "REPORT_CONCLUSION_CHANGED_AFTER_SUBMISSION")
    assert flagged.old_values["report_type"] == "US_5_WORK_DAY" and flagged.new_values["report_type"] == "US_30_DAY"


def _import(user, csv: str) -> dict:
    return _ok(user.post("/api/v1/trial/imports/complaints", params={"on_problems": "skip"}, content=csv.encode()))


def _watch(user, identifier: str) -> dict:
    items = _ok(user.get("/api/v1/complaints/reportability", params={"show": "all", "page_size": 200}))["items"]
    return next(item for item in items if item["complaint_identifier"] == identifier)


def test_f5_a_great_britain_or_canada_complaint_gets_its_assessment_and_clock_and_the_refresh_adds_the_windows(trial):
    from backend.app.db.models.reportability import ReportabilitySettings
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.reportability import rules
    from backend.app.trial import open_deadlines

    user, tenant_id = trial["user"], trial["tenant_id"]
    old = [0, 1, 2, len(rules.TEMPLATES) - 1]  # 0.10.80's trial windows: FDA, EU 15 and 10, India
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = db.query(ReportabilitySettings).filter(ReportabilitySettings.tenant_id == tenant_id).one()
        assert len(row.windows) == 8  # a new trial has every market's
        row.windows = [rules.clean_window(rules.TEMPLATES[index]) for index in old]
        db.commit()
        dry = open_deadlines.refresh(db, tenant_id, apply=False)
        assert len(dry) == 1 and "MHRA" in dry[0] and "Health Canada" in dry[0]
        assert open_deadlines.refresh(db, tenant_id, apply=True)[0].startswith("added")
        db.commit()
        assert open_deadlines.refresh(db, tenant_id, apply=False) == []
    _import(
        user,
        "complaint_id,product_id,description,event_date,received_date,awareness_date,country,patient_involved,"
        "serious_injury,death,malfunction\n"
        "F5-GB-1,F5-PUMP,Patient died; pump free-flowed.,2026-11-01,2026-11-02,2026-11-02,GB,Y,N,Y,Y\n"
        "F5-CA-1,F5-PUMP,Patient injured; pump over-infused.,2026-11-01,2026-11-02,2026-11-02,Canada,Y,Y,N,Y\n",
    )
    for identifier, market in (("F5-GB-1", "GB"), ("F5-CA-1", "CA")):
        item = _watch(user, identifier)
        assert item["state"] != "NO_WINDOW" and item["clocks"], identifier
        assert [entry["market"] for entry in item["markets"]] == [market]
        detail = _ok(user.get(f"/api/v1/complaints/{item['id']}/market-assessments"))
        assert market in detail["enabled_markets"]


def test_f10_a_blank_received_date_stays_blank_and_the_event_date_is_named_as_such(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    _import(
        user,
        "complaint_id,product_id,description,event_date,received_date,awareness_date,country,patient_involved,"
        "serious_injury,death,malfunction\n"
        "F10-1,F10-PUMP,Pump alarm failed; no harm.,2026-10-20,,,US,N,N,N,Y\n",
    )
    from backend.app.db.models.foundation import Complaint
    from backend.app.db.tenant_scope import bind_tenant

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = db.query(Complaint).filter(Complaint.complaint_identifier == "F10-1").one()
        assert row.complaint_timestamp is None and row.event_timestamp is not None
    item = _watch(user, "F10-1")
    # Still the conservative start (the event day), but named as the event date, never "received".
    assert (item["aware_source"], item["aware_date"]) == ("EVENT_DATE", "2026-10-20")
    assert item["received_date"] is None


FACTS_CSV = (
    "complaint_id,product_id,description,event_date,received_date,awareness_date,country,patient_involved,"
    "serious_injury,death,malfunction\n"
    "F3-1,F3-PUMP,Patient died; pump free-flowed.,2026-10-01,2026-10-02,2026-10-02,,Y,N,Y,Y\n"
    "F3-2,F3-PUMP,Patient died; pump free-flowed.,2026-10-01,2026-10-02,2026-10-02,Atlantis,Y,N,Y,Y\n"
    "F4-1,F3-PUMP,Patient died in Ohio; pump free-flowed. Reported to us in August.,,,,US,Y,N,Y,Y\n"
    "F9-1,F3-PUMP,Alarm failed.,2026-10-26,,2026-09-01,US,N,N,N,Y\n"
    "F9-2,F3-PUMP,Patient injured.,2026-10-20,2026-10-21,2026-10-21,US,N,Y,N,Y\n"
    "F9-3,F3-PUMP,Short row\n"
)


def _facts(user, complaint_id: str, **body):
    return user.put(f"/api/v1/complaints/{complaint_id}/reporting-facts", json=body)


def test_f3_f4_f9_a_missing_country_or_awareness_date_is_asked_for_and_blocks_signing(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    check = _ok(user.post("/api/v1/trial/imports/complaints/check", params={"on_problems": "skip"}, content=FACTS_CSV))
    flags = {flag["complaint_id"] or flag["row"]: flag["message"] for flag in check["row_flags"]}
    # F9: flagged in the check, never refused.
    assert "No country" in flags["F3-1"] and '"Atlantis" is not a country' in flags["F3-2"]
    assert "No awareness or received date" in flags["F4-1"]
    assert "before the event date" in flags["F9-1"] and "no patient involved" in flags["F9-2"]
    assert "Has 3 of the header's 11 columns" in flags["F9-3"]
    imported = _import(user, FACTS_CSV)
    assert imported["quality_report"]["row_flags"] == check["row_flags"]

    for identifier in ("F3-1", "F3-2"):
        item = _watch(user, identifier)
        # F3: asked for, with every market's provisional clock meanwhile (never "No window applies").
        assert [need["fact"] for need in item["needs"]] == ["COUNTRY"] and item["provisional"]
        assert item["state"] != "NO_WINDOW" and item["clocks"]
    late = _watch(user, "F4-1")
    # F4: the import time is never a real deadline: provisional, and the awareness date is asked for.
    assert [need["fact"] for need in late["needs"]] == ["AWARENESS_DATE"] and late["provisional"]
    assert late["aware_source"] == "RECORDED_DATE"

    # Home (Oversight) shows it as needing the fact; its checklist asks instead of "No market to assess" (U-01).
    items = _ok(user.get("/api/v1/oversight", params={"show": "all"}))["items"]
    needing = {item["key"]: item["title"] for item in items if item["key"].endswith(":facts")}
    assert any(title.startswith("Enter the incident country") for title in needing.values())
    assert any(title.startswith("Enter the awareness date") for title in needing.values())
    event = _ok(user.get("/api/v1/oversight/events/F3-1"))
    (markets_check,) = [check for check in event["checklist"] if check["code"] == "MARKETS"]
    assert markets_check["result"] == "BLOCKED" and "Enter the incident country" in markets_check["detail"]
    assert event["event"]["needs"][0]["fact"] == "COUNTRY"

    # No market conclusion is signed until the fact is entered.
    no_country = _watch(user, "F3-1")["id"]
    refused = user.post(
        f"/api/v1/complaints/{no_country}/market-assessments/US/sign",
        json={"conclusion": "REPORTABLE", "version": 1, "saved_at": "2026-11-03T00:00:00+00:00", "password": PASSWORD},
    )
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "FACT_NEEDED"
    assert _facts(user, no_country, country="Atlantis").status_code == 422
    _ok(_facts(user, no_country, country="GB"))
    entered = _watch(user, "F3-1")
    assert entered["needs"] == [] and [market["market"] for market in entered["markets"]] == ["GB"]
    (event_row,) = [
        row for row in _audit(tenant_id, "COMPLAINT_REPORTING_FACTS_SET") if row.entity_id == uuid.UUID(no_country)
    ]
    assert (event_row.old_values, event_row.new_values) == ({"country": None}, {"country": "GB"})

    unaware = late["id"]
    assert _facts(user, unaware, awareness_date="2999-01-01").status_code == 422
    _ok(_facts(user, unaware, awareness_date="2026-08-14"))
    known = _watch(user, "F4-1")
    assert known["needs"] == [] and not known["provisional"]
    assert (known["aware_source"], known["aware_date"]) == ("AWARENESS_DATE", "2026-08-14")


def test_f6_report_fields_take_dates_and_codes_only_and_a_bad_stored_value_is_flagged(trial):
    from backend.app.db.models.authority_reports import ReportObligation
    from backend.app.db.tenant_scope import bind_tenant
    from tests.code_lists import ensure_loaded

    ensure_loaded()
    user, complaint, tenant_id = trial["user"], trial["complaint"], trial["tenant_id"]
    (report,) = _reports(user, complaint)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = db.get(ReportObligation, uuid.UUID(report["id"]))
        # A draft again, holding a value typed before 0.10.81 into a date field.
        row.state = "DRAFT"
        row.entries = {**(row.entries or {}), "B4": {"value": "next tuesday", "by": "test", "at": "2026-11-03"}}
        db.commit()
    path = f"{REPORTS}/{report['id']}/fields"
    detail = _ok(user.get(f"{REPORTS}/{report['id']}"))
    b4 = next(item for section in detail["sections"] for item in section["fields"] if item["id"] == "B4")
    # Flagged, not deleted, and counted as missing.
    assert (b4["value"], b4["kind"], b4["problem"]) == ("next tuesday", "DATE", "Enter a date as YYYY-MM-DD")
    assert "B4" in detail["mandatory"]["missing"]
    for field, value, code in (
        ("B4", "next tuesday", "NOT_A_DATE"),
        ("H6_CLINICAL", "headache, probably", "NOT_A_IMDRF_CODE"),
        ("G8", "1234567-2026-00011", "FOLLOWS_FRONT_PAGE"),
        ("D2A", "ZZ1", "NOT_A_LIST_CODE"),
        ("D2A", "ZZZ", "CODE_UNKNOWN"),
    ):
        refused = user.put(f"{path}/{field}", json={"value": value})
        assert refused.status_code == 422 and refused.json()["detail"]["code"] == code, (field, refused.text)
    detail = _ok(user.put(f"{path}/B4", json={"value": "2026-11-03"}))
    assert "B4" not in detail["mandatory"]["missing"]
    assert _ok(user.put(f"{path}/D2A", json={"value": "frn"}))["sections"]


def test_f12_the_mir_forms_never_pre_fill_the_reportability_date_or_the_device_location(trial):
    user = trial["user"]
    (eu,) = [item for item in _ok(user.get(REPORTS))["items"] if item["complaint_ref"] == "SAMPLE-RV-07" and item["id"]]
    detail = _ok(user.get(f"{REPORTS}/{eu['id']}"))
    fields = {item["id"]: item for section in detail["sections"] for item in section["fields"]}
    # 1.2d is the day the information showing reportability arrived, not the signing day; 3.2c is where it is now.
    assert fields["1_2D"]["value"] is None and fields["1_2D"]["source"] is None and fields["1_2D"]["note"]
    assert fields["3_2C"]["value"] is None and fields["3_2C"]["status"] == "MUST_HAVE"
    assert "3_2C" in detail["mandatory"]["missing"]


def test_f7_report_fields_product_identity_registrations_and_parties_are_audited_before_and_after(trial):
    from backend.app.db.models.foundation import Product
    from backend.app.db.tenant_scope import bind_tenant

    user, complaint, tenant_id = trial["user"], trial["complaint"], trial["tenant_id"]
    (report,) = _reports(user, complaint)
    from backend.app.db.models.authority_reports import ReportObligation

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.get(ReportObligation, uuid.UUID(report["id"])).state = "DRAFT"
        db.commit()
    path = f"{REPORTS}/{report['id']}/fields/B4"
    _ok(user.put(path, json={"value": "2026-11-02"}))
    _ok(user.put(path, json={"value": "2026-11-04"}))
    changed = _audit(tenant_id, "REPORT_FIELD_SET")[-1]
    assert changed.old_values == {"B4": {"value": "2026-11-02"}} and changed.new_values == {
        "B4": {"value": "2026-11-04"}
    }

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        product = db.query(Product).filter(Product.tenant_id == tenant_id).order_by(Product.created_at).first()
        product_id, udi = str(product.id), product.udi_di
    reference = "/api/v1/regulatory-reference"
    _ok(user.put(f"{reference}/products/{product_id}/identity", json={"udi_di": "00812345678918"}))
    (identity,) = [event for event in _audit(tenant_id, "PRODUCT_IDENTITY_SET")][-1:]
    assert identity.old_values["udi_di"] == udi and identity.new_values["udi_di"] == "00812345678918"
    added = _ok(
        user.post(
            f"{reference}/products/{product_id}/registrations",
            json={"market": "US", "registration_type": "510K", "registration_number": "K260001", "product_code": "FRN"},
        )
    )
    assert user.delete(f"{reference}/products/{product_id}/registrations/{added['id']}").status_code == 204
    (removed,) = _audit(tenant_id, "PRODUCT_REGISTRATION_REMOVED")[-1:]
    assert removed.old_values["registration_number"] == "K260001" and removed.new_values is None
    party = _ok(
        user.put(
            f"{reference}/responsible-parties",
            json={"market": "US", "role": "MANUFACTURER", "organisation": "F7 Devices"},
        )
    )
    assert user.delete(f"{reference}/responsible-parties/{party['id']}").status_code == 204
    (gone,) = _audit(tenant_id, "RESPONSIBLE_PARTY_REMOVED")[-1:]
    assert gone.old_values["organisation"] == "F7 Devices"


def test_f11_a_cancelled_report_reads_cancelled_and_a_reopened_one_drops_its_cancellation_note(trial):
    from backend.app.db.models.authority_reports import ReportObligation
    from backend.app.db.tenant_scope import bind_tenant

    user, complaint, tenant_id = trial["user"], trial["complaint"], trial["tenant_id"]
    _sign_us(user, complaint, "NO")  # its report, whichever tests ran before
    (report,) = _reports(user, complaint)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.get(ReportObligation, uuid.UUID(report["id"])).state = "DRAFT"
        db.commit()
    detail = _ok(user.get(f"/api/v1/complaints/{complaint}/market-assessments"))
    answers, _ = _answers_from_record(detail, "US", FLAGSHIP_US)
    answers["US5"] = {**answers["US5"], "answer": "NO", "rationale": "Test: the reading error cannot recur unseen."}
    saved = _save(user, complaint, "US", answers, harm_level=detail["severity_level"])
    _ok(_sign(user, complaint, "US", saved, "NOT_REPORTABLE", password=PASSWORD))
    cancelled = _ok(user.get(f"{REPORTS}/{report['id']}"))
    assert cancelled["state"] == "CANCELLED" and cancelled["deadline"]["due_state"] == "CANCELLED"
    assert not cancelled["deadline"]["overdue"]
    listed = next(item for item in _reports(user, complaint) if item["id"] == report["id"])
    assert listed["due_state"] == "CANCELLED"
    note = cancelled["note"]
    assert "says not reportable" in note
    _sign_us(user, complaint, "NO")
    reopened = _ok(user.get(f"{REPORTS}/{report['id']}"))
    assert reopened["state"] == "DRAFT" and reopened["note"] is None and reopened["cancelled_reason"] is None
    (event,) = _audit(tenant_id, "REPORT_REOPENED_BY_CONCLUSION")[-1:]
    assert event.old_values == {"state": "CANCELLED", "note": note} and event.new_values["note"] is None


def test_security_f3_a_download_named_in_any_script_answers_with_both_names(trial):
    from backend.app.db.models.authority_reports import ReportEvidence, ReportSubmission
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.downloads import attachment

    assert attachment("report.pdf") == 'attachment; filename="report.pdf"'
    assert attachment("../a\b/Receipt – दस्तावेज़.txt") == (
        "attachment; filename=\"Receipt .txt\"; filename*=UTF-8''Receipt%20%E2%80%93%20"
        "%E0%A4%A6%E0%A4%B8%E0%A5%8D%E0%A4%A4%E0%A4%BE%E0%A4%B5%E0%A5%87%E0%A4%9C%E0%A4%BC.txt"
    )
    assert attachment('"\r\n') == 'attachment; filename="download"'
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        row = (
            db.query(ReportEvidence)
            .filter(ReportEvidence.tenant_id == trial["tenant_id"], ReportEvidence.content.isnot(None))
            .first()
        )
        submission = db.get(ReportSubmission, row.submission_id)
        row.file_name = "Acknowledgement – India.txt"
        db.commit()
        path = f"{REPORTS}/{submission.obligation_id}/submissions/{submission.id}/evidence/{row.id}/file"
    answer = trial["user"].get(path)
    assert answer.status_code == 200
    assert answer.headers["content-disposition"].endswith("filename*=UTF-8''Acknowledgement%20%E2%80%93%20India.txt")
