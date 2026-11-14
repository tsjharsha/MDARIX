"""The references DB-1 added after tr23 (owner decisions 1 and 2, 14 Nov 2026), for migration ``tr24a``.

- A Case's lot (``intake_events.lot_batch_id``) and the product of a decision, an investigation brief, an assurance
  result and an AI interaction had no reference at all (PV-1 F1 evidence). Each gets the composite
  ``(tenant_id, x_id) -> parent (tenant_id, id)``, so the row must name a lot or product of its own organization.
- ``case_contexts`` (a person's open product, version and case) gets the check that a version is never set without
  its product. Its composite reference to ``product_versions (tenant_id, product_id, id)`` is NOT added: the context is
  kept in the control database, while a tenant on a dedicated data plane keeps its products in that plane, so such a
  reference would refuse every saved context of that tenant (open owner question; the API already checks the version
  belongs to the product against the data plane, backend/app/workspace_context.py).

Like ``tenant_references.py``, the migration counts the rows that would break a rule first and refuses with the
counts; ``scripts/check_tenant_references.py`` prints the same counts read only. Frozen for tr24a.
"""

from __future__ import annotations

from typing import NamedTuple

import sqlalchemy as sa


class NewReference(NamedTuple):
    child: str
    column: str
    parent: str

    @property
    def name(self) -> str:
        return f"fk_{self.child}_{self.column}_tenant"

    @property
    def label(self) -> str:
        return f"{self.child}.{self.column} -> {self.parent}"


PRODUCT_TABLES = ("decisions", "investigation_briefs", "assurance_results", "ai_interactions")
REFERENCES: tuple[NewReference, ...] = (NewReference("intake_events", "lot_batch_id", "lot_batches"),) + tuple(
    NewReference(table, "product_id", "products") for table in PRODUCT_TABLES
)
# The four product references are covered by tr24's (tenant_id, product_id, product_version_id) index on each table.
INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("ix_intake_events_tenant_lot_batch", "intake_events", ("tenant_id", "lot_batch_id")),
)
VERSION_CHECK_TABLES = ("case_contexts",)
VERSION_CHECK = "product_version_id IS NULL OR product_id IS NOT NULL"


def version_check_name(table: str) -> str:
    return f"ck_{table}_version_needs_product"


def _queries() -> list[tuple[str, str]]:
    queries = [
        (
            f"{ref.label}: no such row in the same organization",
            f"SELECT count(*) FROM public.{ref.child} c LEFT JOIN public.{ref.parent} p "
            f"ON p.id = c.{ref.column} AND p.tenant_id = c.tenant_id WHERE c.{ref.column} IS NOT NULL AND p.id IS NULL",
        )
        for ref in REFERENCES
    ]
    queries += [
        (
            f"{table}: a version without a product",
            f"SELECT count(*) FROM public.{table} WHERE product_version_id IS NOT NULL AND product_id IS NULL",
        )
        for table in VERSION_CHECK_TABLES
    ]
    return queries


def tables_read() -> list[str]:
    return sorted({ref.child for ref in REFERENCES} | {ref.parent for ref in REFERENCES} | set(VERSION_CHECK_TABLES))


def violation_counts(connection) -> list[tuple[str, int]]:
    """Every rule with the number of rows that break it. The caller sees every row (owner without forced row-level
    security, or system scope)."""
    return [(label, int(connection.execute(sa.text(sql)).scalar() or 0)) for label, sql in _queries()]


def constraint_names() -> list[str]:
    return [ref.name for ref in REFERENCES] + [version_check_name(table) for table in VERSION_CHECK_TABLES]
