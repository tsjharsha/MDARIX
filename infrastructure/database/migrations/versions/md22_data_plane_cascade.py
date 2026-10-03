"""A data-plane registry row is removed with its organization.

Organizations are archived, never deleted, in normal operation; but test fixtures and provisioning rollbacks delete
an organization row, and since migration md20 every organization has a registry row that would block that delete.
"""

from alembic import op

revision = "md22dataplanecascade"
down_revision = "md21purgingstatus"
branch_labels = None
depends_on = None

FK = "fk_tenant_data_planes_tenant_id_tenants"


def upgrade():
    op.drop_constraint(op.f(FK), "tenant_data_planes", type_="foreignkey")
    op.create_foreign_key(op.f(FK), "tenant_data_planes", "tenants", ["tenant_id"], ["id"], ondelete="CASCADE")


def downgrade():
    op.drop_constraint(op.f(FK), "tenant_data_planes", type_="foreignkey")
    op.create_foreign_key(op.f(FK), "tenant_data_planes", "tenants", ["tenant_id"], ["id"])
