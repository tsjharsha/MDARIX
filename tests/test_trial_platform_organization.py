"""FUN-14: a free-trial request from an address of MDARIX's own platform organization (a staff account's domain, or the
support address's) is never approved automatically; a Platform Administrator reviews it."""

import uuid
from datetime import datetime, timezone

from auth.service import _hash
from backend.app.db.models.foundation import AuthUser
from backend.app.db.models.stage2 import OnboardingRequest
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.support_access import platform_tenant_id
from backend.app.trial import auto_approval
from tests.test_free_trial import _platform_organization


def _request(email: str) -> OnboardingRequest:
    now = datetime.now(timezone.utc)
    return OnboardingRequest(
        id=uuid.uuid4(),
        email=email,
        display_name="Taylor Quality",
        organization="Request Test",
        status="PENDING_REVIEW",
        profile={},
        created_at=now,
        updated_at=now,
    )


def test_a_request_from_the_platform_organization_waits_for_review(monkeypatch):
    _platform_organization()
    tag = uuid.uuid4().hex[:8]
    staff_domain, support_domain = f"staff-{tag}.com", f"help-{tag}.com"
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE", "company-domains")
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX", "100000")
    monkeypatch.setenv("MDARIX_TRIAL_DOMAIN_CHECK", "off")
    monkeypatch.setenv("MDARIX_SUPPORT_EMAIL", f"support@{support_domain}")
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_system(db, "test: the platform organization's domains")
        staff = AuthUser(
            id=uuid.uuid4(),
            tenant_id=platform_tenant_id(db),
            username=f"ops@{staff_domain}",
            display_name="Platform Operator",
            company="MDARIX",
            password_hash=_hash(uuid.uuid4().hex),
            role="PLATFORM_ADMIN",
            status="ACTIVE",
            email_verified=True,
            created_at=now,
            updated_at=now,
        )
        db.add(staff)
        db.flush()
        from_staff = _request(f"new.hire@{staff_domain}")
        from_support = _request(f"someone@{support_domain}")
        from_customer = _request(f"quality.lead@customer-{tag}.com")
        db.add_all([from_staff, from_support, from_customer])
        db.commit()
        try:
            assert {staff_domain, support_domain} <= auto_approval.platform_domains(db)
            # Reserved test domains (the automatic-approval account's) are never taken for a company's.
            assert not any(domain.endswith(".invalid") for domain in auto_approval.platform_domains(db))
            assert auto_approval.eligible(db, from_staff.id) == (False, "PLATFORM_ORGANIZATION")
            assert auto_approval.eligible(db, from_support.id) == (False, "PLATFORM_ORGANIZATION")
            assert auto_approval.eligible(db, from_customer.id) == (True, "COMPANY_DOMAIN")
        finally:
            for row in (from_staff, from_support, from_customer, staff):
                db.delete(row)
            db.commit()
