"""Move one organization out of a multi-tenant deployment into its own tenant cell (ADR-013).

    python scripts/move_tenant_to_cell.py --tenant-key ACME \\
        --target-url postgresql+pg8000://owner:pw@cell-host:5432/mdarix_t_acme --target-env acme/cell.env \\
        --licence acme/licence.json --source-objects-root /var/lib/mdarix/objects --target-objects-root ./acme/objects \\
        [--apply]

The source is the deployment this process is configured for (POSTGRES_* and the keys in its environment), and it is
only ever read: every source transaction is READ ONLY. The target is a cell built by scripts/cell_install.py with
``--no-licence --no-admin-invitation``, holding this organization and nothing else.

What moves: every row of the organization in every tenant table, in foreign-key order, with the same ids, business
ids and timestamps; the organization's and its customer's rows (upserted, since the installer created them from the
enrollment bundle); the customer's contacts, domains and drafts; the global rows the organization's rows point at
(master mappings, configuration baselines); the business-id counters; the audit trail copied verbatim with the chain
trigger paused, then verified in the target against the source's last sequence and hash; the organization's stored
files (local object storage); and the licence, applied last so it tops the audit chain. MFA secrets, connector
credentials and files are decrypted with the source's keys and encrypted again with the cell's.

What does not move: sign-in sessions, MFA challenges, invitation and reset links (people sign in again); the
data-plane registry (the cell's own row exists); export archives and the pending outbox; licensing and platform
operations records (the licence replaces them; platform records stay on the platform).

Without --apply the plan is printed with the source counts and nothing is written. With --apply the copy runs in
one target transaction; a failure leaves the target as it was. The source is never changed by this tool: marking
the organization as moved on the platform is a separate, approved step.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import pkgutil
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import MetaData, Table, create_engine, select, text  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import backend.app.db.models as _models  # noqa: E402
from backend.app.cell_licence import apply_licence  # noqa: E402
from backend.app.cell_packages import PackageError, verify  # noqa: E402
from backend.app.db.base import Base  # noqa: E402
from backend.app.db.session import database_url  # noqa: E402
from backend.app.db.tenant_scope import _APPLY, system_token  # noqa: E402
from backend.app.db.tls import connect_args  # noqa: E402
from scripts.cell_install import environment, tenant_row_counts  # noqa: E402
from scripts.migrate_data_planes import head_revision, plane_state  # noqa: E402

for _module in pkgutil.iter_modules(_models.__path__):
    importlib.import_module(f"backend.app.db.models.{_module.name}")  # every table in Base.metadata, FK order

GOLDEN_TENANT = "ACME_CARE_SYNTHETIC"
SESSION_TABLES = frozenset({"auth_sessions", "mfa_challenges", "password_reset_requests", "user_invitations"})
PLATFORM_TABLES = frozenset(
    {
        "tenant_data_planes",
        "tenant_exports",
        "event_outbox",
        "cells",
        "cell_licences",
        # Licensing: the cell's licence replaces it.
        "tenant_plan_assignments",
        "plan_version_assignments",
        "entitlement_snapshots",
        "subscription_lifecycles",
        "subscription_versions",
        "subscription_reminder_policies",
        "subscription_email_templates",
        "reminder_policy_recipients",
        "renewal_requests",
        "grace_period_exceptions",
        "license_transitions",
        "usage_quota_snapshots",
        # Platform operations about the organization stay on the platform.
        "tenant_environments",
        "provisioning_jobs",
        "provisioning_job_steps",
        "tenant_health_runs",
        "tenant_service_health_checks",
        "tenant_isolation_evidence",
        "tenant_access_transitions",
        "support_access_grants",
        "platform_incidents",
        "onboarding_requests",
        "trial_feedback",
    }
)
SKIPPED = SESSION_TABLES | PLATFORM_TABLES
CUSTOMER_CHILDREN = ("customer_contacts", "customer_domains", "customer_onboarding_drafts")
KEY_SETTINGS = (
    "MDARIX_MFA_ENCRYPTION_KEY",
    "MDARIX_CONNECTOR_ENCRYPTION_KEY",
    "MDARIX_CONNECTOR_ENCRYPTION_KEY_ID",
    "MDARIX_CONNECTOR_ENCRYPTION_KEYS",
    "MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY",
    "MDARIX_OBJECT_STORAGE_SIGNING_SECRET",
)
VERIFY = text("SELECT checked, first_broken_seq, last_seq, last_hash FROM public.mdarix_verify_audit_chain(:t)")


def scoped(connection, token: str) -> None:
    """System scope for this transaction with an explicit token (source and target hold different ones)."""
    connection.execute(_APPLY, {"tenant": "", "bypass": token})


@contextmanager
def read_only(engine, token: str):
    with engine.begin() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        scoped(connection, token)
        yield connection


def read_env_file(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, _, value = line.partition("=")
            values[name.strip()] = value.strip()
    return values


def ordered(names: list[str]) -> list[str]:
    index = {table.name: position for position, table in enumerate(Base.metadata.sorted_tables)}
    return sorted(names, key=lambda name: (index.get(name, len(index)), name))


def table_of(name: str, bind=None) -> Table:
    if name in Base.metadata.tables:
        return Base.metadata.tables[name]
    return Table(name, MetaData(), autoload_with=bind)


def rows_of(connection, tbl: Table, where, order_by=None) -> list[dict]:
    statement = select(tbl).where(where)
    if order_by is not None:
        statement = statement.order_by(order_by)
    elif tbl.primary_key.columns:
        statement = statement.order_by(*tbl.primary_key.columns)
    return [dict(row._mapping) for row in connection.execute(statement)]


def parents_first(tbl: Table, rows: list[dict]) -> list[dict]:
    """Rows of a table that references itself (a signal's canonical signal, a version's predecessor), ordered so a
    referenced row is inserted before the rows that point at it; rows in a cycle keep their order."""
    columns = [fk.parent.name for fk in tbl.foreign_keys if fk.column.table is tbl]
    if not columns:
        return rows
    keys = [column.name for column in tbl.primary_key.columns]
    placed: set = set()
    remaining, result = list(rows), []
    while remaining:
        progress = False
        for row in list(remaining):
            if all(row.get(column) is None or row[column] in placed for column in columns):
                result.append(row)
                placed.add(tuple(row[key] for key in keys) if len(keys) > 1 else row[keys[0]])
                remaining.remove(row)
                progress = True
        if not progress:
            result.extend(remaining)
            break
    return result


def insert_rows(connection, tbl: Table, rows: list[dict], *, ignore_conflicts: bool = False, chunk: int = 500) -> int:
    rows = parents_first(tbl, rows)
    for start in range(0, len(rows), chunk):
        batch = rows[start : start + chunk]
        if ignore_conflicts:
            connection.execute(pg_insert(tbl).on_conflict_do_nothing(), batch)
        else:
            connection.execute(tbl.insert(), batch)
    return len(rows)


def upsert_row(connection, tbl: Table, row: dict, *, frozen=("id", "business_id")) -> None:
    statement = pg_insert(tbl).values(**row)
    changes = {name: statement.excluded[name] for name in row if name not in frozen}
    connection.execute(statement.on_conflict_do_update(index_elements=[tbl.c.id], set_=changes))


def global_references(tbl: Table) -> list[tuple[str, Table, str]]:
    """Foreign keys of ``tbl`` to tables that have no tenant_id (global rows the organization's rows point at)."""
    found = []
    for fk in tbl.foreign_keys:
        target = fk.column.table
        if target.name == "tenants" or "tenant_id" in target.c:
            continue
        found.append((fk.parent.name, target, fk.column.name))
    return found


class TenantMove:
    def __init__(self, *, tenant_key: str, source_engine, target_engine, source_token: str, target_token: str):
        self.tenant_key = tenant_key
        self.source = source_engine
        self.target = target_engine
        self.source_token = source_token
        self.target_token = target_token
        self.tenant_id: uuid.UUID | None = None
        self.customer_id: uuid.UUID | None = None
        self.tables: list[str] = []
        self.report: dict = {"tenant_key": tenant_key, "copied": {}, "skipped": sorted(SKIPPED), "global_rows": {}}

    # ----------------------------------------------------------------------------------------------- source
    def inspect_source(self) -> dict:
        with read_only(self.source, self.source_token) as src:
            tenant = src.execute(
                text("SELECT id, customer_id, tenant_key, status FROM tenants WHERE tenant_key = :k"),
                {"k": self.tenant_key},
            ).first()
            if tenant is None:
                raise PackageError(f"No organization has the key {self.tenant_key}")
            self.tenant_id, self.customer_id = tenant.id, tenant.customer_id
            counts = tenant_row_counts(src, self.tenant_id)
            self.tables = ordered([name for name in counts if name not in SKIPPED])
            chain = src.execute(VERIFY, {"t": self.tenant_id}).first()
            objects = None
            self.report.update(
                {
                    "tenant_id": str(self.tenant_id),
                    "source_counts": {name: counts[name] for name in self.tables if counts[name]},
                    "source_rows": sum(counts[name] for name in self.tables),
                    "skipped_rows": {name: count for name, count in counts.items() if name in SKIPPED and count},
                    "source_audit_chain": {
                        "checked": chain.checked,
                        "first_broken_seq": chain.first_broken_seq,
                        "last_seq": chain.last_seq,
                        "last_hash": chain.last_hash,
                    },
                    "objects": objects,
                }
            )
            if chain.first_broken_seq is not None:
                raise PackageError(f"The source audit chain is broken at #{chain.first_broken_seq}: not moving it")
        return self.report

    # ----------------------------------------------------------------------------------------------- target
    def check_target(self) -> None:
        state, current = plane_state(self.target.url.render_as_string(hide_password=False))
        head = head_revision()
        if state != "MANAGED" or current != head:
            raise PackageError(f"The target database must be migrated to {head} first (found {state} {current})")
        with read_only(self.target, self.target_token) as dst:
            tenants = dst.execute(text("SELECT id, tenant_key FROM tenants")).all()
            if len(tenants) != 1 or tenants[0].id != self.tenant_id or tenants[0].tenant_key != self.tenant_key:
                raise PackageError("The target must hold exactly this organization (install the cell from its bundle)")
            counts = tenant_row_counts(dst, self.tenant_id)
            occupied = {name: count for name, count in counts.items() if count and name not in {"tenant_data_planes"}}
            if occupied:
                raise PackageError(f"The target already holds records of this organization: {occupied}")

    def _copy_global_rows(self, src, dst, tbl: Table, rows: list[dict]) -> None:
        """Global rows that ``rows`` of ``tbl`` point at, and what those point at, before the rows themselves."""
        for column, ref, ref_column in global_references(tbl):
            ids = sorted({row[column] for row in rows if row.get(column) is not None}, key=str)
            if not ids:
                continue
            referenced = rows_of(src, ref, ref.c[ref_column].in_(ids))
            self._copy_global_rows(src, dst, ref, referenced)
            insert_rows(dst, ref, referenced, ignore_conflicts=True)
            self.report["global_rows"][ref.name] = self.report["global_rows"].get(ref.name, 0) + len(referenced)

    def copy(self) -> None:
        tid = self.tenant_id
        with read_only(self.source, self.source_token) as src, self.target.begin() as dst:
            scoped(dst, self.target_token)
            # The organization and its customer, as the source has them (ids and business ids unchanged).
            customers, tenants = table_of("customers"), table_of("tenants")
            upsert_row(dst, customers, rows_of(src, customers, customers.c.id == self.customer_id)[0])
            for name in CUSTOMER_CHILDREN:
                child = table_of(name, src)
                insert_rows(
                    dst, child, rows_of(src, child, child.c.customer_id == self.customer_id), ignore_conflicts=True
                )
            if "customer_domains" in Base.metadata.tables and "domain_verifications" in Base.metadata.tables:
                domains, verifications = table_of("customer_domains"), table_of("domain_verifications")
                domain_ids = [
                    row.id for row in src.execute(select(domains.c.id).where(domains.c.customer_id == self.customer_id))
                ]
                if domain_ids:
                    insert_rows(
                        dst,
                        verifications,
                        rows_of(src, verifications, verifications.c.customer_domain_id.in_(domain_ids)),
                        ignore_conflicts=True,
                    )
            upsert_row(
                dst,
                tenants,
                rows_of(src, tenants, tenants.c.id == tid)[0],
                frozen=("id", "business_id", "deployment_model"),
            )
            # The deferred registry trigger would block ALTER TABLE below.
            dst.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            dst.execute(text("ALTER TABLE public.audit_events DISABLE TRIGGER audit_events_chain"))
            try:
                for name in self.tables:
                    tbl = table_of(name, src)
                    order = tbl.c.chain_seq if name == "audit_events" else None
                    rows = rows_of(src, tbl, tbl.c.tenant_id == tid, order_by=order)
                    if not rows:
                        continue
                    self._copy_global_rows(src, dst, tbl, rows)
                    self.report["copied"][name] = insert_rows(dst, tbl, rows)
            finally:
                dst.execute(text("ALTER TABLE public.audit_events ENABLE TRIGGER audit_events_chain"))
            counters = src.execute(
                text("SELECT scope_id, prefix, last_value FROM business_id_counters WHERE scope_id = :t"), {"t": tid}
            ).all()
            for counter in counters:
                dst.execute(
                    text(
                        "INSERT INTO business_id_counters (scope_id, prefix, last_value, updated_at) "
                        "VALUES (:s, :p, :v, now()) ON CONFLICT (scope_id, prefix) DO UPDATE "
                        "SET last_value = GREATEST(business_id_counters.last_value, EXCLUDED.last_value), updated_at = now()"
                    ),
                    {"s": counter.scope_id, "p": counter.prefix, "v": counter.last_value},
                )
            self.report["business_id_counters"] = len(counters)

    def verify_copy(self) -> list[str]:
        problems = []
        with read_only(self.target, self.target_token) as dst:
            counts = tenant_row_counts(dst, self.tenant_id)
            for name in self.tables:
                expected = self.report["source_counts"].get(name, 0)
                if counts.get(name, 0) != expected:
                    problems.append(f"{name}: source {expected}, target {counts.get(name, 0)}")
            chain = dst.execute(VERIFY, {"t": self.tenant_id}).first()
            self.report["target_audit_chain"] = {
                "checked": chain.checked,
                "first_broken_seq": chain.first_broken_seq,
                "last_seq": chain.last_seq,
                "last_hash": chain.last_hash,
            }
            source_chain = self.report["source_audit_chain"]
            if chain.first_broken_seq is not None:
                problems.append(f"audit chain broken in the target at #{chain.first_broken_seq}")
            if (chain.last_seq, chain.last_hash) != (source_chain["last_seq"], source_chain["last_hash"]):
                problems.append("audit chain head differs between source and target")
            if chain.checked != source_chain["checked"]:
                problems.append(f"audit chain: source checked {source_chain['checked']}, target {chain.checked}")
        self.report["verification_problems"] = problems
        return problems

    # ----------------------------------------------------------------------------------------------- secrets
    def reencrypt(self, target_env: dict[str, str]) -> dict:
        from access_control.connector_secrets import open_sealed, seal
        from auth.totp import decrypt_secret, encrypt_secret

        target_keys = {name: target_env.get(name) for name in KEY_SETTINGS}
        counts = {"mfa_secrets": 0, "connector_credentials": 0}
        tid = self.tenant_id
        with self.target.begin() as dst:
            scoped(dst, self.target_token)
            users = dst.execute(
                text(
                    "SELECT id, mfa_secret_encrypted, mfa_pending_secret_encrypted FROM auth_users WHERE tenant_id = :t "
                    "AND (mfa_secret_encrypted IS NOT NULL OR mfa_pending_secret_encrypted IS NOT NULL)"
                ),
                {"t": tid},
            ).all()
            for user in users:
                values = {}
                for column in ("mfa_secret_encrypted", "mfa_pending_secret_encrypted"):
                    sealed = getattr(user, column)
                    if sealed:
                        plain = decrypt_secret(sealed, str(user.id))  # the source's key: this process's environment
                        with environment(**target_keys):
                            values[column] = encrypt_secret(plain, str(user.id))
                assignments = ", ".join(f"{column} = :{column}" for column in values)
                dst.execute(text(f"UPDATE auth_users SET {assignments} WHERE id = :id"), {**values, "id": user.id})
                counts["mfa_secrets"] += len(values)
            connectors = dst.execute(
                text(
                    "SELECT id, credential_encrypted FROM connector_configurations "
                    "WHERE tenant_id = :t AND credential_encrypted IS NOT NULL"
                ),
                {"t": tid},
            ).all()
            for connector in connectors:
                plain = open_sealed(connector.credential_encrypted, tid, connector.id)
                with environment(**target_keys):
                    resealed = seal(plain, tid, connector.id)
                dst.execute(
                    text("UPDATE connector_configurations SET credential_encrypted = :c WHERE id = :id"),
                    {"c": resealed, "id": connector.id},
                )
                counts["connector_credentials"] += 1
        self.report["reencrypted"] = counts
        return counts

    def copy_objects(self, source_root: str | None, target_root: str, target_env: dict[str, str]) -> int:
        from object_storage.service import ObjectStorageService

        if os.getenv("MDARIX_OBJECT_STORAGE_PROVIDER", "local").lower() != "local":
            raise PackageError(
                "Only local object storage is moved by this tool; copy an S3 prefix with the provider's tools"
            )
        source = ObjectStorageService(root=source_root)
        with environment(
            MDARIX_OBJECT_STORAGE_PROVIDER="local",
            **{
                name: target_env.get(name)
                for name in ("MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY", "MDARIX_OBJECT_STORAGE_SIGNING_SECRET")
            },
        ):
            target = ObjectStorageService(root=target_root)
        tenant = str(self.tenant_id)
        prefix = f"{tenant}/"
        copied = 0
        for key in source.list_tenant_objects(tenant):
            content = source.get(tenant, key)
            marker = Path(str(source.root / key) + ".retention")
            retention = datetime.fromisoformat(marker.read_text(encoding="utf-8").strip()) if marker.is_file() else None
            target.put(tenant, key[len(prefix) :], content, retention_until=retention, internal=True)
            copied += 1
        self.report["objects"] = copied
        return copied

    def apply_licence(self, envelope: dict, public_key: str) -> dict:
        with environment(MDARIX_RLS_SYSTEM_TOKEN=self.target_token):
            db = sessionmaker(bind=self.target, autoflush=False, future=True)()
            try:
                from backend.app.db.tenant_scope import bind_system

                bind_system(db, "tenant move: apply the cell's licence")
                outcome = apply_licence(db, envelope, public_key)
            finally:
                db.close()
        self.report["licence"] = outcome
        return outcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tenant-key", required=True)
    parser.add_argument("--source-url", help="owner login of the source database (default: this environment's)")
    parser.add_argument("--target-url", required=True, help="owner login of the cell database")
    parser.add_argument("--target-env", required=True, help="the cell's settings file written by cell_install.py")
    parser.add_argument("--licence", help="licence.json to apply in the cell after the move")
    parser.add_argument("--platform-public-key", help="to verify the licence (default: the cell's settings file)")
    parser.add_argument("--source-objects-root", help="local object storage root of the source")
    parser.add_argument("--target-objects-root", help="local object storage root of the cell")
    parser.add_argument("--allow-golden", action="store_true", help="allow the golden evaluation organization")
    parser.add_argument("--apply", action="store_true", help="copy (without it: plan and counts only)")
    args = parser.parse_args(argv)

    source_url = args.source_url or database_url()
    if (
        args.tenant_key == GOLDEN_TENANT
        and not args.allow_golden
        and not str(make_url(source_url).database).endswith("_test")
    ):
        print(
            f"REFUSED {GOLDEN_TENANT} is the evaluation organization; pass --allow-golden to move it", file=sys.stderr
        )
        return 2
    target_env = read_env_file(args.target_env)
    target_token = target_env.get("MDARIX_RLS_SYSTEM_TOKEN", "")
    if not target_token:
        print("REFUSED the cell's settings file holds no MDARIX_RLS_SYSTEM_TOKEN", file=sys.stderr)
        return 2
    licence = None
    public_key = args.platform_public_key or target_env.get("MDARIX_PLATFORM_SIGNING_PUBLIC_KEY", "")
    if args.licence:
        with open(args.licence, encoding="utf-8") as handle:
            licence = json.load(handle)
        verify(licence, public_key, kind="LICENCE")

    source_engine = create_engine(source_url, future=True, connect_args=connect_args(), hide_parameters=True)
    target_engine = create_engine(args.target_url, future=True, connect_args=connect_args(), hide_parameters=True)
    move = TenantMove(
        tenant_key=args.tenant_key,
        source_engine=source_engine,
        target_engine=target_engine,
        source_token=system_token(),
        target_token=target_token,
    )
    try:
        move.inspect_source()
        if args.source_objects_root or args.target_objects_root:
            from object_storage.service import ObjectStorageService

            move.report["objects"] = len(
                ObjectStorageService(root=args.source_objects_root).list_tenant_objects(str(move.tenant_id))
            )
        move.check_target()
        if not args.apply:
            move.report["apply"] = False
            print(json.dumps(move.report, indent=2, default=str))
            return 0
        move.copy()
        problems = move.verify_copy()
        if problems:
            move.report["apply"] = "VERIFICATION_FAILED"
            print(json.dumps(move.report, indent=2, default=str))
            return 1
        move.reencrypt(target_env)
        if args.target_objects_root:
            move.copy_objects(args.source_objects_root, args.target_objects_root, target_env)
        if licence is not None:
            move.apply_licence(licence, public_key)
        move.report["apply"] = True
        print(json.dumps(move.report, indent=2, default=str))
        return 0
    except PackageError as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 2
    finally:
        source_engine.dispose()
        target_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
