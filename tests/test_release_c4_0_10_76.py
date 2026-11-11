"""0.10.76, Release C part C4: the EU MIR, Great Britain (MHRA) and Health Canada forms, and Canada's tree.

- Each form lists its sections and fields in the authority's own order, its report types and its fixed lists, and is
  a starter "for your consultant to confirm"; which fields are mandatory follows the report type.
- The forms plug into C3's flow on the new navigation only: a signed reportable conclusion creates the report, the
  meter blocks Send for approval, the PDF follows approval in the form's order. The classic navigation keeps US and
  India.
- Canada's starter tree (SOR/98-282 ss. 59-60) and the EU and GB trees pass their worked complaints.
- The sample's SAMPLE-RV-07 gets its EU MIR (new trials on staging, running trials through the refresh, once).
- C3's follow-ups: "Waiting for my approval" holds a report only for a person who may approve it; approval tasks and
  Home items open the report itself.
"""

from __future__ import annotations

import uuid

import pytest

from tests.report_fill import fill
from fastapi.testclient import TestClient

from backend.app.authority_reports import forms, render, worksheet
from backend.app.decision_guides import rules as guides
from backend.app.main import app
from backend.app.reportability import markets
from tests.test_authority_reports_api import _empty_context
from tests.test_free_trial import PASSWORD, _activation_token, _approved_trial_client
from tests.test_market_assessment_api import WHY, _acknowledge, _save, _sign
from tests.test_release_c3_0_10_75 import REPORTS, TREES, _classic, _flagship, _ok, _purge, _reports, _sign_us
from tests.test_reporting_capa_api import SETTINGS

NEW = (forms.EU_MIR, forms.GB_MIR, forms.HC_MDPR)


def _ids(form: forms.Form) -> list[str]:
    return [item.id for item in form.fields()]


def _mandatory(form: forms.Form, kind: str) -> set[str]:
    entries = {form.type_field: {"value": kind}}
    sections = worksheet.build(form, _empty_context(), entries, {})
    return {item["id"] for section in sections for item in section["fields"] if item["missing_class"] == forms.MUST}


# --------------------------------------------------------------------------------------------- the forms (no database)


def test_each_new_form_follows_the_authoritys_order_types_and_fixed_lists():
    assert forms.BY_MARKET == {
        "US": forms.FDA_3500A,
        "IN": forms.MVPI_MDAE,
        "EU_NI": forms.EU_MIR,
        "GB": forms.GB_MIR,
        "CA": forms.HC_MDPR,
    }
    for form in NEW:
        assert form.starter and form.source_document and "3 Nov 2026" in form.source_document
        assert len(_ids(form)) == len(set(_ids(form)))
        # The type field is the form's own fixed list of report types; every source is a known one.
        (kind,) = [item for item in form.fields() if item.id == form.type_field]
        assert kind.options == form.report_types and kind.source == "report_type"
        assert all(item.source is None for item in form.fields() if item.personal)
        assert all(item.source in (*worksheet.SOURCES, "report_type") for item in form.fields() if item.source)
    assert not forms.FDA_3500A.starter and not forms.MVPI_MDAE.starter
    # EU MIR 7.3.1: sections 1 to 5 in order; its five report types as printed.
    assert [section.code for section in forms.EU_MIR.sections] == [
        "1_1", "1_2", "1_3", "2_1", "2_2", "2_3", "3_1", "3_2", "3_3", "3_4", "4_1", "4_2", "4_3", "5"
    ]  # fmt: skip
    assert _ids(forms.EU_MIR)[:8] == ["1_1A", "1_1B", "1_1C", "1_1D", "1_2A", "1_2B", "1_2C", "1_2D"]
    assert forms.EU_MIR.report_types == (
        "Initial",
        "Follow up",
        "Combined initial and final",
        "Final (Reportable incident)",
        "Final (Non-reportable incident)",
    )
    location = next(item for item in forms.EU_MIR.fields() if item.id == "3_2C")
    assert location.options[:2] == ("Healthcare facility/carer", "Patient/user") and len(location.options) == 9
    # GB MIR 7.2.1: no EUDAMED numbers, the UK Responsible Person as a submitter, GMDN only, the UKAB fields.
    gb = {item.id: item for item in forms.GB_MIR.fields()}
    assert not any("EUDAMED" in item.label for item in gb.values())
    assert "United Kingdom Responsible Person" in gb["1_3_1A"].options and gb["2_2A"].options == ("GMDN",)
    assert {"2_3_UKAB", "2_3_UKAB_CERT"} <= set(gb) and "2_4E" not in gb
    # Health Canada HC Pub. 110180: A to E, its four report types.
    assert [section.code for section in forms.HC_MDPR.sections] == ["A", "B", "C", "D", "E"]
    assert forms.HC_MDPR.report_types == ("Preliminary", "Update", "Final", "Preliminary & Final")
    assert _ids(forms.HC_MDPR)[:5] == ["A1", "A1_II", "A1_III", "A2", "A3"]
    # The classic navigation keeps the US and India worksheets only.
    assert [market for market in forms.BY_MARKET if forms.form_for(market, False)] == ["US", "IN"]
    assert all(forms.form_for(market, True) for market in forms.BY_MARKET)


def test_the_mandatory_fields_follow_the_report_type():
    initial, final = _mandatory(forms.EU_MIR, "Initial"), _mandatory(forms.EU_MIR, "Final (Reportable incident)")
    non = _mandatory(forms.EU_MIR, "Final (Non-reportable incident)")
    # Every type: the authority, the dates, the type, the device's name, the description, the Annex A, E, F codes.
    assert {"1_1A", "1_2A", "1_2B", "1_2C", "1_2E", "2_3A", "3_1A", "3_2A", "3_3A_E", "3_3A_F"} <= initial & final & non
    assert {"1_2F", "1_2G", "4_1A"} <= initial and not {"4_2A", "2_1A", "4_2E_B"} & initial
    assert {"4_2A", "4_2C", "4_2E_B", "4_2F", "2_1A", "2_5"} <= final and "1_2F" not in final
    assert "4_2B" in non and not {"1_2G", "1_2D", "4_2A"} & non
    # A follow-up needs the NCA's reference and the initial actions.
    assert {"1_1C", "4_1C", "4_1D"} <= _mandatory(forms.EU_MIR, "Follow up")
    # GB: MHRA asks every report for the UDI and a code from every IMDRF annex.
    assert {"2_1A", "4_2E_B", "4_2E_C", "4_2E_D", "4_2F"} <= _mandatory(forms.GB_MIR, "Initial")
    # Canada: a preliminary report fills everything but E2 and E3; an update or final the starred fields (and E2, E3).
    prelim, update = _mandatory(forms.HC_MDPR, "Preliminary"), _mandatory(forms.HC_MDPR, "Update")
    assert {"A1", "B2", "B5", "C9", "D1", "E1", "A5_FINAL_DATE"} <= prelim and not {"E2", "E3", "A4"} & prelim
    # A6 (date submitted) is filled at Send for approval (B9 step 11, as FDA's B4): it never blocks sending.
    sent_day = set() if forms.switched_on("MDARIX_B9_CANADA") else {"A6"}  # off: typed, as before B9
    assert update == {"A2", "A3", "A4", "A5", "A5_PREVIOUS", "B1", "C1"} | sent_day
    assert _mandatory(forms.HC_MDPR, "Final") == update | {"E2", "E3"}
    # Patient and reporter fields are never in the meter.
    assert not {"D2", "D3", "D4", "D5"} & _mandatory(forms.HC_MDPR, "Preliminary & Final")
    # An unknown choice falls back to the form's first type.
    assert forms.report_kind(forms.HC_MDPR, {"A5": {"value": "Something else"}}) == "Preliminary"


def test_the_trees_worked_complaints_pass_and_canada_counts_conservatively():
    for market in (markets.EU_NI, markets.GB, markets.CA):
        results = guides.run(market, guides.starter_tests(market))
        assert results and all(item["passed"] for item in results), market
    assert len(guides.starter_tests(markets.CA)) == 6
    unknown = {key: {"answer": "YES"} for key in ("CA1", "CA2", "CA4", "CA5")} | {"CA3": {"answer": "UNKNOWN"}}
    found = markets.evaluate(markets.CA, unknown)
    # Reportable on question 4 already; question 3 Unknown keeps the shorter 10-day report.
    assert (found["suggested"], found["report_type"]) == (markets.REPORTABLE, "CA_10_DAY")
    assert markets.REPORT_TYPES["CA_10_DAY"].days == 10 and markets.REPORT_TYPES["CA_30_DAY"].days == 30
    assert [question.clause.split(";")[0] for question in markets.CA_SET.questions][:2] == [
        "SOR/98-282 s. 59(1)(a)",
        "SOR/98-282 s. 59(1)(b)(i)",
    ]


# --------------------------------------------------------------------------------------------- with the database


@pytest.fixture(scope="module")
def trial():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        _purge(tenant_id)


@pytest.mark.db
def test_the_samples_rv07_has_its_eu_mir_and_it_goes_the_whole_way(trial):
    user = trial["user"]
    items = [item for item in _ok(user.get(REPORTS))["items"] if item["complaint_ref"] == "SAMPLE-RV-07"]
    (eu,) = items
    assert (eu["market"], eu["state"], eu["stage"]) == ("EU_NI", "DRAFT", "CREATED") and eu["id"]
    assert eu["form_title"] == forms.EU_MIR.title
    forms_list = _ok(user.get(REPORTS))["forms"]
    assert [(item["market"], item["starter"]) for item in forms_list] == [
        ("US", False), ("IN", False), ("EU_NI", True), ("GB", True), ("CA", True)
    ]  # fmt: skip
    detail = _ok(user.get(f"{REPORTS}/{eu['id']}"))
    assert detail["sample"] and detail["form"]["starter"] and detail["form"]["report_kind"] == "Initial"
    values = {item["id"]: item for section in detail["sections"] for item in section["fields"]}
    # From the records: the dates, the description, the device, and the signed conclusion's classification (15 days).
    assert all(values[key]["value"] and values[key]["source"] for key in ("1_2B", "1_2C", "3_1A", "2_3A", "1_2E"))
    assert values["1_2G"]["value"] == "All other reportable incidents"
    assert values["1_2E"]["options"] == list(forms.MIR_TYPES)
    # A fixed list takes one of its choices.
    refused = user.put(f"{REPORTS}/{eu['id']}/fields/1_2E", json={"value": "Final"})
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "NOT_A_CHOICE"
    # B8 step 3: the first report is an Initial or a Combined initial and final; a Final follows in the chain.
    # (With MDARIX_B8_EU_MIR off, the type is chosen by hand as before B8.)
    typed = user.put(f"{REPORTS}/{eu['id']}/fields/1_2E", json={"value": "Final (Reportable incident)"})
    if forms.switched_on("MDARIX_B8_EU_MIR"):
        assert typed.status_code == 422 and typed.json()["detail"]["code"] == "NOT_THIS_POSITION"
    else:
        assert typed.status_code == 200, typed.text
    # The type changes the meter: a combined (final) report needs the investigation's fields.
    initial = detail["mandatory"]["total"]
    final = _ok(user.put(f"{REPORTS}/{eu['id']}/fields/1_2E", json={"value": "Combined initial and final"}))
    assert final["form"]["report_kind"] == "Combined initial and final" and final["mandatory"]["total"] > initial
    detail = _ok(user.put(f"{REPORTS}/{eu['id']}/fields/1_2E", json={"clear": True}))
    # Send for approval waits for every mandatory field; then the practice approval, then the PDF.
    blocked = user.post(f"{REPORTS}/{eu['id']}/snapshots")
    assert blocked.status_code == 422 and blocked.json()["detail"]["code"] == "MANDATORY_FIELDS_MISSING"
    for field in detail["mandatory"]["missing"]:
        choice = values[field]["options"]
        if choice:
            _ok(user.put(f"{REPORTS}/{eu['id']}/fields/{field}", json={"value": choice[0]}))
        else:
            fill(user, REPORTS, eu["id"], [field])  # 0.10.81: a date field takes a date, a code field a code
    # D7 (B2 run 3): before approval the PDF is a preview marked DRAFT.
    from io import BytesIO

    from pypdf import PdfReader

    pdf = user.get(f"{REPORTS}/{eu['id']}/worksheet.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert "DRAFT PREVIEW - NOT APPROVED" in PdfReader(BytesIO(pdf.content)).pages[0].extract_text()
    asked = _ok(user.post(f"{REPORTS}/{eu['id']}/snapshots"))
    # No XML file before approval (and the eMDR file is a US report's only).
    xml = user.get(f"{REPORTS}/{eu['id']}/emdr.xml", params={"snapshot": asked["pending_snapshot"]["id"]})
    assert xml.status_code == 404 and xml.json()["detail"]["code"] == "NOT_A_US_REPORT"
    done = _ok(user.post(f"{REPORTS}/{eu['id']}/snapshots/{asked['pending_snapshot']['id']}/approve",
                         json={"password": PASSWORD}))  # fmt: skip
    assert done["stage"] == "APPROVED"
    pdf = user.get(f"{REPORTS}/{eu['id']}/worksheet.pdf", params={"snapshot": done["approved_snapshot"]["id"]})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    # The PDF's lines follow the form's sections in order, and say it is a starter form of its type.
    lines = render.lines(done)
    headings = [text for text, style in lines if style == "heading"]
    assert headings[: len(forms.EU_MIR.sections)] == [section.title for section in forms.EU_MIR.sections]
    assert any("Starter form, for your consultant to confirm. Type of report: Initial." in text for text, _ in lines)


@pytest.mark.db
def test_a_signed_reportable_canada_conclusion_creates_the_health_canada_report(trial):
    user = trial["user"]
    settings = _ok(user.get(SETTINGS))
    # 0.10.81 (F5): a trial has every market's windows, Canada's included.
    assert [item["name"] for item in settings["windows"] if "Health Canada" in item["name"]]
    complaint = _flagship(user)
    _acknowledge(user, "CA")
    answers = {
        key: {"answer": value, "rationale": WHY, "evidence": ["Complaint description"]}
        for key, value in dict(CA1="YES", CA2="YES", CA3="NO", CA4="YES", CA5="YES", CA6="NOT_APPLICABLE").items()
    }
    detail = _ok(user.get(f"/api/v1/complaints/{complaint}/market-assessments"))
    saved = _save(user, complaint, "CA", answers, harm_level=detail["severity_level"])
    assert not [item for item in _reports(user, complaint) if item["market"] == "CA"]
    _ok(_sign(user, complaint, "CA", saved, "REPORTABLE", password=PASSWORD))
    (report,) = [item for item in _reports(user, complaint) if item["market"] == "CA"]
    assert report["form_title"] == forms.HC_MDPR.title and report["stage"] == "CREATED"
    values = {
        item["id"]: item["value"]
        for section in _ok(user.get(f"{REPORTS}/{report['id']}"))["sections"]
        for item in section["fields"]
    }
    assert (values["A5"], values["B1"], values["C1"]) == (
        "Preliminary",
        "30-Day; Canadian",
        "PulseWatch 410 Patient Monitor (Sample)",
    )
    trees = {tree["market"]: tree for tree in _ok(user.get(TREES))["markets"]}
    assert trees["CA"]["enabled"] and trees["CA"]["tests"] == {"passed": 6, "total": 6, "current": True}
    assert trees["CA"]["form"] == {"title": forms.HC_MDPR.title, "starter": True}


@pytest.mark.db
def test_the_decision_trees_show_every_market():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        trees = {tree["market"]: tree for tree in _ok(user.get(TREES))["markets"]}
        assert list(trees) == ["US", "EU_NI", "GB", "IN", "CA"]
        # 0.10.81 (F5): every trial has every market's windows, so every tree is enabled.
        assert [market for market, tree in trees.items() if not tree["enabled"]] == []
        assert trees["GB"]["tests"]["total"] == trees["GB"]["tests"]["passed"] == 5
        assert trees["EU_NI"]["form"]["starter"] and not trees["US"]["form"]["starter"]
    finally:
        _purge(tenant_id)


@pytest.mark.db
def test_the_classic_navigation_keeps_us_and_india_and_the_refresh_adds_rv07s_report_once():
    from backend.app.db.models.authority_reports import ReportObligation
    from backend.app.db.models.foundation import Tenant
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.trial import reports_0_10_75

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        # A running trial from before 0.10.76: its RV-07 has no EU report. The refresh adds it once (dry run first).
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            db.query(ReportObligation).filter(ReportObligation.market == "EU_NI").delete()
            db.commit()
            assert reports_0_10_75.refresh(db, tenant_id, apply=False) == 1
            assert reports_0_10_75.refresh(db, tenant_id, apply=True) == 1
            db.commit()
            assert reports_0_10_75.refresh(db, tenant_id, apply=False) == 0
            (row,) = db.query(ReportObligation).filter(ReportObligation.market == "EU_NI").all()
            assert (row.form_code, row.source_system) == ("EU_MIR", "MDARIX_SAMPLE")
        _classic(tenant_id)
        listed = _ok(user.get(REPORTS))
        assert [item["market"] for item in listed["forms"]] == ["US", "IN"]
        rv07 = next(item for item in listed["items"] if item["complaint_ref"] == "SAMPLE-RV-07")
        refused = user.post(REPORTS, json={"complaint_id": rv07["complaint_id"], "market": "EU_NI"})
        assert refused.status_code == 409 and refused.json()["detail"]["code"] == "NO_WORKSHEET"
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            db.query(ReportObligation).filter(ReportObligation.market == "EU_NI").delete()
            db.get(Tenant, tenant_id).navigation = "classic"
            db.commit()
            # The classic navigation: no report made, and the EU market reads "worksheet comes later" as before.
            assert reports_0_10_75.refresh(db, tenant_id, apply=False) == 0
        rv07 = next(item for item in _ok(user.get(REPORTS))["items"] if item["complaint_ref"] == "SAMPLE-RV-07")
        assert (rv07["state"], rv07["can_start"]) == ("NO_WORKSHEET", False)
    finally:
        _purge(tenant_id)


@pytest.mark.db
def test_waiting_for_my_approval_holds_only_what_i_may_approve_and_links_open_the_report():
    owner, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        mail = f"c4-approver-{uuid.uuid4().hex[:6]}@example.invalid"
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
        _ok(owner.post(f"{REPORTS}/{report['id']}/snapshots"))
        # The preparer may not approve (a colleague may): not in the preparer's "Waiting for my approval".
        assert "my-approval" not in _reports(owner, complaint)[0]["views"]
        assert "my-approval" in _reports(colleague, complaint)[0]["views"]
        # The colleague's approval task and the Oversight item open the report itself.
        (task,) = [
            item
            for item in _ok(colleague.get("/api/v1/tasks", params={"view": "assigned"}))["items"]
            if item["source"]["type"] == "ReportSnapshot"
        ]
        assert task["details"]["obligation_id"] == report["id"]
        item = next(
            row
            for row in _ok(owner.get("/api/v1/oversight", params={"show": "all"}))["items"]
            if row["key"] == f"obligation:{report['id']}"
        )
        assert item["opens"]["target"]["record"] == {"kind": "report", "id": report["id"]}
    finally:
        _purge(tenant_id)
