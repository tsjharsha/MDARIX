"""Invite a Platform Administrator (MDARIX staff), creating the MDARIX operator organization on first use.

Platform staff accounts live in their own organization, separate from every customer's. Run with the database
owner's credentials; the person receives a single-use activation link (valid 72 hours) by email, or, when this
server cannot send email, the link is printed here for you to pass on securely. They set up MFA at first sign-in.

    python scripts/create_platform_admin.py person@yourcompany.com --name "Full Name"
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _operator_tenant(db, now):
    from backend.app.support_access import ensure_platform_tenant

    return ensure_platform_tenant(db, now)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("email")
    parser.add_argument("--name", default="")
    args = parser.parse_args()
    email = args.email.strip().lower()
    if "@" not in email:
        print("Give a valid email address.", file=sys.stderr)
        return 2

    from auth.durable import issue_invitation
    from auth.emailer import EmailDeliveryError, send_activation_email
    from auth.service import _hash
    from backend.app.db.models.foundation import AuthUser, TenantMembership
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system

    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        bind_system(db, "bootstrap: invite a platform administrator")
        tenant = _operator_tenant(db, now)
        user = db.query(AuthUser).filter(AuthUser.tenant_id == tenant.id, AuthUser.username == email).first()
        if user is not None and str(user.status).upper() == "ACTIVE":
            print(f"{email} is already an active platform account.", file=sys.stderr)
            return 1
        if user is None:
            user = AuthUser(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                username=email,
                display_name=args.name.strip() or email.split("@")[0],
                company=tenant.display_name,
                password_hash=_hash(secrets.token_urlsafe(32)),  # unusable until the person sets their own
                role="PLATFORM_ADMIN",
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
        token = issue_invitation(db, user.id, tenant.id)
        try:
            delivery = send_activation_email(email, token, tenant.display_name)
        except EmailDeliveryError as exc:
            delivery = f"FAILED ({exc})"
        if delivery == "SENT":
            print(f"Invitation emailed to {email}; the link works once, within 72 hours.")
        else:
            app_url = os.getenv("MDARIX_APP_URL", "").rstrip("/")
            print(f"Email was not sent ({delivery}). Give {email} this single-use link (72 hours), securely:")
            print(f"{app_url}/activate-account?token={token}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
