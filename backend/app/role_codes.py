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
    {"VIEWER", "INVESTIGATOR", "REVIEWER", "APPROVER", "LEADER", PLATFORM_ADMIN, CUSTOMER_ADMIN}
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


def is_customer_admin_role(role: str | None) -> bool:
    return role_code(role) == CUSTOMER_ADMIN


def is_administrator_role(role: str | None) -> bool:
    return role_code(role) in {PLATFORM_ADMIN, CUSTOMER_ADMIN}
