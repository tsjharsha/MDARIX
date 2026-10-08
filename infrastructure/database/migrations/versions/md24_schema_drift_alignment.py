"""Align ORM metadata and the migrated PostgreSQL schema for deterministic drift checks.

This migration closes historical metadata gaps without removing migration-owned RLS,
vector, or performance objects.  Timestamp backfills make the NOT NULL transitions safe
for databases created before those model invariants were declared.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "md24schemadrift"
down_revision = "md23pilotreadiness"
branch_labels = None
depends_on = None

REQUIRED_TIMESTAMPS = {
    "assurance_checks": ("created_at",),
    "assurance_results": ("generated_at", "created_at"),
    "auth_users": ("created_at", "updated_at"),
    "connector_configurations": ("created_at", "updated_at"),
    "decisions": ("updated_at",),
    "evaluation_runs": ("started_at", "created_at"),
    "investigation_briefs": ("created_at", "updated_at"),
    "mapping_configurations": ("created_at", "updated_at"),
    "mapping_impact_history": ("created_at",),
    "master_mappings": ("created_at", "updated_at"),
    "permission_set_definitions": ("created_at", "updated_at"),
    "persona_assignments": ("created_at", "updated_at"),
    "release_assurance_results": ("generated_at", "created_at"),
    "role_assignments": ("created_at", "updated_at"),
    "role_definitions": ("created_at", "updated_at"),
    "role_permission_sets": ("created_at",),
    "tenant_mapping_overrides": ("created_at", "updated_at"),
    "tenant_mapping_versions": ("created_at", "updated_at"),
    "tenant_memberships": ("created_at", "updated_at"),
}

TENANT_FOREIGN_KEYS = (
    "assurance_checks",
    "assurance_results",
    "auth_users",
    "evaluation_runs",
    "investigation_briefs",
    "password_history",
    "release_assurance_results",
    "role_assignments",
    "role_permission_sets",
)

UTC_TIMESTAMP_COLUMNS = {
    "regulatory_document_versions": ("created_at",),
    "regulatory_documents": ("created_at", "updated_at"),
    "report_jobs": ("created_at", "updated_at"),
}


def _set_timestamp_required(table: str, column: str) -> None:
    op.execute(f'UPDATE "{table}" SET "{column}" = now() WHERE "{column}" IS NULL')
    op.alter_column(table, column, existing_type=sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    for table, columns in REQUIRED_TIMESTAMPS.items():
        for column in columns:
            _set_timestamp_required(table, column)

    for table in TENANT_FOREIGN_KEYS:
        op.create_foreign_key(f"fk_{table}_tenant_id_tenants", table, "tenants", ["tenant_id"], ["id"])

    op.create_unique_constraint(
        "uq_context_snapshot_version",
        "context_snapshots",
        ["tenant_id", "decision_id", "decision_version"],
    )

    for column in ("limitations", "temporal_context", "context_snapshot"):
        op.alter_column(
            "decisions",
            column,
            existing_type=sa.JSON(),
            type_=postgresql.JSONB(),
            postgresql_using=f'"{column}"::jsonb',
        )

    for table, columns in UTC_TIMESTAMP_COLUMNS.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                existing_type=sa.DateTime(timezone=False),
                type_=sa.DateTime(timezone=True),
                postgresql_using=f"\"{column}\" AT TIME ZONE 'UTC'",
            )


def downgrade() -> None:
    for table, columns in reversed(tuple(UTC_TIMESTAMP_COLUMNS.items())):
        for column in reversed(columns):
            op.alter_column(
                table,
                column,
                existing_type=sa.DateTime(timezone=True),
                type_=sa.DateTime(timezone=False),
                postgresql_using=f"\"{column}\" AT TIME ZONE 'UTC'",
            )

    for column in reversed(("limitations", "temporal_context", "context_snapshot")):
        op.alter_column(
            "decisions",
            column,
            existing_type=postgresql.JSONB(),
            type_=sa.JSON(),
            postgresql_using=f'"{column}"::json',
        )

    op.drop_constraint("uq_context_snapshot_version", "context_snapshots", type_="unique")

    for table in reversed(TENANT_FOREIGN_KEYS):
        op.drop_constraint(f"fk_{table}_tenant_id_tenants", table, type_="foreignkey")

    for table, columns in reversed(tuple(REQUIRED_TIMESTAMPS.items())):
        for column in reversed(columns):
            op.alter_column(table, column, existing_type=sa.DateTime(timezone=True), nullable=True)
