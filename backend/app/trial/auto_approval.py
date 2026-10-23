"""Approving a free-trial request at once, for a company or a personal email.

A request from a company domain, or from a personal address at a known mail provider (Gmail, Outlook, Yahoo and the
others in ``PERSONAL_MAIL_DOMAINS``), is approved right after sign-up, so the requester has the activation email within
a minute instead of the next business day. Everything else waits for a Platform Administrator as before: a disposable
address (``DISPOSABLE_MAIL_DOMAINS``: anyone can make one in seconds, so it always waits), a company that already has a
trial or a request (the second colleague is invited by the first), a personal address that already has a request, a
domain that does not exist in DNS, every request beyond the day's cap, and an address of MDARIX's own platform
organization (its staff accounts' domains and addresses, and the support address; FUN-14).

``MDARIX_TRIAL_AUTO_APPROVE`` switches it: ``company-and-personal`` (the default since 0.10.48, an owner decision),
``company-domains`` (a personal address waits for review, as before 0.10.48) or ``off`` (every request waits). Any
other value is read as ``company-domains``, so a mistyped setting never approves more. A changed setting applies once
the API container is created again with it (``docker compose ... up -d``), without a release; sign-up reads it from the
site information (backend/app/site_info.py) and says what will happen before the request is sent.

Made-up company domains could use up the day's automatic approvals with junk workspaces whose invitations bounce
(pre-launch review SEC-07). So the domain must resolve (an A or AAAA record, looked up with a short timeout; a domain
with mail but no address record waits for review), and the caps count the day's requests, not the approvals: a burst of
sign-ups beyond them is seen by a person. Company and personal addresses have a cap each, and each counts only its own
kind: ``MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX`` (company addresses, 20 per UTC day by default) and
``MDARIX_TRIAL_AUTO_APPROVE_PERSONAL_DAILY_MAX`` (personal addresses, 10). The lookup is kept for personal addresses
too: the providers' own domains all resolve, so it costs one cached lookup, and a made-up subdomain of one
(``x@anything.gmail.com``) does not, so that request waits instead of getting an invitation that bounces.
``MDARIX_TRIAL_DOMAIN_CHECK=off`` skips the lookup on a development or test machine only; staging and production always
look the domain up.

Gmail's users are not one company, so the one-trial-per-company rule does not reach across a personal provider: for a
personal address the rule is one request per address, whatever its capitals. Sign-up already refuses an address that
has an account or a request (409), so the rule here only matters should a second request for an address ever be stored;
two different people with Gmail addresses each get their trial.

The approval is the usual one (``service.approve_request``), made by one of the platform's two automatic-approval
accounts, which cannot sign in: "Automatic approval (company email)" or "Automatic approval (personal email)". The
request records who approved it (``reviewed_by``, and the audit event's actor) and no reason, so the account itself
says which rule approved it: the Platform Admin queue shows its name, and approvals made before 0.10.48 keep the
company account's, which was the only rule then. It runs after sign-up's response in its own session, and a failure
leaves the request waiting for review, with the reason logged. An invitation email that fails afterwards never undoes
the approval: it is recorded on the request (the Platform Admin queue shows it next to "Resend invitation"), retried
through the outbox, and the operators are alerted (backend/app/alerts.py), since nobody else would notice. A Platform
Administrator can still end any trial (Customers & Tenants > Trials).
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

# The two accounts that approve automatically, one per rule, so the queue and the audit trail say which rule it was.
APPROVER_USERNAME = "automatic-approval@mdarix.invalid"
APPROVER_NAME = "Automatic approval (company email)"
PERSONAL_APPROVER_USERNAME = "automatic-approval-personal@mdarix.invalid"
PERSONAL_APPROVER_NAME = "Automatic approval (personal email)"

# MDARIX_TRIAL_AUTO_APPROVE: which addresses are approved at once.
COMPANY_AND_PERSONAL = "company-and-personal"
COMPANY_DOMAINS = "company-domains"
OFF = "off"
DEFAULT_MODE = COMPANY_AND_PERSONAL
DEFAULT_DAILY_MAX = 20
DEFAULT_PERSONAL_DAILY_MAX = 10
# Sign-up waits for the lookup (it says "approving" or "we review" at once), so it is short; a slower answer is "no".
DNS_TIMEOUT_SECONDS = 2.0
# A domain found in DNS is not looked up again for an hour: sign-up and the approval after it ask the same question.
DNS_CACHE_SECONDS = 3600
_resolved: dict[str, float] = {}

# Real mail providers, where a person keeps an address of their own for years: approved at once in the default mode,
# reviewed by a person in ``company-domains``.
PERSONAL_MAIL_DOMAINS = frozenset(
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
    }
)

# Throwaway inboxes anyone can open in seconds, without an account: always reviewed by a person, in every mode.
DISPOSABLE_MAIL_DOMAINS = frozenset(
    {
        "mailinator.com",
        "guerrillamail.com",
        "guerrillamail.net",
        "guerrillamail.org",
        "guerrillamail.biz",
        "guerrillamail.de",
        "guerrillamailblock.com",
        "sharklasers.com",
        "grr.la",
        "pokemail.net",
        "spam4.me",
        "10minutemail.com",
        "10minutemail.net",
        "temp-mail.org",
        "temp-mail.io",
        "tempmail.com",
        "yopmail.com",
        "yopmail.fr",
        "yopmail.net",
        "trashmail.com",
        "trashmail.de",
        "trashmail.net",
        "dispostable.com",
        "getnada.com",
        "maildrop.cc",
        "throwawaymail.com",
        "mailnesia.com",
        "mintemail.com",
        "fakeinbox.com",
        "emailondeck.com",
        "discard.email",
        "burnermail.io",
    }
)


def mode() -> str:
    """``company-and-personal`` (unset or empty), ``company-domains`` or ``off``. Any other value is read as
    ``company-domains``: a mistyped setting never approves more than company addresses."""
    value = (os.getenv("MDARIX_TRIAL_AUTO_APPROVE") or "").strip().lower()
    if value in ("off", "false", "0", "no", "manual"):
        return OFF
    if value in ("", COMPANY_AND_PERSONAL):
        return COMPANY_AND_PERSONAL
    return COMPANY_DOMAINS


def _cap(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name) or default))
    except ValueError:
        return default


def daily_max() -> int:
    """How many company-address requests per UTC day can be approved at once."""
    return _cap("MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX", DEFAULT_DAILY_MAX)


def personal_daily_max() -> int:
    """How many personal-address requests per UTC day can be approved at once (a cap of their own)."""
    return _cap("MDARIX_TRIAL_AUTO_APPROVE_PERSONAL_DAILY_MAX", DEFAULT_PERSONAL_DAILY_MAX)


def domain_of(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().lower() if "@" in email else ""


# Top-level domains reserved for tests and examples (RFC 2606, RFC 6761): no organization's mail.
RESERVED_SUFFIXES = (".invalid", ".test", ".example", ".localhost", ".local")


def _listed(domain: str, domains: frozenset[str]) -> bool:
    """The domain, or a subdomain of one, is on the list."""
    return domain in domains or any(domain.endswith("." + listed) for listed in domains)


def mail_kind(domain: str) -> str:
    """``company``, ``personal`` (a mail provider's domain or a subdomain of one), ``disposable`` (a throwaway inbox's,
    or a subdomain of one), or ``reserved`` (a test or example domain, no dot, or an IP-like form: no organization's
    mail)."""
    if not domain or "." not in domain or domain.replace(".", "").isdigit() or domain.endswith(RESERVED_SUFFIXES):
        return "reserved"
    if _listed(domain, DISPOSABLE_MAIL_DOMAINS):
        return "disposable"
    if _listed(domain, PERSONAL_MAIL_DOMAINS):
        return "personal"
    return "company"


def is_company_domain(domain: str) -> bool:
    """A domain that names an organization: not a mail provider's or disposable, not reserved, with a dot and no IP-like
    form."""
    return mail_kind(domain) == "company"


def reviewed_mail_domains() -> list[str]:
    """The mail domains whose requests a person reviews in the current mode (by address alone; caps and the other rules
    aside): the disposable ones, and the personal ones unless they are approved at once. The site information still
    sends it as ``free_mail_domains`` for a sign-up page opened before 0.10.48, which reads only that list."""
    reviewed = (
        DISPOSABLE_MAIL_DOMAINS if mode() == COMPANY_AND_PERSONAL else DISPOSABLE_MAIL_DOMAINS | PERSONAL_MAIL_DOMAINS
    )
    return sorted(reviewed)


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


def platform_addresses(db: Session) -> set[str]:
    """The email addresses of MDARIX's own platform organization: its accounts' (the staff, and the automatic-approval
    accounts) and the support address, in lower case."""
    from backend.app.db.models.foundation import AuthUser
    from backend.app.support_access import platform_tenant_id

    found = {(os.getenv("MDARIX_SUPPORT_EMAIL") or "").strip().lower()}
    tenant_id = platform_tenant_id(db)
    if tenant_id is not None:
        found |= {
            username.strip().lower()
            for (username,) in db.query(AuthUser.username).filter(AuthUser.tenant_id == tenant_id)
        }
    return {address for address in found if "@" in address}


def platform_domains(db: Session) -> set[str]:
    """The company domains of MDARIX's own platform organization: its accounts' (the staff) and the support address's.
    A trial request from one of them is never approved automatically (FUN-14). A personal provider's domain is not one
    of them (a staff member's Gmail address does not stand for every Gmail user); such an address is matched whole
    (``platform_addresses``)."""
    return {domain for domain in map(domain_of, platform_addresses(db)) if is_company_domain(domain)}


def eligible(db: Session, request_id: uuid.UUID, now: datetime | None = None) -> tuple[bool, str]:
    """Whether this request is approved at once, and why not (for the log and the test). Approved: ``COMPANY_DOMAIN``
    or ``PERSONAL_ADDRESS``; waiting: every other answer."""
    from backend.app.db.models.stage2 import OnboardingRequest

    approving = mode()
    if approving == OFF:
        return False, "OFF"
    row = db.get(OnboardingRequest, request_id)
    if row is None or row.status != "PENDING_REVIEW":
        return False, "NOT_PENDING"
    email = row.email.strip().lower()
    domain = domain_of(email)
    kind = mail_kind(domain)
    if kind == "reserved":
        return False, "RESERVED_DOMAIN"
    if kind == "disposable":
        return False, "DISPOSABLE"
    if kind == "personal" and approving != COMPANY_AND_PERSONAL:
        return False, "PERSONAL_MAIL"
    platform = platform_addresses(db)
    # A company domain of the platform organization stands for all its addresses; a personal address only for itself.
    if email in platform or (kind == "company" and domain in map(domain_of, platform)):
        return False, "PLATFORM_ORGANIZATION"
    if kind == "company":
        # One trial per company: the second colleague is invited by the first.
        same = func.lower(OnboardingRequest.email).like(f"%@{domain}")
        already = "COMPANY_ALREADY_HAS_A_REQUEST"
    else:
        # One request per personal address: a provider's other users are other people.
        same = func.lower(func.trim(OnboardingRequest.email)) == email
        already = "ADDRESS_ALREADY_HAS_A_REQUEST"
    if db.query(OnboardingRequest.id).filter(OnboardingRequest.id != row.id, same).first() is not None:
        return False, already
    sent = row.created_at or now or datetime.now(timezone.utc)
    start = datetime.combine(sent.astimezone(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    # The earlier requests of the same kind (company or personal) on the request's UTC day, approved or not: counting
    # only approvals let made-up domains use up the cap unseen (SEC-07). Earlier ones only, so sign-up and the approval
    # after it give the same answer. Each kind has its own cap and never uses up the other's.
    earlier = (
        db.query(OnboardingRequest.email)
        .filter(
            OnboardingRequest.id != row.id,
            OnboardingRequest.created_at >= start,
            OnboardingRequest.created_at < row.created_at,
        )
        .all()
    )
    counted = sum(1 for (other,) in earlier if mail_kind(domain_of(other)) == kind)
    if kind == "company" and counted >= daily_max():
        return False, "DAILY_CAP"
    if kind == "personal" and counted >= personal_daily_max():
        return False, "PERSONAL_DAILY_CAP"
    if domain_check() == "dns" and not domain_resolves(domain):
        return False, "DOMAIN_NOT_FOUND"
    return True, "COMPANY_DOMAIN" if kind == "company" else "PERSONAL_ADDRESS"


def _approver(db: Session, create: bool = True, personal: bool = False):
    """The platform's automatic-approval account for company emails, or with ``personal`` for personal ones (neither
    can sign in), created once in the platform organization."""
    from backend.app.db.models.foundation import AuthUser
    from backend.app.support_access import platform_tenant_id
    from backend.app.trial.service import _hash

    tenant_id = platform_tenant_id(db)
    if tenant_id is None:
        return None
    username, name = (
        (PERSONAL_APPROVER_USERNAME, PERSONAL_APPROVER_NAME) if personal else (APPROVER_USERNAME, APPROVER_NAME)
    )
    user = db.query(AuthUser).filter(AuthUser.username == username).first()
    if user is not None or not create:
        return user
    now = datetime.now(timezone.utc)
    user = AuthUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        username=username,
        display_name=name,
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
        approver = _approver(db, personal=why == "PERSONAL_ADDRESS")
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
