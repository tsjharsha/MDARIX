"""A trial request carries what the requester told MDARIX about their company and trial.

``onboarding_requests.profile`` (JSONB, empty for requests made before this migration): job title, country, phone,
company size, device types and class, markets, current complaint system, complaint volume, trial data plan, the goal
of the evaluation and the confirmation that no patient-identifiable data will be uploaded
(backend/app/trial/request_profile.py). No password is collected.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "md39trialrequestprofile"
down_revision = "md38customerapprovedsupport"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "onboarding_requests",
        sa.Column("profile", postgresql.JSONB(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("onboarding_requests", "profile")
