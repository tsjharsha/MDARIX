"""A second administrator confirms every grant of a role that signs (R11, backend/app/access/signing_grants.py).

``signing_grants``: when an administrator gives a person a role that signs (an Approver, a Leader, a Quality Reviewer
for effectiveness checks, or any role an approval rule authorizes), the grant waits here as PENDING. The person holds
the role at once, for everything except signing; they sign under it only after a different Customer Administrator of
the organization confirms it (CONFIRMED). A refused grant (REFUSED) keeps the person from signing under that role
until it is given again. People who held a role before this migration have no row and sign as before. Tenant-isolated
like ``user_additional_roles``. Control plane only.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "md49signinggrants"
down_revision = "md48legalacceptance"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "signing_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_code", sa.String(60), nullable=False),
        sa.Column("status", sa.String(20), server_default="PENDING", nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True)),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_reason", sa.Text()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signing_grants")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_signing_grants_tenant_id_tenants")),
        sa.ForeignKeyConstraint(["user_id"], ["auth_users.id"], name=op.f("fk_signing_grants_user_id_auth_users")),
        sa.UniqueConstraint("tenant_id", "user_id", "role_code", name="uq_signing_grants_user_role"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED', 'REFUSED')", name=op.f("ck_signing_grants_status_known")
        ),
    )
    op.create_index("ix_signing_grants_tenant_status", "signing_grants", ["tenant_id", "status"])
    _tenant_policy("signing_grants")


def downgrade():
    op.drop_index("ix_signing_grants_tenant_status", table_name="signing_grants")
    op.drop_table("signing_grants")
