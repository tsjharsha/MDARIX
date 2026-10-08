"""Workflow foundation (Phase 1): additional workflow roles per person, and workflow tasks with their history.

- ``user_additional_roles``: roles a person holds besides their account role, so one person can hold several
  workflow roles. Tenant-isolated like ``role_assignments``.
- ``workflow_tasks``: every hand-off between people (assignment, review, approval, evidence request ...), for a person
  or a role queue. Numbered TASK000001 per organization by the business-id trigger of md26; the number never changes.
- ``workflow_task_events``: the history of each task. Tenant-isolated.

The models are in backend/app/db/models/workflow.py. Legacy dedicated organization databases get the same tables
from scripts/add_workflow_tables_to_legacy_planes.py, which runs this module's ``create_workflow_tables``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import quoted as _quoted
from infrastructure.database.migrations.helpers import register_prefixes
from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

from infrastructure.database.migrations.business_ids import COUNTER_TABLE, LATER_OBJECTS, WIDTH

revision = "md27workflow"
down_revision = "md26businessids"
branch_labels = None
depends_on = None

TASK_STATUSES = (
    "NEW",
    "ASSIGNED",
    "ACCEPTED",
    "IN_PROGRESS",
    "WAITING",
    "COMPLETED",
    "DECLINED",
    "ESCALATED",
    "CANCELLED",
    "SUPERSEDED",
)
TASK_PRIORITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
TASKS = next(item for item in LATER_OBJECTS if item.table == "workflow_tasks")


def create_workflow_tables(system_scope: bool = True) -> None:
    """The three tables, their isolation and the task numbering (also used for legacy organization databases)."""
    op.create_table(
        "user_additional_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_code", sa.String(60), nullable=False),
        sa.Column("status", sa.String(20), server_default="ACTIVE", nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("granted_by", sa.String(255)),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_by", sa.String(255)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_additional_roles")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_user_additional_roles_tenant_id_tenants")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["auth_users.id"], name=op.f("fk_user_additional_roles_user_id_auth_users")
        ),
        sa.UniqueConstraint("tenant_id", "user_id", "role_code", name="uq_user_additional_roles_user_role"),
        sa.CheckConstraint("status IN ('ACTIVE', 'REVOKED')", name=op.f("ck_user_additional_roles_status_known")),
    )
    op.create_index("ix_user_additional_roles_tenant_user", "user_additional_roles", ["tenant_id", "user_id"])
    _tenant_policy("user_additional_roles", system_scope)

    op.create_table(
        "workflow_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", sa.String(20), nullable=False),
        sa.Column("task_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("source_entity_type", sa.String(60), nullable=False),
        sa.Column("source_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("assigned_role", sa.String(60)),
        sa.Column("assigned_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("priority", sa.String(20), server_default="MEDIUM", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(30), server_default="NEW", nullable=False),
        sa.Column("is_return", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("completion_outcome", sa.String(60)),
        sa.Column("escalation_level", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("reassignment_reason", sa.Text()),
        sa.Column("details", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_tasks")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_workflow_tasks_tenant_id_tenants")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_workflow_tasks_investigation",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_workflow_tasks_tenant_id_id"),
        sa.CheckConstraint(f"status IN ({_quoted(TASK_STATUSES)})", name=op.f("ck_workflow_tasks_status_known")),
        sa.CheckConstraint(f"priority IN ({_quoted(TASK_PRIORITIES)})", name=op.f("ck_workflow_tasks_priority_known")),
        sa.CheckConstraint(
            "assigned_role IS NOT NULL OR assigned_user_id IS NOT NULL", name=op.f("ck_workflow_tasks_has_assignee")
        ),
    )
    op.create_index(
        "ix_workflow_tasks_tenant_user_status", "workflow_tasks", ["tenant_id", "assigned_user_id", "status"]
    )
    op.create_index("ix_workflow_tasks_tenant_role_status", "workflow_tasks", ["tenant_id", "assigned_role", "status"])
    op.create_index(
        "ix_workflow_tasks_tenant_source", "workflow_tasks", ["tenant_id", "source_entity_type", "source_entity_id"]
    )
    op.create_index("ix_workflow_tasks_tenant_investigation", "workflow_tasks", ["tenant_id", "investigation_id"])
    _tenant_policy("workflow_tasks", system_scope)
    # Task numbers: the md26 assigning function on insert, unique per organization, never changed afterwards.
    op.execute(f"CREATE UNIQUE INDEX {TASKS.index_name} ON public.workflow_tasks (tenant_id, business_id)")
    op.execute(
        f"CREATE TRIGGER {TASKS.trigger_name} BEFORE INSERT ON public.workflow_tasks "
        f"FOR EACH ROW EXECUTE FUNCTION public.mdarix_assign_business_id('{TASKS.prefix}', '{TASKS.scope}', '{WIDTH}')"
    )
    op.execute(
        f"CREATE TRIGGER {TASKS.immutable_trigger_name} BEFORE UPDATE OF business_id ON public.workflow_tasks "
        "FOR EACH ROW WHEN (OLD.business_id IS NOT NULL AND OLD.business_id IS DISTINCT FROM NEW.business_id) "
        "EXECUTE FUNCTION public.mdarix_reject_immutable_identifier()"
    )

    op.create_table(
        "workflow_task_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("actor_ref", sa.String(255)),
        sa.Column("actor_role", sa.String(60)),
        sa.Column("from_status", sa.String(30)),
        sa.Column("to_status", sa.String(30)),
        sa.Column("reason", sa.Text()),
        sa.Column("details", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_task_events")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_workflow_task_events_tenant_id_tenants")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "task_id"],
            ["workflow_tasks.tenant_id", "workflow_tasks.id"],
            name="fk_workflow_task_events_task",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_workflow_task_events_tenant_task", "workflow_task_events", ["tenant_id", "task_id"])
    _tenant_policy("workflow_task_events", system_scope)


def upgrade():
    create_workflow_tables()
    register_prefixes([TASKS])


def downgrade():
    # Prefixes are permanent (md_master.protect_prefix_registry refuses removal); re-applying reuses them.
    op.execute(f"DELETE FROM public.{COUNTER_TABLE} WHERE prefix = '{TASKS.prefix}'")
    op.drop_table("workflow_task_events")
    op.drop_table("workflow_tasks")
    op.drop_table("user_additional_roles")
