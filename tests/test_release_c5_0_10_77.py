"""0.10.77, Release C part C5: codes.

- The loaders read only the publishers' files (data/code_lists) and refuse a malformed one; nothing is ever deleted.
- The sample's IMDRF links are the codes and terms of IMDRF's own Release 2026 file, word for word.
- On the new navigation a mapped code is a suggestion: never filed unconfirmed, confirmed or changed by a person,
  recorded with who and how; one choice fills the FDA and the IMDRF code; the required codes per form and report
  type hold Send for approval; a retired code stays on the report that holds it; the picker searches and browses.
- Product and organization identity fields are checked against the loaded lists and fill the forms.
- Running trials are re-recorded once by the refresh (dry run first); the trend sentence counts each lot.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile

import pytest

from backend.app.authority_reports import forms, render, worksheet
from scripts import load_code_lists as loader
from tests.code_lists import ensure_loaded
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_release_c3_0_10_75 import REPORTS, _flagship, _ok, _purge, _reports, _sign_us

CODES = "/api/v1/regulatory-reference/imdrf/codes"
PRODUCTS = "/api/v1/regulatory-reference/products"
WORKBOOK = loader.MANIFEST.parent / "imdrf-tech-ae-terminologies-n43-ReleaseNumber2026-Annexes-revisedJune.xlsx"


def _fields(detail: dict) -> dict:
    return {item["id"]: item for section in detail["sections"] for item in section["fields"]}


# --------------------------------------------------------------------------------------------- the files (no database)


def test_the_published_files_parse_and_a_malformed_file_is_refused():
    manifest = json.loads(loader.MANIFEST.read_text(encoding="utf-8"))["files"]
    assert [entry["list"] for entry in manifest] == ["IMDRF", "FDA_CDRH", "FDA_PRODUCT_CODE", "EMDN"]
    for entry in manifest:
        assert entry["source_url"].startswith("https://") and entry["published"] and len(entry["sha256"]) == 64
        version, codes, problems = loader.check(entry, (loader.MANIFEST.parent / entry["file"]).read_bytes())
        assert problems == [] and version == entry["version"], entry["list"]
    # IMDRF Release 2026: the seven annexes, one row per code (Annex E repeats some under a second heading).
    release, annexes, problems = loader.parse_imdrf(WORKBOOK.read_bytes())
    assert (release, problems) == ("2026", [])
    assert {annex: len(rows) for annex, rows in annexes.items()} == {
        "A": 491, "B": 34, "C": 160, "D": 45, "E": 812, "F": 82, "G": 307
    }  # fmt: skip
    assert sum(1 for rows in annexes.values() for item in rows if (item["status"] or "").startswith("Retired")) == 15
    # A file that is not the publisher's is refused whole: another SHA-256, a wrong header, a bad code.
    entry = next(item for item in manifest if item["list"] == "FDA_CDRH")
    raw = (loader.MANIFEST.parent / entry["file"]).read_bytes()
    assert any("SHA-256" in problem for problem in loader.check(entry, raw + b"\n")[2])
    assert loader.parse_fda_cdrh(b"code\tterm\nA\tB\n")[1][0].startswith("the header is not")
    header = "\t".join(loader.CDRH_COLUMNS)
    bad = f"{header}\nC1\tMedical Device Problem\tC2\tX\tX\tHigh\t12a\tX\tIMDRF:A090807\n"
    assert "is not a number" in loader.parse_fda_cdrh(bad.encode())[1][0]
    wrong = f"{header}\nC1\tMedical Device Problem\tC2\tX\tX\tHigh\t2459\tX\tIMDRF:E0101\n"
    assert "is not in Annex A" in loader.parse_fda_cdrh(wrong.encode())[1][0]
    twice = f"{header}\n" + "C1\tMedical Device Problem\tC2\tX\tX\tHigh\t2459\tX\tIMDRF:A090807\n" * 2
    assert "appears twice" in loader.parse_fda_cdrh(twice.encode())[1][0]
    assert loader.parse_imdrf(b"not a workbook")[2]
    assert loader.parse_emdn(b"not a workbook")[2]
    packed = io.BytesIO()
    with zipfile.ZipFile(packed, "w") as archive:
        archive.writestr(
            "foiclass.txt", "REVIEW_PANEL|PRODUCTCODE|DEVICENAME|DEVICECLASS|REGULATIONNUMBER\nAN|B1|X|1|\n"
        )
    assert "not three letters" in loader.parse_fda_product_codes(packed.getvalue())[1][0]
    assert loader.parse_fda_product_codes(b"PRODUCTCODE|DEVICENAME\nFRN|Pump\n")[1][0].startswith("missing column")


def test_the_sample_links_are_imdrfs_own_codes_and_terms_word_for_word():
    """The addendum's check: each sample link exists in IMDRF's Release 2026 file, its term matches word for word,
    and its level (the code's length) is the most specific term that says what the complaint says."""
    from backend.app.trial.sample_imports import EARLIER_IMDRF_LINKS, SAMPLE_IMDRF_LINKS, SAMPLE_IMDRF_RELEASE

    _, annexes, _ = loader.parse_imdrf(WORKBOOK.read_bytes())
    annex_a = {item["code"]: item for item in annexes["A"]}
    assert SAMPLE_IMDRF_RELEASE == "2026"
    terms = {code: annex_a[code]["term"] for links in SAMPLE_IMDRF_LINKS.values() for code in links}
    assert terms == {
        "A1601": "Device Alarm System",
        "A1407": "Insufficient Flow or Under Infusion",
        "A160102": "No Audible Alarm",
        "A140502": "Free or Unrestricted Flow",
        "A160103": "Low Audible Alarm",
        "A090807": "High Readings",
        # 0.10.79: the two sample codes that had no link.
        "A090808": "Low Readings",
        "A090811": "Unable to Obtain Readings",
    }
    levels = {code: (len(code) - 1) // 2 for code in terms}
    assert levels == {"A1601": 2, "A1407": 2, "A160102": 3, "A140502": 3, "A160103": 3, "A090807": 3, "A090808": 3,
                      "A090811": 3}  # fmt: skip
    assert SAMPLE_IMDRF_LINKS["FLOW_ZERO_READING"] == ("A090808",)  # RV-07: the flow sensor showed zero flow
    assert SAMPLE_IMDRF_LINKS["SPO2_DROPOUT_HARM"] == ("A090811",)  # RV-01: the SpO2 reading dropped out
    assert "NFF" not in SAMPLE_IMDRF_LINKS
    # The links before 0.10.77 exist too, as written: the level-1 headings and A0908 (level 2).
    assert {annex_a[old]["term"] for _, old in EARLIER_IMDRF_LINKS} == {
        "Infusion or Flow Problem",
        "Protective Measures Problem",
        "Incorrect, Inadequate or Imprecise Result or Readings",
    }
    # Each new code sits under the old one (a more specific term of the same heading).
    assert all(new.startswith(old) for (_, old), new in EARLIER_IMDRF_LINKS.items() if old != "A14" or new[:3] == "A14")
    assert not any((annex_a[code]["status"] or "").startswith(("Retired", "Not selectable")) for code in terms)


def test_a_suggestion_is_never_frozen_and_counts_as_missing():
    form = forms.FDA_3500A
    context = {**_context_with_codes(), "confirm_codes": True}
    sections = worksheet.build(form, context, {}, {})
    problem = _fields({"sections": sections})["H6_PROBLEM"]
    assert (problem["status"], problem["value"]) == ("SUGGESTED", None)
    assert problem["suggestion"] == "A090807 High Readings (FDA 2459)" and problem["code_annex"] == "A"
    assert "H6_PROBLEM" in worksheet.mandatory(sections)["missing"]
    # On the new navigation an initial 3500A needs both health effect codes too.
    assert {"H6_CLINICAL", "H6_IMPACT"} <= set(worksheet.mandatory(sections)["missing"])
    frozen = _fields({"sections": worksheet.frozen(sections)})["H6_PROBLEM"]
    assert "suggestion" not in frozen and frozen["value"] is None
    # Confirmed: the value is the suggestion, recorded as confirmed; the classic navigation keeps 0.10.58's rule.
    entries = worksheet.confirm_suggestions(form, context, {}, "someone", "2026-11-03T10:00:00+00:00")
    confirmed = _fields({"sections": worksheet.build(form, context, entries, {"someone": "Asha"})})["H6_PROBLEM"]
    assert (confirmed["status"], confirmed["value"], confirmed["by"]) == ("CONFIRMED", problem["suggestion"], "Asha")
    classic = _fields({"sections": worksheet.build(form, {**context, "confirm_codes": False}, {}, {})})
    assert classic["H6_PROBLEM"]["status"] == "FROM_RECORD" and classic["H6_CLINICAL"]["missing_class"] != forms.MUST


def _context_with_codes() -> dict:
    from tests.test_authority_reports_api import _empty_context

    context = _empty_context()
    context["complaint"].problem_code = "SPO2_READING_HIGH"
    context["imdrf"] = [{"release": "2026", "annex": "A", "code": "A090807", "term": "High Readings"}]
    context["fda"] = {"A090807": {"code": "2459", "term": "High Readings", "version": "26.08e"}}
    return context


# --------------------------------------------------------------------------------------------- with the database


@pytest.fixture(scope="module")
def trial():
    ensure_loaded()
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    complaint = _flagship(user)
    try:
        yield {"user": user, "tenant_id": tenant_id, "complaint": complaint}
    finally:
        _purge(tenant_id)


@pytest.mark.db
def test_the_loaders_load_once_and_never_delete():
    from backend.app.db.models.regulatory_reference import CodeListFile, ImdrfCode, ReferenceCode
    from backend.app.db.session import SessionLocal

    ensure_loaded()
    entries = json.loads(loader.MANIFEST.read_text(encoding="utf-8"))["files"]
    with SessionLocal() as db:
        counts = {annex: db.query(ImdrfCode).filter_by(release="2026", annex=annex).count() for annex in loader.ANNEXES}
        assert counts == {"A": 491, "B": 34, "C": 160, "D": 45, "E": 812, "F": 82, "G": 307}
        assert db.query(ReferenceCode).filter_by(list="FDA_CDRH", version="26.08e").count() == 1885
        assert db.query(ReferenceCode).filter_by(list="FDA_PRODUCT_CODE").count() >= 7098
        assert db.query(ReferenceCode).filter_by(list="EMDN", version="2026").count() == 8516
        assert {row.list for row in db.query(CodeListFile)} >= {"IMDRF", "FDA_CDRH", "FDA_PRODUCT_CODE", "EMDN"}
        # FDA's mapping: every FDA code names an IMDRF code of the loaded release.
        fda = db.query(ReferenceCode).filter_by(list="FDA_CDRH", version="26.08e").all()
        known = {code for (code,) in db.query(ImdrfCode.code).filter_by(release="2026")}
        assert all(row.imdrf_code in known for row in fda)
        # A second run changes nothing (a dry run, then an apply); a file that leaves out a loaded code is refused.
        lines: list[str] = []
        assert loader.run(db, entries, loader.MANIFEST.parent, apply=False, out=lines.append) == 0
        assert all("0 new, 0 changed" in line for line in lines if line.startswith("CHECKED ") and "IMDRF" not in line)
        with pytest.raises(SystemExit, match="leaves out loaded codes"):
            loader.load_reference(db, "EMDN", "2026", [], apply=False, now=None)
        db.rollback()


@pytest.mark.db
def test_the_code_picker_searches_by_word_and_browses_the_annex(trial):
    user = trial["user"]
    found = _ok(user.get(CODES, params={"pick": 1, "annex": "A", "q": "high readings"}))
    assert found["release"] == "2026" and found["fda_version"] == "26.08e"
    first = found["codes"][0]
    assert (first["code"], first["term"], first["fda"]["code"]) == ("A090807", "High Readings", "2459")
    assert first["definition"].startswith("Reading provided by the device is too high")
    top = _ok(user.get(CODES, params={"pick": 1, "annex": "A"}))["codes"]
    assert [item["code"] for item in top][:2] == ["A01", "A02"] and all(len(item["code"]) == 3 for item in top)
    under = _ok(user.get(CODES, params={"pick": 1, "annex": "A", "parent": "A0908"}))["codes"]
    assert "A090807" in [item["code"] for item in under]
    assert next(item for item in top if item["code"] == "A09")["children"] > 0
    # Retired codes are not offered (A0202 was retired in 2025); Annex E's headings cannot be chosen.
    assert "A0202" not in [
        item["code"] for item in _ok(user.get(CODES, params={"pick": 1, "annex": "A", "q": "A0202"}))["codes"]
    ]
    heading = _ok(user.get(CODES, params={"pick": 1, "annex": "E", "q": "E01"}))["codes"][0]
    assert (heading["code"], heading["selectable"]) == ("E01", False)


@pytest.mark.db
def test_nothing_is_filed_unconfirmed_and_one_choice_fills_fda_and_imdrf(trial):
    from backend.app.db.models.foundation import AuditEvent
    from backend.app.db.session import SessionLocal

    user, complaint = trial["user"], trial["complaint"]
    _ok(_sign_us(user, complaint, "REPORTABLE"))
    (report,) = _reports(user, complaint)
    detail = _ok(user.get(f"{REPORTS}/{report['id']}"))
    assert detail["codes_confirmed"]
    fields = _fields(detail)
    problem = fields["H6_PROBLEM"]
    assert (problem["status"], problem["value"], problem["suggestion"]) == (
        "SUGGESTED",
        None,
        "A090807 High Readings (FDA 2459)",
    )
    assert {"H6_PROBLEM", "H6_CLINICAL", "H6_IMPACT"} <= set(detail["mandatory"]["missing"])
    # Fill every other mandatory field: Send for approval still waits for the codes.
    for field in [item for item in detail["mandatory"]["missing"] if not item.startswith("H6_")]:
        if field != "G8":
            detail = _ok(user.put(f"{REPORTS}/{report['id']}/fields/{field}", json={"value": "Test value"}))
    blocked = user.post(f"{REPORTS}/{report['id']}/snapshots")
    assert blocked.status_code == 422 and "H6_PROBLEM" in blocked.json()["detail"]["missing"]
    # Confirm the suggestion; choose the health effect codes in the picker: each with its FDA code.
    detail = _ok(user.put(f"{REPORTS}/{report['id']}/fields/H6_PROBLEM", json={"confirmed": True}))
    confirmed = _fields(detail)["H6_PROBLEM"]
    assert (confirmed["status"], confirmed["value"]) == ("CONFIRMED", "A090807 High Readings (FDA 2459)")
    wrong_annex = user.put(f"{REPORTS}/{report['id']}/fields/H6_CLINICAL", json={"codes": ["A090807"]})
    assert wrong_annex.status_code == 422 and wrong_annex.json()["detail"]["code"] == "IMDRF_CODE_UNKNOWN"
    detail = _ok(user.put(f"{REPORTS}/{report['id']}/fields/H6_CLINICAL", json={"codes": ["E2403"]}))
    clinical = _fields(detail)["H6_CLINICAL"]
    assert clinical["status"] == "ENTERED" and clinical["value"].startswith("E2403 No Clinical Signs")
    assert "(FDA " in clinical["value"]
    detail = _ok(user.put(f"{REPORTS}/{report['id']}/fields/H6_IMPACT", json={"codes": ["F26"]}))
    assert _fields(detail)["H6_IMPACT"]["value"].startswith("F26 No Health Consequences or Impact")
    # The conclusion code FDA asks on every report (Annex D), chosen in the picker (a test choice).
    detail = _ok(user.put(f"{REPORTS}/{report['id']}/fields/H6_CONCLUSIONS", json={"codes": ["D0101"]}))
    assert _fields(detail)["H6_CONCLUSIONS"]["value"].startswith("D0101 Design Inadequate for Purpose (FDA ")
    # Changing a suggestion records what was suggested.
    changed = _fields(_ok(user.put(f"{REPORTS}/{report['id']}/fields/H6_PROBLEM", json={"codes": ["A090805"]})))
    assert (changed["H6_PROBLEM"]["status"], changed["H6_PROBLEM"]["suggested"]) == (
        "CHANGED",
        "A090807 High Readings (FDA 2459)",
    )
    detail = _ok(user.put(f"{REPORTS}/{report['id']}/fields/H6_PROBLEM", json={"confirmed": True}))
    assert detail["stage"] == "COMPLETE" and not detail["mandatory"]["missing"], detail["mandatory"]
    asked = _ok(user.post(f"{REPORTS}/{report['id']}/snapshots"))
    done = _ok(
        user.post(
            f"{REPORTS}/{report['id']}/snapshots/{asked['pending_snapshot']['id']}/approve",
            json={"password": PASSWORD},
        )
    )
    text = "\n".join(line for line, _ in render.lines(done))
    assert "A090807 High Readings (FDA 2459)" in text and "Suggested" not in text
    with SessionLocal() as db:
        states = [
            row.details.get("code_state")
            for row in db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == trial["tenant_id"], AuditEvent.action == "REPORT_FIELD_SET")
            .order_by(AuditEvent.created_at)  # 0.10.79: in the order they were set (it read them unordered)
            if (row.details or {}).get("field") == "H6_PROBLEM"
        ]
    assert states == ["CONFIRMED", "CHANGED", "CONFIRMED"]


@pytest.mark.db
def test_a_retired_code_stays_on_the_report_that_holds_it(trial):
    from backend.app.db.models.regulatory_reference import ImdrfCode
    from backend.app.db.session import SessionLocal

    user = trial["user"]
    (eu,) = [item for item in _ok(user.get(REPORTS))["items"] if item["complaint_ref"] == "SAMPLE-RV-07"]
    detail = _ok(user.put(f"{REPORTS}/{eu['id']}/fields/3_2A", json={"codes": ["A090811"]}))
    held = _fields(detail)["3_2A"]["value"]
    assert held == "A090811 Unable to Obtain Readings"  # no FDA code on the EU form
    with SessionLocal() as db:
        code = db.query(ImdrfCode).filter_by(release="2026", annex="A", code="A090811").one()
        status = code.status
        code.status = "Retired (2027)"  # as a later release would mark it
        db.commit()
        try:
            again = _fields(_ok(user.get(f"{REPORTS}/{eu['id']}")))["3_2A"]
            assert again["value"] == held  # the report keeps it
            refused = user.put(f"{REPORTS}/{eu['id']}/fields/3_2A", json={"codes": ["A090811"]})
            assert refused.status_code == 422 and refused.json()["detail"]["code"] == "IMDRF_CODE_NOT_SELECTABLE"
            offered = _ok(user.get(CODES, params={"pick": 1, "annex": "A", "q": "unable to obtain readings"}))
            assert "A090811" not in [item["code"] for item in offered["codes"]]
        finally:
            code.status = status
            db.commit()


@pytest.mark.db
def test_the_required_codes_per_report_type_hold_approval(trial):
    user = trial["user"]
    (eu,) = [item for item in _ok(user.get(REPORTS))["items"] if item["complaint_ref"] == "SAMPLE-RV-07"]
    initial = set(_ok(user.get(f"{REPORTS}/{eu['id']}"))["mandatory"]["missing"])
    assert {"3_3A_E", "3_3A_F"} <= initial and not {"4_2E_B", "4_2E_C", "4_2E_D"} & initial
    final = _ok(user.put(f"{REPORTS}/{eu['id']}/fields/1_2E", json={"value": "Final (Reportable incident)"}))
    assert {"4_2E_B", "4_2E_C", "4_2E_D"} <= set(final["mandatory"]["missing"])
    _ok(user.put(f"{REPORTS}/{eu['id']}/fields/1_2E", json={"clear": True}))
    blocked = user.post(f"{REPORTS}/{eu['id']}/snapshots")
    assert blocked.status_code == 422 and "3_3A_E" in blocked.json()["detail"]["missing"]


@pytest.mark.db
def test_product_identity_is_checked_against_the_lists_and_fills_the_forms(trial):
    user = trial["user"]
    (eu,) = [item for item in _ok(user.get(REPORTS))["items"] if item["complaint_ref"] == "SAMPLE-RV-07"]
    product = _ok(user.get("/api/v1/complaints", params={"q": "SAMPLE-RV-07"}))["items"][0]["product_id"]
    path = f"{PRODUCTS}/{product}"
    unknown = user.put(f"{path}/identity", json={"emdn_code": "Z99999999"})
    assert unknown.status_code == 422 and unknown.json()["detail"]["code"] == "EMDN_CODE_UNKNOWN"
    assert user.put(f"{path}/identity", json={"emdn_code": "Z-12"}).json()["detail"]["code"] == "EMDN_CODE_INVALID"
    profile = _ok(user.put(f"{path}/identity", json={"udi_di": "04000000025016", "basic_udi_di": "SAMPLE-BUDI-250",
                                                      "emdn_code": "z12"}))  # fmt: skip
    assert (profile["emdn_code"], profile["basic_udi_di"]) == ("Z12", "SAMPLE-BUDI-250") and profile["emdn_term"]
    refused = user.post(f"{path}/registrations", json={"market": "EU", "registration_type": "CE", "risk_class": "IV",
                                                        "registration_number": "CE-1", "body_name": "NB", "body_number": "0123"})  # fmt: skip
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "RISK_CLASS_UNKNOWN"
    _ok(user.post(f"{path}/registrations", json={"market": "EU", "registration_type": "CE", "risk_class": "iib",
                                                  "registration_number": "CE-1", "body_name": "NB", "body_number": "0123"}))  # fmt: skip
    fake = user.post(f"{path}/registrations", json={"market": "US", "registration_type": "510K",
                                                     "registration_number": "K000001", "product_code": "ZZZ"})  # fmt: skip
    assert fake.status_code == 422 and fake.json()["detail"]["code"] == "PRODUCT_CODE_UNKNOWN"
    party = {"market": "EU", "role": "MANUFACTURER", "organisation": "Sample maker", "srn": "xx-mf-000000001"}
    assert _ok(user.put("/api/v1/regulatory-reference/responsible-parties", json=party))["srn"] == "XX-MF-000000001"
    fields = _fields(_ok(user.get(f"{REPORTS}/{eu['id']}")))
    assert fields["2_4"]["value"] == "IIb" and fields["2_3P_NB"]["value"] == "0123"
    assert fields["1_3_2B"]["value"] == "XX-MF-000000001" and fields["2_1C"]["value"] == "SAMPLE-BUDI-250"
    assert (fields["2_2A"]["value"], fields["2_2B"]["value"]) == ("EMDN", "Z12")


@pytest.mark.db
def test_the_trend_counts_each_lot(trial):
    board = _ok(trial["user"].get("/api/v1/triage/trends", params={"group": "version"}))
    (rising,) = [item for item in board["items"] if item["result"] == "SIGNIFICANT"]
    assert sum(rising["lot_counts"].values()) == rising["recent"] == 9
    assert list(rising["lot_counts"]) == rising["lots"]


@pytest.mark.db
def test_a_running_trial_is_re_recorded_once():
    from backend.app.db.models.authority_reports import ReportObligation
    from backend.app.db.models.regulatory_reference import ImdrfCodeMapping
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.trial import sample_0_10_72, sample_0_10_77
    from backend.app.trial.sample_imports import EARLIER_IMDRF_LINKS

    ensure_loaded()
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            assert sample_0_10_77.refresh(db, tenant_id, apply=False) == 0  # a new trial has them
            rv09 = (
                db.query(ReportObligation)
                .filter_by(tenant_id=tenant_id, form_code="FDA_3500A")
                .filter(ReportObligation.source_system.is_not(None))
                .one()
            )
            assert rv09.entries["H6_PROBLEM"]["code_state"] == "CONFIRMED"
            assert rv09.entries["H6_PROBLEM"]["value"] == "A160103 Low Audible Alarm (FDA 1016)"
            # As a trial made before 0.10.77 had them: the 2025 links, no code entries on RV-09's 3500A.
            back = {new: old for (_, old), new in EARLIER_IMDRF_LINKS.items()}
            rows = [row for row in db.query(ImdrfCodeMapping).filter_by(tenant_id=tenant_id) if row.imdrf_code in back]
            for row in rows:
                row.release, row.imdrf_code = "2025", back[row.imdrf_code]
            rv09.entries = {key: value for key, value in rv09.entries.items() if not key.startswith("H6_") or
                            key == "H6_CONCLUSIONS"}  # fmt: skip
            db.flush()
            assert sample_0_10_77.refresh(db, tenant_id, apply=False) == len(rows) + 3
            assert sample_0_10_72.refresh(db, tenant_id, apply=False) == 0  # 0.10.72 does not add A0908 back
            assert sample_0_10_77.refresh(db, tenant_id, apply=True) == len(rows) + 3
            assert sample_0_10_77.refresh(db, tenant_id, apply=True) == 0  # idempotent
            links = {(row.customer_code, row.release, row.imdrf_code) for row in rows}
            assert ("SPO2_READING_HIGH", "2026", "A090807") in links
            assert ("UNDER_INFUSION_NO_ALARM", "2026", "A160102") in links
            # RV-09 keeps the code it was approved with (A16 then), recorded as confirmed by the sample author.
            frozen = rv09.entries["H6_PROBLEM"]
            assert frozen["code_state"] == "CONFIRMED" and frozen["by"] == rv09.created_by
            assert rv09.entries["H6_CLINICAL"]["value"].startswith("Entered in eSubmitter")
            db.commit()
    finally:
        _purge(tenant_id)
