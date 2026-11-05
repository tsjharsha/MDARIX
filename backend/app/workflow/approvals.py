"""Who approves a waiting report snapshot or decision guide version, told before anyone types a password, and the
approver's task in My Work (J13, 0.10.64).

- ``approvers``: the active colleagues who may approve (regulatory review or approval rights, never an administrator
  or MDARIX staff), leaving out the people separation of duties stops (the preparer, the signer, the editor);
- ``standing``: what the screen shows a person: the approve form, the trial's practice note when separation of duties
  stops a person working alone in a trial (T-B8: the trial records "same person"; a pilot always enforces it), or "A
  colleague with regulatory approval rights approves this", with their names, in place of the form;
- ``ask`` gives each colleague who may approve a REGULATORY_REVIEW task (the existing type; it is due at the end of the
  next working day, or the report's deadline when sooner, so the reminders and the bell carry it); working alone in a
  trial, the person who asked gets it; in a pilot with nobody to ask, the regulatory reviewers' queue does. ``finish``
  ends them when the item is approved, withdrawn, returned to draft or replaced.

Nothing here commits.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.access.permissions import REGULATORY_APPROVE, REGULATORY_REVIEW
from backend.app.role_codes import is_administrator_role, role_label

PERMISSIONS = (REGULATORY_REVIEW, REGULATORY_APPROVE)
RIGHTS = "regulatory approval rights"
TASK_TYPE = "REGULATORY_REVIEW"
NO_RIGHTS = "Your role does not approve this"
# Said at the button wherever a person working alone in a trial approves their own practice work (0.10.71, A6).
PRACTICE_APPROVAL = "Practice approval: in a pilot a colleague approves this."
NOBODY = (
    "nobody else in your organization holds them yet: an administrator gives a colleague the Regulatory Reviewer, "
    "Authorized Decision Maker or Leader role"
)


def approvers(control_db: Session, tenant_id, excluded) -> list[tuple[str, str]]:
    """``[(user id, name)]`` of the active colleagues who may approve, outside ``excluded``, by name."""
    return holders(control_db, tenant_id, PERMISSIONS, excluded)


def colleagues(control_db: Session, tenant_id) -> list[tuple[str, str, frozenset[str]]]:
    """``[(user id, name, permissions)]`` of the active colleagues (never an administrator), by name: read once, for a
    screen that asks who may sign several steps (0.10.88: the complaint page asked it seven times per person)."""
    from backend.app.db.models.foundation import AuthUser
    from backend.app.workflow.people import display_name, permissions_of

    return [
        (str(user.id), display_name(user) or "A colleague", permissions_of(control_db, user))
        for user in control_db.query(AuthUser)
        .filter(AuthUser.tenant_id == tenant_id, AuthUser.status == "ACTIVE")
        .order_by(AuthUser.display_name)
        .limit(500)
        if not is_administrator_role(user.role)
    ]


def holders(control_db: Session, tenant_id, permissions, excluded=(), everyone=None) -> list[tuple[str, str]]:
    """``[(user id, name)]`` of the active colleagues (never an administrator) who hold any of ``permissions``,
    outside ``excluded``, by name: who may sign a step, shown before the work starts (0.10.68, 7.8). ``everyone`` is
    ``colleagues(...)`` when the caller already read it."""
    skip = {str(ref) for ref in excluded if ref}
    return [
        (ref, name)
        for ref, name, granted in (everyone if everyone is not None else colleagues(control_db, tenant_id))
        if ref not in skip and any(permission in granted for permission in permissions)
    ]


def standing(problem: str | None, separation: bool, others: list[str], trial: bool, role: str | None, noun: str):
    """What the approval screen shows this person, before any password: ``may_approve`` (the form), ``same_person``
    (the trial's practice approval of one's own work: only in a trial, only when separation of duties is the sole
    reason and no colleague may approve), the colleagues who may (``approvers``) and the ``message``."""
    same_person = bool(problem) and separation and trial and not others
    if problem is None:
        message = None
    elif same_person:
        message = (
            f"In a pilot a colleague approves this; in the trial you may approve your own practice {noun} as "
            f"{role_label(role) or 'yourself'}."
        )
    elif others:
        message = f"{problem}. A colleague with {RIGHTS} approves this: {', '.join(others)}."
    else:
        message = f"{problem}. A colleague with {RIGHTS} approves this; {NOBODY}."
    return {
        "may_approve": problem is None or same_person,
        "same_person": same_person,
        "approvers": others,
        "message": message,
    }


def ask(
    db: Session,
    control_db: Session,
    tenant_id,
    *,
    source_type: str,
    source_id,
    title: str,
    due_at: datetime | None,
    excluded,
    requester: str,
    trial: bool,
    details: dict,
) -> int:
    """The approver's task for each colleague who may approve (see the module docstring). Returns how many."""
    from backend.app.workflow.tasks import create_task

    people = [ref for ref, _ in approvers(control_db, tenant_id, excluded)]
    if not people and trial:
        people = [requester]  # working alone in the trial: their own practice approval waits in their My Work
    common = dict(
        task_type=TASK_TYPE,
        title=title,
        source_type=source_type,
        source_id=source_id,
        due_at=due_at,
        created_by=requester,
        details=details,
    )
    for person in people:
        create_task(db, tenant_id, assigned_user_id=person, **common)
    if not people:
        create_task(db, tenant_id, **common)  # the regulatory reviewers' queue
    return max(len(people), 1)


def finish(db: Session, tenant_id, *, source_type: str, source_id, outcome: str, actor, approved: bool) -> None:
    """End the approval tasks of an item: completed when it is approved, cancelled otherwise."""
    from backend.app.workflow.tasks import cancel_tasks, complete_tasks

    end = complete_tasks if approved else cancel_tasks
    end(
        db,
        tenant_id,
        source_type=source_type,
        source_id=source_id,
        task_types=[TASK_TYPE],
        outcome=outcome,
        actor_ref=actor,
    )
