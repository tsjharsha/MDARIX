"""Build a tenant cell from nothing (ADR-013/014): one organization, its own database, its own keys.

    python scripts/cell_install.py --database-url postgresql+pg8000://owner:pw@host:5432/mdarix_t_acme \\
        --bundle acme/enrollment.json --licence acme/licence.json --platform-public-key <base64> \\
        --app-url https://acme.cell.example --env-out acme/cell.env --apply

Without --apply it verifies the documents and reports what it would do. With --apply, in order:

1. verifies the enrollment bundle and the licence against the platform's public key;
2. runs every migration (the schema, pgvector and pgcrypto, forced row-level security, the master-data seeds)
   with the owner login of the new database, as the production migrate job does;
3. gives the least-privilege runtime role its login and grants, and stores the cell's own system-scope token;
4. creates the organization and its customer exactly as the bundle names them (same ids, same business ids);
   the registry row that makes this database the organization's data plane follows from migration md20;
5. applies the licence (backend/app/cell_licence.py), unless --no-licence (a tenant move applies it afterwards);
6. verifies the database holds exactly this organization and no business records;
7. invites the first customer administrator and prints the single-use activation link, unless
   --no-admin-invitation (a tenant move brings the organization's people with it);
8. writes the cell's settings file (--env-out): deployment role, organization, database login, every key and
   secret, the pinned platform key. Give it to the cell's containers as their environment file.

Nothing here contacts the platform: the cell is installed from files the platform signed.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from backend.app.cell_licence import apply_licence  # noqa: E402
from backend.app.cell_packages import PackageError, platform_public_key, verify  # noqa: E402
from backend.app.db.data_plane import SHARED_CONTROL_DATA_PLANE  # noqa: E402
from backend.app.db.models.customer_lifecycle import Customer, TenantDataPlane  # noqa: E402
from backend.app.db.models.foundation import AuthUser, Tenant, TenantMembership  # noqa: E402
from backend.app.db.tenant_scope import bind_system  # noqa: E402
from backend.app.db.tls import connect_args  # noqa: E402
from scripts.migrate_data_planes import head_revision, plane_state  # noqa: E402

RUNTIME_ROLE = "mdarix_runtime"
# Rows an installed cell legitimately holds for its organization before any business record exists.
PREFILLED = frozenset({"tenant_data_planes", "tenant_plan_assignments", "audit_events", "cell_licences"})
ADMIN_TABLES = frozenset({"auth_users", "tenant_memberships", "user_invitations"})


def _aes_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def generate_secrets(runtime_password: str | None = None) -> dict[str, str]:
    """Every secret a cell needs, each new (formats as backend/app/config_check.py requires)."""
    return {
        "MDARIX_DB_RUNTIME_PASSWORD": runtime_password or secrets.token_urlsafe(36),
        "MDARIX_RLS_SYSTEM_TOKEN": secrets.token_urlsafe(48),
        "MDARIX_MFA_ENCRYPTION_KEY": _aes_key(),
        "MDARIX_CONNECTOR_ENCRYPTION_KEY": _aes_key(),
        "MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY": _aes_key(),
        "MDARIX_OBJECT_STORAGE_SIGNING_SECRET": secrets.token_urlsafe(40),
        "MDARIX_DEMO_REQUEST_SALT": secrets.token_urlsafe(40),
        "MDARIX_RATE_LIMIT_SALT": secrets.token_urlsafe(40),
    }


@contextmanager
def environment(**values: str | None):
    """Temporarily set (or unset, for None) environment variables; the session's scope binding reads them."""
    previous = {name: os.environ.get(name) for name in values}
    for name, value in values.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def owner_environment(url) -> dict[str, str]:
    """The POSTGRES_* settings the migration scripts read, for the cell database's owner login."""
    return {
        "POSTGRES_USER": url.username or "",
        "POSTGRES_PASSWORD": url.password or "",
        "POSTGRES_HOST": url.host or "localhost",
        "POSTGRES_PORT": str(url.port or 5432),
        "POSTGRES_DB": url.database or "",
    }


def _run(script: str, env: dict[str, str]) -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, env=env, check=True)


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def write_env_file(path: Path, values: dict[str, str]) -> None:
    lines = [f"{name}={value}" for name, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _tenant_tables(connection) -> list[str]:
    rows = connection.execute(
        text(
            "SELECT c.table_name FROM information_schema.columns c JOIN information_schema.tables t "
            "ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
            "WHERE c.table_schema = 'public' AND c.column_name = 'tenant_id' AND t.table_type = 'BASE TABLE' "
            "ORDER BY 1"
        )
    )
    return [row[0] for row in rows]


def tenant_row_counts(connection, tenant_id) -> dict[str, int]:
    """Rows per tenant table for one organization (system scope must be bound on ``connection``)."""
    counts = {}
    for table in _tenant_tables(connection):
        counts[table] = int(
            connection.execute(
                text(f'SELECT count(*) FROM public."{table}" WHERE tenant_id = :t'), {"t": tenant_id}
            ).scalar()
        )
    return counts


def create_organization(db, enrollment: dict, *, now: datetime) -> tuple[Customer, Tenant, bool]:
    """The organization and its customer as the bundle names them; existing rows (a re-run) are left as they are."""
    spec_t, spec_c = enrollment["tenant"], enrollment["customer"]
    tenant_id, customer_id = uuid.UUID(spec_t["id"]), uuid.UUID(spec_c["id"])
    tenant = db.get(Tenant, tenant_id)
    if tenant is not None:
        if tenant.tenant_key != spec_t["tenant_key"] or tenant.customer_id != customer_id:
            raise PackageError("The database already holds a different organization under this id")
        return db.get(Customer, customer_id), tenant, False
    if db.query(Tenant).count():
        raise PackageError("The database already holds another organization: a cell holds exactly one")
    customer = db.get(Customer, customer_id)
    if customer is None:
        customer = Customer(
            id=customer_id,
            **{name: spec_c.get(name) for name in spec_c if name != "id"},
            lifecycle_status="ACTIVE",
            lock_version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(customer)
        db.flush()
    tenant = Tenant(
        id=tenant_id,
        customer_id=customer_id,
        **{name: spec_t.get(name) for name in spec_t if name != "id"},
        deployment_model="CELL",
        provisioning_status="PROVISIONED",
        status="ACTIVE",
        activated_at=now,
        lock_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(tenant)
    db.commit()  # the deferred md20 trigger registers the organization on this database's shared plane
    return customer, tenant, True


def invite_administrator(db, tenant: Tenant, administrator: dict, *, now: datetime) -> str:
    """The organization's first Customer Administrator, invited; returns the single-use activation token."""
    from auth.durable import issue_invitation
    from auth.service import _hash

    email = str(administrator["email"]).strip().lower()
    user = db.query(AuthUser).filter(AuthUser.tenant_id == tenant.id, AuthUser.username == email).first()
    if user is None:
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            username=email,
            display_name=str(administrator.get("display_name") or email.split("@")[0]),
            company=tenant.display_name,
            password_hash=_hash(secrets.token_urlsafe(32)),  # unusable until the person sets their own
            role="CUSTOMER_ADMIN",
            status="INVITED",
            email_verified=False,
            mfa_required=True,
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        db.flush()
        db.add(
            TenantMembership(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                user_id=user.id,
                status="INVITED",
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
    return issue_invitation(db, user.id, tenant.id)


def install(args) -> dict:
    public_key = args.platform_public_key or platform_public_key()
    if not public_key:
        raise PackageError("--platform-public-key (or MDARIX_PLATFORM_SIGNING_PUBLIC_KEY) is required")
    enrollment = verify(_load(args.bundle), public_key, kind="ENROLLMENT")
    licence_envelope = None
    if args.licence and not args.no_licence:
        licence_envelope = _load(args.licence)
        licence = verify(licence_envelope, public_key, kind="LICENCE")
        if licence["tenant_id"] != enrollment["tenant"]["id"]:
            raise PackageError("The licence is for another organization than the bundle")
    elif not args.no_licence:
        raise PackageError("--licence is required (or --no-licence when a tenant move will apply it)")

    url = make_url(args.database_url)
    plain_url = url.render_as_string(hide_password=False)  # str(url) masks the password
    state, current = plane_state(plain_url)
    head = head_revision()
    summary = {
        "database": f"{url.host}:{url.port or 5432}/{url.database}",
        "state_before": state,
        "schema_before": current,
        "schema_head": head,
        "tenant_id": enrollment["tenant"]["id"],
        "tenant_key": enrollment["tenant"]["tenant_key"],
        "hosting_mode": enrollment.get("hosting_mode"),
        "licence": bool(licence_envelope),
        "apply": bool(args.apply),
    }
    if state == "LEGACY":
        raise PackageError("The database was built without migrations: use an empty database")
    if not args.apply:
        return summary

    secret_values = generate_secrets(args.runtime_password or os.getenv("MDARIX_DB_RUNTIME_PASSWORD") or None)
    subprocess_env = {
        **os.environ,
        **owner_environment(url),
        "MDARIX_MIGRATION_DATABASE_URL": plain_url,
        "MDARIX_DB_HARDENING_APPLY": "1",
        "MDARIX_DB_RUNTIME_USER": RUNTIME_ROLE,
        "MDARIX_DB_RUNTIME_PASSWORD": secret_values["MDARIX_DB_RUNTIME_PASSWORD"],
        "MDARIX_RLS_SYSTEM_TOKEN": secret_values["MDARIX_RLS_SYSTEM_TOKEN"],
    }
    subprocess_env.pop("MDARIX_DATA_PLANE_PASSWORD", None)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=subprocess_env, check=True)
    if not args.skip_runtime_role:
        _run("configure_runtime_role.py", subprocess_env)
    _run("grant_runtime_privileges.py", subprocess_env)
    _run("set_rls_system_token.py", subprocess_env)
    summary["state_after"] = plane_state(plain_url)

    now = datetime.now(timezone.utc)
    engine = create_engine(plain_url, future=True, connect_args=connect_args(), hide_parameters=True)
    try:
        with environment(MDARIX_RLS_SYSTEM_TOKEN=secret_values["MDARIX_RLS_SYSTEM_TOKEN"]):
            db = sessionmaker(bind=engine, autoflush=False, future=True)()
            try:
                bind_system(db, "cell install")
                customer, tenant, created = create_organization(db, enrollment, now=now)
                summary["organization_created"] = created
                plane = db.query(TenantDataPlane).filter(TenantDataPlane.tenant_id == tenant.id).first()
                if plane is None or plane.connection_secret_ref != SHARED_CONTROL_DATA_PLANE:
                    raise PackageError("The organization's data-plane registry row is missing or not the shared plane")
                if licence_envelope is not None:
                    summary["licence_applied"] = apply_licence(db, licence_envelope, public_key, now=now)
                counts = tenant_row_counts(db.connection(), tenant.id)
                unexpected = {
                    name: count
                    for name, count in counts.items()
                    if count and name not in PREFILLED and (created or name not in ADMIN_TABLES)
                }
                if unexpected:
                    raise PackageError(f"The database already holds records of this organization: {unexpected}")
                summary["organizations_in_database"] = db.query(Tenant).count()
                if summary["organizations_in_database"] != 1:
                    raise PackageError("A cell holds exactly one organization")
                summary["prefilled_rows"] = {name: count for name, count in counts.items() if count}
                if not args.no_admin_invitation:
                    token = invite_administrator(db, tenant, enrollment["administrator"], now=now)
                    app_url = (args.app_url or os.getenv("MDARIX_APP_URL", "")).rstrip("/")
                    summary["administrator"] = enrollment["administrator"]["email"]
                    summary["activation_link"] = f"{app_url}/activate-account?token={token}"
            finally:
                db.close()
    finally:
        engine.dispose()

    if args.env_out:
        settings = {
            "MDARIX_DEPLOYMENT_ROLE": "CELL",
            "MDARIX_CELL_TENANT_ID": str(enrollment["tenant"]["id"]),
            "MDARIX_CELL_TENANT_KEY": str(enrollment["tenant"]["tenant_key"]),
            "MDARIX_PLATFORM_SIGNING_PUBLIC_KEY": public_key,
            "POSTGRES_HOST": url.host or "localhost",
            "POSTGRES_PORT": str(url.port or 5432),
            "POSTGRES_DB": url.database or "",
            "POSTGRES_USER": RUNTIME_ROLE,
            "POSTGRES_PASSWORD": secret_values["MDARIX_DB_RUNTIME_PASSWORD"],
            "MDARIX_DB_RUNTIME_USER": RUNTIME_ROLE,
            "MDARIX_DB_RUNTIME_PASSWORD": secret_values["MDARIX_DB_RUNTIME_PASSWORD"],
            "MDARIX_RLS_SYSTEM_TOKEN": secret_values["MDARIX_RLS_SYSTEM_TOKEN"],
            "MDARIX_MFA_ENCRYPTION_KEY": secret_values["MDARIX_MFA_ENCRYPTION_KEY"],
            "MDARIX_CONNECTOR_ENCRYPTION_KEY": secret_values["MDARIX_CONNECTOR_ENCRYPTION_KEY"],
            "MDARIX_CONNECTOR_ENCRYPTION_KEY_ID": "k1",
            "MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY": secret_values["MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY"],
            "MDARIX_OBJECT_STORAGE_SIGNING_SECRET": secret_values["MDARIX_OBJECT_STORAGE_SIGNING_SECRET"],
            "MDARIX_DEMO_REQUEST_SALT": secret_values["MDARIX_DEMO_REQUEST_SALT"],
            "MDARIX_RATE_LIMIT_SALT": secret_values["MDARIX_RATE_LIMIT_SALT"],
        }
        if args.app_url:
            settings["MDARIX_APP_URL"] = args.app_url
        write_env_file(Path(args.env_out), settings)
        summary["env_file"] = str(args.env_out)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", required=True, help="owner login of the new, empty cell database")
    parser.add_argument("--bundle", required=True, help="enrollment.json from scripts/cell_platform.py issue")
    parser.add_argument("--licence", help="licence.json from scripts/cell_platform.py issue")
    parser.add_argument("--no-licence", action="store_true", help="install without a licence (a move applies one)")
    parser.add_argument("--platform-public-key", help="the platform's signing public key (else the environment)")
    parser.add_argument("--app-url", help="the cell's https address, for the activation link and the settings file")
    parser.add_argument("--env-out", help="write the cell's settings file here")
    parser.add_argument("--runtime-password", help="password for the runtime role (else generated)")
    parser.add_argument("--skip-runtime-role", action="store_true", help="the operator manages the runtime role")
    parser.add_argument("--no-admin-invitation", action="store_true", help="do not invite the first administrator")
    parser.add_argument("--apply", action="store_true", help="build the cell (without it: verify and report)")
    args = parser.parse_args(argv)
    try:
        summary = install(args)
    except PackageError as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 2
    link = summary.pop("activation_link", None)
    print(json.dumps(summary, indent=2, default=str))
    if link:
        print(f"Give {summary['administrator']} this single-use activation link (72 hours), securely:")
        print(link)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
