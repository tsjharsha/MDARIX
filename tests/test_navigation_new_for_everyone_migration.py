"""ux2navigationnew: every organization on the classic navigation moves to the new one, organizations already on new
are untouched, and the column's default becomes new; the downgrade puts the default back and leaves the rows. Runs
Alembic against a fresh database of its own (the ``migration_database`` fixture in conftest.py)."""

import uuid

from sqlalchemy import text

from tests.test_db1_migration_roundtrip import _alembic

BEFORE = "tr33inconclusive"
DEFAULT = (
    "SELECT column_default FROM information_schema.columns WHERE table_name = 'tenants' AND column_name = 'navigation'"
)
CUSTOMER = (
    "INSERT INTO customers (id, business_id, customer_identifier, legal_name, display_name, customer_type, country) "
    "VALUES (:id, :bid, :key, 'UX2 Nav Ltd', 'UX2 Nav', 'MANUFACTURER', 'IN')"
)
TENANT = (
    "INSERT INTO tenants (id, business_id, customer_id, tenant_key, tenant_identifier, name, display_name, tenant_slug, "
    "created_at, updated_at, navigation, tenant_type, deployment_model, primary_region, residency_region, "
    "cross_border_processing_allowed, provisioning_status, lock_version, status) VALUES (:id, :bid, :customer, :key, :key, :key, "
    ":key, :key, now(), now(), :nav, 'STANDARD', 'SHARED', 'UNSPECIFIED', 'UNSPECIFIED', false, 'PROVISIONED', 1, 'ACTIVE')"
)


def _default(engine) -> str:
    with engine.connect() as connection:
        return connection.execute(text(DEFAULT)).scalar()


def _navigations(engine) -> dict[str, str]:
    with engine.connect() as connection:
        return {str(row[0]): row[1] for row in connection.execute(text("SELECT id, navigation FROM tenants"))}


def test_every_classic_organization_moves_to_the_new_navigation(migration_database):
    engine, env = migration_database
    assert "new" in _default(engine)
    customer = uuid.uuid4()
    rows = {"ux2-classic-a": "classic", "ux2-classic-b": "classic", "ux2-already-new": "new"}
    ids = {key: uuid.uuid4() for key in rows}
    try:
        down = _alembic(env, "downgrade", BEFORE)
        assert down.returncode == 0, down.stderr[-2000:]
        assert "classic" in _default(engine)
        with engine.begin() as connection:
            connection.execute(text(CUSTOMER), {"id": customer, "bid": "CUX2NAV", "key": "UX2-NAV-CUSTOMER"})
            for number, (key, nav) in enumerate(rows.items()):
                bid = f"TUX2NAV{number}"
                connection.execute(
                    text(TENANT), {"id": ids[key], "bid": bid, "customer": customer, "key": key, "nav": nav}
                )
        before = _navigations(engine)
        classic = sum(1 for value in before.values() if value == "classic")
        assert classic >= 2
    finally:
        up = _alembic(env, "upgrade", "head")
    assert up.returncode == 0, up.stderr[-2000:]
    # Exactly the classic rows change, and the migration says how many.
    assert f"{classic} organization(s) moved from classic to new navigation" in up.stdout + up.stderr
    assert set(_navigations(engine).values()) == {"new"} and _navigations(engine).keys() == before.keys()
    assert "new" in _default(engine)
