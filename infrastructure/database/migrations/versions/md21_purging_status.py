"""An organization whose data is being deleted is briefly in status PURGING (backend/app/tenant_purge.py).

The status exists only inside the deleting transaction: the audit trail's immutability trigger lets that
organization's audit rows be deleted only while it is PURGING (migration md18), and the purge ends in ARCHIVED.
"""

from alembic import op

revision = "md21purgingstatus"
down_revision = "md20defaultdataplane"
branch_labels = None
depends_on = None

BEFORE = (
    "'DRAFT','PENDING_APPROVAL','PROVISIONING','PROVISIONED','PENDING_CUSTOMER_ACTIVATION','ACTIVE',"
    "'EXPIRING_SOON','EXPIRED','SUSPENDED','TERMINATED','ARCHIVED'"
)


def upgrade():
    op.drop_constraint(op.f("ck_tenants_tenant_lifecycle_status_allowed"), "tenants", type_="check")
    op.create_check_constraint("tenant_lifecycle_status_allowed", "tenants", f"status in ({BEFORE},'PURGING')")


def downgrade():
    op.drop_constraint(op.f("ck_tenants_tenant_lifecycle_status_allowed"), "tenants", type_="check")
    op.create_check_constraint("tenant_lifecycle_status_allowed", "tenants", f"status in ({BEFORE})")
