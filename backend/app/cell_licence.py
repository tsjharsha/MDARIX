"""The licence a tenant cell runs under.

The platform issues a signed LICENCE document (backend/app/cell_packages.py) naming the organization, its plan, the
plan's features and the organization's limits. Applying it in the cell writes exactly the rows the application
already reads for entitlements (``plan_definitions``, ``feature_entitlements``, ``tenant_plan_assignments``; see
backend/app/access/plan_features.py), supersedes the previous assignment, records the licence in ``cell_licences``
and audits it. A SUSPENDED licence suspends the organization; an ACTIVE one lifts a suspension the licence caused.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.cell_packages import PackageError, verify
from backend.app.db.models.customer_lifecycle import CellLicence
from backend.app.db.models.foundation import (
    AuditEvent,
    FeatureEntitlement,
    PlanDefinition,
    Tenant,
    TenantPlanAssignment,
)

ACTOR = "system:cell-licence"
STATUSES = ("ACTIVE", "SUSPENDED")
REQUIRED = ("licence_id", "tenant_id", "tenant_key", "plan", "features", "status", "issued_at")


def _when(value, name: str, *, nullable: bool = False) -> datetime | None:
    if value in (None, ""):
        if nullable:
            return None
        raise PackageError(f"LICENCE_FIELD_MISSING:{name}")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise PackageError(f"LICENCE_TIME_INVALID:{name}") from exc
    if parsed.tzinfo is None:
        raise PackageError(f"LICENCE_TIME_INVALID:{name}")
    return parsed


def licence_content(
    tenant: Tenant,
    plan: PlanDefinition,
    entitlements: list[FeatureEntitlement],
    limits: dict | None,
    *,
    issued_at: datetime,
    valid_until: datetime | None = None,
    status: str = "ACTIVE",
    licence_id: uuid.UUID | None = None,
) -> dict:
    """The content of a licence for ``tenant`` (the platform signs it with cell_packages.sign)."""
    if status not in STATUSES:
        raise PackageError("LICENCE_STATUS")
    return {
        "licence_id": str(licence_id or uuid.uuid4()),
        "tenant_id": str(tenant.id),
        "tenant_key": tenant.tenant_key,
        "plan": {"code": plan.code, "name": plan.name, "version": plan.version, "description": plan.description},
        "features": [
            {"code": item.feature_code, "enabled": bool(item.enabled), "limits": item.limits or {}}
            for item in sorted(entitlements, key=lambda item: item.feature_code)
        ],
        "limits": limits or {},
        "status": status,
        "issued_at": issued_at.isoformat(),
        "valid_until": valid_until.isoformat() if valid_until else None,
    }


def apply_licence(db: Session, envelope: dict, public_key: str, *, now: datetime | None = None) -> dict:
    """Verify ``envelope`` and make it the organization's plan. Commits. Applying the same licence twice is a no-op."""
    now = now or datetime.now(timezone.utc)
    content = verify(envelope, public_key, kind="LICENCE")
    for name in REQUIRED:
        if name not in content:
            raise PackageError(f"LICENCE_FIELD_MISSING:{name}")
    if content["status"] not in STATUSES:
        raise PackageError("LICENCE_STATUS")
    try:
        tenant_id, licence_id = uuid.UUID(str(content["tenant_id"])), uuid.UUID(str(content["licence_id"]))
    except ValueError as exc:
        raise PackageError("LICENCE_IDENTIFIER") from exc
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise PackageError("LICENCE_TENANT_UNKNOWN")
    if tenant.tenant_key != content["tenant_key"]:
        raise PackageError("LICENCE_TENANT_KEY")
    digest = str(envelope.get("content_sha256"))
    if db.query(CellLicence).filter(CellLicence.content_sha256 == digest).first() is not None:
        return {"applied": False, "reason": "ALREADY_APPLIED", "licence_id": str(licence_id), "content_sha256": digest}
    issued_at = _when(content["issued_at"], "issued_at")
    valid_until = _when(content.get("valid_until"), "valid_until", nullable=True)
    plan_spec = content["plan"]
    if not isinstance(plan_spec, dict) or not plan_spec.get("code"):
        raise PackageError("LICENCE_PLAN")

    plan = db.query(PlanDefinition).filter(PlanDefinition.code == str(plan_spec["code"])).first()
    if plan is None:
        plan = PlanDefinition(
            id=uuid.uuid4(),
            code=str(plan_spec["code"]),
            name=str(plan_spec.get("name") or plan_spec["code"]),
            description=plan_spec.get("description"),
            version=str(plan_spec.get("version") or "1"),
            status="ACTIVE",
            effective_from=issued_at,
            created_at=now,
            updated_at=now,
        )
        db.add(plan)
        db.flush()
    else:
        plan.name = str(plan_spec.get("name") or plan.name)
        plan.version = str(plan_spec.get("version") or plan.version)
        plan.description = plan_spec.get("description", plan.description)
        plan.status = "ACTIVE"
        plan.updated_at = now

    wanted = {str(item["code"]): item for item in content["features"] if isinstance(item, dict) and item.get("code")}
    existing = {
        row.feature_code: row for row in db.query(FeatureEntitlement).filter(FeatureEntitlement.plan_id == plan.id)
    }
    for code, spec in wanted.items():
        row = existing.get(code)
        if row is None:
            db.add(
                FeatureEntitlement(
                    id=uuid.uuid4(),
                    plan_id=plan.id,
                    feature_code=code,
                    enabled=bool(spec.get("enabled", True)),
                    limits=spec.get("limits") or None,
                    status="ACTIVE",
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            row.enabled = bool(spec.get("enabled", True))
            row.limits = spec.get("limits") or None
            row.status = "ACTIVE"
            row.updated_at = now
    for code, row in existing.items():
        if code not in wanted:
            row.enabled = False
            row.status = "INACTIVE"
            row.updated_at = now

    for previous in (
        db.query(TenantPlanAssignment)
        .filter(TenantPlanAssignment.tenant_id == tenant.id, TenantPlanAssignment.status == "ACTIVE")
        .all()
    ):
        previous.status = "SUPERSEDED"
        previous.effective_to = now
        previous.updated_at = now
    db.add(
        TenantPlanAssignment(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            plan_id=plan.id,
            status="ACTIVE" if content["status"] == "ACTIVE" else "SUSPENDED",
            effective_from=min(issued_at, now),
            effective_to=valid_until,
            reason=f"Licence {licence_id}",
            limits=content.get("limits") or None,
            created_at=now,
            updated_at=now,
        )
    )

    last = (
        db.query(CellLicence).filter(CellLicence.tenant_id == tenant.id).order_by(CellLicence.applied_at.desc()).first()
    )
    if content["status"] == "SUSPENDED" and tenant.status == "ACTIVE":
        tenant.status = "SUSPENDED"
        tenant.suspended_at = now
    elif (
        content["status"] == "ACTIVE"
        and tenant.status == "SUSPENDED"
        and last is not None
        and last.status == "SUSPENDED"
    ):
        tenant.status = "ACTIVE"
        tenant.suspended_at = None
    tenant.updated_at = now

    db.add(
        CellLicence(
            id=licence_id,
            tenant_id=tenant.id,
            content_sha256=digest,
            key_id=str(envelope.get("key_id") or "platform"),
            status=content["status"],
            issued_at=issued_at,
            valid_until=valid_until,
            applied_at=now,
            envelope=envelope,
        )
    )
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            actor_ref=ACTOR,
            action="LICENCE_APPLIED",
            entity_type="CellLicence",
            entity_id=licence_id,
            details={
                "plan": plan.code,
                "status": content["status"],
                "valid_until": content.get("valid_until"),
                "features": sorted(wanted),
                "content_sha256": digest,
                "key_id": str(envelope.get("key_id") or "platform"),
            },
            created_at=now,
        )
    )
    db.commit()
    return {
        "applied": True,
        "licence_id": str(licence_id),
        "plan": plan.code,
        "status": content["status"],
        "features": sorted(wanted),
        "valid_until": content.get("valid_until"),
        "content_sha256": digest,
    }
