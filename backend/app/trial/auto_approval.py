"""Approving a free-trial request at once, for a company email.

A request from a company domain is approved right after sign-up, so the requester has the activation email within a
minute instead of the next business day. Everything else waits for a Platform Administrator as before: a free-mail or
disposable address, a company that already has a trial or a request (the second colleague is invited by the first),
a domain that does not exist in DNS, every request beyond the day's cap, and an address of MDARIX's own platform
organization (its staff accounts' domains and the support address's; FUN-14). ``MDARIX_TRIAL_AUTO_APPROVE``
(``company-domains``, the default, or ``off``) switches it; ``MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX`` caps it per UTC
day (20 by default). A Platform Administrator can still end any trial (Customers & Tenants > Trials).

Made-up company domains could use up the day's automatic approvals with junk workspaces whose invitations bounce
(pre-launch review SEC-07). So the domain must resolve (an A or AAAA record, looked up with a short timeout; a domain
with mail but no address record waits for review), and the cap counts the day's company-email requests, not the
approvals: a burst of sign-ups beyond it is seen by a person. ``MDARIX_TRIAL_DOMAIN_CHECK=off`` skips the lookup on a
development or test machine only; staging and production always look the domain up.

The approval is the usual one (``service.approve_request``), made by the platform's "automatic approval" account, an
account that cannot sign in; it runs after sign-up's response in its own session, and a failure leaves the request
waiting for review, with the reason logged. An invitation email that fails afterwards never undoes the approval: it
is recorded on the request (the Platform Admin queue shows it next to "Resend invitation"), retried through the
outbox, and the operators are alerted (backend/app/alerts.py), since nobody else would notice.
"""

from __future__ import annotations

import logging
import os
import secrets
import socket
import threading
import uuid
from datetime import datetime, time, timezone
from time import monotonic

from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger("mdarix.trial.auto_approval")

APPROVER_USERNAME = "automatic-approval@mdarix.invalid"
APPROVER_NAME = "Automatic approval (company email)"
DEFAULT_DAILY_MAX = 20
# Sign-up waits for the lookup (it says "approving" or "we review" at once), so it is short; a slower answer is "no".
DNS_TIMEOUT_SECONDS = 2.0
# A domain found in DNS is not looked up again for an hour: sign-up and the approval after it ask the same question.
DNS_CACHE_SECONDS = 3600
_resolved: dict[str, float] = {}

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


def domain_check() -> str:
    """``dns`` (look the domain up), or ``off`` on a development or test machine whose
    ``MDARIX_TRIAL_DOMAIN_CHECK`` says so; staging and production always look it up."""
    from backend.app.runtime_env import is_local

    value = (os.getenv("MDARIX_TRIAL_DOMAIN_CHECK") or "dns").strip().lower()
    return "off" if value in ("off", "false", "0", "no") and is_local() else "dns"


def _lookup(domain: str, found: list) -> None:
    try:
        found.append(bool(socket.getaddrinfo(domain, None)))
    except (OSError, UnicodeError):  # socket.gaierror: no such domain, or DNS could not be asked
        found.append(False)


def domain_resolves(domain: str) -> bool:
    """Whether the domain exists in DNS (an A or AAAA record, through the system resolver). No answer within
    ``DNS_TIMEOUT_SECONDS``, or DNS that cannot be reached, counts as no: the request waits for review."""
    checked = _resolved.get(domain)
    if checked is not None and monotonic() - checked < DNS_CACHE_SECONDS:
        return True
    found: list = []
    # getaddrinfo has no timeout of its own; a lookup still running after the timeout ends on its own, unread.
    worker = threading.Thread(target=_lookup, args=(domain, found), daemon=True)
    worker.start()
    worker.join(DNS_TIMEOUT_SECONDS)
    if found and found[0]:
        _resolved[domain] = monotonic()
        return True
    return False


def is_company_domain(domain: str) -> bool:
    """A domain that names an organization: not free mail or disposable, not reserved, with a dot and no IP-like
    form."""
    if not domain or "." not in domain or domain.replace(".", "").isdigit() or domain.endswith(RESERVED_SUFFIXES):
        return False
    return domain not in FREE_MAIL_DOMAINS and not any(domain.endswith("." + free) for free in FREE_MAIL_DOMAINS)


def platform_domains(db: Session) -> set[str]:
    """The email domains of MDARIX's own platform organization: its accounts' (the staff) and the support address's.
    A trial request from one of them is never approved automatically (FUN-14)."""
    from backend.app.db.models.foundation import AuthUser
    from backend.app.support_access import platform_tenant_id

    found = {domain_of(os.getenv("MDARIX_SUPPORT_EMAIL") or "")}
    tenant_id = platform_tenant_id(db)
    if tenant_id is not None:
        found |= {
            domain_of(username) for (username,) in db.query(AuthUser.username).filter(AuthUser.tenant_id == tenant_id)
        }
    return {domain for domain in found if is_company_domain(domain)}


def eligible(db: Session, request_id: uuid.UUID, now: datetime | None = None) -> tuple[bool, str]:
    """Whether this request is approved at once, and why not (for the log and the test)."""
    from backend.app.db.models.stage2 import OnboardingRequest

    if mode() == "off":
        return False, "OFF"
    row = db.get(OnboardingRequest, request_id)
    if row is None or row.status != "PENDING_REVIEW":
        return False, "NOT_PENDING"
    domain = domain_of(row.email)
    if not is_company_domain(domain):
        return False, "FREE_MAIL"
    if domain in platform_domains(db):
        return False, "PLATFORM_ORGANIZATION"
    same_company = (
        db.query(OnboardingRequest.id)
        .filter(OnboardingRequest.id != row.id, func.lower(OnboardingRequest.email).like(f"%@{domain}"))
        .first()
    )
    if same_company is not None:
        return False, "COMPANY_ALREADY_HAS_A_REQUEST"
    sent = row.created_at or now or datetime.now(timezone.utc)
    start = datetime.combine(sent.astimezone(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    # The earlier requests from company emails on the request's UTC day, approved or not: counting only approvals let
    # made-up domains use up the cap unseen (SEC-07). Earlier ones only, so sign-up and the approval after it give the
    # same answer.
    earlier = (
        db.query(OnboardingRequest.email)
        .filter(
            OnboardingRequest.id != row.id,
            OnboardingRequest.created_at >= start,
            OnboardingRequest.created_at < row.created_at,
        )
        .all()
    )
    if sum(1 for (email,) in earlier if is_company_domain(domain_of(email))) >= daily_max():
        return False, "DAILY_CAP"
    if domain_check() == "dns" and not domain_resolves(domain):
        return False, "DOMAIN_NOT_FOUND"
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
        result = approve_request(db, request_id, approver)
        if result.get("email_delivery") == "FAILED":
            _alert_invitation_failed(result)
        return {"approved": True, "why": why, "email_delivery": result.get("email_delivery")}
    except Exception as exc:  # the request stays waiting for review; nothing is lost
        db.rollback()
        logger.warning("Automatic trial approval failed, the request waits for review: %s", type(exc).__name__)
        return {"approved": False, "why": "FAILED"}
    finally:
        db.close()


def _alert_invitation_failed(result: dict) -> None:
    """Tell the operators that an automatically approved trial's invitation did not go out (no address or name:
    the request's MDARIX ID and the provider's error). Never raises."""
    from backend.app.alerts import send_alert

    try:
        send_alert(
            "Trial invitation not delivered",
            f"Trial request {result.get('business_id') or result.get('id')} was approved automatically, but its "
            f"invitation email failed: {result.get('email_error') or 'unknown error'}. MDARIX retries it for about "
            "five hours. Platform Admin > Trial requests shows it as not delivered and can resend it.",
        )
    except Exception as exc:  # an alert must never fail the sign-up's background work
        logger.warning("The invitation failure alert could not be sent: %s", type(exc).__name__)


def approve_or_acknowledge(request_id: uuid.UUID, organization: str, display_name: str, email: str) -> None:
    """After sign-up's response: approve the request; if that cannot be done after all, the requester gets the usual
    "we review your request" acknowledgement instead, so nobody waits without word."""
    if approve_if_eligible(request_id).get("approved"):
        return
    from backend.app.trial.service import acknowledge_trial_request

    acknowledge_trial_request(organization, display_name, email)
