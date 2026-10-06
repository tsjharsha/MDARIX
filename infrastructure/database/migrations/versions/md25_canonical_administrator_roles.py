"""Canonicalize persisted administrator roles.

Legacy aliases remain accepted at API and authorization boundaries, but stored
administrator roles are limited to PLATFORM_ADMIN and CUSTOMER_ADMIN.
"""

from alembic import op

revision = "md25canonicalroles"
down_revision = "md24schemadrift"
branch_labels = None
depends_on = None

NORMALIZED_ROLE = "upper(replace(replace(btrim(role), ' ', '_'), '-', '_'))"
# The full name as stored: the metadata naming convention prefixes check constraints with ck_<table>_, so the name is
# given with op.f() (already final) in both directions, or downgrade would look for the unprefixed name.
CONSTRAINT = "ck_auth_users_auth_user_administrator_role_canonical"


def upgrade() -> None:
    op.execute(
        f"UPDATE auth_users SET role = 'PLATFORM_ADMIN' "
        f"WHERE {NORMALIZED_ROLE} IN "
        "('PLATFORM_ADMIN','MDARIX_ADMINISTRATOR','ADMINISTRATOR','ADMIN')"
    )
    op.execute(
        f"UPDATE auth_users SET role = 'CUSTOMER_ADMIN' "
        f"WHERE {NORMALIZED_ROLE} IN ('CUSTOMER_ADMIN','CUSTOMER_ADMINISTRATOR')"
    )
    op.create_check_constraint(
        op.f(CONSTRAINT),
        "auth_users",
        f"{NORMALIZED_ROLE} NOT IN "
        "('PLATFORM_ADMIN','MDARIX_ADMINISTRATOR','ADMINISTRATOR','ADMIN',"
        "'CUSTOMER_ADMIN','CUSTOMER_ADMINISTRATOR') "
        "OR role IN ('PLATFORM_ADMIN','CUSTOMER_ADMIN')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "auth_users", type_="check")
