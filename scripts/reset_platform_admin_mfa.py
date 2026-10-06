"""Break-glass: clear a Platform Administrator's MFA when no other platform administrator can do it in the console.

The normal path is another platform administrator resetting it (POST /api/v1/platform-admin/users/{id}/mfa-reset).
This script is for when that is impossible: the only platform administrator, or every one, lost their authenticator
and recovery codes. It runs on the server with the database owner's credentials (the migrate job), so whoever runs it
already controls the deployment; it still records who did it and why, in the MDARIX_PLATFORM organization's audit
trail. The person sets up a new authenticator at their next sign-in (MFA is required for administrators), and every
session of theirs ends.

    docker compose -f docker-compose.prod.yml --env-file .env.production run --rm migrate \\
        python scripts/reset_platform_admin_mfa.py admin@yourcompany.com --reason "Lost phone, ticket OPS-123" \\
        --operator "Your Name"
"""

from __future__ import annotations

import argparse
import getpass
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OPERATOR_TENANT_KEY = "MDARIX_PLATFORM"
AUDIT_ACTION = "PLATFORM_ADMIN_MFA_BREAK_GLASS_RESET"


def reset_platform_admin_mfa(db, email: str, reason: str, operator: str, now: datetime | None = None) -> dict:
    """Clear the MFA of the platform administrator ``email`` in the operator organization and audit it.

    Returns {"status": ..., ...}; ``status`` is RESET, or NOT_FOUND / NOT_PLATFORM_ADMIN when nothing was changed.
    The caller commits.
    """
    from backend.app import mfa
    from backend.app.db.models.foundation import AuthUser, Tenant
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.role_codes import is_platform_admin_role

    now = now or datetime.now(timezone.utc)
    tenant = db.query(Tenant).filter(Tenant.tenant_key == OPERATOR_TENANT_KEY).first()
    if tenant is None:
        return {"status": "NOT_FOUND", "message": f"No {OPERATOR_TENANT_KEY} organization exists yet"}
    user = db.query(AuthUser).filter(AuthUser.tenant_id == tenant.id, AuthUser.username == email).first()
    if user is None:
        return {
            "status": "NOT_FOUND",
            "message": f"{email} is not an account of the {OPERATOR_TENANT_KEY} organization",
        }
    if not is_platform_admin_role(user.role):
        # Everyone else has an administrator who can reset it in the console; break-glass is for the platform team.
        return {"status": "NOT_PLATFORM_ADMIN", "message": f"{email} is not a platform administrator"}
    was_enrolled = user.mfa_enrolled_at is not None
    revoked = mfa.reset(db, user, now)
    db.add(
        make_audit_event(
            tenant_id=tenant.id,
            actor_ref=f"break-glass:{operator}",
            action=AUDIT_ACTION,
            entity_type="AuthUser",
            entity_id=user.id,
            correlation_id=str(uuid.uuid4()),
            details={
                "source": "scripts/reset_platform_admin_mfa.py",
                "was_enrolled": was_enrolled,
                "sessions_revoked": revoked,
            },
            reason=reason,
            created_at=now,
        )
    )
    return {"status": "RESET", "user_id": str(user.id), "was_enrolled": was_enrolled, "sessions_revoked": revoked}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("email", help="the platform administrator's sign-in email")
    parser.add_argument("--reason", required=True, help="why, with the ticket reference (kept in the audit trail)")
    parser.add_argument("--operator", default="", help="who is running this (default: the shell user)")
    args = parser.parse_args(argv)
    email = args.email.strip().lower()
    reason = args.reason.strip()
    if "@" not in email:
        print("Give the platform administrator's email address.", file=sys.stderr)
        return 2
    if len(reason) < 10:
        print("Give a reason of at least 10 characters (it is kept in the audit trail).", file=sys.stderr)
        return 2
    operator = args.operator.strip() or getpass.getuser()

    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system

    db = SessionLocal()
    try:
        bind_system(db, "break-glass: reset a platform administrator's MFA")
        result = reset_platform_admin_mfa(db, email, reason, operator)
        if result["status"] != "RESET":
            db.rollback()
            print(result["message"], file=sys.stderr)
            return 1
        db.commit()
    finally:
        db.close()
    print(
        f"MFA cleared for {email} (was enrolled: {'yes' if result['was_enrolled'] else 'no'}); "
        f"{result['sessions_revoked']} session(s) ended. They set up a new authenticator at their next sign-in. "
        f"Recorded as {AUDIT_ACTION} in the {OPERATOR_TENANT_KEY} audit trail."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
