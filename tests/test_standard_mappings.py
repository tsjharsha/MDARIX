"""The MDARIX standard mappings take every CSV template, as the customer systems serve it, into a tenant's records.

Each standard mapping must pass the same check as a mapping built by hand (the release gate), and loading every
template through its mapping, in the documented order, must import the whole connected story with nothing refused.
"""

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from backend.app.access.connector_mapping import check_mapping, import_connector_records
from backend.app.db.session import SessionLocal, engine
from backend.app.db.tenant_scope import bind_tenant, system_token
from backend.app.trial.retention import TRIAL_DATA_TABLES
from tests.test_customer_admin_account_security import _tenant

ROOT = Path(__file__).resolve().parents[1]
MAPPINGS = json.loads((ROOT / "backend" / "app" / "access" / "standard_mappings.json").read_text(encoding="utf-8"))


def _records(application: str, record: str) -> list[dict]:
    with (ROOT / "data" / "source-templates" / application / f"{record}.csv").open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def tenant_id():
    with SessionLocal() as db:
        tenant = _tenant(db, "STDMAP")
        db.commit()
        identifier = tenant.id
    yield identifier
    with engine.begin() as connection:
        connection.execute(text("SELECT set_config('app.rls_bypass', :token, true)"), {"token": system_token()})
        for table in (*TRIAL_DATA_TABLES, "evidence_entity_links"):
            connection.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tenant"), {"tenant": identifier})


@pytest.mark.parametrize("mapping", MAPPINGS, ids=[item["code"] for item in MAPPINGS])
def test_every_standard_mapping_passes_the_release_check(mapping):
    result = check_mapping(mapping["target_entity"], mapping["mapping_rules"])
    assert result["status"] == "READY", result


def test_loading_every_template_in_order_imports_the_whole_story(tenant_id):
    outcomes = {}
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        for mapping in MAPPINGS:  # the file is in load order
            stored = SimpleNamespace(
                code=mapping["code"], target_entity=mapping["target_entity"], mapping_rules=mapping["mapping_rules"]
            )
            result = import_connector_records(
                db, tenant_id, mapping["code"], stored, _records(mapping["application"], mapping["record"])
            )
            assert result["status"] == "IMPORTED", (mapping["code"], result)
            db.commit()
            outcomes[mapping["code"]] = result

    def count(table: str, where: str = "") -> int:
        with engine.connect() as connection:
            connection.execute(text("SELECT set_config('app.rls_bypass', :token, false)"), {"token": system_token()})
            return connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE tenant_id = :tenant {where}"), {"tenant": tenant_id}
            ).scalar()

    # Items that are products and items that are components are split by the mappings' filters.
    assert outcomes["TEAMCENTER_ITEMS_PRODUCT"]["skipped"] == 4
    assert count("products") == 2 and count("product_versions") == 3
    assert count("components") == 6  # PS-110, MB-220, FW-AF200, BAT-18, DSP-31, CC-07
    assert count("complaints") == 6  # 4 from TrackWise, 2 complaint-type quality events from Veeva
    assert count("complaints", "AND severity IS NOT NULL AND patient_involved IS NOT NULL") == 4
    assert count("investigations") == 2 and count("investigation_complaints") == 4
    assert count("capas") == 3 and count("lot_batches") == 5 and count("lot_components") >= 4
    assert count("risks") == 2 and count("controls") == 2 and count("requirements") == 2
    assert count("product_components") == 7 and count("component_suppliers") == 4
    assert count("evidence", "AND evidence_type = 'SOURCE_RECORD'") >= 6


def test_administrators_can_start_from_a_standard_mapping():
    from tests.conftest import authenticated_client

    admin = authenticated_client()
    found = admin.get("/api/v1/admin/configuration/standard-mappings?application=teamcenter&record=items").json()
    targets = sorted(item["target_entity"] for item in found["mappings"])
    assert targets == ["Component", "Product"]
    product = next(item for item in found["mappings"] if item["target_entity"] == "Product")
    assert product["mapping_rules"]["_filter"] == {"field": "item_type", "in": ["Product"]}
    assert len(admin.get("/api/v1/admin/configuration/standard-mappings").json()["mappings"]) == len(MAPPINGS)
