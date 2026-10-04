"""Delete everything an organization stored, keeping only a minimal record that it existed.

Used for free trials 30 days after they end (backend/app/trial/retention.py) and for offboarding on request
(docs/runbooks/DATA_REQUESTS.md). The tables are discovered from the database (every table with a ``tenant_id``
column), so a table added later is covered without a code change. Kept, as the record of the contract and of
consent:

* the organization row (status ARCHIVED) and its subscription, plan and license history;
* user accounts and memberships, **pseudonymized**: names and email addresses replaced, passwords and
  authenticator secrets removed, so nobody can sign in and nobody is identifiable;
* the trial request, pseudonymized the same way;
* feedback the person agreed to have published and that was published (their consent covers keeping it);
* the erasure log (``erasure_log``), so a restore from backup can re-apply the deletion (``reapply_erasures``).

Everything else goes: business records, AI records, imports, connector settings and keys, sessions, invitations,
sign-in history, notifications, the audit trail (deleted as a whole, then restarted with one record of this
deletion) and every stored file.

The purge runs in two stages. Stage one, the database rows, is all-or-nothing: if any table still holds rows the
transaction is rolled back, the organization is not archived, and the caller reports the failure. Only once the rows
are committed (status PURGING) does stage two delete the stored files and, when the organization has one, the rows
in its dedicated database; each is retried, and if either still fails the organization stays PURGING, the failure
is recorded in the audit trail and the erasure log, operations is alerted, and an operator finishes it with
``scripts/complete_tenant_purge.py`` (or the next purge attempt resumes it). ARCHIVED is set only when everything is
gone. Nothing is purged or erased while the organization is under a legal hold (``tenants.legal_hold``).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import AuditEvent, AuthUser, Tenant, TenantMembership
from backend.app.db.models.pilot_support import ErasureLog
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
        "erasure_log",
    }
)
# Handled separately: the audit trail is deleted as a whole at the end; published feedback is kept.
SPECIAL_TABLES = frozenset({"audit_events", "trial_feedback"})
SCHEMAS = ("public", "md_master")
# How often stage two (files, dedicated plane) is attempted before the purge is left for an operator to finish.
COMPLETION_ATTEMPTS = 3

REMOVED_DOMAIN = "@removed.invalid"
REMOVED_NAME = "Removed user"
REMOVED_PASSWORD = "!removed"
# What _pseudonymize_account replaces, recorded in the erasure log so a reviewer knows exactly what was removed.
PSEUDONYMIZED_COLUMNS = {
    "auth_users": [
        "username",
        "display_name",
        "company",
        "password_hash",
        "status",
        "email_verified",
        "mfa_secret_encrypted",
        "mfa_pending_secret_encrypted",
        "mfa_recovery_hashes",
        "mfa_last_step",
    ],
    "tenant_memberships": ["status"],
}


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


def tenant_has_rows(db: Session, tenant_id) -> list[str]:
    """The tenant tables that still hold rows for ``tenant_id`` (empty after a complete purge)."""
    present = []
    for table in tenant_tables(db):
        if db.execute(text(f"SELECT 1 FROM {table} WHERE tenant_id = :tenant LIMIT 1"), {"tenant": tenant_id}).first():
            present.append(table.split(".")[-1].strip('"'))
    return present


def _require_no_legal_hold(tenant: Tenant | None) -> None:
    """A legal hold (set by a platform administrator, legal_hold_api.py) stops every deletion for the organization."""
    if tenant is not None and tenant.legal_hold:
        raise PurgeFailed("LEGAL_HOLD")


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
    user.username = f"removed-{user.id.hex[:16]}{REMOVED_DOMAIN}"
    user.display_name = REMOVED_NAME
    user.company = "Removed"
    user.password_hash = REMOVED_PASSWORD
    user.status = "REMOVED"
    user.email_verified = False
    user.mfa_secret_encrypted = None
    user.mfa_pending_secret_encrypted = None
    user.mfa_recovery_hashes = None
    user.mfa_last_step = None
    user.updated_at = now


def person_is_pseudonymized(db: Session, user: AuthUser) -> bool:
    """True when nothing identifying the person remains: the account is pseudonymized and its sign-in rows are gone.
    False for an account restored from a backup taken before the erasure (scripts/reapply_erasures.py)."""
    if not (
        user.username.endswith(REMOVED_DOMAIN)
        and user.display_name == REMOVED_NAME
        and user.password_hash == REMOVED_PASSWORD
        and user.status == "REMOVED"
        and user.mfa_secret_encrypted is None
    ):
        return False
    for table in PERSONAL_ACCOUNT_TABLES:
        if db.execute(text(f'SELECT 1 FROM "{table}" WHERE user_id = :user LIMIT 1'), {"user": user.id}).first():
            return False
    return True


def erase_person(
    db: Session, user: AuthUser, actor_ref: str, reason: str, now: datetime | None = None, *, reapply: bool = False
) -> dict:
    """Erase one person's personal data on request (docs/runbooks/DATA_REQUESTS.md); does not commit.

    The account is pseudonymized (name, email and credentials replaced), their sign-in records, sessions,
    invitations and unpublished feedback are deleted, and their roles removed. Business records they created keep
    the account's id, which no longer identifies anyone. Audit rows cannot be changed: they keep the id and, for
    the retention period, the network address recorded at the time, as the runbook explains. The erasure is written
    to ``erasure_log`` so it can be re-applied after a restore from backup; ``reapply`` is that re-application, for
    which the account's status no longer matters (the request was already verified the first time)."""
    now = now or datetime.now(timezone.utc)
    _require_no_legal_hold(db.get(Tenant, user.tenant_id))
    if not reapply and (user.status or "").upper() not in {"OFFBOARDED", "REMOVED", "SUSPENDED"}:
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
    result = {"user_id": str(user.id), "deleted_records": deleted, "pseudonymized": PSEUDONYMIZED_COLUMNS}
    db.add(
        ErasureLog(
            tenant_id=user.tenant_id,
            kind="PERSON_ERASED",
            subject_ref=str(user.id),
            performed_by=actor_ref,
            reason=reason,
            details={**result, "reapplied": reapply},
            performed_at=now,
        )
    )
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
        request.email = f"removed-{request.id.hex[:16]}{REMOVED_DOMAIN}"
        request.display_name = "Removed"
        request.updated_at = now
    return len(users)


def _dedicated_plane(control: Session, tenant_id):
    from backend.app.db.data_plane import SHARED_CONTROL_DATA_PLANE
    from backend.app.db.models.customer_lifecycle import TenantDataPlane

    return (
        control.query(TenantDataPlane)
        .filter(
            TenantDataPlane.tenant_id == tenant_id, TenantDataPlane.connection_secret_ref != SHARED_CONTROL_DATA_PLANE
        )
        .first()
    )


def _purge_dedicated_plane(control: Session, tenant_id) -> dict[str, int]:
    """Delete the organization's rows from its dedicated database, if it has one (stage two: the control database
    is already purged and committed; a failure here leaves the organization PURGING for the next attempt)."""
    from backend.app.db.data_plane import session_factory
    from backend.app.db.tenant_scope import bind_system

    row = _dedicated_plane(control, tenant_id)
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


def _pending_purge(db: Session, tenant_id) -> ErasureLog | None:
    """The erasure-log row of a purge whose files or dedicated plane are not yet confirmed deleted."""
    rows = (
        db.query(ErasureLog)
        .filter(ErasureLog.tenant_id == tenant_id, ErasureLog.kind == "TENANT_PURGED")
        .order_by(ErasureLog.performed_at.desc())
        .all()
    )
    for row in rows:
        if not (row.details or {}).get("completed"):
            return row
    return None


def _attempt(step: str, work, attempts: int) -> tuple[object, str | None]:
    """Run ``work`` up to ``attempts`` times; returns (value, None) or (None, "ErrorType: message")."""
    error = None
    for number in range(1, attempts + 1):
        try:
            return work(), None
        except Exception as exc:  # the step is retried; the last error is recorded for the operator
            error = f"{type(exc).__name__}: {str(exc)[:200]}"
            logger.warning("Purge step %s attempt %d/%d failed: %s", step, number, attempts, error)
    return None, error


def complete_purge(
    db: Session,
    tenant_id,
    actor_ref: str,
    *,
    storage=None,
    now: datetime | None = None,
    attempts: int = COMPLETION_ATTEMPTS,
) -> dict:
    """Stage two of a purge whose rows are already committed: delete the stored files and the dedicated plane's rows,
    then archive the organization and restart its trail with the one TENANT_DATA_DELETED record. Commits. When a
    step still fails after ``attempts`` tries the organization stays PURGING, the failure is recorded (audit event
    TENANT_PURGE_INCOMPLETE, erasure log) and operations is alerted; running this again finishes it."""
    from backend.app.alerts import send_alert
    from backend.app.db.tenant_scope import bind_system

    tenant_id = uuid.UUID(str(tenant_id))
    now = now or datetime.now(timezone.utc)
    bind_system(db, f"complete purge of tenant {tenant_id}")
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise PurgeFailed("TENANT_NOT_FOUND")
    log = _pending_purge(db, tenant_id)
    if log is None or str(tenant.status).upper() != "PURGING":
        raise PurgeFailed("NO_PENDING_PURGE")
    details = dict(log.details or {})
    result = {key: details.get(key) for key in ("deleted_records", "audit_events_deleted", "users_pseudonymized")}
    result["deleted_records"] = dict(result["deleted_records"] or {})
    result["not_deleted_tables"] = []
    errors: dict[str, str] = {}

    if storage is None:
        from object_storage.service import ObjectStorageService

        storage = ObjectStorageService()
    files, error = _attempt("files", lambda: storage.delete_tenant(str(tenant_id)), attempts)
    if error:
        errors["files"] = error
    result["files_deleted"] = files

    plane_deleted, error = _attempt("plane", lambda: _purge_dedicated_plane(db, tenant_id), attempts)
    if error:
        errors["plane"] = error
    else:
        result["deleted_records"].update(plane_deleted or {})

    bind_system(db, f"complete purge of tenant {tenant_id}: record the outcome")
    tenant = db.get(Tenant, tenant_id)
    log = db.get(ErasureLog, log.id)
    if errors:
        result["status"] = "PURGING"
        result["incomplete"] = errors
        log.details = {**details, **result, "completed": False, "last_attempt_at": now.isoformat()}
        db.add(
            AuditEvent(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                actor_ref=actor_ref,
                action="TENANT_PURGE_INCOMPLETE",
                entity_type="Tenant",
                entity_id=tenant_id,
                reason=log.reason,
                details={"incomplete": errors, "attempts": attempts},
                created_at=now,
            )
        )
        db.commit()
        send_alert(
            "Organization purge incomplete",
            f"The database rows of organization {tenant.tenant_key} are deleted but "
            f"{' and '.join(sorted(errors))} could not be removed after {attempts} attempts "
            f"({'; '.join(f'{step}: {error}' for step, error in sorted(errors.items()))}). "
            "The organization stays PURGING; run scripts/complete_tenant_purge.py once the cause is fixed.",
        )
        logger.error("Tenant %s purge incomplete: %s", tenant_id, errors)
        return result
    tenant.status = "ARCHIVED"
    tenant.updated_at = now
    result["status"] = "ARCHIVED"
    log.details = {**details, **result, "completed": True, "completed_at": now.isoformat()}
    # The organization's trail restarts with one record of what was deleted, by whom and why.
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=actor_ref,
            action="TENANT_DATA_DELETED",
            entity_type="Tenant",
            entity_id=tenant_id,
            reason=log.reason,
            details=result,
            created_at=now,
        )
    )
    db.commit()
    logger.info("Tenant %s purged: %s", tenant_id, result)
    return result


def purge_tenant(
    db: Session,
    tenant_id,
    actor_ref: str,
    *,
    reason: str,
    storage=None,
    now: datetime | None = None,
    attempts: int = COMPLETION_ATTEMPTS,
    evidence: dict | None = None,
) -> dict:
    """Delete one organization's data (see the module docstring) and archive it. Commits the database rows
    all-or-nothing, then deletes files and the dedicated plane (``complete_purge``). Raises PurgeFailed, with
    nothing changed, when rows would remain or the organization is under a legal hold. ``evidence`` (for example
    which export was handed back, or why none was) is kept in the erasure log and the deletion record, which are
    the only records that survive the purge. Called again for an organization left PURGING, it resumes stage two."""
    from backend.app.db.tenant_scope import bind_system

    tenant_id = uuid.UUID(str(tenant_id))
    now = now or datetime.now(timezone.utc)
    bind_system(db, f"purge tenant {tenant_id}")
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise PurgeFailed("TENANT_NOT_FOUND")
    _require_no_legal_hold(tenant)
    if str(tenant.status).upper() == "PURGING" and _pending_purge(db, tenant_id) is not None:
        return complete_purge(db, tenant_id, actor_ref, storage=storage, now=now, attempts=attempts)
    tenant.status = "PURGING"
    tenant.updated_at = now
    db.flush()
    try:
        deleted, remaining = delete_rows(db, tenant_tables(db), tenant_id)
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
        rows_result = {
            "deleted_records": deleted,
            "audit_events_deleted": int(audit_rows.rowcount or 0),
            "users_pseudonymized": people,
            "dedicated_plane": _dedicated_plane(db, tenant_id) is not None,
            **(evidence or {}),
        }
        # Written in the same transaction as the deletes: if the rows are gone, the log says so, and vice versa.
        db.add(
            ErasureLog(
                tenant_id=tenant_id,
                kind="TENANT_PURGED",
                subject_ref=str(tenant_id),
                performed_by=actor_ref,
                reason=reason,
                details={**rows_result, "completed": False},
                performed_at=now,
            )
        )
        db.commit()
    except PurgeFailed:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Purge of tenant %s failed", tenant_id)
        raise PurgeFailed(f"{type(exc).__name__}") from exc
    return complete_purge(db, tenant_id, actor_ref, storage=storage, now=now, attempts=attempts)


def tenants_purging(db: Session) -> list[Tenant]:
    """Organizations whose rows are deleted but whose files or dedicated plane still await deletion."""
    return [
        tenant
        for tenant in db.query(Tenant).filter(Tenant.status == "PURGING").order_by(Tenant.updated_at).all()
        if _pending_purge(db, tenant.id) is not None
    ]


def reapply_erasures(
    db: Session, actor_ref: str, *, dry_run: bool = False, storage=None, now: datetime | None = None
) -> dict:
    """After a restore from backup, repeat every erasure and purge the log records whose subject has personal data
    again (scripts/reapply_erasures.py). Each re-applied log row gets ``reapplied_at``. Commits per subject unless
    ``dry_run``. Subjects under a legal hold are reported, not touched."""
    from backend.app.db.tenant_scope import bind_system

    now = now or datetime.now(timezone.utc)
    bind_system(db, "re-apply erasures after restore")
    summary: dict = {"checked": 0, "reapplied": [], "pending": [], "skipped": [], "failed": [], "dry_run": dry_run}
    rows = db.query(ErasureLog).order_by(ErasureLog.performed_at).all()
    for log in rows:
        summary["checked"] += 1
        item = {"log_id": str(log.id), "kind": log.kind, "subject_ref": log.subject_ref, "tenant_id": str(log.tenant_id)}
        if log.kind == "PERSON_ERASED":
            try:
                user = db.get(AuthUser, uuid.UUID(log.subject_ref))
            except ValueError:
                user = None
            if user is None:
                summary["skipped"].append({**item, "why": "ACCOUNT_NOT_PRESENT"})
                continue
            if person_is_pseudonymized(db, user):
                summary["skipped"].append({**item, "why": "ALREADY_ERASED"})
                continue
            if dry_run:
                summary["pending"].append(item)
                continue
            try:
                erase_person(db, user, actor_ref, f"Re-applied after restore: {log.reason or ''}".strip(), now, reapply=True)
            except PurgeFailed as exc:
                db.rollback()
                bind_system(db, "re-apply erasures after restore")
                summary["failed"].append({**item, "error": str(exc)})
                continue
            db.get(ErasureLog, log.id).reapplied_at = now
            db.commit()
            summary["reapplied"].append(item)
        elif log.kind == "TENANT_PURGED":
            tenant = db.get(Tenant, log.tenant_id)
            if tenant is None:
                summary["skipped"].append({**item, "why": "TENANT_NOT_PRESENT"})
                continue
            if not (log.details or {}).get("completed") and str(tenant.status).upper() == "PURGING":
                summary["skipped"].append({**item, "why": "PURGE_IN_PROGRESS"})
                continue
            present = tenant_has_rows(db, tenant.id)
            people = [
                user for user in db.query(AuthUser).filter(AuthUser.tenant_id == tenant.id) if not person_is_pseudonymized(db, user)
            ]
            if str(tenant.status).upper() == "ARCHIVED" and not present and not people:
                summary["skipped"].append({**item, "why": "ALREADY_PURGED"})
                continue
            item["data_present"] = {"tables": present, "accounts": len(people), "status": tenant.status}
            if dry_run:
                summary["pending"].append(item)
                continue
            try:
                outcome = purge_tenant(
                    db,
                    tenant.id,
                    actor_ref,
                    reason=f"Re-applied after restore: {log.reason or ''}".strip(),
                    storage=storage,
                    now=now,
                    evidence={"reapplied_log_id": str(log.id)},
                )
            except PurgeFailed as exc:
                db.rollback()
                bind_system(db, "re-apply erasures after restore")
                summary["failed"].append({**item, "error": str(exc)})
                continue
            bind_system(db, "re-apply erasures after restore")
            db.get(ErasureLog, log.id).reapplied_at = now
            db.commit()
            summary["reapplied"].append({**item, "status": outcome["status"]})
        else:
            summary["skipped"].append({**item, "why": "UNKNOWN_KIND"})
    return summary
