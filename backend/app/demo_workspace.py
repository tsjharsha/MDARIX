"""The AcmeCare demo workspace: a curated investigation story in its own tenant, for a named demo team, resettable.

- setup: creates the demo tenant when missing (customer, data location, plan, approval rules), loads the story into
  an empty workspace, and creates or refreshes one demo user per role (all sharing MDARIX_DEMO_PASSWORD). Demo
  accounts left in the golden evaluation tenant by earlier versions are retired there (deactivated, sessions and
  membership ended, address renamed, history kept) and recreated here; users of any other tenant are refused.
  Idempotent.
- reset: deletes every record of the demo tenant (decisions, AI runs, uploads...) and reloads the story, dated
  relative to today, so each demo starts from the same state. Users, plan and the audit trail are kept; the reset
  itself is audited. The golden evaluation tenant is never touched.
- status: what the workspace holds, who can sign in (name, address and role) and the golden path by business id.

Setup and reset also write the golden path (backend/app/demo_golden_path/): case ACD-INV-401 taken from its signal
through triage, scope, evidence, intelligence, reviews and the Decision Brief to a signed decision with its follow-up
and late evidence, so every workflow screen has a worked example; ACD-INV-101, -201 and -301 stay mid-investigation
for live demos, and detection leaves new signals awaiting triage.

The story itself is in backend/app/demo_story.py (synthetic data only). The demo team uses example addresses on the
reserved .invalid domain, so no email is ever delivered to them.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from auth.service import _hash
from backend.app import demo_story as story
from backend.app.db.data_plane import SHARED_CONTROL_DATA_PLANE
from backend.app.db.models.customer_lifecycle import Customer, TenantDataPlane
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
from backend.app.db.models.stage2 import AuthSession

DEMO_TENANT_KEY = "ACMECARE_DEMO"
DEMO_TENANT_NAME = "AcmeCare Instruments (Demo)"
# Earlier versions ran the demo inside the golden evaluation tenant; its demo users are moved out on setup.
LEGACY_DEMO_TENANT_KEY = "ACME_CARE_SYNTHETIC"
DEMO_FEATURES = ("ASK_MDARIX", "DECISION_CENTER_SIGNATURES")
# (role, email, display name). One person per workflow role (backend/app/role_codes.py WORKFLOW_ROLES): the PMS /
# Signal Triage Lead, the Quality Investigator, the Risk and Regulatory Reviewers, the Quality Reviewer, the Authorized
# Decision Maker (Approver) and the Leader, plus a read-only Viewer and the Customer Administrator.
DEMO_TEAM = (
    ("TRIAGE_LEAD", "triage@acmecare-demo.invalid", "Tara Triage"),
    ("Investigator", "investigator@acmecare-demo.invalid", "Ines Investigator"),
    # UX3: the Product Quality Engineer (its Today is the Product Lifecycle Twin).
    ("PRODUCT_QUALITY_ENGINEER", "pqe@acmecare-demo.invalid", "Priya Product Quality"),
    ("RISK_REVIEWER", "risk@acmecare-demo.invalid", "Rita Risk"),
    ("REGULATORY_REVIEWER", "regulatory@acmecare-demo.invalid", "Rory Regulatory"),
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
        raise DemoWorkspaceError("The demo tenant does not exist yet. Run: python scripts/demo_tenant.py setup")
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


def _ensure_tenant(db: Session, now: datetime) -> Tenant:
    """The demo tenant with its data location, plan and approval rules; created when missing."""
    from backend.app.governance_router import bootstrap, ensure_governance_defaults

    tenant = db.query(Tenant).filter(Tenant.tenant_key == DEMO_TENANT_KEY).first()
    if tenant is None:
        customer = Customer(
            id=uuid.uuid4(),
            customer_identifier="CUST-ACMECARE-DEMO",
            legal_name=DEMO_TENANT_NAME,
            display_name=DEMO_TENANT_NAME,
            customer_type="SYNTHETIC",
            country="UNSPECIFIED",
            lifecycle_status="ACTIVE",
            lock_version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(customer)
        db.flush()
        tenant = Tenant(
            id=uuid.uuid4(),
            customer_id=customer.id,
            tenant_key=DEMO_TENANT_KEY,
            tenant_identifier=DEMO_TENANT_KEY,
            tenant_slug="acmecare-demo",
            name=DEMO_TENANT_NAME,
            display_name=DEMO_TENANT_NAME,
            tenant_type="STANDARD",
            deployment_model="SHARED",
            primary_region="UNSPECIFIED",
            residency_region="UNSPECIFIED",
            cross_border_processing_allowed=False,
            provisioning_status="PROVISIONED",
            status="ACTIVE",
            lock_version=1,
            activated_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(tenant)
        db.flush()

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
        raise DemoWorkspaceError("The demo tenant is registered to another data plane; refusing to change it.")
    db.flush()
    bootstrap(db, tenant)  # plan with Ask and signatures, approval authority, segregation of duties (commits)
    # Every tenant's decision rules: Approvers and Leaders may approve and sign, nobody approves their own decision.
    # Only what is missing is added (commits when it adds anything).
    ensure_governance_defaults(db, tenant)

    assignment = (
        db.query(TenantPlanAssignment)
        .filter(TenantPlanAssignment.tenant_id == tenant.id, TenantPlanAssignment.status == "ACTIVE")
        .first()
    )
    enabled = set()
    if assignment is not None:
        enabled = {
            code
            for (code,) in db.query(FeatureEntitlement.feature_code).filter(
                FeatureEntitlement.plan_id == assignment.plan_id,
                FeatureEntitlement.enabled.is_(True),
                FeatureEntitlement.status == "ACTIVE",
            )
        }
    missing = [feature for feature in DEMO_FEATURES if feature not in enabled]
    if missing:
        raise DemoWorkspaceError(f"The demo plan does not enable {', '.join(missing)}; assign a plan that does first.")
    return tenant


def _index(db: Session, tenant_id) -> int:
    """Make the story searchable (chunks and vectors). Failures are recorded per chunk, never fatal."""
    from retrieval.indexing import index_tenant_evidence

    return index_tenant_evidence(db, tenant_id)["indexing"]["indexed"]


def _retire_legacy_account(db: Session, user: AuthUser, legacy_tenant_id, now: datetime) -> None:
    """End a demo account in the golden tenant without deleting it: it can no longer sign in, its sessions and
    membership end, and its address is renamed so the demo tenant can reuse it. Its history stays intact."""
    db.query(TenantMembership).filter(
        TenantMembership.tenant_id == legacy_tenant_id, TenantMembership.user_id == user.id
    ).update({"status": "INACTIVE", "is_default": False, "updated_at": now}, synchronize_session=False)
    db.query(AuthSession).filter(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)).update(
        {"revoked_at": now}, synchronize_session=False
    )
    user.username = f"retired-{user.id.hex[:12]}-{user.username}"
    user.status, user.updated_at = "INACTIVE", now
    db.flush()


def setup_demo(db: Session, password: str) -> dict:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise DemoWorkspaceError(f"Set MDARIX_DEMO_PASSWORD (at least {MIN_PASSWORD_LENGTH} characters).")
    now = datetime.now(timezone.utc)
    tenant = _ensure_tenant(db, now)
    loaded = None
    if not db.query(Product.id).filter(Product.tenant_id == tenant.id).first():
        loaded = load_story(db, tenant.id, now)
        db.commit()
        _index(db, tenant.id)

    legacy = db.query(Tenant).filter(Tenant.tenant_key == LEGACY_DEMO_TENANT_KEY).first()
    created, refreshed, moved = [], [], []
    password_hash = _hash(password)
    for role, email, name in DEMO_TEAM:
        user = db.query(AuthUser).filter(AuthUser.username == email).first()
        if user is not None and user.tenant_id != tenant.id:
            if legacy is None or user.tenant_id != legacy.id:
                raise DemoWorkspaceError(f"{email} belongs to another tenant; refusing to move it.")
            _retire_legacy_account(db, user, legacy.id, now)
            moved.append(email)
            user = None  # a fresh account is created in the demo tenant below
        if user is None:
            user = AuthUser(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                username=email,
                display_name=name,
                company=DEMO_TENANT_NAME,
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
            user.company = DEMO_TENANT_NAME
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
            membership.status, membership.is_default, membership.updated_at = "ACTIVE", True, now
    _audit(
        db,
        tenant.id,
        "DEMO_WORKSPACE_SETUP",
        {"created": created, "refreshed": refreshed, "moved_from_golden_tenant": moved, "story_loaded": loaded},
        now,
    )
    db.commit()
    # Dated from today when the story was loaded now, else from the day it was loaded; idempotent.
    golden = _seed_golden_path(db, tenant.id, now if loaded else None)
    _seed_workflow_tasks(db, tenant.id)
    _seed_signals(db, tenant.id)
    return {
        "tenant_key": tenant.tenant_key,
        "created": created,
        "refreshed": refreshed,
        "moved": moved,
        "golden_path": golden,
    }


def reset_demo(db: Session) -> dict:
    """Delete everything in the demo tenant and reload the story. Commits. Never touches any other tenant."""
    from backend.app.trial.retention import delete_tenant_records

    now = datetime.now(timezone.utc)
    tenant = _tenant(db)
    deleted, remaining = delete_tenant_records(db, tenant.id)
    if remaining:
        db.rollback()
        raise DemoWorkspaceError(f"Could not clear demo records in: {', '.join(remaining)}")
    loaded = load_story(db, tenant.id, now)
    db.commit()
    indexed = _index(db, tenant.id)
    _audit(db, tenant.id, "DEMO_WORKSPACE_RESET", {"deleted": deleted, "loaded": loaded, "indexed": indexed}, now)
    db.commit()
    golden = _seed_golden_path(db, tenant.id, now)
    _seed_workflow_tasks(db, tenant.id)
    _seed_signals(db, tenant.id)
    return {"deleted": deleted, "golden_path_seeded": golden, **status(db)}


def _seed_golden_path(db: Session, tenant_id, now: datetime | None) -> dict:
    """The golden path of the story (backend/app/demo_golden_path/): case ACD-INV-401 from its signal to a signed
    decision, written once the team exists and before the other tasks and signals are derived from the story. In a
    session of its own bound to the demo tenant, in one transaction; idempotent. A failure is logged and reported,
    never failing the setup or the reset."""
    from backend.app.demo_golden_path import seed_golden_path

    return seed_golden_path(db, tenant_id, now)


def _seed_workflow_tasks(db: Session, tenant_id) -> None:
    """The story's open work as My Work tasks (backend/app/workflow/backfill.py): each open case's task for its owner,
    decisions awaiting approval in the approvers' queue. Run once the team exists, in a session of its own bound to
    the demo tenant (same database); idempotent. A failure is logged and never fails the setup or the reset."""
    import logging

    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.workflow.backfill import backfill_tenant

    try:
        with Session(bind=db.get_bind(), autoflush=False) as session:
            bind_tenant(session, tenant_id)
            backfill_tenant(session, session, tenant_id, apply=True)
            session.commit()
    except Exception:
        logging.getLogger("mdarix.demo_workspace").exception("The demo workspace's workflow tasks were not seeded")


def _seed_signals(db: Session, tenant_id) -> None:
    """Signals from the story's complaints (the complaint threshold rule, backend/app/signals/detection.py), so the
    demo shows triage work. Idempotent; a failure is logged and never fails the setup or the reset."""
    from backend.app.signals.hooks import seed_demo_signals

    seed_demo_signals(db, tenant_id)


def load_story(db: Session, tenant_id: uuid.UUID, now: datetime | None = None) -> dict:
    """Write the curated story (backend/app/demo_story.py) into an empty demo tenant. Does not commit."""
    from backend.app.db.models.evidence_intelligence import EvidenceEntityLink
    from backend.app.db.models.foundation import (
        Component,
        ComponentSupplier,
        Control,
        InvestigationComplaint,
        InvestigationEvidence,
        LotBatch,
        ManufacturingSite,
        ProductComponent,
        ProductVersion,
        Risk,
    )

    now = now or datetime.now(timezone.utc)

    def ago(days: int) -> datetime:
        return now - timedelta(days=days)

    def stamp(days: int) -> dict:
        moment = ago(days)
        return {
            "tenant_id": tenant_id,
            "source_system": "ACMECARE_DEMO",
            "source_timestamp": moment,
            "effective_timestamp": moment,
            "recorded_timestamp": moment,
            "ingestion_timestamp": moment,
            "created_at": moment,
            "updated_at": moment,
        }

    def add(row):
        db.add(row)
        return row

    site_id, site_name, site_location = story.SITE
    site = add(
        ManufacturingSite(
            id=uuid.uuid4(),
            site_identifier=site_id,
            name=site_name,
            location=site_location,
            source_identifier=site_id,
            **stamp(900),
        )
    )
    suppliers = {
        code: add(Supplier(id=uuid.uuid4(), supplier_identifier=code, name=name, source_identifier=code, **stamp(800)))
        for code, name in story.SUPPLIERS
    }
    db.flush()
    products, versions, lots = {}, {}, {}
    for spec in story.PRODUCTS:
        product = add(
            Product(
                id=uuid.uuid4(),
                product_identifier=spec["id"],
                name=spec["name"],
                description=f"{spec['family']} device. {story.SYNTHETIC}",
                product_family=spec["family"],
                manufacturer_context="AcmeCare Instruments (synthetic demo)",
                source_identifier=spec["id"],
                **stamp(spec["versions"][0][1] + 30),
            )
        )
        db.flush()
        products[spec["id"]] = product
        for revision, released in spec["versions"]:
            versions[(spec["id"], revision)] = add(
                ProductVersion(
                    id=uuid.uuid4(),
                    product_id=product.id,
                    version_identifier=revision,
                    description=f"{spec['name']} {revision}",
                    release_timestamp=ago(released),
                    source_identifier=f"{spec['id']}-{revision}",
                    **stamp(released),
                )
            )
        db.flush()
        latest = versions[(spec["id"], spec["versions"][-1][0])]
        for code, name, revision, supplier_code in spec["components"]:
            component = add(
                Component(
                    id=uuid.uuid4(),
                    component_identifier=code,
                    name=name,
                    revision=revision,
                    source_identifier=code,
                    **stamp(spec["versions"][-1][1]),
                )
            )
            db.flush()
            add(
                ProductComponent(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    product_version_id=latest.id,
                    component_id=component.id,
                    relationship_status="active",
                    effective_timestamp=ago(spec["versions"][-1][1]),
                    created_at=now,
                )
            )
            if supplier_code:
                add(
                    ComponentSupplier(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        component_id=component.id,
                        supplier_id=suppliers[supplier_code].id,
                        effective_timestamp=ago(spec["versions"][-1][1]),
                        created_at=now,
                    )
                )
        for lot_code, made in spec["lots"]:
            revision = spec["versions"][-1][0] if made <= spec["versions"][-1][1] else spec["versions"][0][0]
            lots[lot_code] = add(
                LotBatch(
                    id=uuid.uuid4(),
                    lot_identifier=lot_code,
                    product_version_id=versions[(spec["id"], revision)].id,
                    manufacturing_site_id=site.id,
                    source_identifier=lot_code,
                    **stamp(made),
                )
            )
    for code, kind, description, days in story.CHANGES:
        add(
            Change(
                id=uuid.uuid4(),
                change_identifier=code,
                change_type=kind,
                description=description,
                event_timestamp=ago(days),
                source_identifier=code,
                **stamp(days),
            )
        )
    for code, product_code, description in story.RISKS:
        add(
            Risk(
                id=uuid.uuid4(),
                risk_identifier=code,
                product_id=products[product_code].id,
                description=description,
                source_identifier=code,
                **stamp(400),
            )
        )
    for code, kind, description in story.CONTROLS:
        add(
            Control(
                id=uuid.uuid4(),
                control_identifier=code,
                control_type=kind,
                description=description,
                source_identifier=code,
                **stamp(400),
            )
        )
    db.flush()

    investigations = {}
    for code, product_code, question, state, opened, closed in story.INVESTIGATIONS:
        investigations[code] = add(
            Investigation(
                id=uuid.uuid4(),
                investigation_identifier=code,
                product_id=products[product_code].id,
                investigation_question=question,
                status=state,
                opened_at=ago(opened),
                closed_at=ago(closed) if closed is not None else None,
                owner_ref="investigator@acmecare-demo.invalid",
                source_identifier=code,
                **stamp(opened),
            )
        )
    db.flush()
    open_case = {
        product_code: investigations[code]
        for code, product_code, _, state, _, _ in story.INVESTIGATIONS
        if state == "open"
    }
    for index, record in enumerate(story.COMPLAINTS, 1):
        # (product, version, lot, days ago, description[, problem code])
        product_code, revision, lot_code, days, description = record[:5]
        problem_code = record[5] if len(record) > 5 else None
        complaint = add(
            Complaint(
                id=uuid.uuid4(),
                complaint_identifier=f"ACD-CMP-{index:04d}",
                product_id=products[product_code].id,
                product_version_id=versions[(product_code, revision)].id,
                lot_batch_id=lots[lot_code].id,
                event_timestamp=ago(days),
                complaint_timestamp=ago(max(days - 1, 0)),
                description=description,
                problem_code=problem_code,
                source_identifier=f"ACD-CMP-{index:04d}",
                **stamp(days),
            )
        )
        db.flush()
        if product_code in open_case:
            add(
                InvestigationComplaint(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    investigation_id=open_case[product_code].id,
                    complaint_id=complaint.id,
                    created_at=now,
                )
            )
    product_of_case = {code: product_code for code, product_code, *_ in story.INVESTIGATIONS}
    versions_of = {
        spec["id"]: [versions[(spec["id"], revision)] for revision, _ in spec["versions"]] for spec in story.PRODUCTS
    }
    evidence_count = 0
    for investigation_code, records in story.EVIDENCE.items():
        investigation = investigations[investigation_code]
        product_code = product_of_case[investigation_code]
        for code, kind, title, days, reliability, text in records:
            # Evidence that reaches the golden case later in its story is attached by the golden path, at its moment.
            deferred = code in story.GOLDEN_DEFERRED_EVIDENCE
            evidence = add(
                Evidence(
                    id=uuid.uuid4(),
                    evidence_identifier=code,
                    investigation_id=None if deferred else investigation.id,
                    evidence_type=kind,
                    title=title,
                    source_reference=story.SYNTHETIC,
                    reliability_status=reliability,
                    fact_type="source_fact",
                    content=text,
                    source_identifier=code,
                    **stamp(days),
                )
            )
            db.flush()
            if not deferred:
                add(
                    InvestigationEvidence(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        investigation_id=investigation.id,
                        evidence_id=evidence.id,
                        relevance="Part of the curated demo story.",
                        created_at=now,
                    )
                )
            # Link the record to its product and versions, as ingestion does, so case search finds it.
            for entity_type, entity_id, reference in [("Product", products[product_code].id, product_code)] + [
                ("ProductVersion", version.id, version.version_identifier) for version in versions_of[product_code]
            ]:
                add(
                    EvidenceEntityLink(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        evidence_id=evidence.id,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        raw_reference=reference,
                        resolution_status="RESOLVED",
                    )
                )
            evidence_count += 1
    db.flush()
    _load_review_examples(db, tenant_id, products, versions, lots, investigations, now, stamp)
    return {
        "products": len(products),
        "investigations": len(investigations),
        "complaints": len(story.COMPLAINTS) + len(story.REVIEW_EXAMPLES),
        "evidence": evidence_count,
    }


def _load_review_examples(db: Session, tenant_id, products, versions, lots, investigations, now: datetime, stamp):
    """The complaint review, reporting and CAPA examples of the story (story.REVIEW_EXAMPLES, story.EARLIER_CAPAS)
    and the demo organization's reporting windows, so Complaints and Records show findings from the first minute.
    Does not commit."""
    from backend.app.db.models.foundation import Capa
    from backend.app.db.models.reportability import ReportabilitySettings
    from backend.app.reportability.rules import TEMPLATES, clean_window

    for suffix, product_code, revision, lot_code, days, description, fields in story.REVIEW_EXAMPLES:
        aware = now - timedelta(days=days)
        identifier = f"ACD-CMP-{suffix}"
        db.add(
            Complaint(
                id=uuid.uuid4(),
                complaint_identifier=identifier,
                product_id=products[product_code].id,
                product_version_id=versions[(product_code, revision)].id,
                lot_batch_id=lots[lot_code].id,
                event_timestamp=aware - timedelta(days=1),
                complaint_timestamp=aware,
                awareness_timestamp=aware,
                description=description,
                source_identifier=identifier,
                **{"status": "open", **fields},
                **stamp(days),
            )
        )
    for code, product_code, case_code, title, status, opened, due, check_in in story.EARLIER_CAPAS:
        db.add(
            Capa(
                id=uuid.uuid4(),
                capa_identifier=code,
                title=title,
                action_type="CORRECTIVE",
                source_type="QUALITY_SYSTEM",
                product_id=products[product_code].id,
                investigation_id=investigations[case_code].id if case_code else None,
                status=status,
                opened_at=now - timedelta(days=opened),
                due_at=now - timedelta(days=due),
                effectiveness_check_at=(now + timedelta(days=check_in)) if check_in is not None else None,
                source_identifier=code,
                **stamp(opened),
            )
        )
    db.add(
        ReportabilitySettings(
            tenant_id=tenant_id,
            windows=[clean_window(TEMPLATES[index]) for index in story.REPORTING_WINDOW_TEMPLATES],
            lookback_days=365,
            version=1,
            updated_by="system:demo-setup",
            updated_at=now,
        )
    )
    db.flush()


def status(db: Session) -> dict:
    tenant = _tenant(db)

    def count(model) -> int:
        return int(db.query(func.count(model.id)).filter(model.tenant_id == tenant.id).scalar() or 0)

    plane = db.query(TenantDataPlane).filter(TenantDataPlane.tenant_id == tenant.id).first()
    from backend.app.demo_golden_path import golden_path_status
    from backend.app.role_codes import role_code, role_label

    team = []
    for role, email, name in DEMO_TEAM:
        user = db.query(AuthUser).filter(AuthUser.username == email, AuthUser.tenant_id == tenant.id).first()
        # Who can sign in, as whom, under which role (the password is MDARIX_DEMO_PASSWORD and is never shown).
        team.append(
            {
                "role": role,
                "role_code": role_code(role),
                "role_label": role_label(role),
                "name": name,
                "email": email,
                "active": bool(user and user.status == "ACTIVE"),
            }
        )
    plan = (
        db.query(PlanDefinition.code)
        .join(TenantPlanAssignment, TenantPlanAssignment.plan_id == PlanDefinition.id)
        .filter(TenantPlanAssignment.tenant_id == tenant.id, TenantPlanAssignment.status == "ACTIVE")
        .scalar()
    )
    return {
        "tenant_key": tenant.tenant_key,
        "tenant_business_id": tenant.business_id,
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
        "golden_path": golden_path_status(db, tenant.id),
    }
