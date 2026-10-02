"""Authenticator-app MFA: an encrypted secret per account, replay protection, hashed recovery codes, and a session
MFA state (a session that still owes a code, or must set up MFA, can do nothing else).

Existing accounts keep MFA off until they enroll; existing sessions are unaffected (state NULL = fully signed in).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "md08totpmfa"
down_revision = "md07workerheartbeats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auth_users", sa.Column("mfa_secret_encrypted", sa.Text(), nullable=True))
    op.add_column("auth_users", sa.Column("mfa_pending_secret_encrypted", sa.Text(), nullable=True))
    op.add_column("auth_users", sa.Column("mfa_last_step", sa.BigInteger(), nullable=True))
    op.add_column("auth_users", sa.Column("mfa_recovery_hashes", postgresql.JSONB(), nullable=True))
    op.add_column("auth_sessions", sa.Column("mfa_state", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("auth_sessions", "mfa_state")
    op.drop_column("auth_users", "mfa_recovery_hashes")
    op.drop_column("auth_users", "mfa_last_step")
    op.drop_column("auth_users", "mfa_pending_secret_encrypted")
    op.drop_column("auth_users", "mfa_secret_encrypted")
