"""The md26 business-identifier object list is consistent with the models and the registry (no database needed)."""

import re

import pytest

from backend.app.db.base import Base
from infrastructure.database.migrations.business_ids import GLOBAL_SCOPE, INDEX_NAMES, OBJECTS, WIDTH
from infrastructure.database.migrations.drift_policy import MIGRATION_OWNED_INDEXES, MIGRATION_OWNED_TABLES

pytestmark = pytest.mark.unit

TABLES = Base.metadata.tables


def test_each_object_and_prefix_appears_once():
    assert len({item.table for item in OBJECTS}) == len(OBJECTS)
    assert len({item.prefix for item in OBJECTS}) == len(OBJECTS)


def test_prefixes_fit_the_registry_rules_and_the_column():
    for item in OBJECTS:
        # md_master.business_id_prefix: ^[A-Z]{1,12}$; the column holds the prefix and at least six digits.
        assert re.fullmatch(r"[A-Z]{1,12}", item.prefix), item.prefix
        assert len(item.prefix) + WIDTH <= 20
        assert item.scope in {"global", "tenant"}


def test_every_object_has_a_model_declaring_business_id():
    for item in OBJECTS:
        assert item.table in TABLES, f"no model for {item.table}"
        column = TABLES[item.table].c.get("business_id")
        assert column is not None and not column.nullable and column.type.length == 20, item.table
        assert column.server_default is not None, f"{item.table}.business_id must be server-generated"


def test_natural_keys_and_ordering_columns_exist():
    for item in OBJECTS:
        columns = TABLES[item.table].c
        for key in item.natural_key:
            assert key in columns, f"{item.table}.{key}"
        assert item.order_by in columns, f"{item.table}.{item.order_by}"
        if item.scope == "tenant":
            assert "tenant_id" in columns and not columns["tenant_id"].nullable, item.table


def test_database_object_names_fit_postgres_identifiers():
    for item in OBJECTS:
        for name in (item.index_name, item.trigger_name, item.immutable_trigger_name):
            assert len(name) <= 63, name


def test_the_drift_gate_knows_the_migration_owned_objects():
    assert INDEX_NAMES <= MIGRATION_OWNED_INDEXES
    assert "business_id_counters" in MIGRATION_OWNED_TABLES


def test_the_global_scope_is_the_nil_uuid():
    assert GLOBAL_SCOPE == "00000000-0000-0000-0000-000000000000"
