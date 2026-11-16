"""The one definition of a free-trial organization, which every Platform Admin list reuses (TO-1, TO-D1).

- **Trial organization:** a tenant whose latest subscription is on the Free Trial plan, whatever its state: running,
  ended, ended early or with its data deleted (archived).
- **Converted:** a tenant that held the Free Trial plan (a superseded plan assignment) and whose subscription is now on
  another plan. It is a customer and appears in the main lists.
- **Trial-only customer:** a customer all of whose tenants are trial organizations (every approved trial creates its
  own customer, backend/app/trial/service.py).

The SQL clauses let a list leave trials out before it counts and pages, so its totals, pages and exports agree.
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, exists, not_, or_, select
from sqlalchemy.orm import Session, aliased

from backend.app.db.models.foundation import PlanDefinition, Tenant, TenantPlanAssignment
from backend.app.db.models.stage2 import SubscriptionLifecycle
from backend.app.trial.service import FREE_TRIAL_PLAN


def trial_tenant_ids():
    """A select of the ids of every trial organization: the tenants whose latest subscription is on the Free Trial
    plan (no newer subscription on another plan)."""
    subscription = aliased(SubscriptionLifecycle)
    newer = aliased(SubscriptionLifecycle)
    return (
        select(subscription.tenant_id)
        .join(PlanDefinition, PlanDefinition.id == subscription.plan_id)
        .where(
            PlanDefinition.code == FREE_TRIAL_PLAN,
            ~exists().where(
                newer.tenant_id == subscription.tenant_id,
                newer.created_at > subscription.created_at,
                newer.plan_id != subscription.plan_id,
            ),
        )
    )


def trial_tenant_clause(tenant_id_column):
    """True for rows whose ``tenant_id_column`` is a trial organization."""
    return tenant_id_column.in_(trial_tenant_ids())


def not_trial_clause(tenant_id_column):
    """True for rows whose ``tenant_id_column`` is not a trial organization (a row with no tenant is kept)."""
    return or_(tenant_id_column.is_(None), tenant_id_column.not_in(trial_tenant_ids()))


def trial_only_customer_clause(customer_id_column):
    """True for customers that have tenants, every one of them a trial organization."""
    some = exists().where(Tenant.customer_id == customer_id_column)
    other = aliased(Tenant)
    non_trial = exists().where(other.customer_id == customer_id_column, not_trial_clause(other.id))
    return and_(some, not_(non_trial))


def not_trial_only_customer_clause(customer_id_column):
    """True for customers shown in the main lists: those with a pilot or paying tenant, or with no tenant yet."""
    return not_(trial_only_customer_clause(customer_id_column))


def is_trial(db: Session, tenant_id: uuid.UUID) -> bool:
    return db.query(Tenant.id).filter(Tenant.id == tenant_id, trial_tenant_clause(Tenant.id)).first() is not None


def was_trial(db: Session, tenant_id: uuid.UUID) -> bool:
    """True when the tenant ever held the Free Trial plan (current or superseded)."""
    return (
        db.query(TenantPlanAssignment.id)
        .join(PlanDefinition, PlanDefinition.id == TenantPlanAssignment.plan_id)
        .filter(TenantPlanAssignment.tenant_id == tenant_id, PlanDefinition.code == FREE_TRIAL_PLAN)
        .first()
        is not None
    )


def is_converted(db: Session, tenant_id: uuid.UUID) -> bool:
    """A former trial now on another plan: a customer."""
    return was_trial(db, tenant_id) and not is_trial(db, tenant_id)


def converted_tenant_ids():
    """A select of the ids of converted trials: a superseded Free Trial assignment and no longer a trial."""
    return (
        select(TenantPlanAssignment.tenant_id)
        .join(PlanDefinition, PlanDefinition.id == TenantPlanAssignment.plan_id)
        .where(
            PlanDefinition.code == FREE_TRIAL_PLAN,
            TenantPlanAssignment.status == "SUPERSEDED",
            TenantPlanAssignment.tenant_id.not_in(trial_tenant_ids()),
        )
        .distinct()
    )
