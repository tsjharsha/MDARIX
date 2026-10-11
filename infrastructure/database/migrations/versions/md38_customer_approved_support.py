"""Support access needs the customer's approval (ADR-015, backend/app/support_access.py).

A grant now carries MDARIX's approval (who and when) and the customer's decision (which Customer Administrator,
when, why), plus who revoked it. Grants approved before this migration were approved by platform administrators
only: they become AWAITING_CUSTOMER, so none opens anything until the customer approves it.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "md38customerapprovedsupport"
down_revision = "md37platformcelllink"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("approved_at", sa.DateTime(timezone=True)),
    ("customer_decided_by", postgresql.UUID(as_uuid=True)),
    ("customer_decided_at", sa.DateTime(timezone=True)),
    ("customer_decision_reason", sa.Text()),
    ("revoked_by", postgresql.UUID(as_uuid=True)),
)


def _every_row(statement: str) -> None:
    """Run ``statement`` over every organization's grants. The table's row-level security is forced (md05), so even
    the owner sees no rows outside a scope: lift the forcing for this statement only, inside the migration's own
    transaction, so it is restored whatever happens."""
    op.execute("ALTER TABLE public.support_access_grants NO FORCE ROW LEVEL SECURITY")
    op.execute(statement)
    op.execute("ALTER TABLE public.support_access_grants FORCE ROW LEVEL SECURITY")


def upgrade():
    for name, column_type in _COLUMNS:
        op.add_column("support_access_grants", sa.Column(name, column_type, nullable=True))
    _every_row(
        "UPDATE public.support_access_grants SET status = 'AWAITING_CUSTOMER', approved_at = updated_at "
        "WHERE status = 'APPROVED' AND customer_decided_by IS NULL"
    )


def downgrade():
    # Before this migration only APPROVED, PENDING, REVOKED and EXPIRED existed.
    _every_row(
        "UPDATE public.support_access_grants SET status = CASE status WHEN 'AWAITING_CUSTOMER' THEN 'APPROVED' "
        "WHEN 'DENIED' THEN 'REVOKED' ELSE status END WHERE status IN ('AWAITING_CUSTOMER', 'DENIED')"
    )
    for name, _ in reversed(_COLUMNS):
        op.drop_column("support_access_grants", name)
