"""Organization-safe references, and a record's version always a version of its product (DB-1: DB-01, PV-1 F1/F15).

Chained from ``tr22tenantfkcheck``, which has already refused if any existing row breaks these rules. No column is
added, dropped or renamed, and the application writes the same rows as before; the 0.10.94 images run on this schema.

- The 41 single-column references between organization tables (db-audit N1) become composite ``(tenant_id, x_id) ->
  parent (tenant_id, id)``, with the same ON DELETE behaviour. Each is added NOT VALID, validated, and then the
  single-column one is dropped; the provisioning job step keeps both, because its ``tenant_id`` may be empty.
  Targets without ``UNIQUE (tenant_id, id)`` get it.
- ``product_versions`` gets ``UNIQUE (tenant_id, product_id, id)``, and the nine tables with a product and a version
  (complaints, risks, requirements, signals, intake events, decisions, investigation briefs, assurance results, AI
  interactions) reference it with ``(tenant_id, product_id, product_version_id)``, plus a check that a version is
  never set without its product. This is the enforcer of the master-data rule VERSION_BELONGS_TO_PRODUCT (F15).

The lists are in infrastructure/database/migrations/tenant_references.py; the models mirror them.
"""

from alembic import op

from infrastructure.database.migrations.tenant_references import (
    KEEP_SINGLE_COLUMN,
    NEW_TARGET_UNIQUES,
    PRODUCT_VERSION_TABLES,
    PRODUCT_VERSION_UNIQUE,
    REFERENCES,
    unique_name,
    version_check_name,
    version_fk_name,
)

revision = "tr23compositetenantfks"
down_revision = "tr22tenantfkcheck"
branch_labels = None
depends_on = None

_VERSION_COLUMNS = "(tenant_id, product_id, product_version_id)"
_VERSION_TARGET = "public.product_versions (tenant_id, product_id, id)"


def _on_delete(ondelete: str | None) -> str:
    return f" ON DELETE {ondelete}" if ondelete else ""


def add_composite_references(legacy: bool = False) -> None:
    """Every change of this migration. ``legacy``: a legacy organization database may lack a single-column reference
    under its usual name, so it is dropped only if it is there."""
    exists = " IF EXISTS" if legacy else ""
    for table in NEW_TARGET_UNIQUES:
        op.execute(f"ALTER TABLE public.{table} ADD CONSTRAINT {unique_name(table)} UNIQUE (tenant_id, id)")
    op.execute(
        f"ALTER TABLE public.product_versions ADD CONSTRAINT {PRODUCT_VERSION_UNIQUE} UNIQUE (tenant_id, product_id, id)"
    )
    for ref in REFERENCES:
        op.execute(
            f"ALTER TABLE public.{ref.child} ADD CONSTRAINT {ref.new_name} FOREIGN KEY (tenant_id, {ref.column}) "
            f"REFERENCES public.{ref.parent} (tenant_id, id){_on_delete(ref.ondelete)} NOT VALID"
        )
        op.execute(f"ALTER TABLE public.{ref.child} VALIDATE CONSTRAINT {ref.new_name}")
        if ref.old_name not in KEEP_SINGLE_COLUMN:
            op.execute(f"ALTER TABLE public.{ref.child} DROP CONSTRAINT{exists} {ref.old_name}")
    for table in PRODUCT_VERSION_TABLES:
        op.execute(
            f"ALTER TABLE public.{table} ADD CONSTRAINT {version_fk_name(table)} FOREIGN KEY {_VERSION_COLUMNS} "
            f"REFERENCES {_VERSION_TARGET} NOT VALID"
        )
        op.execute(f"ALTER TABLE public.{table} VALIDATE CONSTRAINT {version_fk_name(table)}")
        op.execute(
            f"ALTER TABLE public.{table} ADD CONSTRAINT {version_check_name(table)} "
            "CHECK (product_version_id IS NULL OR product_id IS NOT NULL) NOT VALID"
        )
        op.execute(f"ALTER TABLE public.{table} VALIDATE CONSTRAINT {version_check_name(table)}")


def upgrade():
    add_composite_references()


def apply_to_legacy_plane(system_scope: bool = True) -> None:
    """tr22's pre-check, then this migration's changes, in the caller's transaction (legacy organization database)."""
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    spec = spec_from_file_location("tr22_tenant_fk_check", Path(__file__).with_name("tr22_tenant_fk_check.py"))
    check = module_from_spec(spec)
    spec.loader.exec_module(check)
    check.check_rows(system_scope)
    add_composite_references(legacy=True)


def downgrade():
    for table in reversed(PRODUCT_VERSION_TABLES):
        op.execute(f"ALTER TABLE public.{table} DROP CONSTRAINT {version_check_name(table)}")
        op.execute(f"ALTER TABLE public.{table} DROP CONSTRAINT {version_fk_name(table)}")
    for ref in reversed(REFERENCES):
        if ref.old_name not in KEEP_SINGLE_COLUMN:
            op.execute(
                f"ALTER TABLE public.{ref.child} ADD CONSTRAINT {ref.old_name} FOREIGN KEY ({ref.column}) "
                f"REFERENCES public.{ref.parent} (id){_on_delete(ref.ondelete)}"
            )
        op.execute(f"ALTER TABLE public.{ref.child} DROP CONSTRAINT {ref.new_name}")
    op.execute(f"ALTER TABLE public.product_versions DROP CONSTRAINT {PRODUCT_VERSION_UNIQUE}")
    for table in reversed(NEW_TARGET_UNIQUES):
        op.execute(f"ALTER TABLE public.{table} DROP CONSTRAINT {unique_name(table)}")
