"""Canonical role codes shared by authentication, authorization and persistence.

Only the two administrator roles are canonicalized here. Custom tenant roles
retain their configured spelling; authorization compares their normalized code.
"""

from __future__ import annotations

PLATFORM_ADMIN = "PLATFORM_ADMIN"
CUSTOMER_ADMIN = "CUSTOMER_ADMIN"

PLATFORM_ADMIN_ALIASES = frozenset({PLATFORM_ADMIN, "MDARIX_ADMINISTRATOR", "ADMINISTRATOR", "ADMIN"})
CUSTOMER_ADMIN_ALIASES = frozenset({CUSTOMER_ADMIN, "CUSTOMER_ADMINISTRATOR"})
CANONICAL_SYSTEM_ROLES = frozenset(
    {
        "VIEWER",
        "SERVICE_DESK",
        "TRIAGE_LEAD",
        "INVESTIGATOR",
        "RISK_REVIEWER",
        "REGULATORY_REVIEWER",
        "REVIEWER",
        "APPROVER",
        "LEADER",
        PLATFORM_ADMIN,
        CUSTOMER_ADMIN,
    }
)

# What people see for each standard role (the codes above never change). UX1: one list, the same names as the
# workspace personas (access_control/personas.py) on the trial's Team, the invite form and "Viewing as".
ROLE_LABELS: dict[str, str] = {
    "SERVICE_DESK": "Service Desk",
    "TRIAGE_LEAD": "Complaint Handler",
    "INVESTIGATOR": "Investigator",
    "RISK_REVIEWER": "Risk Reviewer",
    "REGULATORY_REVIEWER": "Regulatory Reviewer",
    "REVIEWER": "Quality Reviewer",
    "APPROVER": "Decision Maker",
    "LEADER": "Quality Leader",
    "VIEWER": "Executive (view only)",
    CUSTOMER_ADMIN: "Customer Administrator",
    PLATFORM_ADMIN: "Platform Administrator",
}

# Roles a person may hold in addition to their account role (never an administrator role), in workflow order.
WORKFLOW_ROLES = (
    "TRIAGE_LEAD",
    "INVESTIGATOR",
    "RISK_REVIEWER",
    "REGULATORY_REVIEWER",
    "REVIEWER",
    "APPROVER",
    "LEADER",
)


def role_code(role: str | None) -> str:
    """Normalize a role for comparison and resolve supported admin aliases."""

    value = "_".join(str(role or "").strip().upper().replace("-", " ").split())
    if value in PLATFORM_ADMIN_ALIASES:
        return PLATFORM_ADMIN
    if value in CUSTOMER_ADMIN_ALIASES:
        return CUSTOMER_ADMIN
    return value


def canonical_stored_role(role: str | None) -> str:
    """Canonicalize administrator values without renaming custom tenant roles."""

    original = str(role or "").strip()
    normalized = role_code(original)
    if normalized in CANONICAL_SYSTEM_ROLES:
        return normalized
    return original


def is_platform_admin_role(role: str | None) -> bool:
    return role_code(role) == PLATFORM_ADMIN


# The role spellings the platform-administration route guard accepts. Unlike PLATFORM_ADMIN_ALIASES (still used to
# canonicalize what is stored and to refuse every spelling of a platform role in user administration), the generic
# "ADMIN" and "ADMINISTRATOR" do not open platform administration.
PLATFORM_ADMIN_GUARD_CODES = frozenset({PLATFORM_ADMIN, "MDARIX_ADMINISTRATOR"})


def is_strict_platform_admin_role(role: str | None) -> bool:
    """True only for PLATFORM_ADMIN (and MDARIX_ADMINISTRATOR), without resolving the generic administrator aliases."""
    value = "_".join(str(role or "").strip().upper().replace("-", " ").split())
    return value in PLATFORM_ADMIN_GUARD_CODES


def is_customer_admin_role(role: str | None) -> bool:
    return role_code(role) == CUSTOMER_ADMIN


def is_administrator_role(role: str | None) -> bool:
    return role_code(role) in {PLATFORM_ADMIN, CUSTOMER_ADMIN}


def role_label(role: str | None) -> str:
    """The name people see for a role: the standard label, else the role as the organization wrote it."""
    return ROLE_LABELS.get(role_code(role)) or str(role or "").strip()


def is_administrator_name(value: str | None) -> bool:
    """True for an administrator role's code or any spelling of it ("Admin") and for the label people see
    ("Platform Administrator"). A custom role never carries one of these (R11): administrator roles are given on the
    account only."""
    labels = {role_code(ROLE_LABELS[code]) for code in (PLATFORM_ADMIN, CUSTOMER_ADMIN)}
    return is_administrator_role(value) or role_code(value) in labels
