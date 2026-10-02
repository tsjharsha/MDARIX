"""Whether a tenant's active plan includes a feature.

Core features (controlled decision signatures, Ask MDARIX) are part of every active plan unless the plan explicitly
lists the feature as disabled. Other features must be listed and enabled on the plan.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.app.db.models.foundation import FeatureEntitlement, PlanDefinition, TenantPlanAssignment

CORE_FEATURES = frozenset({"DECISION_CENTER_SIGNATURES", "ASK_MDARIX"})


def plan_includes(db, tenant_id, feature_code: str) -> bool:
    now = datetime.now(timezone.utc)
    active = (
        db.query(TenantPlanAssignment)
        .join(PlanDefinition, PlanDefinition.id == TenantPlanAssignment.plan_id)
        .filter(
            TenantPlanAssignment.tenant_id == tenant_id,
            TenantPlanAssignment.status == "ACTIVE",
            PlanDefinition.status == "ACTIVE",
            TenantPlanAssignment.effective_from <= now,
        )
    )
    if active.first() is None:
        return False  # no active plan, no features
    listed = active.join(FeatureEntitlement, FeatureEntitlement.plan_id == PlanDefinition.id).filter(
        FeatureEntitlement.feature_code == feature_code
    )
    if listed.filter(FeatureEntitlement.enabled.is_(True), FeatureEntitlement.status == "ACTIVE").first() is not None:
        return True
    if listed.first() is not None:
        return False  # the plan lists the feature, switched off
    return feature_code in CORE_FEATURES
