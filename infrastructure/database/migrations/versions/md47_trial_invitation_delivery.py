"""Whether a free trial's invitation email reached the mail provider (backend/app/trial/service.py).

An approved request records the outcome of its latest invitation email: SENT, FAILED (the provider refused it or
could not be reached; MDARIX retries it through the outbox and alerts the operators) or NOT_CONFIGURED (no email on
this server), and when it was tried. The Platform Admin queue shows an invitation that did not go out next to "Resend
invitation", so a trial that never got its email is no longer indistinguishable from one whose owner has simply not
activated yet. Empty for requests decided before this migration. Control plane only.
"""

import sqlalchemy as sa
from alembic import op

revision = "md47invitedelivery"
down_revision = "md46trialmvp"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("onboarding_requests", sa.Column("invitation_delivery", sa.String(20), nullable=True))
    op.add_column(
        "onboarding_requests", sa.Column("invitation_attempted_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade():
    op.drop_column("onboarding_requests", "invitation_attempted_at")
    op.drop_column("onboarding_requests", "invitation_delivery")
