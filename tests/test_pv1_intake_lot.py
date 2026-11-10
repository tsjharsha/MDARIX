"""PV-1 F2 (0.10.95): the intake lot must belong to the chosen product; with no product, the product is the lot's."""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.models.foundation import LotBatch, ProductVersion
from backend.app.db.session import SessionLocal
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db

INTAKE = "/api/v1/intake"


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:pv1-intake-cleanup")


def _two_lots(tenant_id):
    """Two sample lots of different products: (lot number, product id) each."""
    with SessionLocal() as db:
        rows = (
            db.query(LotBatch.lot_identifier, ProductVersion.product_id)
            .join(ProductVersion, ProductVersion.id == LotBatch.product_version_id)
            .filter(LotBatch.tenant_id == tenant_id)
            .all()
        )
    first = rows[0]
    other = next(row for row in rows if row.product_id != first.product_id)
    return first, other


def _body(**extra):
    answers = {f"Q{n}": {"answer": "NO"} for n in range(1, 10)}
    return {
        "kind": "CONTACT",
        "reporter_words": "Caller reports the pump alarmed twice at night.",
        "answers": answers,
    } | extra


def test_a_lot_of_another_product_is_refused(trial):
    first, other = _two_lots(trial["tenant_id"])
    refused = trial["user"].post(INTAKE, json=_body(product_id=str(first.product_id), lot=other.lot_identifier))
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["code"] == "LOT_NOT_FOR_PRODUCT"
    # The lot of the chosen product is still taken.
    kept = trial["user"].post(INTAKE, json=_body(product_id=str(first.product_id), lot=first.lot_identifier))
    assert kept.status_code == 200, kept.text
    assert kept.json()["product_id"] == str(first.product_id) and not kept.json()["product_from_lot"]


def test_a_lot_without_a_product_gives_the_lots_product(trial):
    first, _ = _two_lots(trial["tenant_id"])
    event = trial["user"].post(INTAKE, json=_body(lot=first.lot_identifier))
    assert event.status_code == 200, event.text
    found = event.json()
    assert found["product_id"] == str(first.product_id)
    assert found["product_from_lot"] and found["identifiers"]["product"]["source"] == "LOT"
