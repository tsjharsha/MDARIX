"""Which legal texts a free-trial requester accepted, and when (CMP-15, backend/app/auth_router.py signup).

Sending the trial request accepts the Terms of Service and the Free Trial Agreement and acknowledges the Privacy
Policy. The request now records, at that moment, the version of each text the website served: its "Last updated"
date and the SHA-256 of its exact text (backend/app/site_info.py legal_versions), with the time. It names nobody, so
it stays when the request's personal data is erased, as the record of what was accepted. Empty for requests sent
before this migration. Control plane only.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "md48legalacceptance"
down_revision = "md47invitedelivery"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("onboarding_requests", sa.Column("legal_acceptance", postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column("onboarding_requests", "legal_acceptance")
