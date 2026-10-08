"""The evidence review of the case. (Part of the demo golden path; see __init__.py.)"""

from __future__ import annotations
from datetime import datetime

from backend.app.demo_golden_path.context import Story


# --------------------------------------------------------------------------------------------- evidence review

# (evidence, review status, relationship, days ago, reason, limitation)
EVIDENCE_REVIEWS = (
    ("ACD-EV-4011", "ACCEPTED", "SUPPORTING", 58, None, None),
    ("ACD-EV-4014", "ACCEPTED", "CONTRADICTING", 56, None, None),
    (
        "ACD-EV-4015",
        "REJECTED",
        "UNRELATED",
        38,
        "Hearsay without dates, lots or temperatures; it cannot be traced to any complaint or cassette lot.",
        None,
    ),
    ("ACD-EV-4012", "ACCEPTED", "SUPPORTING", 32, None, None),
    (
        "ACD-EV-4013",
        "ACCEPTED_WITH_LIMITATION",
        "SUPPORTING",
        29,
        None,
        "Only two returned cassettes were tested; one reproduced the alarm.",
    ),
)


def _ctx(person=None):
    """What the endpoint helpers read from a request: the signed-in person's id and the correlation id (none for
    the seeding)."""
    from types import SimpleNamespace

    return SimpleNamespace(correlation_id=None, user_id=person.user_id if person is not None else None)


def review_evidence(
    s: Story, code: str, status: str, relationship: str, moment: datetime, *, reason=None, limitation=None
):
    """Ines's review of one piece of the case's evidence (link, history row, EVIDENCE_REVIEWED), as
    ``POST /api/v1/investigations/{id}/evidence/{evidence_id}/review`` writes it."""
    from backend.app.access.permissions import EVIDENCE_REVIEW
    from backend.app.db.models.foundation import InvestigationEvidence
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.evidence_workflow.inventory import review_event
    from backend.app.evidence_workflow.rules import review_problem

    problem = review_problem(status, relationship, reason, limitation)
    if problem:
        raise ValueError(f"{code}: {problem}")
    ines = s.person("INVESTIGATOR")
    ev = s.evidence[code]
    link = (
        s.db.query(InvestigationEvidence)
        .filter(
            InvestigationEvidence.tenant_id == s.tenant_id,
            InvestigationEvidence.investigation_id == s.case.id,
            InvestigationEvidence.evidence_id == ev.id,
        )
        .one()
    )
    link.created_at = min(s.case.opened_at, moment)
    before = {
        "review_status": link.review_status,
        "relationship": link.relationship,
        "review_reason": link.review_reason,
        "limitation": link.limitation,
    }
    link.review_status = status
    link.relationship = relationship
    link.review_reason = reason
    link.limitation = limitation
    link.reviewed_by = ines.user_id
    link.reviewed_at = moment
    review_event(
        s.db,
        tenant_id=s.tenant_id,
        case_id=s.case.id,
        evidence_id=ev.id,
        event_type="REVIEWED",
        actor=ines,
        permission=EVIDENCE_REVIEW,
        from_status=before["review_status"],
        to_status=status,
        from_relationship=before["relationship"],
        to_relationship=relationship,
        reason=reason,
        details={"limitation": limitation} if limitation else None,
        now=moment,
    )
    s.db.add(
        make_audit_event(
            tenant_id=s.tenant_id,
            actor_ref=ines.user_id,
            action="EVIDENCE_REVIEWED",
            entity_type="InvestigationEvidence",
            entity_id=link.id,
            reason=reason,
            old_values=before,
            new_values={
                "review_status": status,
                "relationship": relationship,
                "review_reason": reason,
                "limitation": limitation,
            },
            details={
                "investigation_id": str(s.case.id),
                "evidence_id": str(ev.id),
                "actor_role": ines.role_for(EVIDENCE_REVIEW),
            },
            created_at=moment,
        )
    )
    s.db.flush()
    return link


def review_case_evidence(s: Story) -> None:
    for code, status, relationship, days, reason, limitation in EVIDENCE_REVIEWS:
        review_evidence(s, code, status, relationship, s.at(days), reason=reason, limitation=limitation)
