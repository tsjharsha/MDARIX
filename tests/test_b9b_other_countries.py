"""B9b steps 3-6 (OC-01..OC-20): a country outside the five markets, its signed conclusion and its Other Regulatory
Report (attach-only), through the API as a person uses it."""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.app.db.models.foundation import SignedApprovalRecord
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_reporting_capa_api import (
    PASSWORD,
    REASON,
    SETTINGS,
    _actions,
    _client,
    _complaint,
    _organization,
    _product,
)

# B6b B3: scenarios this file verifies (its register row names it, or it is the group's own test file).
pytestmark = [pytest.mark.db, pytest.mark.requirement("OC-03", "OC-04", "OC-09", "OC-12", "OC-19")]

WHY = "Read from the complaint record and the distributor's report"
REPORTS = "/api/v1/reports"
REPORTABLE = dict(OT1="NO", OT2="YES", OT3="NO", OT4="NO", OT5="YES", OT6="NO", OT7="YES")
NONE = dict(OT1="NO", OT2="NO", OT3="NO", OT4="NO", OT5="NO", OT6="NO", OT7="YES")
WINDOW = {
    "name": "TGA serious threat to health (30 days, starter)",
    "markets": ["AU"],
    "triggers": ["DEATH", "SERIOUS_INJURY", "MALFUNCTION"],
    "days": 30,
    "day_basis": "CALENDAR",
    "note": "Our procedure QP-08, for our consultant to confirm.",
    "basis": [],
}


def _answers(values: dict) -> dict:
    return {
        key: {"answer": value, "rationale": WHY, "evidence": ["Complaint description"]} for key, value in values.items()
    }


@pytest.fixture(scope="module")
def org():
    from backend.app.trial.retention import purge_trial

    tenant_id, other_id = _organization("OCA"), _organization("OCB")
    clients = {
        "regulatory": _client(tenant_id, "REGULATORY_REVIEWER", "Rita Regulatory"),
        "viewer": _client(tenant_id, "VIEWER"),
        "other": _client(other_id, "REGULATORY_REVIEWER"),
    }
    settings = clients["regulatory"].get(SETTINGS).json()
    saved = clients["regulatory"].put(
        SETTINGS, json={"windows": [*settings["templates"][:3], WINDOW], "lookback_days": 365, "reason": REASON}
    )
    assert saved.status_code == 200, saved.text
    try:
        yield {"tenant_id": tenant_id, "other_id": other_id, "product": _product(tenant_id), **clients}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:b9b-cleanup")
            purge_trial(db, other_id, "test:b9b-cleanup")


def _url(complaint_id: str, country: str, tail: str = "") -> str:
    return f"/api/v1/complaints/{complaint_id}/market-assessments/OTHER-{country}{tail}"


def _item(detail: dict, country: str) -> dict:
    return next(item for item in detail["other_countries"] if item["country"] == country)


def _save(client, complaint_id: str, country: str, values: dict) -> dict:
    saved = client.put(_url(complaint_id, country), json={"answers": _answers(values)})
    assert saved.status_code == 200, saved.text
    return _item(saved.json(), country)


def _sign(client, complaint_id: str, country: str, item: dict, conclusion: str, **extra):
    draft = item["draft"]
    body = {"conclusion": conclusion, "version": draft["version"], "saved_at": draft["saved_at"], "password": PASSWORD}
    body["change_reason"] = "New information from the distributor changes the answers."
    return client.post(_url(complaint_id, country, "/sign"), json={**body, **extra})


def _reportable(org, country: str = "AU", **fields) -> tuple[str, dict]:
    complaint = _complaint(org["tenant_id"], org["product"], country="Australia", malfunction=True, **fields)
    item = _save(org["regulatory"], complaint, country, REPORTABLE)
    signed = _sign(org["regulatory"], complaint, country, item, "REPORTABLE")
    assert signed.status_code == 200, signed.text
    return complaint, _item(signed.json(), country)


def _report(client, complaint_id: str, country: str = "AU") -> dict:
    listed = client.get(REPORTS, params={"complaint_id": complaint_id})
    assert listed.status_code == 200, listed.text
    rows = [row for row in listed.json()["items"] if row["country"] == country and row["kind"] == "INITIAL"]
    assert len(rows) == 1, rows
    return rows[0]


def _file(text: str = "%PDF-1.4 our report to the TGA") -> dict:
    return {"name": "report.pdf", "content_type": "application/pdf", "data": base64.b64encode(text.encode()).decode()}


def _submit(client, obligation_id: str, **extra):
    body = {
        "submitted_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        "report_id": "TGA-2026-0042",
        "file": _file(),
        "password": PASSWORD,
        **extra,
    }
    return client.post(f"{REPORTS}/{obligation_id}/attached-submission", json=body)


def test_the_picker_offers_countries_outside_the_five_and_sends_the_others_to_their_tree(org):
    """OC-01, OC-20."""
    picked = org["regulatory"].get("/api/v1/other-countries")
    assert picked.status_code == 200, picked.text
    codes = {item["code"] for item in picked.json()["countries"]}
    assert {"AU", "CH", "JP", "BR"} <= codes
    assert not codes & {"US", "CA", "IN", "GB", "FR", "DE", "IE", "NO", "IS", "LI", "GF", "RE", "AX", "MF"}
    sent = {item["code"]: item["message"] for item in picked.json()["not_offered"]}
    assert sent["GF"] == sent["AX"] == "This may fall under the EU MDR: check with your consultant"
    complaint = _complaint(org["tenant_id"], org["product"], country="France", malfunction=True)
    for code, market in (("FR", "EU_NI"), ("NO", "EU_NI"), ("GB", "GB"), ("US", "US"), ("IN", "IN")):
        moved = org["regulatory"].put(_url(complaint, code), json={"answers": {}})
        assert moved.status_code == 422 and moved.json()["detail"]["code"] == "COUNTRY_HAS_ITS_OWN_TREE", code
        assert moved.json()["detail"]["market"] == market
    outermost = org["regulatory"].put(_url(complaint, "RE"), json={"answers": {}})
    assert outermost.status_code == 422 and "EU MDR" in outermost.json()["detail"]["message"]
    assert org["regulatory"].put(_url(complaint, "ZZ"), json={"answers": {}}).status_code == 404


def test_unknown_stays_pending_and_reportable_creates_one_report_with_the_floor_signed(org):
    """OC-02, OC-03, OC-16; the signed material names OTHER-floor-1 and the generic-starter note."""
    regulatory = org["regulatory"]
    complaint = _complaint(org["tenant_id"], org["product"], country="Australia", malfunction=True)
    pending = _save(regulatory, complaint, "CH", {**NONE, "OT1": "UNKNOWN"})
    assert pending["evaluation"]["suggested"] == "PENDING_INFORMATION"
    refused = _sign(regulatory, complaint, "CH", pending, "NOT_REPORTABLE")
    assert refused.status_code == 422, refused.text
    item = _save(regulatory, complaint, "AU", REPORTABLE)
    assert item["evaluation"]["suggested"] == "REPORTABLE" and item["label"] == "Australia (other country)"
    assert any("not this country's law" in note for note in item["evaluation"]["notes"])
    signed = _sign(regulatory, complaint, "AU", item, "REPORTABLE")
    assert signed.status_code == 200, signed.text
    current = _item(signed.json(), "AU")["current"]
    assert current["conclusion"] == "REPORTABLE" and current["floor_code"] == "OTHER-floor-1"
    with SessionLocal() as db:
        bind_system(db, "test: the signature")
        record = db.get(SignedApprovalRecord, uuid.UUID(current["signed_record_id"]))
        assert "Australia" in record.signature_meaning and "not this country's law" in record.signature_meaning
    # The five markets never list the country; the Reports list does, once (OC-02), as "To be submitted".
    assert all(market["market"] != "OTHER" for market in signed.json()["markets"])
    report = _report(regulatory, complaint)
    assert report["form_title"] == "Other Regulatory Report" and report["state_label"] == "To be submitted"
    assert report["market_label"] == "Australia (other country)"
    # A second country on the same complaint, side by side.
    swiss = _save(regulatory, complaint, "CH", REPORTABLE)
    assert _sign(regulatory, complaint, "CH", swiss, "REPORTABLE").status_code == 200
    assert _report(regulatory, complaint, "CH")["id"] != report["id"]


def test_the_window_naming_the_country_gives_the_due_date_else_the_customer_enters_it(org):
    """OC-10, OC-11."""
    complaint, item = _reportable(org)
    assert item["current"]["window_name"] == WINDOW["name"] and item["current"]["due_on"]
    report = _report(org["regulatory"], complaint)
    assert report["due_on"] == item["current"]["due_on"]
    detail = org["regulatory"].get(f"{REPORTS}/{report['id']}").json()
    assert detail["due_source_label"] == "Your reporting window" and detail["banner"].startswith("Report prepared")
    assert (
        org["regulatory"]
        .put(f"{REPORTS}/{report['id']}/attached-due-date", json={"due_on": "2026-12-01", "reason": REASON})
        .json()["detail"]["code"]
        == "WINDOW_DUE_DATE"
    )
    # Japan: no window names it, so the person enters the date; an overdue one is listed as overdue.
    japan = _complaint(org["tenant_id"], org["product"], country="Japan", malfunction=True)
    signed = _sign(org["regulatory"], japan, "JP", _save(org["regulatory"], japan, "JP", REPORTABLE), "REPORTABLE")
    assert _item(signed.json(), "JP")["current"]["due_on"] is None
    report = _report(org["regulatory"], japan, "JP")
    assert report["due_on"] is None
    short = org["regulatory"].put(
        f"{REPORTS}/{report['id']}/attached-due-date", json={"due_on": "2026-01-02", "reason": "x"}
    )
    assert short.status_code == 422
    entered = org["regulatory"].put(
        f"{REPORTS}/{report['id']}/attached-due-date",
        json={"due_on": (date.today() - timedelta(days=2)).isoformat(), "reason": REASON},
    )
    assert entered.status_code == 200, entered.text
    assert entered.json()["due_source_label"] == "Due date entered by the customer"
    assert _report(org["regulatory"], japan, "JP")["overdue"] is True
    assert "REPORT_DUE_DATE_ENTERED" in _actions(org["tenant_id"], report["id"])


def test_submitted_needs_a_file_a_date_a_report_id_or_not_issued_and_the_recorders_signature(org, monkeypatch):
    """OC-04, OC-05, OC-12, OC-13, OC-19; OC-D3: no second person."""
    complaint, _ = _reportable(org)
    regulatory, report = org["regulatory"], _report(org["regulatory"], complaint)
    assert _submit(regulatory, report["id"], file=None).json()["detail"]["code"] == "FILE_REQUIRED"
    assert _submit(regulatory, report["id"], report_id="").json()["detail"]["code"] == "REPORT_ID_NEEDED"
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert _submit(regulatory, report["id"], submitted_at=future).json()["detail"]["code"] == "SUBMITTED_TIME"
    wrong = _submit(regulatory, report["id"], password="not the password")
    assert wrong.status_code in (401, 403) and _report(regulatory, complaint)["state"] == "DRAFT"
    from object_storage.service import ObjectStorageService

    monkeypatch.setattr(ObjectStorageService, "scan", lambda self, data, content_type: False)
    infected = _submit(regulatory, report["id"])
    assert infected.json()["detail"]["code"] == "MALWARE_SCAN_REJECTED"
    monkeypatch.undo()
    # The approval route of the built-in forms is not this report's (OC-D3).
    assert regulatory.post(f"{REPORTS}/{report['id']}/snapshots", json={}).json()["detail"]["code"] == (
        "ATTACHED_NO_APPROVAL"
    )
    done = _submit(regulatory, report["id"], report_id="", not_issued_yet=True)
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["state_label"] == "Submitted" and body["submissions"][0]["report_id"] == "Not issued yet"
    content = body["submissions"][0]["evidence"][0]
    assert content["sha256"] == hashlib.sha256(b"%PDF-1.4 our report to the TGA").hexdigest()
    with SessionLocal() as db:
        bind_system(db, "test: the submission signature")
        record = db.get(SignedApprovalRecord, uuid.UUID(body["submissions"][0]["signature_id"]))
        assert record.decision_type == "ATTACHED_REPORT_SUBMITTED"
        assert record.signature_meaning.startswith(
            "I recorded that this report was submitted to the authority of Australia"
        )
    assert _submit(regulatory, report["id"]).json()["detail"]["code"] == "NOT_SUBMITTABLE"
    submission = body["submissions"][0]["id"]
    later = regulatory.put(
        f"{REPORTS}/{report['id']}/attached-report-id", json={"submission_id": submission, "report_id": "TGA-77"}
    )
    assert later.status_code == 200 and later.json()["submissions"][0]["report_id"] == "TGA-77"
    again = regulatory.put(
        f"{REPORTS}/{report['id']}/attached-report-id", json={"submission_id": submission, "report_id": "TGA-78"}
    )
    assert again.json()["detail"]["code"] == "REPORT_ID_RECORDED"
    # A second file is a new piece of evidence: the first stays (OC-12).
    extra = regulatory.post(
        f"{REPORTS}/{report['id']}/submissions/{submission}/evidence",
        json={
            "kind": "OTHER",
            "outcome": "RECEIPT",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "file": _file("a corrected copy"),
        },
    )
    assert extra.status_code == 200, extra.text
    assert len(extra.json()["submissions"][0]["evidence"]) == 2
    actions = _actions(org["tenant_id"], report["id"])
    assert {"REPORT_ATTACHED_SUBMITTED", "REPORT_ID_ENTERED", "REPORT_EVIDENCE_RECORDED"} <= set(actions)


def test_acknowledgement_follow_ups_and_close(org):
    """OC-06, OC-07, OC-08, OC-09."""
    complaint, _ = _reportable(org)
    regulatory, report = org["regulatory"], _report(org["regulatory"], complaint)
    follow = regulatory.post(f"{REPORTS}/{report['id']}/attached-follow-ups", json={"reason": REASON})
    assert follow.json()["detail"]["code"] == "NOT_SUBMITTED"
    submission = _submit(regulatory, report["id"]).json()["submissions"][0]["id"]
    acknowledged = regulatory.post(
        f"{REPORTS}/{report['id']}/submissions/{submission}/evidence",
        json={
            "kind": "ACCEPTANCE",
            "outcome": "ACCEPTED",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "file": _file("TGA acknowledgement"),
            "authority_reference": "ACK-1",
        },
    )
    assert acknowledged.status_code == 200 and acknowledged.json()["state_label"] == "Acknowledged"
    first = regulatory.post(f"{REPORTS}/{report['id']}/attached-follow-ups", json={"reason": REASON})
    second = regulatory.post(f"{REPORTS}/{report['id']}/attached-follow-ups", json={"reason": REASON})
    assert first.status_code == second.status_code == 200, first.text
    assert first.json()["parent"]["id"] == report["id"] and first.json()["state_label"] == "To be submitted"
    parent = regulatory.get(f"{REPORTS}/{report['id']}").json()
    assert parent["state_label"] == "Follow-up required" and len(parent["follow_ups"]) == 2
    close = regulatory.post(f"{REPORTS}/{report['id']}/complete", json={"reason": REASON})
    assert close.json()["detail"]["code"] == "FOLLOW_UP_OPEN"
    for child in (first.json(), second.json()):
        done = _submit(regulatory, child["id"], report_id=f"TGA-FU-{child['id'][:4]}")
        assert done.status_code == 200, done.text
        assert regulatory.post(f"{REPORTS}/{child['id']}/complete", json={"reason": REASON}).status_code == 200
    closed = regulatory.post(f"{REPORTS}/{report['id']}/complete", json={"reason": REASON})
    assert closed.status_code == 200 and closed.json()["state_label"] == "Closed"


def test_not_reportable_later_cancels_a_report_not_yet_submitted(org):
    complaint, item = _reportable(org)
    regulatory = org["regulatory"]
    draft = _save(regulatory, complaint, "AU", NONE)
    resigned = _sign(regulatory, complaint, "AU", draft, "NOT_REPORTABLE")
    assert resigned.status_code == 200, resigned.text
    assert _report(regulatory, complaint)["state"] == "CANCELLED"


def test_another_organization_and_a_viewer_cannot_see_or_change_it(org):
    """OC-14."""
    complaint, _ = _reportable(org)
    report = _report(org["regulatory"], complaint)
    assert org["other"].get(f"{REPORTS}/{report['id']}").status_code == 404
    assert _submit(org["other"], report["id"]).status_code == 404
    assert org["other"].put(_url(complaint, "AU"), json={"answers": {}}).status_code == 404
    assert _submit(org["viewer"], report["id"]).status_code == 403
    assert org["viewer"].put(_url(complaint, "AU"), json={"answers": {}}).status_code == 403


def test_the_switch_off_hides_the_picker_and_routes_and_keeps_records_readable(org, monkeypatch):
    """OC-17."""
    complaint, _ = _reportable(org)
    report = _report(org["regulatory"], complaint)
    monkeypatch.setenv("MDARIX_B9B_OTHER", "off")
    assert org["regulatory"].get("/api/v1/other-countries").status_code == 404
    assert org["regulatory"].put(_url(complaint, "AU"), json={"answers": {}}).status_code == 404
    assert _submit(org["regulatory"], report["id"]).status_code == 404
    detail = org["regulatory"].get(f"/api/v1/complaints/{complaint}/market-assessments").json()
    assert detail["other_countries_on"] is False and _item(detail, "AU")["current"]["conclusion"] == "REPORTABLE"
    shown = org["regulatory"].get(f"{REPORTS}/{report['id']}").json()
    assert shown["state_label"] == "To be submitted" and shown["can"]["submit"] is False
    monkeypatch.setenv("MDARIX_B9B_OTHER", "on")
    assert org["regulatory"].get("/api/v1/other-countries").status_code == 200


def test_an_open_country_keeps_the_complaint_open_on_the_watch_on_its_own_line(org):
    """Run-2 decision Q4: unsigned, or Reportable with its report not closed, is open, with its due date."""
    regulatory = org["regulatory"]
    complaint = _complaint(org["tenant_id"], org["product"], country="Japan", malfunction=True)

    def watched() -> dict:
        found = regulatory.get("/api/v1/complaints/reportability", params={"show": "all", "page_size": 200})
        assert found.status_code == 200, found.text
        return next(row for row in found.json()["items"] if row["id"] == complaint)

    item = _save(regulatory, complaint, "JP", REPORTABLE)
    line = watched()
    assert line["state"] != "DECIDED" and line["other_countries"][0]["state_label"] == "Not signed yet"
    assert _sign(regulatory, complaint, "JP", item, "REPORTABLE").status_code == 200
    report = _report(regulatory, complaint, "JP")
    # The list says the report's own status, never a worksheet's "ready for approval" (OC-D3).
    assert report["stage"] is None and report["stage_label"] == "To be submitted"
    # The server's day is the UTC day; a local date.today() is a day ahead of it before 05:30 IST.
    late = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    regulatory.put(f"{REPORTS}/{report['id']}/attached-due-date", json={"due_on": late, "reason": REASON})
    line = watched()
    assert line["state"] == "OVERDUE"
    assert line["other_countries"] == [
        {
            "country": "JP",
            "label": "Japan (other country)",
            "state_label": "To be submitted",
            "due_on": late,
            "due_label": "Due date entered by the customer",
            "clock_state": "OVERDUE",
            "report_id": report["id"],
        }
    ]
    assert _submit(regulatory, report["id"], report_id="PMDA-1").status_code == 200
    assert watched()["other_countries"][0]["state_label"] == "Submitted"
    assert regulatory.post(f"{REPORTS}/{report['id']}/complete", json={"reason": REASON}).status_code == 200
    assert watched()["other_countries"] == []


def test_the_complaints_decision_record_holds_the_country_and_the_report_with_its_files(org):
    """OC-15, per complaint: the event's decision record lists the signed conclusion and the submission's files."""
    complaint, _ = _reportable(org)
    report = _report(org["regulatory"], complaint)
    assert _submit(org["regulatory"], report["id"], report_id="TGA-REC-1").status_code == 200
    event = org["regulatory"].get(f"/api/v1/oversight/events/{complaint}")
    assert event.status_code == 200, event.text
    entries = event.json()["decision_record"]["entries"]
    assert any(entry["kind"] == "Market conclusion, Australia (other country)" for entry in entries)
    entry = next(entry for entry in entries if entry["kind"] == "Other Regulatory Report, Australia (other country)")
    assert "TGA-REC-1" in entry["summary"] and "report.pdf" in entry["summary"]
    assert hashlib.sha256(b"%PDF-1.4 our report to the TGA").hexdigest() in entry["summary"]
    assert entry["meaning"].startswith("I recorded that this report was submitted") and entry["signer"] == (
        "Rita Regulatory"
    )


def test_review_fixes_the_report_keeps_its_states_and_the_five_markets_their_screens(org, monkeypatch):
    """Run-2 review: a rejected (received) report is never cancelled by Not reportable; the shared routes neither
    change a report while the switch is off nor reopen a closed one; a follow-up never sent can be cancelled; the
    disposition screen of a complaint with a reportable country still reads (five markets untouched)."""
    from backend.app.complaint_disposition import service as disposition
    from backend.app.db.tenant_scope import bind_tenant

    complaint, _ = _reportable(org)
    regulatory, report = org["regulatory"], _report(org["regulatory"], complaint)
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        assert (
            disposition.screen_facts(db, uuid.UUID(str(org["tenant_id"])), uuid.UUID(complaint), date.today())
            is not None
        )
    submission = _submit(regulatory, report["id"]).json()["submissions"][0]["id"]
    evidence = f"{REPORTS}/{report['id']}/submissions/{submission}/evidence"
    now = datetime.now(timezone.utc).isoformat()
    rejected = regulatory.post(
        evidence, json={"kind": "REJECTION", "outcome": "REJECTED", "received_at": now, "file": _file("no")}
    )
    assert rejected.status_code == 200 and rejected.json()["state_label"] == "Rejected by authority", rejected.text
    resigned = _sign(regulatory, complaint, "AU", _save(regulatory, complaint, "AU", NONE), "NOT_REPORTABLE")
    assert resigned.status_code == 200 and _report(regulatory, complaint)["state"] == "CORRECTION_REQUIRED"
    # The generic follow-up route is not this report's.
    generic = regulatory.post(
        f"{REPORTS}/{report['id']}/follow-up", json={"due_on": date.today().isoformat(), "note": REASON}
    )
    assert generic.json()["detail"]["code"] == "ATTACHED_OWN_ROUTES"
    # A fresh report: submitted, a follow-up started by mistake and cancelled, then closed; no evidence after Close.
    complaint, _ = _reportable(org)
    report = _report(regulatory, complaint)
    submission = _submit(regulatory, report["id"]).json()["submissions"][0]["id"]
    child = regulatory.post(f"{REPORTS}/{report['id']}/attached-follow-ups", json={"reason": REASON}).json()
    assert child["can"]["cancel"] is True
    cancelled = regulatory.post(f"{REPORTS}/{child['id']}/cancel", json={"reason": REASON})
    assert cancelled.status_code == 200 and cancelled.json()["state_label"] == "Cancelled before it was sent"
    monkeypatch.setenv("MDARIX_B9B_OTHER", "off")
    assert regulatory.post(f"{REPORTS}/{report['id']}/complete", json={"reason": REASON}).status_code == 404
    monkeypatch.setenv("MDARIX_B9B_OTHER", "on")
    assert regulatory.post(f"{REPORTS}/{report['id']}/complete", json={"reason": REASON}).status_code == 200
    late = regulatory.post(
        f"{REPORTS}/{report['id']}/submissions/{submission}/evidence",
        json={"kind": "REJECTION", "outcome": "REJECTED", "received_at": now, "file": _file("late")},
    )
    assert late.json()["detail"]["code"] == "NOT_OPEN_FOR_EVIDENCE"
    assert _report(regulatory, complaint)["state"] == "COMPLETE"


def test_the_cases_view_of_other_countries_is_listed_and_runs():
    """B9b screens: the Cases list's "Reported in another country" view (a Case whose complaint has such a report)."""
    from datetime import datetime as moment

    from backend.app.db.models.intake import IntakeEvent
    from backend.app.intake import cases_list

    assert cases_list.VIEWS["other_countries"] == "Reported in another country"
    with SessionLocal() as db:
        bind_system(db, "test: the cases view")
        condition = cases_list._condition("other_countries", "nobody", moment.now(timezone.utc))
        assert db.query(IntakeEvent.id).filter(condition).limit(1).all() is not None


def test_the_cases_view_lists_a_case_whose_complaint_has_an_other_country_report_and_no_other(org):
    """Follow-up (11 Nov): a Case escalated to a complaint with an Other Regulatory Report is in "Reported in another
    country"; a Case escalated to a complaint with none is not."""
    from backend.app.db.models.intake import IntakeEvent

    reported, _ = _reportable(org)
    assert _report(org["regulatory"], reported)["market"] == "OTHER"
    plain = _complaint(org["tenant_id"], org["product"], country="Australia", malfunction=True)
    now, cases = datetime.now(timezone.utc), {}
    with SessionLocal() as db:
        bind_system(db, "test: the cases view")
        for name, complaint in (("reported", reported), ("plain", plain)):
            case = IntakeEvent(
                id=uuid.uuid4(),
                tenant_id=org["tenant_id"],
                reference=f"OC-{uuid.uuid4().hex[:10].upper()}",
                kind="CONTACT",
                reporter_words="The monitor stopped reading during use (synthetic).",
                complaint_id=uuid.UUID(complaint),
                status="ESCALATED",
                created_by="test",
                created_at=now,
                updated_at=now,
            )
            db.add(case)
            cases[name] = str(case.id)
        db.commit()
    listed = org["regulatory"].get("/api/v1/intake/cases", params={"view": "other_countries", "size": 100})
    assert listed.status_code == 200, listed.text
    ids = {item["id"] for item in listed.json()["items"]}
    assert cases["reported"] in ids and cases["plain"] not in ids
    everything = org["regulatory"].get("/api/v1/intake/cases", params={"view": "all", "size": 100}).json()
    assert {cases["reported"], cases["plain"]} <= {item["id"] for item in everything["items"]}


def test_the_inspection_pack_lists_the_reports_and_their_files(org):
    """OC-15."""
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.readiness_home import pack

    complaint, _ = _reportable(org)
    report = _report(org["regulatory"], complaint)
    assert _submit(org["regulatory"], report["id"], report_id="TGA-PACK-1").status_code == 200
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        text = pack.other_regulatory_reports(db, org["tenant_id"], date.today()).decode("utf-8")
    line = next(row for row in text.splitlines() if "TGA-PACK-1" in row)
    assert "Australia" in line and "Submitted" in line and "report.pdf" in line
    assert hashlib.sha256(b"%PDF-1.4 our report to the TGA").hexdigest() in line
    assert pack.file_basis(pack.OTHER_REPORTS_FILE)
