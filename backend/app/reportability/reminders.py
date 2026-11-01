"""Reminders for reporting and CAPA, swept by the scheduler for every active organization.

- Reportability: a REPORTABILITY_DECISION task in the regulatory reviewers' queue for each complaint whose reporting
  clock is due soon or overdue and that has no decision yet (at most ``NEW_TASKS_PER_RUN`` new ones a run, the most
  urgent first, so a first import of old complaints never floods the queue). A task whose complaint no longer needs a
  decision (decided here, settled by its case's regulatory review, or off the watch) is completed.
- CAPA effectiveness: an EFFECTIVENESS_CHECK task for each planned check whose day is near or past
  (backend/app/capa_effectiveness/router.py ``sweep_tenant``).

Tasks are not tied to a case, so closing a case never cancels them. Everything is idempotent.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from backend.app.reportability import rules, service
from backend.app.reportability.router import COMPLAINT_SOURCE, REMINDER_TASK

logger = logging.getLogger("mdarix.reportability")
NEW_TASKS_PER_RUN = 50
ACTOR = "system:scheduler"


def _due_at(day: str) -> datetime:
    return datetime.combine(date.fromisoformat(day), datetime.max.time().replace(microsecond=0), tzinfo=timezone.utc)


def sweep_reportability(db: Session, tenant_id: uuid.UUID, today: date | None = None) -> dict:
    """Create and settle the organization's reportability reminder tasks. Does not commit."""
    from backend.app.db.models.workflow import OPEN_TASK_STATUSES, WorkflowTask
    from backend.app.workflow import tasks as task_service

    today = today or service.today_utc()
    watched = service.watch(db, None, tenant_id, show="open", page=1, page_size=10**6, today=today)["items"]
    waiting = {item["id"]: item for item in watched}
    open_tasks = (
        db.query(WorkflowTask)
        .filter(
            WorkflowTask.tenant_id == tenant_id,
            WorkflowTask.task_type == REMINDER_TASK,
            WorkflowTask.status.in_(list(OPEN_TASK_STATUSES)),
        )
        .all()
    )
    settled = 0
    reminded = {str(task.source_entity_id) for task in open_tasks}
    for task in open_tasks:
        if str(task.source_entity_id) in waiting:
            continue
        with db.begin_nested():
            task_service.complete_tasks(
                db,
                tenant_id,
                source_type=COMPLAINT_SOURCE,
                source_id=task.source_entity_id,
                task_types=[REMINDER_TASK],
                outcome="NO_LONGER_NEEDED",
                actor_ref=ACTOR,
                reason="The complaint's reportability is decided or it left the watch",
            )
        settled += 1
    created = 0
    for item in watched:  # most urgent first
        if created >= NEW_TASKS_PER_RUN:
            break
        if item["state"] not in (rules.OVERDUE, rules.DUE_SOON) or item["id"] in reminded or not item["binding"]:
            continue
        binding = item["binding"]
        ref = item["business_id"] or item["complaint_identifier"] or "a complaint"
        overdue = item["state"] == rules.OVERDUE
        with db.begin_nested():
            task_service.create_task(
                db,
                tenant_id,
                task_type=REMINDER_TASK,
                title=f"Reportability decision for {ref}: {'overdue since' if overdue else 'due'} {binding['due_date']}"
                f" ({binding['window']})",
                source_type=COMPLAINT_SOURCE,
                source_id=uuid.UUID(item["id"]),
                priority="CRITICAL" if overdue or item.get("death") else "HIGH",
                due_at=_due_at(binding["due_date"]),
                created_by=ACTOR,
                details={
                    "complaint_id": item["id"],
                    "complaint_business_id": ref,
                    "window": binding["window"],
                    "due_date": binding["due_date"],
                },
            )
        created += 1
    return {"created": created, "settled": settled}


def active_tenant_ids(control_db: Session) -> list:
    """Every active organization this deployment serves, on the shared plane or its own database (also the reminders
    sweep's list, backend/app/oversight/service.py)."""
    from backend.app.customer_lifecycle import customer_allows_access_clause
    from backend.app.db.models.customer_lifecycle import TenantDataPlane
    from backend.app.db.models.foundation import Tenant
    from backend.app.deployment_role import served_tenants_clause

    return [
        row.id
        for row in control_db.query(Tenant.id)
        .join(TenantDataPlane, TenantDataPlane.tenant_id == Tenant.id)
        .filter(
            Tenant.status.in_(["ACTIVE", "active"]),
            TenantDataPlane.status == "ACTIVE",
            customer_allows_access_clause(),
            served_tenants_clause(Tenant.id),
        )
        .order_by(Tenant.id)
        .all()
    ]


def run_for_all_tenants(control_db: Session) -> dict:
    """The scheduler job: both sweeps for every active organization, on the shared plane or its own database, each
    committed on its own. A failing organization is logged and reported and the others still run; the job then fails
    so the scheduler alerts after repeated failures."""
    from backend.app.capa_effectiveness.router import sweep_tenant as sweep_effectiveness
    from backend.app.db.data_plane import open_tenant_data_session

    totals = {"tenants": 0, "reportability_created": 0, "reportability_settled": 0, "effectiveness_created": 0}
    failed = []
    for tenant_id in active_tenant_ids(control_db):
        try:
            with open_tenant_data_session(tenant_id) as data:
                try:
                    done = sweep_reportability(data, tenant_id)
                    made = sweep_effectiveness(data, tenant_id)
                    data.commit()
                except Exception:
                    data.rollback()
                    raise
        except Exception as exc:
            logger.exception("The reporting and CAPA reminders failed for organization %s", tenant_id)
            failed.append({"tenant_id": str(tenant_id), "error": type(exc).__name__})
            continue
        totals["tenants"] += 1
        totals["reportability_created"] += done["created"]
        totals["reportability_settled"] += done["settled"]
        totals["effectiveness_created"] += made
    if failed:
        raise RuntimeError(f"Reporting and CAPA reminders failed for {len(failed)} organization(s): {failed}")
    return {**totals, "failed": failed}
