"""Delete everything an organization stored, keeping only a minimal record that it existed.

Used for free trials 30 days after they end (backend/app/trial/retention.py) and for offboarding on request
(docs/runbooks/DATA_REQUESTS.md). The tables are discovered from the database (every table with a ``tenant_id``
column), so a table added later is covered without a code change. Kept, as the record of the contract and of
consent:

* the organization row (status ARCHIVED) and its subscription, plan and license history;
* user accounts and memberships, **pseudonymized**: names and email addresses replaced, passwords and
  authenticator secrets removed, so nobody can sign in and nobody is identifiable;
* the trial request, pseudonymized the same way;
* feedback the person agreed to have published and that was published (their consent covers keeping it).

Everything else goes: business records, AI records, imports, connector settings and keys, sessions, invitations,
sign-in history, notifications, the audit trail (deleted as a whole, then restarted with one record of this
deletion) and every stored file. The purge is all-or-nothing: if any table still holds rows or a file cannot be
deleted, the database work is rolled back, the organization is not archived, and the caller reports the failure.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import AuditEvent, AuthUser, Tenant, TenantMembership
from backend.app.db.models.stage2 import OnboardingRequest

logger = logging.getLogger("mdarix.tenant_purge")

# Kept as the record of the contract, pseudonymized where they name people (see the module docstring).
KEEP_TABLES = frozenset(
    {
        "auth_users",
        "tenant_memberships",
        "onboarding_requests",
        "subscription_lifecycles",
        "subscription_versions",
        "license_transitions",
        "tenant_plan_assignments",
        "plan_version_assignments",
        "tenant_access_transitions",
        "tenant_data_planes",
    }
)
# Handled separately: the audit trail is deleted as a whole at the end; published feedback is kept.
SPECIAL_TABLES = frozenset({"audit_events", "trial_feedback"})
SCHEMAS = ("public", "md_master")


class PurgeFailed(RuntimeError):
    """The organization's data could not be deleted completely; nothing was changed."""


def tenant_tables(db: Session) -> list[str]:
    """Every table holding rows for one organization, schema-qualified, except those kept or handled separately."""
    rows = db.execute(
        text(
            "SELECT c.table_schema, c.table_name FROM information_schema.columns c "
            "JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
            "WHERE c.column_name = 'tenant_id' AND t.table_type = 'BASE TABLE' AND c.table_schema = ANY(:schemas) "
            "ORDER BY c.table_schema, c.table_name"
        ),
        {"schemas": list(SCHEMAS)},
    ).all()
    return [
        f'"{schema}"."{table}"' for schema, table in rows if table not in KEEP_TABLES and table not in SPECIAL_TABLES
    ]


def delete_rows(db: Session, tables: list[str], tenant_id) -> tuple[dict[str, int], list[str]]:
    """Delete the tenant's rows from ``tables``, retrying in passes until foreign keys allow every delete.
    Returns rows deleted per table and the tables that still could not be emptied. Does not commit."""
    remaining = list(tables)
    deleted: dict[str, int] = {}
    while remaining:
        progress = False
        for table in list(remaining):
            savepoint = db.begin_nested()
            try:
                result = db.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tenant"), {"tenant": tenant_id})
                savepoint.commit()
            except DBAPIError:
                savepoint.rollback()
                continue
            if result.rowcount:
                deleted[table.split(".")[-1].strip('"')] = result.rowcount
            remaining.remove(table)
            progress = True
        if not progress:
            break
    return deleted, remaining


# Rows that exist only to let one person sign in or that record their sign-in activity (deleted on erasure).
PERSONAL_ACCOUNT_TABLES = (
    "auth_sessions",
    "mfa_challenges",
    "password_history",
    "password_reset_requests",
    "user_invitations",
    "authentication_events",
)


def _pseudonymize_account(user: AuthUser, now: datetime) -> None:
    user.username = f"removed-{user.id.hex[:16]}@removed.invalid"
    user.display_name = "Removed user"
    user.company = "Removed"
    user.password_hash = "!removed"
    user.status = "REMOVED"
    user.email_verified = False
    user.mfa_secret_encrypted = None
    user.mfa_pending_secret_encrypted = None
    user.mfa_recovery_hashes = None
    user.mfa_last_step = None
    user.updated_at = now


def erase_person(db: Session, user: AuthUser, actor_ref: str, reason: str, now: datetime | None = None) -> dict:
    """Erase one person's personal data on request (docs/runbooks/DATA_REQUESTS.md); does not commit.

    The account is pseudonymized (name, email and credentials replaced), their sign-in records, sessions,
    invitations and unpublished feedback are deleted, and their roles removed. Business records they created keep
    the account's id, which no longer identifies anyone. Audit rows cannot be changed: they keep the id and, for
    the retention period, the network address recorded at the time, as the runbook explains."""
    now = now or datetime.now(timezone.utc)
    if (user.status or "").upper() not in {"OFFBOARDED", "REMOVED", "SUSPENDED"}:
        raise PurgeFailed("USER_STILL_ACTIVE")
    deleted: dict[str, int] = {}
    present = {
        name
        for (name,) in db.execute(
            text(
                "SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' AND column_name = 'user_id'"
            )
        )
    }
    for table in (*PERSONAL_ACCOUNT_TABLES, "role_assignments", "persona_assignments"):
        if table in present:
            count = db.execute(text(f'DELETE FROM "{table}" WHERE user_id = :user'), {"user": user.id}).rowcount
            if count:
                deleted[table] = count
    feedback = db.execute(
        text("DELETE FROM trial_feedback WHERE user_id = :user AND publication_status <> 'PUBLISHED'"),
        {"user": user.id},
    ).rowcount
    if feedback:
        deleted["trial_feedback"] = feedback
    _pseudonymize_account(user, now)
    db.query(TenantMembership).filter(TenantMembership.user_id == user.id).update(
        {"status": "REMOVED", "updated_at": now}, synchronize_session=False
    )
    result = {"user_id": str(user.id), "deleted_records": deleted}
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=user.tenant_id,
            actor_ref=actor_ref,
            action="PERSONAL_DATA_ERASED",
            entity_type="AuthUser",
            entity_id=user.id,
            reason=reason,
            details=result,
            created_at=now,
        )
    )
    return result


def _pseudonymize_people(db: Session, tenant_id, now: datetime) -> int:
    users = db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id).all()
    for user in users:
        _pseudonymize_account(user, now)
    db.query(TenantMembership).filter(TenantMembership.tenant_id == tenant_id).update(
        {"status": "REMOVED", "updated_at": now}, synchronize_session=False
    )
    for request in db.query(OnboardingRequest).filter(OnboardingRequest.tenant_id == tenant_id).all():
        request.email = f"removed-{request.id.hex[:16]}@removed.invalid"
        request.display_name = "Removed"
        request.updated_at = now
    return len(users)


def _purge_dedicated_plane(control: Session, tenant_id) -> dict[str, int]:
    """Delete the organization's rows from its dedicated database, if it has one (committed there first; the control
    database is purged afterwards, so a failure here leaves everything in place for the next attempt)."""
    from backend.app.db.data_plane import SHARED_CONTROL_DATA_PLANE, session_factory
    from backend.app.db.models.customer_lifecycle import TenantDataPlane
    from backend.app.db.tenant_scope import bind_system

    row = (
        control.query(TenantDataPlane)
        .filter(
            TenantDataPlane.tenant_id == tenant_id, TenantDataPlane.connection_secret_ref != SHARED_CONTROL_DATA_PLANE
        )
        .first()
    )
    if row is None:
        return {}
    plane = session_factory(row.database_ref, row.connection_secret_ref)()
    try:
        bind_system(plane, f"purge tenant {tenant_id} (dedicated plane)")
        plane.execute(
            text("UPDATE tenants SET status = 'PURGING', updated_at = now() WHERE id = :tenant"), {"tenant": tenant_id}
        )
        deleted, remaining = delete_rows(plane, tenant_tables(plane), tenant_id)
        if remaining:
            raise PurgeFailed(f"PLANE_ROWS_REMAIN:{','.join(sorted(remaining))}")
        plane.execute(text("SELECT set_config('mdarix.audit_purge_tenant', :tenant, true)"), {"tenant": str(tenant_id)})
        audit = plane.execute(
            text("DELETE FROM audit_events WHERE tenant_id = :tenant"), {"tenant": tenant_id}
        ).rowcount
        plane.execute(
            text("UPDATE tenants SET status = 'ARCHIVED', updated_at = now() WHERE id = :tenant"), {"tenant": tenant_id}
        )
        plane.commit()
        if audit:
            deleted["audit_events"] = audit
        return {f"plane:{name}": count for name, count in deleted.items()}
    except Exception:
        plane.rollback()
        raise
    finally:
        plane.close()


def purge_tenant(
    db: Session, tenant_id, actor_ref: str, *, reason: str, storage=None, now: datetime | None = None
) -> dict:
    """Delete one organization's data (see the module docstring) and archive it. Commits on success; raises
    PurgeFailed, with nothing changed, when anything would remain."""
    from backend.app.db.tenant_scope import bind_system

    tenant_id = uuid.UUID(str(tenant_id))
    now = now or datetime.now(timezone.utc)
    bind_system(db, f"purge tenant {tenant_id}")
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise PurgeFailed("TENANT_NOT_FOUND")
    tenant.status = "PURGING"
    tenant.updated_at = now
    db.flush()
    try:
        plane_deleted = _purge_dedicated_plane(db, tenant_id)
        deleted, remaining = delete_rows(db, tenant_tables(db), tenant_id)
        deleted.update(plane_deleted)
        feedback = db.execute(
            text("DELETE FROM trial_feedback WHERE tenant_id = :tenant AND publication_status <> 'PUBLISHED'"),
            {"tenant": tenant_id},
        ).rowcount
        if feedback:
            deleted["trial_feedback"] = feedback
        if remaining:
            raise PurgeFailed(f"ROWS_REMAIN:{','.join(sorted(remaining))}")
        people = _pseudonymize_people(db, tenant_id, now)
        db.execute(text("SELECT set_config('mdarix.audit_purge_tenant', :tenant, true)"), {"tenant": str(tenant_id)})
        audit_rows = db.execute(text("DELETE FROM audit_events WHERE tenant_id = :tenant"), {"tenant": tenant_id})
        db.execute(text("SELECT set_config('mdarix.audit_purge_tenant', '', true)"))
        db.execute(
            text("UPDATE tenant_data_planes SET status = 'RETIRED', updated_at = :now WHERE tenant_id = :tenant"),
            {"now": now, "tenant": tenant_id},
        )
        if storage is None:
            from object_storage.service import ObjectStorageService

            storage = ObjectStorageService()
        files = storage.delete_tenant(str(tenant_id))
    except PurgeFailed:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Purge of tenant %s failed", tenant_id)
        raise PurgeFailed(f"{type(exc).__name__}") from exc
    tenant = db.get(Tenant, tenant_id)
    tenant.status = "ARCHIVED"
    tenant.updated_at = now
    result = {
        "deleted_records": deleted,
        "not_deleted_tables": [],
        "audit_events_deleted": int(audit_rows.rowcount or 0),
        "files_deleted": files,
        "users_pseudonymized": people,
    }
    # The organization's trail restarts with one record of what was deleted, by whom and why.
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=actor_ref,
            action="TENANT_DATA_DELETED",
            entity_type="Tenant",
            entity_id=tenant_id,
            reason=reason,
            details=result,
            created_at=now,
        )
    )
    db.commit()
    logger.info("Tenant %s purged: %s", tenant_id, result)
    return result
