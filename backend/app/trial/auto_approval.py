"""Approving a free-trial request at once, for a company email.

A request from a company domain is approved right after sign-up, so the requester has the activation email within a
minute instead of the next business day. Everything else waits for a Platform Administrator as before: a free-mail or
disposable address, a company that already has a trial or a request (the second colleague is invited by the first),
and every request beyond the day's cap. ``MDARIX_TRIAL_AUTO_APPROVE`` (``company-domains``, the default, or ``off``)
switches it; ``MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX`` caps it per UTC day (20 by default). A Platform Administrator can
still end any trial (Customers & Tenants > Trials).

The approval is the usual one (``service.approve_request``), made by the platform's "automatic approval" account, an
account that cannot sign in; it runs after sign-up's response in its own session, and a failure leaves the request
waiting for review, with the reason logged.
"""

from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, time, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger("mdarix.trial.auto_approval")

APPROVER_USERNAME = "automatic-approval@mdarix.invalid"
APPROVER_NAME = "Automatic approval (company email)"
DEFAULT_DAILY_MAX = 20

# Addresses anyone can create: their requests are reviewed by a person.
FREE_MAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "yahoo.co.in",
        "yahoo.co.uk",
        "ymail.com",
        "rocketmail.com",
        "outlook.com",
        "hotmail.com",
        "hotmail.co.uk",
        "live.com",
        "msn.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
        "pm.me",
        "gmx.com",
        "gmx.de",
        "gmx.net",
        "web.de",
        "mail.com",
        "email.com",
        "yandex.com",
        "yandex.ru",
        "zoho.com",
        "zohomail.com",
        "rediffmail.com",
        "qq.com",
        "163.com",
        "126.com",
        "sina.com",
        "naver.com",
        "inbox.com",
        "tutanota.com",
        "tuta.io",
        "fastmail.com",
        "hey.com",
        "mailinator.com",
        "guerrillamail.com",
        "sharklasers.com",
        "10minutemail.com",
        "temp-mail.org",
        "tempmail.com",
        "yopmail.com",
        "trashmail.com",
        "dispostable.com",
        "getnada.com",
        "maildrop.cc",
    }
)


def mode() -> str:
    value = (os.getenv("MDARIX_TRIAL_AUTO_APPROVE") or "company-domains").strip().lower()
    return "off" if value in ("off", "false", "0", "no", "manual") else "company-domains"


def daily_max() -> int:
    try:
        return max(0, int(os.getenv("MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX") or DEFAULT_DAILY_MAX))
    except ValueError:
        return DEFAULT_DAILY_MAX


def domain_of(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().lower() if "@" in email else ""


# Top-level domains reserved for tests and examples (RFC 2606, RFC 6761): no organization's mail.
RESERVED_SUFFIXES = (".invalid", ".test", ".example", ".localhost", ".local")


def is_company_domain(domain: str) -> bool:
    """A domain that names an organization: not free mail or disposable, not reserved, with a dot and no IP-like
    form."""
    if not domain or "." not in domain or domain.replace(".", "").isdigit() or domain.endswith(RESERVED_SUFFIXES):
        return False
    return domain not in FREE_MAIL_DOMAINS and not any(domain.endswith("." + free) for free in FREE_MAIL_DOMAINS)


def eligible(db: Session, request_id: uuid.UUID, now: datetime | None = None) -> tuple[bool, str]:
    """Whether this request is approved at once, and why not (for the log and the test)."""
    from backend.app.db.models.foundation import AuditEvent
    from backend.app.db.models.stage2 import OnboardingRequest

    if mode() == "off":
        return False, "OFF"
    row = db.get(OnboardingRequest, request_id)
    if row is None or row.status != "PENDING_REVIEW":
        return False, "NOT_PENDING"
    domain = domain_of(row.email)
    if not is_company_domain(domain):
        return False, "FREE_MAIL"
    same_company = (
        db.query(OnboardingRequest.id)
        .filter(OnboardingRequest.id != row.id, func.lower(OnboardingRequest.email).like(f"%@{domain}"))
        .first()
    )
    if same_company is not None:
        return False, "COMPANY_ALREADY_HAS_A_REQUEST"
    now = now or datetime.now(timezone.utc)
    start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    approver = _approver(db, create=False)
    today = 0
    if approver is not None:
        today = (
            db.query(func.count(AuditEvent.id))
            .filter(
                AuditEvent.actor_ref == str(approver.id),
                AuditEvent.action == "TRIAL_REQUEST_APPROVED",
                AuditEvent.created_at >= start,
            )
            .scalar()
            or 0
        )
    if today >= daily_max():
        return False, "DAILY_CAP"
    return True, "COMPANY_DOMAIN"


def _approver(db: Session, create: bool = True):
    """The platform's automatic-approval account (cannot sign in), created once in the platform organization."""
    from backend.app.db.models.foundation import AuthUser
    from backend.app.support_access import platform_tenant_id
    from backend.app.trial.service import _hash

    tenant_id = platform_tenant_id(db)
    if tenant_id is None:
        return None
    user = db.query(AuthUser).filter(AuthUser.username == APPROVER_USERNAME).first()
    if user is not None or not create:
        return user
    now = datetime.now(timezone.utc)
    user = AuthUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        username=APPROVER_USERNAME,
        display_name=APPROVER_NAME,
        company="MDARIX",
        password_hash=_hash(secrets.token_urlsafe(32)),
        role="Viewer",
        status="DISABLED",
        email_verified=False,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    return user


def approve_if_eligible(request_id: uuid.UUID) -> dict:
    """Approve the request when it qualifies (see the module docstring). Runs after sign-up's response, in its own
    session; never raises. Returns what happened."""
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system
    from backend.app.trial.service import approve_request

    db = SessionLocal()
    try:
        bind_system(db, "trial sign-up: automatic approval")
        ok, why = eligible(db, request_id)
        if not ok:
            logger.info("Trial request waits for review: %s", why)
            return {"approved": False, "why": why}
        approver = _approver(db)
        if approver is None:
            return {"approved": False, "why": "NO_PLATFORM_ORGANIZATION"}
        db.commit()
        approve_request(db, request_id, approver)
        return {"approved": True, "why": why}
    except Exception as exc:  # the request stays waiting for review; nothing is lost
        db.rollback()
        logger.warning("Automatic trial approval failed, the request waits for review: %s", type(exc).__name__)
        return {"approved": False, "why": "FAILED"}
    finally:
        db.close()


def approve_or_acknowledge(request_id: uuid.UUID, organization: str, display_name: str, email: str) -> None:
    """After sign-up's response: approve the request; if that cannot be done after all, the requester gets the usual
    "we review your request" acknowledgement instead, so nobody waits without word."""
    if approve_if_eligible(request_id).get("approved"):
        return
    from backend.app.trial.service import acknowledge_trial_request

    acknowledge_trial_request(organization, display_name, email)
