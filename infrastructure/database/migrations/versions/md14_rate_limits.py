"""Rate-limit counters shared by every API process.

One row per (scope, hashed key, window start) counts attempts in a fixed window (backend/app/rate_limit.py). The
table holds no tenant data and no plain identifiers: keys are salted SHA-256 hashes of an address, email or user id.
"""

from alembic import op
import sqlalchemy as sa

revision = "md14ratelimits"
down_revision = "md13trialfeedback"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rate_limit_counters",
        sa.Column("scope", sa.String(40), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("scope", "key_hash", "window_start"),
    )
    op.create_index("ix_rate_limit_counters_window", "rate_limit_counters", ["window_start"])
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON public.rate_limit_counters TO mdarix_runtime; END IF; END $$;"
    )
    # Sign-in lockout rows were keyed by the email alone; they are now keyed by email and address (see auth_router),
    # so the old rows can never be read again. MFA and signature lockouts ("mfa:<id>", "sign:<id>") are kept.
    op.execute("DELETE FROM login_throttles WHERE identifier NOT LIKE '%:%'")


def downgrade():
    op.drop_index("ix_rate_limit_counters_window", table_name="rate_limit_counters")
    op.drop_table("rate_limit_counters")
