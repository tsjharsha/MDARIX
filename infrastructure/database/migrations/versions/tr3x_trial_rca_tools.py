"""RCA tools (spec approved by the owner 12 Nov 2026, section 8.1): root-cause methods, the confirmed cause at signing,
section comments on a brief and the per-risk harm estimate.

Chained from ``tr31othercountries`` (the head of the line it was cut from); re-attached at merge under the one-head
rule. Expand-only: nullable columns or columns with a default, no new table, no data step, no backfill. Existing rows
keep NULL or the default, so every decision signed before RCA reads "Not categorised" and is never rewritten.

- ``hypotheses.cause_category`` (fishbone: PEOPLE, PROCESS, METHOD, MATERIAL, MACHINE, ENVIRONMENT, SOFTWARE) and
  ``hypotheses.failure_mode_id``, a reference that includes the organization to ``failure_modes`` (indexed).
- ``failure_chains.method``: CHAIN (default) or FIVE_WHYS.
- ``decisions.root_cause_category`` (the categories, or NOT_DETERMINED) and ``decisions.root_cause_hypothesis_ids``
  (a JSON array, default empty): what the decision maker ticked while signing.
- ``brief_review_actions.section_key``: the dossier section a reviewer comment names.
- ``risks``: hazard, harm, severity, the estimated probability of the harm per unit (above 0, at most 1), where it
  came from (IMPORTED or ENTERED) and the codes it covers (a JSON object, default empty).

Row-level security is unchanged (no new table; every table here already forces it). Downgrade refuses while any of
these columns holds a value (no silent loss). Legacy dedicated organization databases get the same from
scripts/add_workflow_tables_to_legacy_planes.py, which runs ``add_rca_tools``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

from infrastructure.database.migrations.helpers import quoted

revision = "trrcatools"
down_revision = "tr31othercountries"
branch_labels = None
depends_on = None

CAUSE_CATEGORIES = ("PEOPLE", "PROCESS", "METHOD", "MATERIAL", "MACHINE", "ENVIRONMENT", "SOFTWARE")
NOT_DETERMINED = "NOT_DETERMINED"
CHAIN_METHODS = ("CHAIN", "FIVE_WHYS")
ESTIMATE_SOURCES = ("IMPORTED", "ENTERED")
FAILURE_MODE_INDEX = "ix_hypotheses_tenant_failure_mode"
# DB-1 naming (tenant_references.Reference.new_name): the reference includes the organization.
FAILURE_MODE_REFERENCE = "fk_hypotheses_failure_mode_id_tenant"

# What a downgrade would lose: refused while any of these finds a row.
IN_USE = (
    "SELECT count(*) FROM hypotheses WHERE cause_category IS NOT NULL OR failure_mode_id IS NOT NULL",
    "SELECT count(*) FROM failure_chains WHERE method <> 'CHAIN'",
    "SELECT count(*) FROM decisions WHERE root_cause_category IS NOT NULL OR root_cause_hypothesis_ids <> '[]'::jsonb",
    "SELECT count(*) FROM brief_review_actions WHERE section_key IS NOT NULL",
    "SELECT count(*) FROM risks WHERE estimated_probability IS NOT NULL OR hazard IS NOT NULL OR harm IS NOT NULL "
    "OR severity IS NOT NULL OR estimate_source IS NOT NULL OR match_codes <> '{}'::jsonb",
)


def add_rca_tools(system_scope: bool = True) -> None:
    """Every change of this migration (also used for legacy organization databases; isolation unchanged)."""
    op.add_column("hypotheses", sa.Column("cause_category", sa.String(20), nullable=True))
    op.create_check_constraint(
        op.f("ck_hypotheses_cause_category_known"),
        "hypotheses",
        f"cause_category IS NULL OR cause_category IN ({quoted(CAUSE_CATEGORIES)})",
    )
    op.add_column("hypotheses", sa.Column("failure_mode_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        op.f(FAILURE_MODE_REFERENCE),
        "hypotheses",
        "failure_modes",
        ["tenant_id", "failure_mode_id"],
        ["tenant_id", "id"],
    )
    op.create_index(FAILURE_MODE_INDEX, "hypotheses", ["tenant_id", "failure_mode_id"])

    op.add_column(
        "failure_chains", sa.Column("method", sa.String(20), nullable=False, server_default=sa.text("'CHAIN'"))
    )
    op.create_check_constraint(
        op.f("ck_failure_chains_method_known"), "failure_chains", f"method IN ({quoted(CHAIN_METHODS)})"
    )

    op.add_column("decisions", sa.Column("root_cause_category", sa.String(20), nullable=True))
    op.create_check_constraint(
        op.f("ck_decisions_root_cause_category_known"),
        "decisions",
        f"root_cause_category IS NULL OR root_cause_category IN ({quoted((*CAUSE_CATEGORIES, NOT_DETERMINED))})",
    )
    op.add_column(
        "decisions",
        sa.Column("root_cause_hypothesis_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.create_check_constraint(
        op.f("ck_decisions_root_cause_hypothesis_ids_array"),
        "decisions",
        "jsonb_typeof(root_cause_hypothesis_ids) = 'array'",
    )

    op.add_column("brief_review_actions", sa.Column("section_key", sa.String(40), nullable=True))

    op.add_column("risks", sa.Column("hazard", sa.Text(), nullable=True))
    op.add_column("risks", sa.Column("harm", sa.Text(), nullable=True))
    op.add_column("risks", sa.Column("severity", sa.String(40), nullable=True))
    op.add_column("risks", sa.Column("estimated_probability", sa.Numeric(), nullable=True))
    op.create_check_constraint(
        op.f("ck_risks_estimated_probability_range"),
        "risks",
        "estimated_probability IS NULL OR (estimated_probability > 0 AND estimated_probability <= 1)",
    )
    op.add_column("risks", sa.Column("estimate_source", sa.String(20), nullable=True))
    op.create_check_constraint(
        op.f("ck_risks_estimate_source_known"),
        "risks",
        f"estimate_source IS NULL OR estimate_source IN ({quoted(ESTIMATE_SOURCES)})",
    )
    op.add_column("risks", sa.Column("match_codes", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.create_check_constraint(op.f("ck_risks_match_codes_object"), "risks", "jsonb_typeof(match_codes) = 'object'")


def upgrade():
    add_rca_tools()


def downgrade():
    # Off, a row-level policy that would hide a row raises instead of filtering: the counts below see every tenant.
    op.execute("SET LOCAL row_security = off")
    bind = op.get_bind()
    if any(bind.execute(sa.text(query)).scalar() for query in IN_USE):
        raise RuntimeError(
            "Root-cause categories, 5 Whys, section comments or risk estimates exist: they would be lost by "
            "downgrading trrcatools"
        )
    for name in (
        "ck_risks_match_codes_object",
        "ck_risks_estimate_source_known",
        "ck_risks_estimated_probability_range",
    ):
        op.drop_constraint(op.f(name), "risks", type_="check")
    for column in ("match_codes", "estimate_source", "estimated_probability", "severity", "harm", "hazard"):
        op.drop_column("risks", column)
    op.drop_column("brief_review_actions", "section_key")
    op.drop_constraint(op.f("ck_decisions_root_cause_hypothesis_ids_array"), "decisions", type_="check")
    op.drop_constraint(op.f("ck_decisions_root_cause_category_known"), "decisions", type_="check")
    op.drop_column("decisions", "root_cause_hypothesis_ids")
    op.drop_column("decisions", "root_cause_category")
    op.drop_constraint(op.f("ck_failure_chains_method_known"), "failure_chains", type_="check")
    op.drop_column("failure_chains", "method")
    op.drop_index(FAILURE_MODE_INDEX, table_name="hypotheses")
    op.drop_constraint(op.f(FAILURE_MODE_REFERENCE), "hypotheses", type_="foreignkey")
    op.drop_column("hypotheses", "failure_mode_id")
    op.drop_constraint(op.f("ck_hypotheses_cause_category_known"), "hypotheses", type_="check")
    op.drop_column("hypotheses", "cause_category")
