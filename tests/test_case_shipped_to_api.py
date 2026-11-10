"""ID-2 (0.10.93): "Products and lots shipped to this hospital" at Log a case. The caller's hospital is matched to the
consignees of the organization's shipment records (``lot_distributions``) by exact name or customer reference, never
fuzzily; another organization's shipments are never offered; several sites under one name are listed; the list is
bounded and read in one query. A Case logged from the picker keeps "source: shipment record" on its identifiers."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.app.db.models.foundation import AuditEvent, LotBatch
from backend.app.db.models.lot_impact import LotDistribution
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.intake import service
from tests.test_free_trial import _approved_trial_client
from tests.test_intake_triage_api import INTAKE, _all_no, _ok

pytestmark = pytest.mark.db

SHIPPED = f"{INTAKE}/shipped-to"
CEDAR = "Cedar Plains Medical Center (Sample)"  # a sample consignee (trial/sample_lot_impact.py)
ONLY_B = "Only In B Hospital"


def _purge(tenant_id) -> None:
    from backend.app.trial.retention import purge_trial

    with SessionLocal() as db:
        purge_trial(db, tenant_id, "test:shipped-to-cleanup")


def _ship_in(tenant_id) -> None:
    """Organization B: 51 US shipments to ONLY_B and, newest of all, one to the same name in Germany (other spacing and
    case): two sites under one name, more than the bound."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_system(db, "test:shipped-to")
        lot = db.query(LotBatch).filter(LotBatch.tenant_id == tenant_id).order_by(LotBatch.lot_identifier).first()
        rows = [(ONLY_B, "US", date(2026, 1, 1) + timedelta(days=day)) for day in range(service.SHIPPED_LIMIT + 1)]
        rows.append(("  only in b   HOSPITAL ", "DE", date(2026, 6, 1)))
        for consignee, country, shipped in rows:
            db.add(
                LotDistribution(
                    tenant_id=tenant_id,
                    lot_batch_id=lot.id,
                    consignee=consignee,
                    country=country,
                    quantity=1,
                    ship_date=shipped,
                    created_at=now,
                    updated_at=now,
                )
            )
        db.commit()


@pytest.fixture(scope="module")
def trials():
    user_a, approval_a, _ = _approved_trial_client()
    user_b, approval_b, _ = _approved_trial_client()
    a, b = uuid.UUID(approval_a["tenant_id"]), uuid.UUID(approval_b["tenant_id"])
    try:
        _ship_in(b)
        yield {"a": user_a, "b": user_b, "tenant_a": a, "tenant_b": b}
    finally:
        _purge(a)
        _purge(b)


def test_a_sample_hospital_is_offered_its_products_and_lots_newest_first(trials):  # ID-2 match, sample data
    found = _ok(trials["a"].get(SHIPPED, params={"site": f"  {CEDAR.upper()} "}))
    lots = {item["lot"] for item in found["items"]}
    assert {"SAMPLE-ORBIT-300-LOT-003", "SAMPLE-ORBIT-300-LOT-006", "SAMPLE-PULSE-410-LOT-002"} <= lots
    assert all(item["consignee"] == CEDAR and item["product_id"] and item["product_name"] for item in found["items"])
    assert all(item["version"] for item in found["items"])
    dates = [item["ship_date"] for item in found["items"]]
    assert dates == sorted(dates, reverse=True) and found["truncated"] is False
    assert [site["consignee"] for site in found["sites"]] == [CEDAR]
    # The customer reference matches too.
    assert _ok(trials["a"].get(SHIPPED, params={"site": "smp-c-1001"}))["items"] == found["items"]


def test_no_match_or_no_site_is_an_empty_list_never_an_error_or_a_guess(trials):  # ID-2 no match
    for site in ("Cedar Plains", "Cedar Plains Medical Center", "", "   "):
        assert _ok(trials["a"].get(SHIPPED, params={"site": site})) == {"sites": [], "items": [], "truncated": False}


def test_another_organizations_shipments_are_never_offered(trials):  # ID-2 tenant isolation
    assert _ok(trials["a"].get(SHIPPED, params={"site": ONLY_B}))["items"] == []
    assert _ok(trials["b"].get(SHIPPED, params={"site": ONLY_B}))["items"]


def test_several_sites_are_listed_by_name_and_the_list_is_bounded(trials):  # ID-2 several sites, bound
    found = _ok(trials["b"].get(SHIPPED, params={"site": "only in b hospital"}))
    assert len(found["items"]) == service.SHIPPED_LIMIT and found["truncated"] is True
    assert sorted(site["country"] for site in found["sites"]) == ["DE", "US"]
    assert found["items"][0]["country"] == "DE"


def test_the_list_is_read_in_one_query(trials):  # ID-2: no N+1
    from sqlalchemy import event

    seen = []
    with SessionLocal() as db:
        bind_system(db, "test:shipped-to-budget")
        service.shipped_to(db, trials["tenant_b"], ONLY_B)  # the transaction's own set-up statements first
        engine = db.get_bind()
        listener = lambda *args, **kwargs: seen.append(1)  # noqa: E731
        event.listen(engine, "before_cursor_execute", listener)
        try:
            found = service.shipped_to(db, trials["tenant_b"], ONLY_B)
        finally:
            event.remove(engine, "before_cursor_execute", listener)
    assert len(found["items"]) == service.SHIPPED_LIMIT and len(seen) == 1


def test_a_case_logged_from_the_picker_keeps_shipment_record_as_its_source(trials):  # ID-2 audit, ID-1
    user, tenant_id = trials["a"], trials["tenant_a"]
    picked = _ok(user.get(SHIPPED, params={"site": CEDAR}))["items"][0]
    entry = {"status": "UNCONFIRMED", "source": "SHIPMENT_RECORD"}
    event = _ok(
        user.post(
            INTAKE,
            json={
                "kind": "CONTACT",
                "reporter_words": "The hospital's biomedical team reports an alarm that does not stop.",
                "reporter_site": CEDAR,
                "answers": _all_no(),
                "product_id": picked["product_id"],
                "lot": picked["lot"],
                "identifiers": {"product": entry, "version": entry, "lot": entry},
            },
        )
    )
    expected = {key: {"not_sure": False, **entry} for key in ("product", "version", "lot")}
    assert event["identifiers"] == expected
    with SessionLocal() as db:
        bind_system(db, "test:shipped-to-audit")
        logged = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.tenant_id == tenant_id,
                AuditEvent.entity_id == uuid.UUID(event["id"]),
                AuditEvent.action == "INTAKE_LOGGED",
            )
            .one()
        )
        assert logged.details["identifiers"] == expected
