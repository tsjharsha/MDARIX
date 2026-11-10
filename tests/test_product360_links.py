"""W1 (0.10.94), Product 360 backend, on a free trial's sample as its own user: the light read, the product's own
changes with the before/after split (IV-14, OD-11), the list's counts, the six tiles and one list paged, origin on every
row, and another organization's product (P360-01..-04 in part, -05 data, -06, -09, -11)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db

ORBIT, PULSE = "SAMPLE-ORBIT-300", "SAMPLE-PULSE-410"


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def trial():
    from backend.app.db.session import SessionLocal
    from backend.app.trial.retention import purge_trial

    user, approval, _email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:product360-cleanup")


def _scalar(sql: str, **params):
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system

    with SessionLocal() as db:
        bind_system(db, "test: read the expected counts")
        return db.execute(text(sql), params).scalar()


def test_the_light_read_gives_counts_and_only_the_products_own_changes(trial):
    user, tenant = trial["user"], str(trial["tenant_id"])
    light = _ok(user.get(f"/api/v1/products/{ORBIT}/product-360", params={"version_id": "Rev B", "light": "1"}))
    assert light["complaints"] == [] and light["timeline"] == [] and light["evidence"] == []
    assert light["failure_modes"] == [] and light["controls"] == []
    expected = _scalar(
        "SELECT count(*) FROM complaints c JOIN product_versions v ON v.id=c.product_version_id "
        "JOIN products p ON p.id=c.product_id WHERE c.tenant_id=:t AND p.product_identifier=:p "
        "AND v.version_identifier='Rev B'",
        t=tenant,
        p=ORBIT,
    )
    assert expected > 0 and light["overview"]["complaint_count"] == expected and light["overview"]["light"] is True
    assert light["product"]["origin"]["kind"] == "SAMPLE" and light["product"]["origin"]["label"] == "Sample"
    assert all(row["origin"]["kind"] == "SAMPLE" for row in light["manufacturing"]["lots"])
    # The supplier link's date and the lot details for the Configuration and Lots tabs.
    sensor = next(s for s in light["configuration"]["suppliers"] if s["component_identifier"] == f"{ORBIT}-C1")
    assert sensor["name"].startswith("NovaSense") and sensor["supplied_from"]
    lot_3 = next(lot for lot in light["manufacturing"]["lots"] if lot["lot_identifier"].endswith("-LOT-003"))
    assert lot_3["complaints"] > 0 and lot_3["per_1000"] is not None
    assert any("NS-SL-2417" in line for line in lot_3["genealogy"])

    # OD-11: only the change recorded as affecting OrbitCare's pressure sensor, with the IV-14 split.
    (change,) = light["changes"]
    assert change["change_identifier"] == "SAMPLE-CHG-014" and change["affects"] == [f"{ORBIT}-C1"]
    on_affected = (
        "SELECT count(*) FROM complaints c JOIN product_versions v ON v.id=c.product_version_id "
        "JOIN products p ON p.id=c.product_id JOIN changes ch ON ch.tenant_id=c.tenant_id "
        "AND ch.change_identifier='SAMPLE-CHG-014' WHERE c.tenant_id=:t AND p.product_identifier=:p "
        "AND v.version_identifier='Rev B' AND c.event_timestamp {} coalesce(ch.effective_timestamp, ch.event_timestamp)"
    )
    assert change["complaints_before"] == _scalar(on_affected.format("<"), t=tenant, p=ORBIT)
    assert change["complaints_after"] == _scalar(on_affected.format(">="), t=tenant, p=ORBIT) > 0
    # Before W1 every product listed every change of the organization.
    pulse = _ok(user.get(f"/api/v1/products/{PULSE}/product-360", params={"light": "1"}))
    assert pulse["changes"] == []
    # The full read keeps its rows and gets the same fix.
    full = _ok(user.get(f"/api/v1/products/{ORBIT}/product-360", params={"version_id": "Rev B"}))
    assert len(full["complaints"]) == expected and [c["change_identifier"] for c in full["changes"]] == [
        "SAMPLE-CHG-014"
    ]


def test_the_product_list_gives_origin_and_the_newest_versions_counts(trial):
    rows = _ok(trial["user"].get("/api/v1/products", params={"counts": "1"}))
    orbit = next(row for row in rows if row["product_identifier"] == ORBIT)
    assert orbit["origin"]["kind"] == "SAMPLE"
    counts = orbit["counts"]
    assert counts["version_identifier"] == "Rev B" and counts["open_capas"] >= 1
    assert counts["open_complaints"] > 0 and counts["open_investigations"] >= 1
    assert all(row["counts"] is None for row in _ok(trial["user"].get("/api/v1/products")))


def test_six_tiles_with_newest_three_and_the_capa_check_planned_not_recorded(trial):
    user = trial["user"]
    body = _ok(user.get(f"/api/v1/products/{ORBIT}/links", params={"version": "Rev B"}))
    assert body["product"]["product_identifier"] == ORBIT and body["version"]["version_identifier"] == "Rev B"
    tiles = body["tiles"]
    assert set(tiles) == {"complaints", "investigations", "signals", "capas", "risks", "reports"}
    assert all(len(tile["items"]) <= 3 and tile["count"] >= len(tile["items"]) for tile in tiles.values())
    complaints = tiles["complaints"]["items"]
    assert [row["event_timestamp"] for row in complaints] == sorted(
        (row["event_timestamp"] for row in complaints), reverse=True
    )
    assert all(row["origin"]["kind"] == "SAMPLE" and row["version_identifier"] == "Rev B" for row in complaints)
    assert "SAMPLE-INV-001" in [row["investigation_identifier"] for row in tiles["investigations"]["items"]]
    capa = next(row for row in tiles["capas"]["items"] if row["capa_identifier"] == "SAMPLE-CAPA-02")
    assert capa["check"]["state"] == "PLANNED"
    assert (
        capa["check"]["label"].startswith("Effectiveness check planned for ")
        and "not yet recorded" in capa["check"]["label"]
    )
    assert {row["risk_identifier"] for row in tiles["risks"]["items"]} >= {"SAMPLE-RSK-01", "SAMPLE-RSK-02"}
    monthly = body["monthly"]
    assert len(monthly["months"]) == 12 and {s["version_identifier"] for s in monthly["series"]} == {"Rev A", "Rev B"}
    assert all(len(s["counts"]) == 12 for s in monthly["series"])
    # PulseWatch has no risk in MDARIX (the sample's deliberate risk-file gap).
    pulse = _ok(user.get(f"/api/v1/products/{PULSE}/links"))
    assert pulse["version"] is None and pulse["tiles"]["risks"] == {"count": 0, "items": []}


def test_one_list_is_paged_with_the_usual_headers(trial):
    user = trial["user"]
    base = f"/api/v1/products/{ORBIT}/links"
    first = user.get(base, params={"version": "Rev B", "kind": "complaints", "limit": 2})
    rows, total = _ok(first), int(first.headers["X-Total-Count"])
    assert len(rows) == 2 and total > 2 and first.headers["X-Next-Offset"] == "2"
    beyond = user.get(base, params={"version": "Rev B", "kind": "complaints", "limit": 2, "offset": total + 5})
    assert _ok(beyond) == [] and beyond.headers["X-Total-Count"] == str(total) and beyond.headers["X-Next-Offset"] == ""
    every = _ok(user.get(base, params={"version": "Rev B", "kind": "complaints", "limit": 1000}))
    assert len(every) == total and len({row["id"] for row in every}) == total
    capas = user.get(base, params={"kind": "capas", "limit": 20})
    assert "SAMPLE-CAPA-02" in [row["capa_identifier"] for row in _ok(capas)]
    assert user.get(base, params={"kind": "everything"}).status_code == 422


def test_an_unknown_or_another_organizations_product_is_not_found(trial):
    user = trial["user"]
    assert user.get("/api/v1/products/NO-SUCH-PRODUCT/links").status_code == 404
    missing_version = user.get(f"/api/v1/products/{ORBIT}/links", params={"version": "Rev Z"})
    assert missing_version.status_code == 404 and missing_version.json()["detail"]["code"] == "VERSION_NOT_FOUND"
    other = _scalar("SELECT id::text FROM products WHERE tenant_id <> :t LIMIT 1", t=str(trial["tenant_id"]))
    if other:
        for path in (f"/api/v1/products/{other}/links", f"/api/v1/products/{other}/product-360?light=1"):
            response = user.get(path)
            assert response.status_code == 404 and other not in response.text


def test_a_chosen_version_shows_only_the_investigations_covering_it_pv1(trial):
    """PV-1 (owner, 10 Nov 2026): with a version chosen, the light read and the tiles list the investigations with a
    complaint on it (one spanning both versions under each); every version lists them all; an unknown version is 404,
    never read as another one."""
    from datetime import datetime, timezone

    from backend.app.db.models.foundation import Complaint, Investigation, InvestigationComplaint, Product
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant

    user, tenant_id = trial["user"], trial["tenant_id"]
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        product = db.query(Product).filter(Product.tenant_id == tenant_id, Product.product_identifier == ORBIT).one()
        on = {}
        for complaint, version in db.execute(
            text(
                "SELECT c.id, v.version_identifier FROM complaints c JOIN product_versions v ON v.id=c.product_version_id "
                "WHERE c.tenant_id=:t AND c.product_id=:p ORDER BY c.complaint_identifier"
            ),
            {"t": str(tenant_id), "p": str(product.id)},
        ):
            on.setdefault(version, complaint)
        assert {"Rev A", "Rev B"} <= set(on)
        for identifier, versions in (("T-PV1-A", ["Rev A"]), ("T-PV1-AB", ["Rev A", "Rev B"])):
            case = Investigation(
                tenant_id=tenant_id,
                investigation_identifier=identifier,
                product_id=product.id,
                investigation_question="PV-1 test",
                status="open",
                created_at=now,
                updated_at=now,
            )
            db.add(case)
            db.flush()
            for version in versions:
                db.add(
                    InvestigationComplaint(
                        tenant_id=tenant_id, investigation_id=case.id, complaint_id=on[version], created_at=now
                    )
                )
        db.commit()
        assert db.query(Complaint).filter(Complaint.id == on["Rev A"]).one()

    def light(version):
        view = _ok(user.get(f"/api/v1/products/{ORBIT}/product-360", params={"version_id": version, "light": "1"}))
        return {row["investigation_identifier"] for row in view["investigations"]}

    def tiles(version=None):
        params = {"version": version} if version else {}
        found = _ok(user.get(f"/api/v1/products/{ORBIT}/links", params=params))["tiles"]["investigations"]
        listed = _ok(user.get(f"/api/v1/products/{ORBIT}/links", params={**params, "kind": "investigations"}))
        assert {row["investigation_identifier"] for row in listed} >= {
            i["investigation_identifier"] for i in found["items"]
        }
        return {row["investigation_identifier"] for row in listed}

    assert {"T-PV1-A", "T-PV1-AB"} <= light("Rev A") and "SAMPLE-INV-001" not in light("Rev A")
    assert {"SAMPLE-INV-001", "T-PV1-AB"} <= light("Rev B") and "T-PV1-A" not in light("Rev B")
    assert tiles("Rev A") == light("Rev A") and tiles("Rev B") == light("Rev B")
    assert {"SAMPLE-INV-001", "T-PV1-A", "T-PV1-AB"} <= tiles()
    spanning = next(
        row
        for row in _ok(user.get(f"/api/v1/products/{ORBIT}/links", params={"kind": "investigations"}))
        if row["investigation_identifier"] == "T-PV1-AB"
    )
    assert spanning["versions"] == ["Rev A", "Rev B"] and spanning["applies_to"] == "VERSION"
    unknown = user.get(f"/api/v1/products/{ORBIT}/product-360", params={"version_id": "Rev Z", "light": "1"})
    assert unknown.status_code == 404 and unknown.json()["detail"]["code"] == "VERSION_NOT_FOUND"
    # CAPAs on a version say whether they come from its investigation or are the product's own.
    capas = _ok(user.get(f"/api/v1/products/{ORBIT}/links", params={"version": "Rev A", "kind": "capas"}))
    assert all(row["applies_to"] in ("PRODUCT", "VERSION") for row in capas)
    assert "SAMPLE-CAPA-02" not in {row["capa_identifier"] for row in capas}  # from SAMPLE-INV-001, on Rev B
