"""An authority report can be cancelled (release 0.10.75, Release C, part C3).

The fourteenth migration of the trial line, chained from ``tr13viewpersona`` (``tr03pmssources`` stays reserved for
proactive PMS); after the forward merge, ``mvp-1.0`` adds a merge revision joining its head and this one.

Expand-only: the state check of ``report_obligations`` also allows ``CANCELLED`` (no stored row changes; code before
this release never writes it). A report is created when a person signs a market conclusion as reportable; when a
later signed conclusion of that market says "not reportable", a report not yet submitted is cancelled, its reason kept
in ``note`` and in the audit trail. A cancelled report is never deleted: signing reportable again reopens it.

Legacy dedicated organization databases get the same from scripts/add_workflow_tables_to_legacy_planes.py, which runs
``allow_cancelled_reports``.
"""

from alembic import op

from infrastructure.database.migrations.helpers import quoted

revision = "tr14reportcancelled"
down_revision = "tr13viewpersona"
branch_labels = None
depends_on = None

TABLE = "report_obligations"
CHECK = "ck_report_obligations_state_known"
STATES = (
    "DRAFT",
    "CORRECTION_REQUIRED",
    "APPROVED",
    "SUBMITTED_PENDING",
    "ACCEPTED",
    "SUBMITTED_NO_ACK",
    "FOLLOW_UP_DUE",
    "COMPLETE",
)


def allow_cancelled_reports(system_scope: bool = True) -> None:
    """The wider state check (also used for legacy organization databases; ``system_scope`` is not needed: the table
    keeps its isolation)."""
    op.drop_constraint(op.f(CHECK), TABLE, type_="check")
    op.create_check_constraint(op.f(CHECK), TABLE, f"state IN ({quoted((*STATES, 'CANCELLED'))})")


def upgrade():
    allow_cancelled_reports()


def downgrade():
    # A cancelled report goes back to a draft (its reason stays in its note), so the narrower check holds.
    op.execute(f"UPDATE {TABLE} SET state = 'DRAFT' WHERE state = 'CANCELLED'")
    op.drop_constraint(op.f(CHECK), TABLE, type_="check")
    op.create_check_constraint(op.f(CHECK), TABLE, f"state IN ({quoted(STATES)})")
