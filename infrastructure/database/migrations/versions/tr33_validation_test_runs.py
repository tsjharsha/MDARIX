"""Recorded test runs for the validation evidence screen (E2).

Chained from ``tr32aiready``. Expand-only: one new platform table, ``validation_test_runs`` (one row per uploaded
pytest JUnit XML, backend/app/db/models/validation_runs.py). It has no organization: row-level security is forced
with the tr21 pattern, so every session reads it and only system scope (a platform administrator) inserts. The
runtime role gets SELECT and INSERT only; no route updates or deletes a run.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "tr33validationruns"
down_revision = "tr32aiready"
branch_labels = None
depends_on = None

TABLE = "validation_test_runs"
_SYSTEM = "(SELECT public.mdarix_system_scope())"
POLICIES = (
    ("mdarix_validation_runs_read", "SELECT", "USING (true)"),
    ("mdarix_validation_runs_insert", "INSERT", f"WITH CHECK ({_SYSTEM})"),
)


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("commit", sa.String(40), nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("passed", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False),
        sa.Column("meta", postgresql.JSONB(), nullable=False),
        sa.Column("tests", postgresql.JSONB(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
    )
    op.create_index("ix_validation_test_runs_uploaded_at", TABLE, ["uploaded_at"])
    op.execute(f"ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{TABLE} FORCE ROW LEVEL SECURITY")
    for name, command, clause in POLICIES:
        op.execute(f"CREATE POLICY {name} ON public.{TABLE} FOR {command} {clause}")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
        f"GRANT SELECT, INSERT ON public.{TABLE} TO mdarix_runtime; "
        f"REVOKE UPDATE, DELETE ON public.{TABLE} FROM mdarix_runtime; END IF; END $$;"
    )


def downgrade():
    op.drop_table(TABLE)
