"""Every business record the customer systems hold can be imported, linked and found by the AI.

One connected story (product, site, lot, components, suppliers, BOM, genealogy, complaints, investigation, CAPA,
change, risk file, evidence) goes through the same checked workspace import as products, lots and complaints.
"""

import uuid

import pytest
from sqlalchemy import text

from backend.app.access.connector_mapping import check_mapping, keep_record, map_records, record_filter
from backend.app.db.session import engine
from tests.test_business_permissions import _client_with_role

TAG = uuid.uuid4().hex[:6].upper()
P = f"BRI-{TAG}"


def _csv(header: str, *rows: str) -> str:
    return "\n".join([header, *rows]) + "\n"


def _import(client, entity: str, body: str) -> dict:
    response = client.post(f"/api/v1/data/import/{entity}", content=body)
    assert response.status_code == 200, (entity, response.text)
    return response.json()


def _scalar(sql: str, **params):
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar()


def _cleanup() -> None:
    like = f"%{TAG}%"
    with engine.begin() as connection:
        evidence = "SELECT id FROM evidence WHERE evidence_identifier LIKE :like"
        for statement in (
            f"DELETE FROM evidence_entity_links WHERE evidence_id IN ({evidence})",
            f"DELETE FROM evidence_chunk_embeddings WHERE chunk_id IN (SELECT id FROM evidence_chunks WHERE evidence_id IN ({evidence}))",
            f"DELETE FROM evidence_chunks WHERE evidence_id IN ({evidence})",
            "DELETE FROM reality_relationships WHERE provenance->>'origin' = 'import' AND (source_entity_id IN "
            "(SELECT id FROM controls WHERE control_identifier LIKE :like UNION SELECT id FROM failure_modes WHERE "
            "failure_mode_identifier LIKE :like UNION SELECT id FROM requirements WHERE requirement_identifier LIKE :like "
            "UNION SELECT id FROM changes WHERE change_identifier LIKE :like))",
            "DELETE FROM capas WHERE capa_identifier LIKE :like",
            "DELETE FROM investigation_complaints WHERE investigation_id IN (SELECT id FROM investigations WHERE investigation_identifier LIKE :like)",
            "DELETE FROM evidence WHERE evidence_identifier LIKE :like",
            "DELETE FROM investigations WHERE investigation_identifier LIKE :like",
            "DELETE FROM complaints WHERE complaint_identifier LIKE :like",
            "DELETE FROM lot_components WHERE lot_batch_id IN (SELECT id FROM lot_batches WHERE lot_identifier LIKE :like)",
            "DELETE FROM lot_batches WHERE lot_identifier LIKE :like",
            "DELETE FROM product_components WHERE component_id IN (SELECT id FROM components WHERE component_identifier LIKE :like)",
            "DELETE FROM component_suppliers WHERE component_id IN (SELECT id FROM components WHERE component_identifier LIKE :like)",
            "DELETE FROM controls WHERE control_identifier LIKE :like",
            "DELETE FROM failure_modes WHERE failure_mode_identifier LIKE :like",
            "DELETE FROM requirements WHERE requirement_identifier LIKE :like",
            "DELETE FROM risks WHERE risk_identifier LIKE :like",
            "DELETE FROM changes WHERE change_identifier LIKE :like",
            "DELETE FROM components WHERE component_identifier LIKE :like",
            "DELETE FROM suppliers WHERE supplier_identifier LIKE :like",
            "DELETE FROM manufacturing_sites WHERE site_identifier LIKE :like",
            "DELETE FROM product_versions WHERE product_id IN (SELECT id FROM products WHERE product_identifier LIKE :like)",
            "DELETE FROM products WHERE product_identifier LIKE :like",
        ):
            connection.execute(text(statement), {"like": like})


@pytest.fixture(scope="module", autouse=True)
def _clean():
    _cleanup()
    yield
    _cleanup()


def test_a_whole_product_story_imports_and_links_across_systems():
    client = _client_with_role("Investigator")
    _import(client, "products", _csv("product_id,product_name,version", f"{P},AquaFlow test pump,Rev D"))
    _import(client, "sites", _csv("site_id,site_name,location", f"S-{TAG},Galway final assembly,IE Galway"))
    lots = _import(
        client,
        "lots",
        _csv("lot_id,product_id,version,manufacture_date,site_id", f"L-{TAG},{P},Rev D,2026-07-20,S-{TAG}"),
    )
    assert lots["created"] == 1
    assert (
        _scalar(
            "SELECT s.site_identifier FROM lot_batches l JOIN manufacturing_sites s ON s.id = l.manufacturing_site_id "
            "WHERE l.lot_identifier = :lot",
            lot=f"L-{TAG}",
        )
        == f"S-{TAG}"
    )
    _import(client, "components", _csv("component_id,component_name,revision", f"PS-{TAG},Pressure sensor,B"))
    _import(client, "suppliers", _csv("supplier_id,supplier_name", f"SUP-{TAG},Kestrel Sensors"))
    assert _import(client, "bom", _csv("product_id,version,component_id", f"{P},Rev D,PS-{TAG}"))["created"] == 1
    _import(client, "component_suppliers", _csv("component_id,supplier_id", f"PS-{TAG},SUP-{TAG}"))
    genealogy = _csv("lot_id,component_id,component_lot_id", f"L-{TAG},PS-{TAG},KS-{TAG}")
    assert _import(client, "lot_genealogy", genealogy)["created"] == 1
    assert _import(client, "lot_genealogy", genealogy)["updated"] == 1  # same row again: no duplicate

    complaints = _import(
        client,
        "complaints",
        _csv(
            "complaint_id,product_id,description,version,lot_id,severity,country,problem_code,serial_number,"
            "patient_involved,serious_injury,device_returned",
            f"C1-{TAG},{P},Occlusion alarm with a clear line,Rev D,L-{TAG},Major,IE,ALM-OCC,SN-1,Y,N,Y",
            f"C2-{TAG},{P},Alarm again during night infusion,Rev D,L-{TAG},Critical,DE,ALM-OCC,SN-2,Y,N,N",
        ),
    )
    assert complaints["created"] == 2
    assert (
        _scalar(
            "SELECT severity || ':' || patient_involved::text || ':' || serious_injury::text FROM complaints "
            "WHERE complaint_identifier = :id",
            id=f"C1-{TAG}",
        )
        == "Major:true:false"
    )

    _import(
        client,
        "investigations",
        _csv(
            "investigation_id,product_id,question,status,opened_date,owner,complaint_ids",
            f"INV-{TAG},{P},Why do Rev D pumps raise false occlusion alarms?,open,2026-09-02,QE-1,C1-{TAG};C2-{TAG}",
        ),
    )
    assert (
        _scalar(
            "SELECT count(*) FROM investigation_complaints ic JOIN investigations i ON i.id = ic.investigation_id "
            "WHERE i.investigation_identifier = :id",
            id=f"INV-{TAG}",
        )
        == 2
    )
    _import(
        client,
        "capas",
        _csv(
            "capa_id,title,status,product_id,investigation_id,due_date",
            f"CAPA-{TAG},Restore threshold margin,open,{P},INV-{TAG},2026-12-15",
        ),
    )
    _import(
        client,
        "changes",
        _csv(
            "change_id,change_type,description,effective_date,affected_ids",
            f"ECN-{TAG},ECN,Threshold lowered,2026-07-01,{P};PS-{TAG}",
        ),
    )
    _import(client, "risks", _csv("risk_id,product_id,description,version", f"RSK-{TAG},{P},Delayed therapy,Rev D"))
    _import(
        client,
        "failure_modes",
        _csv("failure_mode_id,failure_mode_name,risk_id", f"FM-{TAG},Sensor drifts high,RSK-{TAG}"),
    )
    _import(
        client,
        "controls",
        _csv("control_id,description,risk_id", f"CTL-{TAG},Threshold verified in production,RSK-{TAG}"),
    )
    _import(
        client,
        "requirements",
        _csv("requirement_id,product_id,text,risk_id", f"REQ-{TAG},{P},Alarm within 30 s,RSK-{TAG}"),
    )
    _import(
        client,
        "evidence",
        _csv(
            "evidence_id,title,evidence_type,content,review_status,product_id",
            f"TR-{TAG},Drift test,Test result,Offset 7.8 kPa: fail,approved,{P}",
        ),
    )
    assert (
        _scalar("SELECT reliability_status FROM evidence WHERE evidence_identifier = :id", id=f"TR-{TAG}")
        == "validated"
    )
    relations = _scalar(
        "SELECT count(*) FROM reality_relationships r JOIN risks k ON k.id = r.target_entity_id WHERE k.risk_identifier = :id",
        id=f"RSK-{TAG}",
    )
    assert relations == 3  # control, failure mode and requirement all point at the risk

    # The AI can find the imported records: each has searchable text linked to the product.
    indexed = _scalar(
        "SELECT count(DISTINCT e.id) FROM evidence e JOIN evidence_chunks c ON c.evidence_id = e.id "
        "JOIN evidence_entity_links l ON l.evidence_id = e.id JOIN products p ON p.id = l.entity_id "
        "WHERE l.entity_type = 'Product' AND p.product_identifier = :product AND e.evidence_type = 'SOURCE_RECORD'",
        product=P,
    )
    assert indexed >= 6  # 2 complaints, investigation, CAPA, risk, requirement
    text_of_complaint = _scalar(
        "SELECT content FROM evidence WHERE evidence_identifier = :id", id=f"RECORD:COMPLAINT:C1-{TAG}"
    )
    assert "Severity: Major" in text_of_complaint and "Patient involved: yes" in text_of_complaint


def test_a_record_that_refers_to_something_not_loaded_writes_nothing():
    client = _client_with_role("Investigator")
    _import(client, "products", _csv("product_id,product_name,version", f"{P}-X,Second pump,Rev A"))
    body = _csv("product_id,version,component_id", f"{P}-X,Rev A,NOPE-{TAG}")
    check = client.post("/api/v1/data/import/bom/check", content=body).json()
    assert not check["ready"] and "Load it first" in check["issues"][0]["message"]
    assert client.post("/api/v1/data/import/bom", content=body).status_code == 422
    flags = client.post(
        "/api/v1/data/import/complaints/check",
        content=_csv("complaint_id,product_id,description,death", f"CX-{TAG},{P}-X,Alarm,maybe"),
    ).json()
    assert not flags["ready"] and flags["issues"][0]["message"] == "Use Y or N."


def test_a_mapping_can_fill_any_record_and_keep_only_some_rows():
    rules = {
        "item_number": {"target_field": "Component.component_id", "transform": "trim"},
        "name": {"target_field": "Component.component_name", "transform": "trim"},
        "_filter": {"field": "item_type", "in": ["Component", "Assembly"]},
    }
    assert check_mapping("Component", rules)["status"] == "READY"
    assert record_filter(rules) == {"field": "item_type", "in": ["Component", "Assembly"]}
    assert keep_record(record_filter(rules), {"item_type": "component"}) is True
    assert keep_record(record_filter(rules), {"item_type": "Product"}) is False

    class Mapping:
        target_entity = "Component"
        mapping_rules = rules

    entity, rows = map_records(
        Mapping(),
        [
            {"item_number": "PUMP-1", "name": "Pump", "item_type": "Product"},
            {"item_number": " PS-1 ", "name": "Sensor", "item_type": "Component"},
        ],
    )
    assert entity == "components" and rows == [{"component_id": "PS-1", "component_name": "Sensor"}]
    unknown = check_mapping("Spaceship", {"a": {"target_field": "Spaceship.id"}})
    assert unknown["status"] == "NEEDS_CHANGES" and "Capa" in unknown["problems"][0]
