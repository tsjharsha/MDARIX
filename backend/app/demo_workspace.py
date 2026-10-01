"""The AcmeCare demo workspace: the golden investigation story, visible to a named demo team, resettable on demand.

- setup: registers the workspace's data location, checks its plan features, and creates or refreshes one demo user
  per role (all sharing MDARIX_DEMO_PASSWORD). Idempotent.
- reset: deletes every record the demo created (decisions, AI runs, uploads...) and reloads the original story, so
  each demo starts from the same state. Users, plan and the audit trail are kept; the reset itself is audited.
- status: what the workspace holds and who can sign in.

The demo team uses example addresses on the reserved .invalid domain, so no email is ever delivered to them.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from auth.service import _hash
from backend.app.db.data_plane import SHARED_CONTROL_DATA_PLANE
from backend.app.db.models.customer_lifecycle import TenantDataPlane
from backend.app.db.models.foundation import (
    AuditEvent,
    AuthUser,
    Change,
    Complaint,
    Evidence,
    FeatureEntitlement,
    Investigation,
    PlanDefinition,
    Product,
    Supplier,
    Tenant,
    TenantMembership,
    TenantPlanAssignment,
)

DEMO_TENANT_KEY = "ACME_CARE_SYNTHETIC"
DEMO_FEATURES = ("ASK_MDARIX", "DECISION_CENTER_SIGNATURES")
# (role, email, display name)
DEMO_TEAM = (
    ("Investigator", "investigator@acmecare-demo.invalid", "Ines Investigator"),
    ("Reviewer", "reviewer@acmecare-demo.invalid", "Ravi Reviewer"),
    ("Approver", "approver@acmecare-demo.invalid", "Ana Approver"),
    ("Leader", "leader@acmecare-demo.invalid", "Lena Leader"),
    ("Viewer", "viewer@acmecare-demo.invalid", "Victor Viewer"),
    ("CUSTOMER_ADMIN", "admin@acmecare-demo.invalid", "Carla Customer Admin"),
)
MIN_PASSWORD_LENGTH = 12


class DemoWorkspaceError(RuntimeError):
    pass


def _tenant(db: Session) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.tenant_key == DEMO_TENANT_KEY).first()
    if tenant is None:
        raise DemoWorkspaceError("The AcmeCare tenant does not exist yet. Run: python scripts/demo_tenant.py reset")
    return tenant


def _audit(db: Session, tenant_id, action: str, details: dict, now: datetime) -> None:
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref="system:demo-workspace",
            action=action,
            entity_type="Tenant",
            entity_id=tenant_id,
            details=details,
            created_at=now,
        )
    )


def setup_demo(db: Session, password: str) -> dict:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise DemoWorkspaceError(f"Set MDARIX_DEMO_PASSWORD (at least {MIN_PASSWORD_LENGTH} characters).")
    now = datetime.now(timezone.utc)
    tenant = _tenant(db)

    plane = db.query(TenantDataPlane).filter(TenantDataPlane.tenant_id == tenant.id).first()
    if plane is None:
        db.add(
            TenantDataPlane(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                database_ref=f"shared-control:{tenant.tenant_key}",
                connection_secret_ref=SHARED_CONTROL_DATA_PLANE,
                region="UNSPECIFIED",
                residency_region="UNSPECIFIED",
                schema_version="control-plane",
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            )
        )
    elif plane.connection_secret_ref != SHARED_CONTROL_DATA_PLANE or plane.status != "ACTIVE":
        raise DemoWorkspaceError("The AcmeCare tenant is registered to another data plane; refusing to change it.")

    assignment = (
        db.query(TenantPlanAssignment)
        .filter(TenantPlanAssignment.tenant_id == tenant.id, TenantPlanAssignment.status == "ACTIVE")
        .first()
    )
    missing_features: list[str] = list(DEMO_FEATURES)
    if assignment is not None:
        enabled = {
            code
            for (code,) in db.query(FeatureEntitlement.feature_code).filter(
                FeatureEntitlement.plan_id == assignment.plan_id,
                FeatureEntitlement.enabled.is_(True),
                FeatureEntitlement.status == "ACTIVE",
            )
        }
        missing_features = [feature for feature in DEMO_FEATURES if feature not in enabled]
    if missing_features:
        raise DemoWorkspaceError(
            f"The AcmeCare plan does not enable {', '.join(missing_features)}; assign a plan that does first."
        )

    created, refreshed = [], []
    password_hash = _hash(password)
    for role, email, name in DEMO_TEAM:
        user = db.query(AuthUser).filter(AuthUser.username == email).first()
        if user is not None and user.tenant_id != tenant.id:
            raise DemoWorkspaceError(f"{email} belongs to another tenant; refusing to move it.")
        if user is None:
            user = AuthUser(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                username=email,
                display_name=name,
                company="AcmeCare Instruments (demo)",
                password_hash=password_hash,
                role=role,
                status="ACTIVE",
                email_verified=True,
                password_changed_at=now,
                created_at=now,
                updated_at=now,
            )
            db.add(user)
            db.flush()
            created.append(email)
        else:
            user.display_name, user.role, user.status, user.email_verified = name, role, "ACTIVE", True
            user.password_hash, user.password_changed_at, user.updated_at = password_hash, now, now
            refreshed.append(email)
        membership = (
            db.query(TenantMembership)
            .filter(TenantMembership.tenant_id == tenant.id, TenantMembership.user_id == user.id)
            .first()
        )
        if membership is None:
            db.add(
                TenantMembership(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    user_id=user.id,
                    status="ACTIVE",
                    is_default=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            membership.status, membership.updated_at = "ACTIVE", now
    _audit(db, tenant.id, "DEMO_WORKSPACE_SETUP", {"created": created, "refreshed": refreshed}, now)
    db.commit()
    return {"tenant_key": tenant.tenant_key, "created": created, "refreshed": refreshed}


def reset_demo(db: Session) -> dict:
    """Delete everything the demo created and reload the original story. Commits."""
    from backend.app.trial.retention import delete_tenant_records
    from ingestion.normalization.service import NormalizationService
    from ingestion.services.ingestion_service import GOLDEN_SOURCE, IngestionService

    now = datetime.now(timezone.utc)
    tenant = db.query(Tenant).filter(Tenant.tenant_key == DEMO_TENANT_KEY).first()
    deleted: dict[str, int] = {}
    if tenant is not None:
        deleted, remaining = delete_tenant_records(db, tenant.id)
        if remaining:
            db.rollback()
            raise DemoWorkspaceError(f"Could not clear demo records in: {', '.join(remaining)}")
        db.commit()
    IngestionService(GOLDEN_SOURCE).ingest_all()
    NormalizationService().normalize_all()
    import importlib.util
    from pathlib import Path

    # The three extra demo devices (OrbitCare, PulseWatch, VentraLink) come from the demo expansion seed.
    spec = importlib.util.spec_from_file_location(
        "seed_demo_expansion", Path(__file__).resolve().parents[2] / "scripts" / "seed_demo_expansion.py"
    )
    expansion = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(expansion)
    expansion.run()
    tenant = _tenant(db)
    # Make the restored story searchable again (chunks and vectors were cleared with the rest).
    from retrieval.indexing import index_tenant_evidence

    indexing = index_tenant_evidence(db, tenant.id)["indexing"]
    _audit(db, tenant.id, "DEMO_WORKSPACE_RESET", {"deleted": deleted, "indexed": indexing["indexed"]}, now)
    db.commit()
    return {"deleted": deleted, **status(db)}


def status(db: Session) -> dict:
    tenant = _tenant(db)

    def count(model) -> int:
        return int(db.query(func.count(model.id)).filter(model.tenant_id == tenant.id).scalar() or 0)

    plane = db.query(TenantDataPlane).filter(TenantDataPlane.tenant_id == tenant.id).first()
    team = []
    for role, email, _ in DEMO_TEAM:
        user = db.query(AuthUser).filter(AuthUser.username == email, AuthUser.tenant_id == tenant.id).first()
        team.append({"role": role, "email": email, "active": bool(user and user.status == "ACTIVE")})
    plan = (
        db.query(PlanDefinition.code)
        .join(TenantPlanAssignment, TenantPlanAssignment.plan_id == PlanDefinition.id)
        .filter(TenantPlanAssignment.tenant_id == tenant.id, TenantPlanAssignment.status == "ACTIVE")
        .scalar()
    )
    return {
        "tenant_key": tenant.tenant_key,
        "plan": plan,
        "data_location_registered": bool(plane and plane.status == "ACTIVE"),
        "records": {
            "products": count(Product),
            "complaints": count(Complaint),
            "investigations": count(Investigation),
            "evidence": count(Evidence),
            "changes": count(Change),
            "suppliers": count(Supplier),
        },
        "team": team,
    }
