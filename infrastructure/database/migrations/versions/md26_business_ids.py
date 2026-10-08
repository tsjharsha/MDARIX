"""Human-readable business identifiers for every business object (CUST000001, CMP000001, ...).

Every object in infrastructure/database/migrations/business_ids.py gets a ``business_id`` column: its prefix and a
number of at least six digits. The UUID ``id`` stays the technical key (links, APIs, integrations); ``business_id``
is what people see.

- Numbers come from ``business_id_counters`` (one row per scope and prefix) inside the inserting transaction, so they
  are gap-free: a save that rolls back also rolls back its number. Platform objects share one global scope; an
  organization's data is numbered per organization (each customer's first complaint is CMP000001), which also works
  across dedicated organization databases.
- A re-import (INSERT ... ON CONFLICT on the object's natural key) keeps the existing number instead of consuming one.
- A row copied with its number (a dedicated-database move, a restore) keeps it, and the counter moves past it.
- The number never changes (an update trigger refuses it) and is never reused, even after a record is deleted.
- Existing rows are numbered oldest first. Tables with forced row-level security are relaxed for the owner only for
  the backfill, inside this transaction, and forced again.
- The md_master.business_id_prefix registry records every prefix (new ones are added) with a width of six.
"""

import sqlalchemy as sa
from alembic import op

from infrastructure.database.migrations.business_ids import COUNTER_TABLE, GLOBAL_SCOPE, OBJECTS, WIDTH

revision = "md26businessids"
down_revision = "md25canonicalroles"
branch_labels = None
depends_on = None

# The registry's owning schemas (documentation of where each object belongs in the master-data model).
OWNING_SCHEMA = {"global": "md_control", "tenant": "md_transaction"}
# Prefixes md01 already registered (width 5); downgrade returns them to that width and removes only md26's own.
MD01_PREFIXES = frozenset(
    "AIEX CAPA CHG CMP COMP CTL CUST DBR DEC EVD EVR FC FM HYP INC INV LOT PROD PV RPT RSK SITE SUP TEN UNK".split()
)

ASSIGN_FUNCTION = f"""
CREATE OR REPLACE FUNCTION public.mdarix_assign_business_id() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $fn$
DECLARE
    v_prefix text := TG_ARGV[0];
    v_scope_kind text := TG_ARGV[1];
    v_width integer := TG_ARGV[2]::integer;
    v_row jsonb := to_jsonb(NEW);
    v_scope uuid := '{GLOBAL_SCOPE}';
    v_where text := '';
    v_existing text;
    v_next bigint;
    v_index integer;
BEGIN
    IF v_scope_kind = 'tenant' AND v_row ? 'tenant_id' AND v_row->>'tenant_id' IS NOT NULL THEN
        v_scope := (v_row->>'tenant_id')::uuid;
    END IF;

    -- A row copied with its number (a dedicated-database move, a restore) keeps it; the counter never falls behind.
    IF NEW.business_id IS NOT NULL THEN
        IF NEW.business_id ~ ('^' || v_prefix || '[0-9]+$') THEN
            INSERT INTO public.{COUNTER_TABLE} AS c (scope_id, prefix, last_value)
            VALUES (v_scope, v_prefix, substr(NEW.business_id, length(v_prefix) + 1)::bigint)
            ON CONFLICT (scope_id, prefix) DO UPDATE
               SET last_value = greatest(c.last_value, EXCLUDED.last_value), updated_at = now();
        END IF;
        RETURN NEW;
    END IF;

    -- A re-import of an existing record (INSERT ... ON CONFLICT on its natural key): keep that record's number, so
    -- nothing is consumed. A plain duplicate insert still fails on the natural key as before.
    IF TG_NARGS > 3 THEN
        IF v_scope_kind = 'tenant' THEN
            v_where := format(' AND tenant_id = %L', v_scope);
        END IF;
        FOR v_index IN 3 .. TG_NARGS - 1 LOOP
            IF v_row->>TG_ARGV[v_index] IS NULL THEN
                v_where := NULL;
                EXIT;
            END IF;
            v_where := v_where || format(' AND %I = %L', TG_ARGV[v_index], v_row->>TG_ARGV[v_index]);
        END LOOP;
        IF v_where IS NOT NULL THEN
            EXECUTE format('SELECT business_id FROM %I.%I WHERE true%s LIMIT 1', TG_TABLE_SCHEMA, TG_TABLE_NAME, v_where)
               INTO v_existing;
            IF v_existing IS NOT NULL THEN
                NEW.business_id := v_existing;
                RETURN NEW;
            END IF;
        END IF;
    END IF;

    -- The next number of this scope and prefix; the counter row is locked until the transaction ends (gap-free).
    INSERT INTO public.{COUNTER_TABLE} AS c (scope_id, prefix, last_value)
    VALUES (v_scope, v_prefix, 1)
    ON CONFLICT (scope_id, prefix) DO UPDATE SET last_value = c.last_value + 1, updated_at = now()
    RETURNING last_value INTO v_next;
    NEW.business_id := v_prefix || CASE WHEN length(v_next::text) < v_width
                                        THEN lpad(v_next::text, v_width, '0') ELSE v_next::text END;
    RETURN NEW;
END
$fn$;
"""


def _scope_sql(item) -> str:
    return "tenant_id" if item.scope == "tenant" else f"'{GLOBAL_SCOPE}'::uuid"


def _registry_present(connection) -> bool:
    return bool(connection.execute(sa.text("SELECT to_regclass('md_master.business_id_prefix') IS NOT NULL")).scalar())


def create_counter_and_function() -> None:
    """The counter table and the assigning function (also used by scripts/add_business_ids_to_legacy_planes.py)."""
    op.create_table(
        COUNTER_TABLE,
        sa.Column("scope_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prefix", sa.String(12), nullable=False),
        sa.Column("last_value", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("scope_id", "prefix", name=op.f(f"pk_{COUNTER_TABLE}")),
    )
    # Only the definer function writes it; the runtime role has no direct access.
    op.execute(f"REVOKE ALL ON public.{COUNTER_TABLE} FROM PUBLIC")
    op.execute(ASSIGN_FUNCTION)
    op.execute("REVOKE ALL ON FUNCTION public.mdarix_assign_business_id() FROM PUBLIC")


def add_business_id(connection, item) -> None:
    """Add, backfill and protect one object's business_id (also used for legacy organization databases)."""
    table = item.table
    forced = connection.execute(
        sa.text("SELECT relforcerowsecurity FROM pg_class WHERE oid = to_regclass(:name)"),
        {"name": f"public.{table}"},
    ).scalar()
    op.add_column(table, sa.Column("business_id", sa.String(20), nullable=True))
    if forced:
        op.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
    scope = _scope_sql(item)
    op.execute(
        f"""
        WITH numbered AS (
            SELECT id, row_number() OVER (PARTITION BY {scope} ORDER BY {item.order_by} NULLS LAST, id) AS n
            FROM public.{table}
        )
        UPDATE public.{table} AS t
           SET business_id = '{item.prefix}' || CASE WHEN length(numbered.n::text) < {WIDTH}
                                                   THEN lpad(numbered.n::text, {WIDTH}, '0')
                                                   ELSE numbered.n::text END
          FROM numbered
         WHERE t.id = numbered.id
        """
    )
    op.execute(
        f"""
        INSERT INTO public.{COUNTER_TABLE} (scope_id, prefix, last_value)
        SELECT {scope}, '{item.prefix}', count(*) FROM public.{table} GROUP BY 1
        """
    )
    if forced:
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.alter_column(table, "business_id", existing_type=sa.String(20), nullable=False)
    unique_columns = "tenant_id, business_id" if item.scope == "tenant" else "business_id"
    op.execute(f"CREATE UNIQUE INDEX {item.index_name} ON public.{table} ({unique_columns})")
    arguments = ", ".join(f"'{value}'" for value in (item.prefix, item.scope, str(WIDTH), *item.natural_key))
    op.execute(
        f"CREATE TRIGGER {item.trigger_name} BEFORE INSERT ON public.{table} "
        f"FOR EACH ROW EXECUTE FUNCTION public.mdarix_assign_business_id({arguments})"
    )
    op.execute(
        f"CREATE TRIGGER {item.immutable_trigger_name} BEFORE UPDATE OF business_id ON public.{table} "
        "FOR EACH ROW WHEN (OLD.business_id IS NOT NULL AND OLD.business_id IS DISTINCT FROM NEW.business_id) "
        "EXECUTE FUNCTION public.mdarix_reject_immutable_identifier()"
    )


def upgrade():
    connection = op.get_bind()
    create_counter_and_function()
    for item in OBJECTS:
        add_business_id(connection, item)

    if _registry_present(connection):
        for item in OBJECTS:
            sequence = f"seq_business_id_{item.prefix.lower()}"
            op.execute(f"CREATE SEQUENCE IF NOT EXISTS md_master.{sequence}")
            op.execute(
                f"""
                INSERT INTO md_master.business_id_prefix (prefix, entity_name, sequence_name, id_width, owning_schema)
                VALUES ('{item.prefix}', '{item.entity}', '{sequence}', {WIDTH}, '{OWNING_SCHEMA[item.scope]}')
                ON CONFLICT (prefix) DO UPDATE SET id_width = {WIDTH}
                """
            )


def downgrade():
    connection = op.get_bind()
    for item in reversed(OBJECTS):
        op.execute(f"DROP TRIGGER IF EXISTS {item.immutable_trigger_name} ON public.{item.table}")
        op.execute(f"DROP TRIGGER IF EXISTS {item.trigger_name} ON public.{item.table}")
        op.execute(f"DROP INDEX IF EXISTS public.{item.index_name}")
        op.drop_column(item.table, "business_id")
    op.execute("DROP FUNCTION IF EXISTS public.mdarix_assign_business_id()")
    op.drop_table(COUNTER_TABLE)
    if _registry_present(connection):
        for item in OBJECTS:
            if item.prefix in MD01_PREFIXES:
                op.execute(f"UPDATE md_master.business_id_prefix SET id_width = 5 WHERE prefix = '{item.prefix}'")
            # Other prefixes stay registered. # Prefixes are permanent (md_master.protect_prefix_registry refuses removal); re-applying reuses them.
