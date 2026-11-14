"""Workflow records (migration md27): the additional workflow roles a person holds, and the tasks that carry every
hand-off between people (My Work), with the history of each task.

- ``user_additional_roles``: roles a person holds besides their account role (``auth_users.role``), so one person in a
  small company can be, say, Investigator and Risk Reviewer. Effective permissions are the union of all their roles.
- ``workflow_tasks``: one piece of work for a person or for everyone holding a role (a role queue), always about one
  source record (an investigation, a decision, a risk, an evidence request ...). Numbered TASK000001 per organization.
- ``workflow_task_events``: what happened to a task, who did it and under which role. Never updated.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.db.business_id import business_id_column

__all__ = [
    "TASK_PRIORITIES",
    "TASK_STATUSES",
    "OPEN_TASK_STATUSES",
    "UserAdditionalRole",
    "WorkflowTask",
    "WorkflowTaskEvent",
]

# Every status a task can have. NEW: in a role queue, nobody owns it yet. ASSIGNED: given to a person who has not
# accepted it. ACCEPTED / IN_PROGRESS: being worked on. WAITING: blocked on someone else (a supplier, a reviewer).
# COMPLETED, CANCELLED and SUPERSEDED end a task; DECLINED and ESCALATED need someone to act on it again.
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
OPEN_TASK_STATUSES = ("NEW", "ASSIGNED", "ACCEPTED", "IN_PROGRESS", "WAITING", "DECLINED", "ESCALATED")
TASK_PRIORITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _quoted(values) -> str:
    return ", ".join(f"'{value}'" for value in values)


class UserAdditionalRole(Base):
    """A workflow role a person holds in addition to their account role. Revoking keeps the row (status REVOKED)."""

    __tablename__ = "user_additional_roles"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role_code: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ACTIVE")
    reason: Mapped[str | None] = mapped_column(Text)
    granted_by: Mapped[str | None] = mapped_column(String(255))
    granted_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    revoked_by: Mapped[str | None] = mapped_column(String(255))
    revoked_at = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # DB-1 (tr23).
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["auth_users.tenant_id", "auth_users.id"],
            name="fk_user_additional_roles_user_id_tenant",
        ),
        UniqueConstraint("tenant_id", "user_id", "role_code", name="uq_user_additional_roles_user_role"),
        CheckConstraint("status IN ('ACTIVE', 'REVOKED')", name="status_known"),
        Index("ix_user_additional_roles_tenant_user", "tenant_id", "user_id"),
    )


class SigningGrant(Base):
    """An administrator gave a person a role that signs (R11): until a second administrator confirms it, the person
    does not sign under that role (backend/app/access/signing_grants.py). One row per person and role; a new grant
    of the same role after it was taken away opens the row again."""

    __tablename__ = "signing_grants"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role_code: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    requested_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        # DB-1 (tr23).
        ForeignKeyConstraint(
            ["tenant_id", "user_id"], ["auth_users.tenant_id", "auth_users.id"], name="fk_signing_grants_user_id_tenant"
        ),
        UniqueConstraint("tenant_id", "user_id", "role_code", name="uq_signing_grants_user_role"),
        CheckConstraint("status IN ('PENDING', 'CONFIRMED', 'REFUSED')", name="status_known"),
        Index("ix_signing_grants_tenant_status", "tenant_id", "status"),
    )


class WorkflowTask(Base):
    """One piece of work: for a person (``assigned_user_id``) or a role queue (``assigned_role`` only)."""

    __tablename__ = "workflow_tasks"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    business_id: Mapped[str] = business_id_column()
    task_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    assigned_role: Mapped[str | None] = mapped_column(String(60))
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    priority: Mapped[str] = mapped_column(String(20), nullable=False, server_default="MEDIUM")
    due_at = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="NEW")
    is_return: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    accepted_at = mapped_column(DateTime(timezone=True))
    completed_at = mapped_column(DateTime(timezone=True))
    completion_outcome: Mapped[str | None] = mapped_column(String(60))
    escalation_level: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    reassignment_reason: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_workflow_tasks_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_workflow_tasks_investigation",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"status IN ({_quoted(TASK_STATUSES)})", name="status_known"),
        CheckConstraint(f"priority IN ({_quoted(TASK_PRIORITIES)})", name="priority_known"),
        CheckConstraint("assigned_role IS NOT NULL OR assigned_user_id IS NOT NULL", name="has_assignee"),
        Index("ix_workflow_tasks_tenant_user_status", "tenant_id", "assigned_user_id", "status"),
        Index("ix_workflow_tasks_tenant_role_status", "tenant_id", "assigned_role", "status"),
        Index("ix_workflow_tasks_tenant_source", "tenant_id", "source_entity_type", "source_entity_id"),
        Index("ix_workflow_tasks_tenant_investigation", "tenant_id", "investigation_id"),
    )


class WorkflowTaskEvent(Base):
    """What happened to a task: created, assigned, accepted, declined, claimed, reassigned, completed, cancelled."""

    __tablename__ = "workflow_task_events"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_ref: Mapped[str | None] = mapped_column(String(255))
    actor_role: Mapped[str | None] = mapped_column(String(60))
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str | None] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "task_id"],
            ["workflow_tasks.tenant_id", "workflow_tasks.id"],
            name="fk_workflow_task_events_task",
            ondelete="CASCADE",
        ),
        Index("ix_workflow_task_events_tenant_task", "tenant_id", "task_id"),
    )
