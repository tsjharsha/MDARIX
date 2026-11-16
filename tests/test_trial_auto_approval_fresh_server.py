"""A fresh server (a new install, CI) where nobody ran scripts/create_platform_admin.py has no platform organization.
Sign-up still promised "Your trial is being prepared", so the automatic approval creates the organization its approval
account lives in instead of leaving every request waiting without a word (the CI browser job's three sign-ups)."""

from datetime import datetime, timezone

from sqlalchemy import text

from backend.app.auth_router import PLATFORM_TENANT_KEY
from backend.app.db.models.foundation import Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.support_access import ensure_platform_tenant, platform_tenant_id
from backend.app.trial import auto_approval


def _without_platform_organization(db) -> None:
    """Hide this database's platform organization and approval accounts, inside the test's transaction only (the
    identifier guards are switched off for it too, and back on at the rollback)."""
    db.execute(text("ALTER TABLE tenants DISABLE TRIGGER tenants_identifier_immutable"))
    db.execute(text("ALTER TABLE customers DISABLE TRIGGER customers_identifier_immutable"))
    db.execute(
        text(
            "UPDATE tenants SET tenant_key = 'HIDDEN_' || id, tenant_identifier = 'HIDDEN_' || id, "
            "tenant_slug = 'hidden-' || id WHERE tenant_key = :key"
        ),
        {"key": PLATFORM_TENANT_KEY},
    )
    db.execute(
        text("UPDATE customers SET customer_identifier = 'HIDDEN-OP' WHERE customer_identifier = 'MDARIX-OPERATOR'")
    )
    db.execute(
        text("UPDATE tenant_data_planes SET database_ref = 'hidden:' || id WHERE database_ref = :ref"),
        {"ref": f"shared-control:{PLATFORM_TENANT_KEY}"},
    )
    db.execute(
        text("UPDATE auth_users SET username = 'hidden-' || id WHERE username IN (:company, :personal)"),
        {"company": auto_approval.APPROVER_USERNAME, "personal": auto_approval.PERSONAL_APPROVER_USERNAME},
    )


def test_the_automatic_approval_account_is_made_on_a_server_without_a_platform_organization():
    db = SessionLocal()
    try:
        bind_system(db, "test: automatic approval on a fresh server")
        _without_platform_organization(db)
        assert platform_tenant_id(db) is None
        approver = auto_approval._approver(db)
        assert approver is not None and approver.status == "DISABLED"
        assert db.get(Tenant, approver.tenant_id).tenant_key == PLATFORM_TENANT_KEY
        # The personal-email account joins the same organization; the script finds it instead of making a second.
        assert auto_approval._approver(db, personal=True).tenant_id == approver.tenant_id
        assert ensure_platform_tenant(db, datetime.now(timezone.utc)).id == approver.tenant_id
    finally:
        db.rollback()
        db.close()
