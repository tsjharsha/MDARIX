"""0.10.56: a free trial's Excel/CSV import is governed like the MVP's (R14 stored quarantine, R16 row lineage, R17
data-quality report), and the sample shows each of them with G2a's regulatory identity.

Through the real API, as the trial user: the sample's import run, its set-aside rows (harm first, personal data
masked), a sample complaint's origin and its IMDRF links, a sample product's UDI-DI and GMDN; then the trial's own
import with a row set aside, its report, its file name, its quarantine and its rows' origin; another trial sees none
of it; removing the sample takes the sample's run with it.
"""

import pytest

from tests.test_free_trial import _approved_trial_client
from tests.test_free_trial import _clean_trial_workspaces  # noqa: F401 (module fixture)

pytestmark = pytest.mark.db

RUNS = "/api/v1/data/import/runs"


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _complaint(user, **filters) -> dict:
    items = _ok(user.get("/api/v1/complaints", params=filters))["items"]
    assert items, filters
    return items[0]


def test_the_sample_shows_an_import_run_its_set_aside_rows_lineage_and_reference_data():
    user, _approval, _email = _approved_trial_client()
    runs = _ok(user.get(RUNS))["runs"]
    # The complaints export, and the distribution export behind a case's Lot impact (sample_lot_impact.py).
    assert sorted(run["entity"] for run in runs) == ["complaints", "distribution"]
    run = next(run for run in runs if run["entity"] == "complaints")
    assert run["sample"] and run["file_name"] == "Sample complaints export.xlsx" and run["entity"] == "complaints"
    report = run["report"]
    total = _ok(user.get("/api/v1/complaints", params={"source_system": "MDARIX_SAMPLE"}))["total"]
    # Every sample complaint came in with the export except SAMPLE-RV-10, the India hospital's report that arrives
    # weeks later (sample_reports.py, 0.10.58, staged after the import run so its counts stay): it has no import.
    assert report["rows_read"] == total - 1 + 2 and report["rows_accepted"] == total - 1
    assert report["rows_quarantined"] == 2 and report["balanced"] is True
    india = _complaint(user, q="SAMPLE-RV-10")
    assert india["complaint_identifier"] == "SAMPLE-RV-10"
    assert _ok(user.get(f"/api/v1/data/import/origin/complaints/{india['id']}"))["imports"] == []

    detail = _ok(user.get(f"{RUNS}/{run['import_ref']}"))
    assert (
        detail["quarantine_now"] == {"open": 2, "reprocessed": 0, "dismissed": 0}
        and detail["imported_by"] == "MDARIX sample author"
    )

    rows = _ok(user.get("/api/v1/data/import/quarantine", params={"import_ref": run["import_ref"]}))["items"]
    assert [row["row"]["complaint_id"] for row in rows] == ["SAMPLE-RJ-02", "SAMPLE-RJ-01"]  # harm first
    harm = rows[0]
    assert harm["suggests_harm"] and harm["harm_words"] == ["hospital"]
    assert "[PERSON]" in harm["row"]["description"] and "Maria" not in harm["row"]["description"]
    assert "555" not in harm["row"]["description"]
    assert any("personal" in problem for problem in harm["problems"])
    assert any("event_date" in problem for problem in harm["problems"])
    assert rows[1]["problems"] == ["description: 'description' is required."]

    complaint = _complaint(user, problem_code="UNDER_INFUSION_NO_ALARM")
    origin = _ok(user.get(f"/api/v1/data/import/origin/complaints/{complaint['id']}"))
    assert origin["key"] == f"{complaint['complaint_identifier']}:{complaint['product_identifier']}"
    (imported,) = origin["imports"]
    assert imported["import_ref"] == run["import_ref"] and imported["line"] >= 2
    assert imported["file_name"] == "Sample complaints export.xlsx" and imported["has_report"]

    links = _ok(
        user.get(
            "/api/v1/regulatory-reference/imdrf/links",
            params=[("code", "UNDER_INFUSION_NO_ALARM"), ("code", "PRESSURE_ALARM"), ("code", "NFF")],
        )
    )["links"]
    # 0.10.77: IMDRF Release 2026's most specific terms (sample_imports.SAMPLE_IMDRF_LINKS).
    assert [link["code"] for link in links["UNDER_INFUSION_NO_ALARM"]] == ["A1407", "A160102"]
    assert [link["code"] for link in links["PRESSURE_ALARM"]] == ["A1601"] and "NFF" not in links

    profile = _ok(user.get(f"/api/v1/regulatory-reference/products/{complaint['product_id']}"))
    assert profile["gmdn_code"] is None and profile["udi_di"] == "04000000030010"
    assert profile["gmdn_term"] == "General-purpose infusion pump"


def test_a_trial_import_is_governed_and_its_report_names_the_file():
    user, _approval, _email = _approved_trial_client()
    csv = (
        "complaint_id,product_id,product_name,description\n"
        "OWN-1,OWN-PUMP,Own Pump,Alarm sounded during priming\n"
        "OWN-2,OWN-PUMP,Own Pump,\n"
        "OWN-3,OWN-PUMP,Own Pump,Door latch loose\n"
    )
    result = _ok(
        user.post(
            "/api/v1/trial/imports/complaints",
            params={"on_problems": "skip", "file_name": "C:\\exports\\Own complaints.csv", "date_column": "none"},
            content=csv,
            headers={"Content-Type": "text/csv"},
        )
    )
    assert result["quarantined_rows"] == 1 and result["import_ref"]
    assert result["quality_report"] == {
        "rows_read": 3,
        "rows_accepted": 2,
        "rows_quarantined": 1,
        "rows_changed": 0,
        "rows_new": 2,
        "rows_unchanged": 0,
        "balanced": True,
        "columns_not_used": [],  # 0.10.65: every column of the file was used
        "row_flags": [],  # 0.10.81: no row contradicts itself or lacks a reporting fact
        "also_created": {"products": 1},  # 0.10.84: the product the file named, counted as loaded by Import
    }
    newest = _ok(user.get(RUNS))["runs"][0]
    assert newest["import_ref"] == result["import_ref"] and newest["file_name"] == "Own complaints.csv"
    assert not newest["sample"] and newest["imported_by"]
    rows = _ok(user.get("/api/v1/data/import/quarantine", params={"import_ref": result["import_ref"]}))["items"]
    assert [(row["line"], row["row"]["complaint_id"]) for row in rows] == [(3, "OWN-2")]

    own = _complaint(user, q="OWN-3")
    (imported,) = _ok(user.get(f"/api/v1/data/import/origin/complaints/{own['id']}"))["imports"]
    assert (imported["import_ref"], imported["line"], imported["file_name"]) == (
        result["import_ref"],
        4,
        "Own complaints.csv",
    )

    # Another organization reads none of it.
    other, _, _ = _approved_trial_client()
    assert other.get(f"{RUNS}/{result['import_ref']}").status_code == 404
    assert other.get(f"/api/v1/data/import/origin/complaints/{own['id']}").status_code == 404
    assert (
        other.get("/api/v1/data/import/quarantine", params={"import_ref": result["import_ref"]}).json()["items"] == []
    )
    assert result["import_ref"] not in {run["import_ref"] for run in _ok(other.get(RUNS))["runs"]}


def test_removing_the_sample_removes_its_import_run():
    user, _approval, _email = _approved_trial_client()
    preview = _ok(user.get("/api/v1/trial/sample-data/removal"))
    assert preview["has_sample"]
    _ok(user.post("/api/v1/trial/sample-data/removal", json={"confirm": True}))
    assert _ok(user.get(RUNS))["runs"] == []
    assert _ok(user.get("/api/v1/data/import/quarantine"))["counts"] == {"open": 0, "reprocessed": 0, "dismissed": 0}
    assert _ok(user.get("/api/v1/regulatory-reference/imdrf/links", params={"code": "PRESSURE_ALARM"}))["links"] == {}
