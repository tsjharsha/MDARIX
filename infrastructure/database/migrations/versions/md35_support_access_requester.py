"""Support access grants record who requested them.

Approval of a grant refuses the platform administrator who requested it as well as the one who would receive it.
Before this column the grant only named its recipient, so the requester could approve a grant made for a colleague.
Existing grants keep a null requester (they were created before the rule), which the approval treats as unknown.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "md35supportrequester"
down_revision = "md34rlsdefence"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("support_access_grants", sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True))


def downgrade():
    op.drop_column("support_access_grants", "requested_by")
