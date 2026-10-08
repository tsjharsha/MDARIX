"""The shared context of the story: constants, pure time helpers, the Story and how it is built. (Part of the demo golden path; see __init__.py.)"""

from __future__ import annotations
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_
from sqlalchemy.orm import Session
from backend.app import demo_story as story


logger = logging.getLogger("mdarix.demo_workspace")

SEED_ACTOR = "system:demo-workspace"
SEEDED_ACTION = "DEMO_SEEDED"
# The team members the golden path needs, by role code (backend/app/demo_workspace.py DEMO_TEAM).
NEEDED_ROLES = ("TRIAGE_LEAD", "INVESTIGATOR", "RISK_REVIEWER", "REGULATORY_REVIEWER", "REVIEWER", "APPROVER")


class GoldenPathSkipped(RuntimeError):
    """The workspace cannot hold the golden path (its story predates it, or a team member is missing)."""


# ----------------------------------------------------------------------------------------------- pure helpers


def story_moment(now: datetime, days: int, minutes: int = 0) -> datetime:
    """``days`` before ``now``, ``minutes`` later in that day (keeps the order of steps taken on the same day)."""
    return now - timedelta(days=days) + timedelta(minutes=minutes)


def retimed(value: datetime | None, wall: datetime, moment: datetime) -> datetime | None:
    """A timestamp written by a helper that reads the wall clock during this run (``value >= wall``) moves to the
    story ``moment``; anything else is kept."""
    if value is None or value < wall:
        return value
    return moment


def scope_split(complaint_ids: list, excluded_index: int, late_index: int) -> tuple[list, list]:
    """Scope version 2 of the golden case: every complaint before the late one is included except the excluded one.
    Returns ``(included, excluded)`` as lists of ids, in story order."""
    included = [item for index, item in enumerate(complaint_ids[:late_index]) if index != excluded_index]
    return included, [complaint_ids[excluded_index]]


# ---------------------------------------------------------------------------------------------- the context


@dataclass
class Story:
    """What every step of the golden path shares: the bound session, the tenant, the story's today, the wall-clock
    start of this run, the case and its records, the team (``Person`` per role code) and what was made."""

    db: Session
    tenant_id: uuid.UUID
    now: datetime
    wall: datetime
    case: object
    product: object
    version: object
    complaints: list
    evidence: dict
    users: dict
    team: dict
    made: dict = field(default_factory=dict)

    def at(self, days: int, minutes: int = 0) -> datetime:
        return story_moment(self.now, days, minutes)

    def user(self, role: str):
        return self.users[role]

    def person(self, role: str):
        return self.team[role]

    def settle(self, moment: datetime) -> None:
        """Re-date to ``moment`` what the helpers stamped with the wall clock since the run started (workflow tasks
        and their history, signals with their history and complaint links). Audit events are never changed."""
        from backend.app.db.models.decision_outcomes import ImpactAssessment
        from backend.app.db.models.signals import Signal, SignalComplaint, SignalEvent
        from backend.app.db.models.workflow import WorkflowTask, WorkflowTaskEvent

        self.db.flush()
        for model, names in (
            (ImpactAssessment, ("created_at", "updated_at")),
            (WorkflowTask, ("created_at", "updated_at", "accepted_at", "completed_at")),
            (WorkflowTaskEvent, ("created_at",)),
            (Signal, ("created_at", "updated_at")),
            (SignalEvent, ("created_at",)),
            (SignalComplaint, ("added_at",)),
        ):
            columns = [getattr(model, name) for name in names]
            rows = (
                self.db.query(model)
                .filter(model.tenant_id == self.tenant_id, or_(*(column >= self.wall for column in columns)))
                .all()
            )
            for row in rows:
                for name in names:
                    setattr(row, name, retimed(getattr(row, name), self.wall, moment))
        self.db.flush()


def _person(db: Session, user):
    """The team member as the evidence and intelligence services see a signed-in person (roles, permissions)."""
    from backend.app.evidence_workflow.people import Person
    from backend.app.workflow.people import permissions_of, roles_of

    return Person(
        user_id=str(user.id),
        user_uuid=user.id,
        tenant_id=user.tenant_id,
        permissions=permissions_of(db, user),
        roles=roles_of(db, user),
        account_role=user.role,
    )


def story_today(opened_at: datetime, opened_days: int) -> datetime:
    """The day the story was loaded, read back from the golden case (stamped ``opened_days`` before it)."""
    return opened_at + timedelta(days=opened_days)


def _opened_days() -> int:
    return next(item[4] for item in story.INVESTIGATIONS if item[0] == story.GOLDEN_CASE)


def _context(db: Session, tenant_id: uuid.UUID, now: datetime | None) -> Story:
    from backend.app.db.models.foundation import AuthUser, Complaint, Evidence, Investigation, Product, ProductVersion
    from backend.app.demo_workspace import DEMO_TEAM
    from backend.app.role_codes import role_code

    case = (
        db.query(Investigation)
        .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == story.GOLDEN_CASE)
        .with_for_update()
        .first()
    )
    if case is None:
        raise GoldenPathSkipped(f"{story.GOLDEN_CASE} is not in this workspace; reset the demo to load the story")
    # Without a given today (a workspace loaded earlier), the story is dated from the day it was loaded.
    now = now or story_today(case.created_at, _opened_days())
    product = db.query(Product).filter(Product.tenant_id == tenant_id, Product.id == case.product_id).one()
    identifiers = [
        f"ACD-CMP-{index:04d}" for index, record in enumerate(story.COMPLAINTS, 1) if record[0] == story.GOLDEN_PRODUCT
    ]
    found = {
        row.complaint_identifier: row
        for row in db.query(Complaint).filter(
            Complaint.tenant_id == tenant_id, Complaint.complaint_identifier.in_(identifiers)
        )
    }
    codes = [code for code, *_ in story.EVIDENCE[story.GOLDEN_CASE]]
    evidence = {
        row.evidence_identifier: row
        for row in db.query(Evidence).filter(Evidence.tenant_id == tenant_id, Evidence.evidence_identifier.in_(codes))
    }
    if len(found) != len(identifiers) or len(evidence) != len(codes):
        raise GoldenPathSkipped("The golden case's complaints or evidence are missing; reset the demo")
    # The version the complaints (and so the signal) are about.
    version = (
        db.query(ProductVersion)
        .filter(
            ProductVersion.tenant_id == tenant_id,
            ProductVersion.id == found[identifiers[0]].product_version_id,
        )
        .one()
    )
    emails = [email for _, email, _ in DEMO_TEAM]
    users = {}
    for user in db.query(AuthUser).filter(
        AuthUser.tenant_id == tenant_id, AuthUser.username.in_(emails), AuthUser.status == "ACTIVE"
    ):
        users.setdefault(role_code(user.role), user)
    missing = [role for role in NEEDED_ROLES if role not in users]
    if missing:
        raise GoldenPathSkipped(f"The demo team has nobody for {', '.join(missing)}; run setup first")
    return Story(
        db=db,
        tenant_id=tenant_id,
        now=now,
        wall=datetime.now(timezone.utc),
        case=case,
        product=product,
        version=version,
        complaints=[found[identifier] for identifier in identifiers],
        evidence=evidence,
        users=users,
        team={role: _person(db, users[role]) for role in NEEDED_ROLES},
    )
