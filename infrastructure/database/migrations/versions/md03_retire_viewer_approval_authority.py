"""Retire the default approval authority that the governance demo bootstrap gave the Viewer role.

Every tenant that touched a governance route received an ACTIVE "Viewer may approve decisions" authority,
which let any read-only user sign approvals. The bootstrap now grants it to the Approver role instead; this
migration retires the existing Viewer grants. Each retired row is marked in `scope` so the downgrade restores
exactly those rows and nothing an administrator set up.
"""

from alembic import op
from sqlalchemy import text

revision = "md03retireviewerauth"
down_revision = "md02masterseed"
branch_labels = None
depends_on = None

_MARKER = "md03retireviewerauth"


def upgrade():
    op.get_bind().execute(
        text(
            """
            UPDATE approval_authorities
               SET status = 'RETIRED',
                   scope = coalesce(scope, '{}'::jsonb) || jsonb_build_object('retired_by', CAST(:marker AS text)),
                   updated_at = now()
             WHERE role_name = 'Viewer'
               AND object_type = 'Decision'
               AND decision_type = 'INVESTIGATION_REVIEW'
               AND status = 'ACTIVE'
            """
        ),
        {"marker": _MARKER},
    )


def downgrade():
    op.get_bind().execute(
        text(
            """
            UPDATE approval_authorities
               SET status = 'ACTIVE', scope = scope - 'retired_by', updated_at = now()
             WHERE scope ->> 'retired_by' = :marker
            """
        ),
        {"marker": _MARKER},
    )
