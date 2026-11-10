"""The investigation challenge and the closed loop (backlog item B5, after the WHIF freeze).

DB-1 (tr21-tr24) is not built yet; when it lands, the chain is re-ordered at the release join.

The twenty-sixth migration of the trial line, chained from ``tr25routinepath`` (B7's head). Expand-only: six nullable
columns on two existing tables and one check that allows NULL. Nothing is dropped, renamed or moved; row-level security
is unchanged (no new table).

- ``hypotheses.draft_rule`` and ``draft_rule_version``: the rule (H-1 to H-5) and its version that drafted a
  hypothesis a person adopted from the Challenge view. NULL for every hypothesis written by a person or the AI run.
- ``decision_follow_ups.action_reference``, ``action_kind``, ``action_effective_on`` and ``action_scope``: a field
  action or product change recorded lightly when its follow-up is completed (the customer's reference, the kind of
  field action, the date it took effect, the lots and versions it covers or the new version).

Legacy dedicated organization databases get the same from scripts/add_workflow_tables_to_legacy_planes.py, which runs
``add_challenge_loop``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import quoted

revision = "tr26challengeloop"
down_revision = "tr25routinepath"
branch_labels = None
depends_on = None

ACTION_KINDS = ("CORRECTION", "REMOVAL", "ADVISORY_NOTICE", "SOFTWARE_UPDATE", "OTHER")
FOLLOW_UP_COLUMNS = ("action_reference", "action_kind", "action_effective_on", "action_scope")


def add_challenge_loop(system_scope: bool = True) -> None:
    """Every change of this migration (also used for legacy organization databases; the tables keep their isolation)."""
    op.add_column("hypotheses", sa.Column("draft_rule", sa.String(10), nullable=True))
    op.add_column("hypotheses", sa.Column("draft_rule_version", sa.Integer(), nullable=True))
    table = "decision_follow_ups"
    op.add_column(table, sa.Column("action_reference", sa.String(120), nullable=True))
    op.add_column(table, sa.Column("action_kind", sa.String(30), nullable=True))
    op.add_column(table, sa.Column("action_effective_on", sa.Date(), nullable=True))
    op.add_column(table, sa.Column("action_scope", postgresql.JSONB(), nullable=True))
    op.create_check_constraint(
        op.f("ck_decision_follow_ups_action_kind_known"),
        table,
        f"action_kind IS NULL OR action_kind IN ({quoted(ACTION_KINDS)})",
    )


def upgrade():
    add_challenge_loop()


def downgrade():
    op.drop_constraint(op.f("ck_decision_follow_ups_action_kind_known"), "decision_follow_ups", type_="check")
    for column in reversed(FOLLOW_UP_COLUMNS):
        op.drop_column("decision_follow_ups", column)
    op.drop_column("hypotheses", "draft_rule_version")
    op.drop_column("hypotheses", "draft_rule")
