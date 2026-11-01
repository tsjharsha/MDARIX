"""Stored quarantine (R14, backend/app/import_quarantine.py).

``import_quarantine_rows``: a row a workspace import set aside, with its reasons and its values (personal data
masked), kept OPEN until a person corrects it and it is imported again (REPROCESSED). ``harm_words`` lists the harm
words its text holds, so the row reaches triage even while quarantined (A2). Tenant-isolated; a free trial never
stores its set-aside rows.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "md50importquarantine"
down_revision = "md49signinggrants"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "import_quarantine_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_ref", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity", sa.String(30), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("line", sa.Integer(), nullable=False),
        sa.Column("row", postgresql.JSONB(), nullable=False),
        sa.Column("problems", postgresql.JSONB(), nullable=False),
        sa.Column("harm_words", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("status", sa.String(20), server_default="OPEN", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", sa.String(120)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_quarantine_rows")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_import_quarantine_rows_tenant_id_tenants")
        ),
        sa.CheckConstraint("status in ('OPEN','REPROCESSED')", name="import_quarantine_status_allowed"),
    )
    op.create_index("ix_import_quarantine_tenant_status", "import_quarantine_rows", ["tenant_id", "status"])
    op.create_index("ix_import_quarantine_import", "import_quarantine_rows", ["import_ref"])
    _tenant_policy("import_quarantine_rows")


def downgrade():
    op.drop_index("ix_import_quarantine_import", table_name="import_quarantine_rows")
    op.drop_index("ix_import_quarantine_tenant_status", table_name="import_quarantine_rows")
    op.drop_table("import_quarantine_rows")
