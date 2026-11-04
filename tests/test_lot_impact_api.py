"""0.10.61, T-G5 (MVP G5 with G26's lot genealogy in cases) through the API as a trial user (migration tr08): the
Distribution import with its set-aside rows and the shipped-beyond-released flag, the case's Lot impact with the
suggested factor, the lots with and without complaints, units by country and in stock, "distribution not imported",
an exclusion with its reason kept with the case scope, the signed list and "changed since signed", the CSV and PDF,
and the pilot that sees none of it."""

from __future__ import annotations

import csv
import io
import uuid
from collections import defaultdict

import pytest

from backend.app.lot_impact import service
from backend.app.trial import business_imports
from tests.conftest import authenticated_client
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_reporting_capa_api import _client

# Database tests by default, its pure tests marked unit (tests/conftest.py DB_WITHOUT_GOLDEN).

ORBIT_LOT = "SAMPLE-ORBIT-300-LOT-{:03d}"


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def trial():
    from backend.app.db.models.foundation import Investigation
    from backend.app.db.session import SessionLocal
    from backend.app.trial.retention import purge_trial

    user, approval, _email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    with SessionLocal() as db:
        case_id = (
            db.query(Investigation.id)
            .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == "SAMPLE-INV-001")
            .scalar()
        )
    try:
        yield {"user": user, "tenant_id": tenant_id, "base": f"/api/v1/investigations/{case_id}/lot-impact"}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:lot-impact-cleanup")


# --------------------------------------------------------------------------------------------- the rules


@pytest.mark.unit
def test_a_shipment_row_needs_a_country_code_and_at_least_one_unit():
    assert business_imports.distribution_problem({"country": "in", "quantity": "1,250"}) is None
    assert business_imports.distribution_problem({"country": "India", "quantity": "5"})[0] == "country"
    assert business_imports.distribution_problem({"country": "UK", "quantity": "5"})[0] == "country"
    assert business_imports.distribution_problem({"country": "US", "quantity": "0"})[0] == "quantity"
    assert business_imports.units("1 250") == 1250 and len(business_imports.COUNTRY_CODES) == 249


@pytest.mark.unit
def test_changes_since_signed_read_in_plain_words():
    def lot(name, **values):
        return {
            "id": name,
            "lot_identifier": name,
            "complaints": 0,
            "released": 30,
            "shipped": None,
            "in_stock": None,
            "distribution_imported": False,
            "by_country": [],
            "excluded": False,
            **values,
        }

    factor = {"id": "f", "label": "Sensor lot A"}
    signed = {"factor": factor, "lots": [lot("L1", complaints=2), lot("L2")]}
    now = {
        "factor": factor,
        "lots": [
            lot("L1", complaints=3),
            lot("L2", distribution_imported=True, shipped=20, in_stock=10, by_country=[{"country": "IN", "units": 20}]),
            lot("L3"),
        ],
    }
    assert service.changes(signed, now) == [
        "L3 now shares the factor",
        "L1: complaints 2 to 3",
        "L2: distribution now imported (20 units shipped)",
    ]
    assert service.changes(signed, signed) == []
    assert service.per_thousand(9, 150) == 60.0 and service.per_thousand(1, None) is None


# --------------------------------------------------------------------------------------------- the sample


def test_the_sample_keeps_the_trend_units_and_adds_genealogy_and_distribution(trial):
    """Lot 005 and the three new lots release 150 units together on lot 005's day, as lot 005 did: the trend check's
    units in the field (by release day and quantity) are those of 0.10.60, so the rise and the signal stay."""
    from backend.app.db.models.foundation import Complaint, LotBatch, LotComponent, ProductVersion
    from backend.app.db.session import SessionLocal

    tenant_id = trial["tenant_id"]
    with SessionLocal() as db:
        rev_b = (
            db.query(LotBatch)
            .join(ProductVersion, ProductVersion.id == LotBatch.product_version_id)
            .filter(LotBatch.tenant_id == tenant_id, LotBatch.lot_identifier.like("SAMPLE-ORBIT-300-LOT-%"))
            .filter(ProductVersion.version_identifier == "Rev B")
            .all()
        )
        units = defaultdict(int)
        for lot in rev_b:
            units[lot.effective_timestamp.date()] += lot.quantity
        assert sorted(units.values()) == [150, 150, 150] and len(rev_b) == 6
        assert db.query(Complaint).filter(Complaint.tenant_id == tenant_id).count() == 44  # with the flagship
        new = [lot.id for lot in rev_b if lot.lot_identifier[-3:] in ("006", "007", "008")]
        assert db.query(Complaint).filter(Complaint.lot_batch_id.in_(new)).count() == 0
        assert db.query(LotComponent).filter(LotComponent.tenant_id == tenant_id).count() == 12
    board = _ok(trial["user"].get("/api/v1/triage/trends", params={"group": "version"}))
    orbit = next(item for item in board["items"] if item["name"] == "OrbitCare 300 Infusion Pump (Sample) Rev B")
    assert orbit["result"] == "SIGNIFICANT" and orbit["basis"] == "UNITS"
    # The insights now read the genealogy: the two lots with most complaints share the sensor lot.
    insights = _ok(trial["user"].get("/api/v1/trial/insights"))
    lots = next(item for item in insights["questions"] if item["key"] == "lots")["answer"]
    assert any("NS-SL-2417 (Sample)" in fact for fact in lots["facts"])
    assert not any("do not link a lot to the component lots" in line for line in lots["missing"])


def test_the_sample_distribution_run_sets_a_row_aside_and_flags_a_lot(trial):
    runs = _ok(trial["user"].get("/api/v1/data/import/runs"))["runs"]
    run = next(item for item in runs if item["entity"] == "distribution")
    assert run["sample"] and run["file_name"] == "Sample distribution export.csv"
    report = run["report"]
    assert report["balanced"] and report["rows_quarantined"] == 1
    assert [flag["lot_id"] for flag in report["flags"]] == ["SAMPLE-PULSE-410-LOT-002"]
    aside = _ok(trial["user"].get("/api/v1/data/import/quarantine", params={"import_ref": run["import_ref"]}))
    assert "is not in your workspace" in aside["items"][0]["problems"][0]


# --------------------------------------------------------------------------------------------- the list


def test_the_case_suggests_the_sensor_lot_and_lists_the_lots_that_share_it(trial):
    screen = _ok(trial["user"].get(trial["base"]))
    assert "recommends no recall" in screen["never_decides"] and screen["practice_label"]
    assert screen["suggestion"]["label"] == "Pressure Sensor (Sample) lot NS-SL-2417 (Sample)"
    assert screen["suggestion"]["why"] == "2 of the investigation's 2 lots share it"
    assert screen["source"] == "suggested" and screen["saved"] is None and screen["signed"] is None
    kinds = {item["kind"] for item in screen["options"]}
    assert kinds == {"COMPONENT_LOT", "SUPPLIER", "PRODUCT_VERSION"}
    listed = screen["list"]
    lots = {row["lot_identifier"]: row for row in listed["lots"]}
    assert set(lots) == {ORBIT_LOT.format(n) for n in (3, 4, 6, 7, 8)}
    assert [row["lot_identifier"] for row in listed["lots"]][:2] == [ORBIT_LOT.format(3), ORBIT_LOT.format(4)]
    assert lots[ORBIT_LOT.format(3)]["per_1000"] == 60.0  # 9 complaints of 150 units
    assert lots[ORBIT_LOT.format(4)]["in_stock"] == 30
    eight = lots[ORBIT_LOT.format(8)]
    assert eight["distribution_imported"] is False and eight["shipped"] is None and eight["in_stock"] is None
    assert lots[ORBIT_LOT.format(6)]["evidence"][0].startswith("Lot genealogy: built with Pressure Sensor (Sample)")
    totals = listed["totals"]
    assert (totals["with_complaints"], totals["without_complaints"], totals["not_imported"]) == (2, 3, 1)
    assert {item["country"] for item in totals["by_country"]} == {"US", "IN", "DE", "FR"}
    assert totals["released"] == 390 and totals["shipped"] == 310 and totals["in_stock"] == 50

    supplier = next(item for item in screen["options"] if item["label"] == "NovaSense Components (Sample)")
    preview = _ok(trial["user"].get(trial["base"], params={"kind": "SUPPLIER", "ref": supplier["id"]}))
    assert preview["source"] == "preview" and preview["list"]["totals"]["lots"] == 6  # lot 005 too
    assert trial["user"].get(trial["base"], params={"kind": "SUPPLIER", "ref": str(uuid.uuid4())}).status_code == 404


def test_an_exclusion_needs_a_reason_and_is_kept_with_the_case_scope(trial):
    user, base = trial["user"], trial["base"]
    screen = _ok(user.get(base))
    factor = {key: screen["suggestion"][key] for key in ("kind", "id", "lot")}
    lot_8 = next(row["id"] for row in screen["list"]["lots"] if row["lot_identifier"] == ORBIT_LOT.format(8))
    short = user.put(base, json={"factor": factor, "excluded": [{"lot_id": lot_8, "reason": "No"}]})
    assert short.status_code == 422 and short.json()["detail"]["code"] == "EXCLUSION_REASON_REQUIRED"
    stranger = user.put(base, json={"factor": factor, "excluded": [{"lot_id": str(uuid.uuid4()), "reason": "x" * 20}]})
    assert stranger.status_code == 422
    reason = "Lot 008 is quarantined in our warehouse and has not shipped."
    saved = _ok(user.put(base, json={"factor": factor, "excluded": [{"lot_id": lot_8, "reason": reason}]}))
    assert saved["source"] == "saved" and saved["saved"]["factor"]["kind"] == "COMPONENT_LOT"
    assert saved["list"]["totals"]["lots"] == 4 and saved["list"]["totals"]["excluded"] == 1
    # Saving the same list again writes no new version.
    again = _ok(user.put(base, json={"factor": factor, "excluded": [{"lot_id": lot_8, "reason": reason}]}))
    assert again["saved"]["scope_version"] == saved["saved"]["scope_version"]
    scope = _ok(user.get(base.replace("/lot-impact", "/scope")))
    left_out = scope["current"]["excluded_lots"]
    assert [(item["id"], item["lot_identifier"], item["reason"]) for item in left_out] == [
        (lot_8, ORBIT_LOT.format(8), reason)
    ]
    assert len(scope["current"]["lots"]) == 4 and scope["current"]["change_reason"].startswith("Lot impact on ")


def test_the_person_signs_the_list_and_a_later_import_shows_changed_since_signed(trial):
    user, base, tenant_id = trial["user"], trial["base"], trial["tenant_id"]
    screen = _ok(user.get(base))
    factor = {key: screen["saved"]["factor"][key] for key in ("kind", "id", "lot")}
    # Put lot 008 back: the person signs all five lots.
    screen = _ok(user.put(base, json={"factor": factor, "excluded": []}))
    fingerprint = screen["list"]["fingerprint"]
    viewer, investigator = _client(tenant_id, "VIEWER"), _client(tenant_id, "INVESTIGATOR")
    assert viewer.put(base, json={"factor": factor}).status_code == 403
    body = {"password": PASSWORD, "fingerprint": fingerprint}
    assert investigator.post(f"{base}/sign", json=body).status_code == 403  # prepares, does not sign
    assert user.post(f"{base}/sign", json={**body, "password": "not the password"}).status_code == 403
    stale = user.post(f"{base}/sign", json={**body, "fingerprint": "0" * 64})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "LIST_CHANGED"
    signed = _ok(user.post(f"{base}/sign", json=body))["signed"]
    assert signed["changed"] is False and signed["changes"] == []
    assert signed["signature"]["content_fingerprint"] == fingerprint
    assert "recommends no field action" in signed["signature"]["meaning"]

    # Lot 008's distribution comes in: the signed list stays as signed and the screen says what changed.
    shipment = "lot_id,consignee,country,quantity,ship_date\nSAMPLE-ORBIT-300-LOT-008,Rheinwald Clinic (Sample),DE,12,2026-10-20\n"
    _ok(user.post("/api/v1/trial/imports/distribution", content=shipment))
    after = _ok(user.get(base))["signed"]
    assert after["changed"] is True
    assert after["changes"] == ["SAMPLE-ORBIT-300-LOT-008: distribution now imported (12 units shipped)"]
    assert {row["lot_identifier"]: row for row in after["list"]["lots"]}[ORBIT_LOT.format(8)]["shipped"] is None

    exported = user.get(f"{base}/list.csv")
    assert exported.status_code == 200
    rows = list(csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"))))
    assert {row["record"] for row in rows} == {"Practice record"}
    assert any(row["lot"] == ORBIT_LOT.format(8) and row["consignee"] == "Distribution not imported" for row in rows)
    pdf = user.get(f"{base}/list.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert viewer.get(f"{base}/list.csv").status_code == 403


def test_the_distribution_import_sets_unknown_lots_aside_and_flags_over_shipping(trial):
    user = trial["user"]
    templates = _ok(user.get("/api/v1/trial/status"))["templates"]
    distribution = next(item for item in templates if item["entity"] == "distribution")
    assert "consignee" in distribution["help"] and distribution["required"][:2] == ["lot_id", "consignee"]
    rows = (
        "Lot Number,Ship To Name,Country Code,Qty,Ship Date\n"
        "SAMPLE-ORBIT-300-LOT-004,Bluegate Medical Supply (Sample),US,40,2026-10-21\n"
        "NO-SUCH-LOT,Bluegate Medical Supply (Sample),US,5,2026-10-21\n"
        "SAMPLE-ORBIT-300-LOT-004,Bluegate Medical Supply (Sample),Germany,5,2026-10-22\n"
    )
    checked = _ok(user.post("/api/v1/trial/imports/distribution/check", content=rows))
    assert not checked["ready"]
    messages = {issue["column"]: issue["message"] for issue in checked["issues"]}
    assert "not in your workspace" in messages["lot_id"] and "ISO country code" in messages["country"]
    done = _ok(user.post("/api/v1/trial/imports/distribution", params={"on_problems": "skip"}, content=rows))
    report = done["quality_report"]
    assert report["rows_accepted"] == 1 and report["rows_quarantined"] == 2 and report["balanced"]
    # Lot 004 released 150 and has now shipped 160.
    assert [flag["lot_id"] for flag in report["flags"]] == ["SAMPLE-ORBIT-300-LOT-004"]
    assert "160 units shipped, 150 released" in report["flags"][0]["message"]


def test_a_pilot_sees_neither_the_lot_impact_nor_the_distribution_import():
    admin = authenticated_client()
    case = admin.get(f"/api/v1/investigations/{uuid.uuid4()}/lot-impact")
    assert case.status_code == 404 and case.json()["detail"]["code"] == "NOT_A_TRIAL_WORKSPACE"
    templates = _ok(admin.get("/api/v1/data/import/templates"))["templates"]
    assert "distribution" not in {item["entity"] for item in templates}
    assert "lot_genealogy" in {item["entity"] for item in templates}
    refused = admin.post("/api/v1/data/import/distribution/check", content="lot_id\nL1\n")
    assert refused.status_code == 404
    assert admin.get("/api/v1/data/import/templates/distribution.csv").status_code == 404
