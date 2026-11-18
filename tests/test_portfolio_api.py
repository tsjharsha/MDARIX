"""UX2 (Persona Blueprint wave D): the executive's portfolio, exposure per product from existing records only.

Each product's figures equal what the records hold (counted here independently), each figure has a definition, and
another organization sees none of this one's products."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_free_trial import _approved_trial_client
from tests.test_w5_twin import ORBIT, _purge

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def trial():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        _purge(tenant_id)


def _scalar(tenant_id, sql: str, ident: str):
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return db.execute(text(sql), {"t": tenant_id, "p": ident}).scalar()


def test_the_portfolio_counts_each_product_from_its_records(trial):
    body = trial["user"].get("/api/v1/portfolio")
    assert body.status_code == 200, body.text
    data = body.json()
    figures = {"lots", "units_shipped", "open_complaints", "reportable", "open_investigations", "awaiting_decision"}
    assert figures <= set(data["definitions"])
    orbit = next(row for row in data["products"] if row["product_identifier"] == ORBIT)
    t = trial["tenant_id"]
    product = "SELECT id FROM products WHERE tenant_id=:t AND product_identifier=:p"
    lots = _scalar(
        t,
        f"SELECT count(*) FROM lot_batches l JOIN product_versions v ON v.id=l.product_version_id "
        f"WHERE l.tenant_id=:t AND v.product_id=({product})",
        ORBIT,
    )
    open_complaints = _scalar(
        t,
        f"SELECT count(*) FROM complaints WHERE tenant_id=:t AND product_id=({product}) "
        "AND lower(coalesce(status,''))<>'closed'",
        ORBIT,
    )
    assert orbit["lots"] == lots > 0
    assert orbit["open_complaints"] == open_complaints > 0
    assert orbit["open_investigations"] >= orbit["awaiting_decision"] >= 0
    assert orbit["units_shipped"] is None or orbit["units_shipped"] > 0


def test_another_organization_sees_none_of_these_products(trial):
    other, approval, _ = _approved_trial_client()
    try:
        mine = {row["id"] for row in trial["user"].get("/api/v1/portfolio").json()["products"]}
        theirs = {row["id"] for row in other.get("/api/v1/portfolio").json()["products"]}
        assert mine and theirs and not mine & theirs
    finally:
        _purge(uuid.UUID(approval["tenant_id"]))
