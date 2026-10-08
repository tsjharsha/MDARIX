"""Platform side of a tenant cell (ADR-014): the signing key and the signed documents a cell is installed from.

    python scripts/cell_platform.py keygen --out platform-signing.key
        A new Ed25519 key pair. The private key goes to the file (keep it with the release pipeline, never in a
        cell); the public key is printed, and every cell pins it as MDARIX_PLATFORM_SIGNING_PUBLIC_KEY.

    python scripts/cell_platform.py issue --tenant-key ACME --hosting-mode MDARIX_MANAGED \\
        --admin-email admin@customer.example --admin-name "Jane Doe" --private-key-file platform-signing.key --out ./acme
        Writes acme/enrollment.json (the organization, its customer and its first administrator) and
        acme/licence.json (the organization's active plan, features and limits), both signed; registers the cell
        in the platform's ``cells`` table as PROVISIONING and records the organization's deployment model as CELL.
        scripts/cell_install.py builds the cell from these two files.

Runs against the platform (MULTI or PLATFORM) database the environment points at, in system scope.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.cell_licence import licence_content  # noqa: E402
from backend.app.cell_packages import PackageError, generate_keypair, sign  # noqa: E402
from backend.app.db.models.customer_lifecycle import Cell, Customer  # noqa: E402
from backend.app.db.models.foundation import (  # noqa: E402
    AuditEvent,
    FeatureEntitlement,
    PlanDefinition,
    Tenant,
    TenantPlanAssignment,
)
from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.db.tenant_scope import bind_system  # noqa: E402

ACTOR = "system:cell-platform"
HOSTING_MODES = ("MDARIX_MANAGED", "CUSTOMER_CLOUD", "CUSTOMER_ON_PREM")
TENANT_FIELDS = (
    "business_id",
    "tenant_key",
    "tenant_identifier",
    "name",
    "display_name",
    "tenant_slug",
    "tenant_type",
    "primary_region",
    "residency_region",
    "database_region",
    "backup_region",
    "storage_region",
    "ai_processing_region",
    "disaster_recovery_region",
    "cross_border_processing_allowed",
)
CUSTOMER_FIELDS = (
    "business_id",
    "customer_identifier",
    "legal_name",
    "display_name",
    "trading_name",
    "customer_type",
    "industry",
    "company_size",
    "country",
    "state_province",
    "headquarters",
    "website",
)


def enrollment_content(
    tenant: Tenant, customer: Customer, *, hosting_mode: str, admin_email: str, admin_name: str, now: datetime
) -> dict:
    if hosting_mode not in HOSTING_MODES:
        raise PackageError(f"hosting mode must be one of {', '.join(HOSTING_MODES)}")
    return {
        "tenant": {"id": str(tenant.id), **{name: getattr(tenant, name) for name in TENANT_FIELDS}},
        "customer": {"id": str(customer.id), **{name: getattr(customer, name) for name in CUSTOMER_FIELDS}},
        "administrator": {"email": admin_email.strip().lower(), "display_name": admin_name.strip() or admin_email},
        "hosting_mode": hosting_mode,
        "issued_at": now.isoformat(),
    }


def active_plan(db, tenant: Tenant) -> tuple[PlanDefinition, list[FeatureEntitlement], TenantPlanAssignment]:
    assignment = (
        db.query(TenantPlanAssignment)
        .join(PlanDefinition, PlanDefinition.id == TenantPlanAssignment.plan_id)
        .filter(
            TenantPlanAssignment.tenant_id == tenant.id,
            TenantPlanAssignment.status == "ACTIVE",
            PlanDefinition.status == "ACTIVE",
        )
        .order_by(TenantPlanAssignment.effective_from.desc())
        .first()
    )
    if assignment is None:
        raise PackageError(f"{tenant.tenant_key} has no active plan to license")
    plan = db.get(PlanDefinition, assignment.plan_id)
    entitlements = (
        db.query(FeatureEntitlement)
        .filter(FeatureEntitlement.plan_id == plan.id, FeatureEntitlement.status == "ACTIVE")
        .all()
    )
    return plan, entitlements, assignment


def issue(
    db,
    tenant_key: str,
    *,
    hosting_mode: str,
    admin_email: str,
    admin_name: str,
    private_key: str,
    valid_until: datetime | None = None,
    now: datetime | None = None,
) -> tuple[dict, dict]:
    """The signed enrollment bundle and licence for ``tenant_key``; registers the cell. Commits."""
    now = now or datetime.now(timezone.utc)
    bind_system(db, "cell platform: issue a cell's documents")
    tenant = db.query(Tenant).filter(Tenant.tenant_key == tenant_key).first()
    if tenant is None:
        raise PackageError(f"No organization has the key {tenant_key}")
    customer = db.get(Customer, tenant.customer_id)
    plan, entitlements, assignment = active_plan(db, tenant)
    enrollment = sign(
        "ENROLLMENT",
        enrollment_content(
            tenant, customer, hosting_mode=hosting_mode, admin_email=admin_email, admin_name=admin_name, now=now
        ),
        private_key,
    )
    licence = sign(
        "LICENCE",
        licence_content(tenant, plan, entitlements, assignment.limits, issued_at=now, valid_until=valid_until),
        private_key,
    )
    cell = db.query(Cell).filter(Cell.tenant_id == tenant.id).first()
    if cell is None:
        cell = Cell(id=uuid.uuid4(), tenant_id=tenant.id, hosting_mode=hosting_mode, created_at=now, updated_at=now)
        db.add(cell)
    cell.hosting_mode = hosting_mode
    cell.status = "PROVISIONING"
    cell.updated_at = now
    tenant.deployment_model = "CELL"
    tenant.updated_at = now
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            actor_ref=ACTOR,
            action="CELL_DOCUMENTS_ISSUED",
            entity_type="Cell",
            entity_id=cell.id,
            details={
                "hosting_mode": hosting_mode,
                "licence_id": licence["content"]["licence_id"],
                "licence_sha256": licence["content_sha256"],
                "enrollment_sha256": enrollment["content_sha256"],
                "administrator": enrollment["content"]["administrator"]["email"],
            },
            created_at=now,
        )
    )
    db.commit()
    return enrollment, licence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    keygen = commands.add_parser("keygen", help="generate the platform signing key pair")
    keygen.add_argument("--out", help="file for the private key (printed instead when omitted)")
    issuing = commands.add_parser("issue", help="write a signed enrollment bundle and licence for an organization")
    issuing.add_argument("--tenant-key", required=True)
    issuing.add_argument("--hosting-mode", choices=HOSTING_MODES, required=True)
    issuing.add_argument("--admin-email", required=True)
    issuing.add_argument("--admin-name", default="")
    issuing.add_argument("--private-key-file", required=True)
    issuing.add_argument("--valid-until", help="ISO-8601 time the licence expires (none: open-ended)")
    issuing.add_argument("--out", required=True, help="directory for enrollment.json and licence.json")
    args = parser.parse_args(argv)

    if args.command == "keygen":
        private, public = generate_keypair()
        if args.out:
            path = Path(args.out)
            path.write_text(private + "\n", encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            print(f"Private key written to {path} (keep it with the release pipeline).")
        else:
            print(f"MDARIX_PLATFORM_SIGNING_PRIVATE_KEY={private}")
        print(f"MDARIX_PLATFORM_SIGNING_PUBLIC_KEY={public}")
        return 0

    private_key = Path(args.private_key_file).read_text(encoding="utf-8").strip()
    valid_until = None
    if args.valid_until:
        valid_until = datetime.fromisoformat(args.valid_until.replace("Z", "+00:00"))
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=timezone.utc)
    db = SessionLocal()
    try:
        enrollment, licence = issue(
            db,
            args.tenant_key,
            hosting_mode=args.hosting_mode,
            admin_email=args.admin_email,
            admin_name=args.admin_name,
            private_key=private_key,
            valid_until=valid_until,
        )
    except PackageError as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 2
    finally:
        db.close()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "enrollment.json").write_text(json.dumps(enrollment, indent=2), encoding="utf-8")
    (out / "licence.json").write_text(json.dumps(licence, indent=2), encoding="utf-8")
    print(json.dumps({"enrollment": str(out / "enrollment.json"), "licence": str(out / "licence.json")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
