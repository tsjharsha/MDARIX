"""People behind tasks, read from the control database: who an account reference is, their name, their roles and
which of their roles grants a permission (recorded on every task change as the role the person acted under).

The role functions of backend/app/access/permissions.py (``roles_of_user``, ``permissions_for_roles``) are imported
when used, so this module loads even in a build that predates them.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.business_ids import as_uuid, wanted_ids
from backend.app.db.models.foundation import AuthUser
from backend.app.role_codes import is_platform_admin_role, role_code

logger = logging.getLogger("mdarix.workflow")


def find_user(control_db: Session, tenant_id, ref, *, active_only: bool = True) -> AuthUser | None:
    """The organization's account given by id or by sign-in name (a case's ``owner_ref``), else None."""
    text = str(ref or "").strip()
    if not text:
        return None
    key = as_uuid(text)
    clause = AuthUser.id == key if key is not None else func.lower(AuthUser.username) == text.lower()
    query = control_db.query(AuthUser).filter(AuthUser.tenant_id == as_uuid(tenant_id), clause)
    if active_only:
        query = query.filter(AuthUser.status == "ACTIVE")
    return query.first()


def display_name(user: AuthUser | None) -> str | None:
    if user is None:
        return None
    return (user.display_name or "").strip() or (user.username or "").strip() or None


def names_by_id(control_db: Session, tenant_id, refs: Iterable) -> dict[str, str]:
    """``{str(user id): name}`` for the organization's accounts among ``refs``, in one query."""
    ids = wanted_ids(refs)
    if not ids:
        return {}
    rows = control_db.query(AuthUser).filter(AuthUser.tenant_id == as_uuid(tenant_id), AuthUser.id.in_(list(ids)))
    return {str(user.id): display_name(user) for user in rows if display_name(user)}


def roles_of(control_db: Session, user: AuthUser | None) -> list[str]:
    """Every role the person holds (account role, active assignment and additional workflow roles), normalized."""
    if user is None:
        return []
    from backend.app.access.permissions import roles_of_user

    found: list[str] = []
    for item in roles_of_user(control_db, user) or ():
        code = role_code(getattr(item, "role_code", None) or getattr(item, "code", None) or item)
        if code and code not in found:
            found.append(code)
    return found


def permissions_of(control_db: Session, user: AuthUser | None) -> frozenset[str]:
    if user is None:
        return frozenset()
    from backend.app.access.permissions import permissions_for_roles

    return frozenset(permissions_for_roles(roles_of(control_db, user)) or ())


def role_granting(roles: Iterable[str], permission: str | None, fallback: str | None = None) -> str | None:
    """The first of ``roles`` that grants ``permission``, else ``fallback`` (the account role)."""
    from backend.app.access.permissions import permissions_for_roles

    if permission:
        for role in roles:
            if permission in (permissions_for_roles([role]) or ()):
                return role
    return (role_code(fallback) or None) if fallback else None


def acting_role(control_db: Session | None, tenant_id, user_id, permission: str | None) -> str | None:
    """The role a person acted under for ``permission`` (else their account role); None when it cannot be told.
    Never raises: it only labels history rows."""
    if control_db is None:
        return None
    try:
        user = find_user(control_db, tenant_id, user_id, active_only=False)
        if user is None:
            return None
        return role_granting(roles_of(control_db, user), permission, user.role)
    except Exception:
        logger.warning("The acting role of %s could not be determined", user_id, exc_info=True)
        return None


def may_hold_tasks(control_db: Session, user: AuthUser, permission: str) -> bool:
    """An active colleague (never MDARIX staff) whose roles grant ``permission``."""
    if user is None or str(user.status or "").upper() != "ACTIVE" or is_platform_admin_role(user.role):
        return False
    return permission in permissions_of(control_db, user)
