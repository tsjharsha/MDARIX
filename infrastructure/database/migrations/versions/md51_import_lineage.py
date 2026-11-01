"""Row lineage (R16, backend/app/import_lineage.py).

``import_lineage``: for every row a workspace import writes, the import it came in with (``import_ref``, also on the
import's DATA_IMPORTED audit event), its line in the file, and the mapping version used. Tenant-isolated.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "md51importlineage"
down_revision = "md50importquarantine"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "import_lineage",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_ref", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity", sa.String(30), nullable=False),
        sa.Column("record_key", sa.String(400), nullable=False),
        sa.Column("line", sa.Integer(), nullable=False),
        sa.Column("mapping_version", sa.String(80), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_lineage")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_import_lineage_tenant_id_tenants")),
    )
    op.create_index("ix_import_lineage_record", "import_lineage", ["tenant_id", "entity", "record_key"])
    op.create_index("ix_import_lineage_import", "import_lineage", ["import_ref"])
    _tenant_policy("import_lineage")


def downgrade():
    op.drop_index("ix_import_lineage_import", table_name="import_lineage")
    op.drop_index("ix_import_lineage_record", table_name="import_lineage")
    op.drop_table("import_lineage")
