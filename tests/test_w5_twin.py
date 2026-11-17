"""W5 (spec section 7): the Product Lifecycle Twin through the API as a trial user. The connected view of OrbitCare 300
Rev B, a change's impact and a preview of one, the field-action scope (its fingerprint the lot impact list's own, by
site beside it), the CSV and its audit, the simulated PLM, ERP and eQMS runs (balanced, idempotent, no record added,
kept out of /runs), another organization and a pilot that see none of it, sample removal and restart, the refresh of
an older trial and the query budgets."""

from __future__ import annotations

import csv
import io
import uuid

import pytest

from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.conftest import authenticated_client
from tests.test_free_trial import _approved_trial_client
from tests.test_reporting_capa_api import _client

pytestmark = pytest.mark.db

ORBIT = "SAMPLE-ORBIT-300"
LOT = ORBIT + "-LOT-{:03d}"
SENSOR_LOT = "NS-SL-2417 (Sample)"
SCOPE = {"kind": "COMPONENT_LOT", "ref": f"{ORBIT}-C1", "lot": SENSOR_LOT}
SOURCES, RUNS = "/api/v1/data/import/sources", "/api/v1/data/import/runs"


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _purge(tenant_id) -> None:
    from backend.app.trial.retention import purge_trial

    with SessionLocal() as db:
        purge_trial(db, tenant_id, "test:w5-twin-cleanup")


@pytest.fixture(scope="module")
def trial():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        _purge(tenant_id)


def _business_counts(tenant_id) -> dict[str, int]:
    from sqlalchemy import text

    tables = ("products", "product_versions", "components", "product_components", "suppliers", "changes")
    tables += ("lot_batches", "lot_components", "lot_distributions", "capas", "complaints", "investigations")
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return {
            table: db.execute(text(f"SELECT count(*) FROM {table} WHERE tenant_id=:t"), {"t": tenant_id}).scalar()
            for table in tables
        }


# 1, 2 ------------------------------------------------------------------------------------------ the connected view


def test_the_connected_view_of_rev_b_counts_every_link_in_the_chain(trial):
    view = _ok(trial["user"].get(f"/api/v1/products/{ORBIT}/twin", params={"version": "Rev B"}))
    assert view["version"]["version_identifier"] == "Rev B"
    assert {part["component_identifier"] for part in view["components"]} == {f"{ORBIT}-C{n}" for n in (1, 2, 3)}
    assert {row["name"] for row in view["suppliers"]} == {
        "NovaSense Components (Sample)",
        "Precision Sensors Ltd (Sample)",
    }
    assert [lot["lot_identifier"] for lot in view["lots"]] == [LOT.format(n) for n in range(3, 9)]
    lots = {lot["lot_identifier"]: lot for lot in view["lots"]}
    assert lots[LOT.format(8)]["distribution_imported"] is False and lots[LOT.format(8)]["shipped"] is None
    assert lots[LOT.format(3)]["complaints"] > 0 and lots[LOT.format(6)]["complaints"] == 0
    trace = view["trace"]
    assert trace["lot"] == SENSOR_LOT and trace["lots_with_complaints"] == 2 and len(trace["lots"]) == 5
    assert trace["scope"].startswith("COMPONENT_LOT:") and trace["scope"].endswith(f":{SENSOR_LOT}")
    assert view["component_lots"][0] == trace
    assert {item["country"] for item in view["markets"]["by_country"]} == {"US", "IN", "DE", "FR", "NL"}
    assert len(view["markets"]["sites"]) == 7 and view["markets"]["not_imported"] == 1
    assert view["complaints"]["total"] >= view["complaints"]["open"] > 0
    assert "SAMPLE-INV-001" in {row["investigation_identifier"] for row in view["investigations"]}
    assert {row["risk_identifier"] for row in view["risks"]} == {"SAMPLE-RSK-01", "SAMPLE-RSK-02"}
    capa = next(row for row in view["capas"] if row["capa_identifier"] == "SAMPLE-CAPA-02")
    assert capa["check"]["state"] in {"PLANNED", "NONE"}
    assert [row["change_identifier"] for row in view["changes"]] == ["SAMPLE-CHG-014"]
    sources = view["sources"]
    assert sources["simulated"] and sources["label"] == "Simulated, not a live connection"
    assert all(caption.endswith("Simulated, not a live connection") for caption in sources["captions"].values())
    assert sources["captions"]["parts"].startswith("From PLM") and sources["captions"]["lots"].startswith("From ERP")


def test_without_a_version_the_twin_is_product_level_only(trial):
    view = _ok(trial["user"].get(f"/api/v1/products/{ORBIT}/twin"))
    assert view["version"] is None
    assert view["components"] == [] and view["lots"] == [] and view["component_lots"] == [] and view["trace"] is None
    assert view["markets"]["by_country"] == [] and view["markets"]["sites"] == []
    assert view["complaints"]["total"] > 0 and view["limits"][0].startswith("No version chosen")
    missing = trial["user"].get(f"/api/v1/products/{ORBIT}/twin", params={"version": "Rev Z"})
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "VERSION_NOT_FOUND"


# 3, 4 ------------------------------------------------------------------------------------------- change impact


def test_chg_014_impact_lists_rev_b_its_lots_risks_capa_and_case(trial):
    impact = _ok(trial["user"].get(f"/api/v1/products/{ORBIT}/change-impact", params={"change": "SAMPLE-CHG-014"}))
    assert impact["preview"] is False and impact["change"]["change_identifier"] == "SAMPLE-CHG-014"
    assert [row["version_identifier"] for row in impact["versions"]] == ["Rev B"]
    assert impact["versions"][0]["basis"].startswith("The change record names Pressure Sensor (Sample)")
    assert sorted(lot["lot_identifier"] for lot in impact["lots"]) == [LOT.format(n) for n in range(3, 9)]
    assert impact["lots"][0]["complaints"] >= impact["lots"][-1]["complaints"]  # complaints first
    assert all(lot["basis"] == "Builds Rev B (lot record)" for lot in impact["lots"])
    assert {row["risk_identifier"] for row in impact["risks"]} == {"SAMPLE-RSK-01", "SAMPLE-RSK-02"}
    assert all(row["basis"] for row in impact["risks"])
    assert [row["capa_identifier"] for row in impact["capas"]] == ["SAMPLE-CAPA-02"]
    assert impact["capas"][0]["check"]["label"]
    assert "SAMPLE-INV-001" in {row["investigation_identifier"] for row in impact["investigations"]}
    before_after = impact["before_after"]
    assert before_after["after"] > 0 and before_after["basis"]
    assert impact["markets"]["not_imported"] == 1 and impact["open_complaints"]["count"] > 0
    assert impact["scope"]["lot"] == SENSOR_LOT
    for missing in ({"change": "SAMPLE-CHG-999"}, {"component": str(uuid.uuid4())}, {}):
        refused = trial["user"].get(f"/api/v1/products/{ORBIT}/change-impact", params=missing)
        assert refused.status_code == 404, missing


def test_a_preview_by_component_or_by_supplier_writes_nothing(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    view = _ok(user.get(f"/api/v1/products/{ORBIT}/twin", params={"version": "Rev B"}))
    board = next(part for part in view["components"] if part["component_identifier"] == f"{ORBIT}-C2")
    novasense = next(row for row in view["suppliers"] if row["name"] == "NovaSense Components (Sample)")
    before = _business_counts(tenant_id)
    base = f"/api/v1/products/{ORBIT}/change-impact"
    by_board = _ok(user.get(base, params={"component": board["id"]}))
    assert by_board["preview"] is True and by_board["change"] is None and by_board["before_after"] is None
    # The control board is in Rev A's configuration and in Rev B's.
    assert sorted(row["version_identifier"] for row in by_board["versions"]) == ["Rev A", "Rev B"]
    assert by_board["versions"][0]["basis"].startswith("Bill of materials:")
    by_supplier = _ok(user.get(base, params={"supplier": novasense["id"]}))
    assert [row["version_identifier"] for row in by_supplier["versions"]] == ["Rev B"]
    assert {part["component_identifier"] for part in by_supplier["components"]} == {f"{ORBIT}-C1"}
    assert _business_counts(tenant_id) == before


# 5, 6, 7 -------------------------------------------------------------------------------------- field-action scope


def test_the_field_action_scope_of_the_sensor_lot(trial):
    scope = _ok(trial["user"].get("/api/v1/field-scope", params=SCOPE))
    lots = {row["lot_identifier"]: row for row in scope["lots"]}
    assert set(lots) == {LOT.format(n) for n in (3, 4, 6, 7, 8)}
    totals = scope["totals"]
    assert (totals["lots"], totals["with_complaints"], totals["not_imported"]) == (5, 2, 1)
    assert (totals["released"], totals["shipped"], totals["in_stock"]) == (390, 310, 50)
    assert {item["country"] for item in scope["by_market"]} == {"US", "IN", "DE", "FR"}
    assert len(scope["by_site"]) == 6 and sum(site["units"] for site in scope["by_site"]) == 310
    assert lots[LOT.format(8)]["distribution_imported"] is False and lots[LOT.format(8)]["shipped"] is None
    assert len(scope["cannot_tell"]) == 8 and "No recall recommendation" in scope["cannot_tell"][6]
    assert "recommends no recall" in scope["never_decides"] and scope["whole_organization"] is True
    assert [row["investigation_identifier"] for row in scope["investigations"]] == ["SAMPLE-INV-001"]
    assert [row["change_identifier"] for row in scope["changes"]] == ["SAMPLE-CHG-014"]
    by_id = _ok(trial["user"].get("/api/v1/field-scope", params={**SCOPE, "ref": scope["factor"]["id"]}))
    assert by_id["fingerprint"] == scope["fingerprint"]
    refused = trial["user"].get("/api/v1/field-scope", params={**SCOPE, "lot": "NS-SL-0000"})
    assert refused.status_code == 404 and refused.json()["detail"]["code"] == "FACTOR_NOT_FOUND"


def test_by_site_stays_outside_the_fingerprinted_list(trial):
    from backend.app.db.models.foundation import Investigation
    from backend.app.human_decision.rules import fingerprint

    user, tenant_id = trial["user"], trial["tenant_id"]
    scope = _ok(user.get("/api/v1/field-scope", params=SCOPE))
    material = {
        "factor": {key: scope["factor"][key] for key in ("kind", "id", "lot", "label")},
        "lots": scope["lots"],
        "totals": scope["totals"],
    }
    assert fingerprint(material) == scope["fingerprint"]
    assert fingerprint({**material, "by_site": scope["by_site"]}) != scope["fingerprint"]
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        case = (
            db.query(Investigation.id)
            .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == "SAMPLE-INV-001")
            .scalar()
        )
    # The case's Lot impact suggests the same sensor lot: the same list signs the same fingerprint.
    listed = _ok(user.get(f"/api/v1/investigations/{case}/lot-impact"))["list"]
    assert listed["factor"]["lot"] == SENSOR_LOT and listed["fingerprint"] == scope["fingerprint"]
    assert "by_site" not in listed


def test_the_scope_csv_is_audited_and_needs_data_export(trial):
    from backend.app.db.models.foundation import AuditEvent

    user, tenant_id = trial["user"], trial["tenant_id"]
    response = user.get("/api/v1/field-scope.csv", params=SCOPE)
    assert response.status_code == 200, response.text
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert {row["record"] for row in rows} == {"Practice record"}
    eight = [row for row in rows if row["lot"] == LOT.format(8)]
    assert len(eight) == 1 and eight[0]["consignee"] == "Distribution not imported" and eight[0]["units"] == ""
    assert sum(int(row["units"]) for row in rows if row["units"]) == 310
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        audit = db.query(AuditEvent).filter(
            AuditEvent.tenant_id == tenant_id, AuditEvent.action == "FIELD_ACTION_SCOPE_EXPORTED"
        )
        assert audit.count() == 1 and audit.one().details["lots"] == 5
    viewer = _client(tenant_id, "VIEWER")
    assert viewer.get("/api/v1/field-scope.csv", params=SCOPE).status_code == 403
    assert viewer.get("/api/v1/field-scope", params=SCOPE).status_code == 200  # reading is open to members


# 8, 9 ------------------------------------------------------------------------------------- isolation and the pilot


def test_another_organization_and_a_pilot_see_none_of_it(trial):
    scope = _ok(trial["user"].get("/api/v1/field-scope", params=SCOPE))
    other, approval, _ = _approved_trial_client()
    try:
        assert other.get("/api/v1/field-scope", params={**SCOPE, "ref": scope["factor"]["id"]}).status_code == 404
        change = _ok(trial["user"].get(f"/api/v1/products/{ORBIT}/change-impact", params={"change": "SAMPLE-CHG-014"}))
        refused = other.get(f"/api/v1/products/{ORBIT}/change-impact", params={"change": change["change"]["id"]})
        assert refused.status_code == 404
        product = _ok(trial["user"].get(f"/api/v1/products/{ORBIT}/twin"))["product"]["id"]
        assert other.get(f"/api/v1/products/{product}/twin").status_code == 404
    finally:
        _purge(uuid.UUID(approval["tenant_id"]))
    pilot = authenticated_client()
    for path in (
        f"/api/v1/products/{ORBIT}/twin",
        f"/api/v1/products/{ORBIT}/change-impact?change=SAMPLE-CHG-014",
        "/api/v1/field-scope?kind=COMPONENT_LOT&ref=x&lot=y",
        "/api/v1/field-scope.csv?kind=COMPONENT_LOT&ref=x&lot=y",
        SOURCES,
    ):
        refused = pilot.get(path)
        assert refused.status_code == 404 and refused.json()["detail"]["code"] == "NOT_A_TRIAL_WORKSPACE", path


# 10, 11 -------------------------------------------------------------------------------------- the simulated runs


EXPECTED = {
    # file name: (system, entity, written, set aside, a word of the set-aside reason)
    "items and revisions (Simulated).csv": ("PLM", "products", 2, 1, "Duplicate of row"),
    "bill of materials (Simulated).csv": ("PLM", "bom", None, 1, "SAMPLE-ORBIT-300-C9"),
    "change orders (Simulated).csv": ("PLM", "changes", 1, 0, None),
    "suppliers (Simulated).csv": ("ERP", "suppliers", 2, 0, None),
    "batches (Simulated).csv": ("ERP", "lots", 8, 1, "12O"),
    "batch where-used (Simulated).csv": ("ERP", "lot_genealogy", 12, 1, "Duplicate of row"),
    "CAPAs (Simulated).csv": ("eQMS", "capas", 1, 1, "SAMPLE-INV-099"),
}


def test_the_seven_simulated_runs_balance_with_the_real_reasons_and_add_nothing(trial):
    from backend.app.db.models.ingestion import ImportQuarantineRow
    from backend.app.trial.sample_sources import stage_sample_sources

    user, tenant_id = trial["user"], trial["tenant_id"]
    sources = _ok(user.get(SOURCES))
    assert sources["label"] == "Simulated, not a live connection" and sources["added_after_start"] is False
    assert [system["key"] for system in sources["systems"]] == ["PLM", "ERP", "eQMS"]
    runs = {run["file_name"]: (system["key"], run) for system in sources["systems"] for run in system["runs"]}
    simulated = {name: item for name, item in runs.items() if item[1]["simulated"]}
    assert set(simulated) == set(EXPECTED)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        reasons = {
            str(row.import_ref): row.problems
            for row in db.query(ImportQuarantineRow).filter(ImportQuarantineRow.tenant_id == tenant_id)
        }
    for name, (system, entity, written, aside, reason) in EXPECTED.items():
        key, run = simulated[name]
        report = run["report"]
        assert key == system and run["entity"] == entity, name
        assert report["balanced"] and run["reconciled"] and run["lineage_rows"] == report["rows_accepted"], name
        assert report["rows_quarantined"] == aside and (written is None or report["rows_accepted"] == written), name
        assert run["columns"] and run["not_used"] == report["columns_not_used"], name
        assert all(item["header"] and item["column"] for item in run["columns"]), name
        if reason:
            assert any(reason in problem for problem in reasons[run["import_ref"]]), (name, reasons[run["import_ref"]])
    # The two earlier sample runs are the eQMS's complaints and the ERP's shipments.
    assert runs["Sample complaints export.xlsx"][0] == "eQMS" and runs["Sample distribution export.csv"][0] == "ERP"
    before = _business_counts(tenant_id)
    triage = _ok(user.get("/api/v1/data/import/quarantine"))["counts"]
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        from datetime import datetime, timezone

        assert stage_sample_sources(db, tenant_id, datetime.now(timezone.utc)) == {"created": False}  # once
    assert _business_counts(tenant_id) == before
    assert _ok(user.get("/api/v1/data/import/quarantine"))["counts"] == triage


def test_runs_leaves_the_simulated_runs_out_and_sources_needs_records_write(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    assert sorted(run["entity"] for run in _ok(user.get(RUNS))["runs"]) == ["complaints", "distribution"]
    sources = _ok(user.get(SOURCES))
    one = next(run for system in sources["systems"] for run in system["runs"] if run["entity"] == "capas")
    assert _ok(user.get(f"{RUNS}/{one['import_ref']}"))["file_name"] == "CAPAs (Simulated).csv"
    assert _client(tenant_id, "VIEWER").get(SOURCES).status_code == 403


# 12, 13 ------------------------------------------------------------------------------- removal, restart, refresh


def _script():
    import importlib.util

    spec = importlib.util.spec_from_file_location("refresh_trial_story", "scripts/refresh_trial_story.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return script


def test_sample_removal_takes_the_runs_and_a_restart_brings_them_back():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        _ok(user.post("/api/v1/trial/sample-data/removal", json={"confirm": True}))
        assert all(system["runs"] == [] for system in _ok(user.get(SOURCES))["systems"])
        assert _ok(user.get(SOURCES))["added_after_start"] is None
        _ok(user.post("/api/v1/trial/sample-data/restart", json={"confirm": True}))
        runs = [run for system in _ok(user.get(SOURCES))["systems"] for run in system["runs"]]
        assert len([run for run in runs if run["simulated"]]) == 7
    finally:
        _purge(tenant_id)


def test_the_refresh_adds_the_simulated_runs_to_an_older_trial_once():
    from sqlalchemy import text

    from backend.app.trial.sample_data import SAMPLE_SOURCE
    from backend.app.trial.sample_sources import ENTITIES

    script = _script()
    user, approval, _ = _approved_trial_client()
    tenant_id, key = uuid.UUID(approval["tenant_id"]), approval["tenant_key"]
    try:
        # An older trial: no simulated run yet (its audit records stay: a run without its rows is not listed).
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            for table in ("import_lineage", "import_quarantine_rows"):
                db.execute(
                    text(f"DELETE FROM {table} WHERE tenant_id=:t AND source=:s AND entity = ANY(:e)"),
                    {"t": tenant_id, "s": SAMPLE_SOURCE, "e": ENTITIES},
                )
            db.commit()
        older = _ok(user.get(SOURCES))
        assert older["added_after_start"] is None
        assert sorted(run["entity"] for system in older["systems"] for run in system["runs"]) == [
            "complaints",
            "distribution",
        ]
        with SessionLocal() as db:
            planned = {item["tenant"]: item for item in script.refresh(db, apply=False)}[key]
        assert "the simulated sources (W5)" in planned["sample"]
        with SessionLocal() as db:
            script.refresh(db, apply=True)
        refreshed = _ok(user.get(SOURCES))
        assert len([run for system in refreshed["systems"] for run in system["runs"] if run["simulated"]]) == 7
        with SessionLocal() as db:
            assert {item["tenant"]: item["result"] for item in script.refresh(db, apply=False)}[
                key
            ] == "already has the story"
    finally:
        _purge(tenant_id)


# 14 ------------------------------------------------------------------------------------------------ query budgets
# The budgets themselves, flat with the organization's size, are in tests/test_b6a_query_budget.py.


def test_each_read_stays_in_its_query_budget_and_under_half_a_second(trial):
    import time
    from types import SimpleNamespace

    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    from backend.app.data_import_router import import_sources
    from backend.app.product360 import twin

    tenant = str(trial["tenant_id"])
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        reads = {
            "twin": (30, lambda: twin.twin(db, tenant, ORBIT, "Rev B")),
            "impact": (25, lambda: twin.change_impact(db, tenant, ORBIT, "SAMPLE-CHG-014")),
            "scope": (12, lambda: twin.field_scope(db, tenant, twin.factor_of(db, tenant, **SCOPE))),
            "sources": (8, lambda: import_sources(ctx=SimpleNamespace(tenant_id=tenant), db=db, data=db)),
        }
        for name, (limit, read) in reads.items():
            read()  # the first call warms what a process keeps (not counted)
            seen = {"count": 0}

            def count(*_args, **_kwargs):
                seen["count"] += 1

            event.listen(Engine, "before_cursor_execute", count)
            try:
                start = time.perf_counter()
                read()
                took = time.perf_counter() - start
            finally:
                event.remove(Engine, "before_cursor_execute", count)
            assert seen["count"] <= limit and took < 0.5, (name, seen["count"], limit, round(took, 3))
