"""The flagship story (W1, WHIF demo): one investigation, one product, one version, in seven steps.

SAMPLE-INV-001, "Why did pressure-alarm complaints rise after OrbitCare 300 Rev B?", from the signal to the action:

1. signal: the person opened the OrbitCare 300 trend from the story (a mark);
2. product: the person opened Rev B's Product 360 from the story (a mark);
3. evidence: the person opened the case's evidence overview from the story (a mark);
4. ai: a person reviewed one of the case's AI proposals (an observation or the saved result: an ``ai_output_reviews``
   row; or an AI hypothesis a person judged). Seeding never ticks it: the sample's proposals are unreviewed;
5. brief: a person accepted the sample author's brief for decision (APPROVED_FOR_DECISION);
6. decision: a signed BRIEF decision on the case (its audit event says whether an authenticator code was checked);
7. action: an effectiveness check is planned on a CAPA of the case (SAMPLE-CAPA-02 by default). The tick stays on
   the planned check (W1 spec); the card then reads planned -> synthetic follow-up (W1d) -> signed result.

Ticks are read from saved records, as one_story.py reads its ten steps, in order (``one_story.in_order``); the marks
(steps 1 to 3) are kept with the ten-step story's marks, under the run "flagship" and the investigation's id, so a
restart (a new investigation id) starts them again. The product's version comes from the case's complaints: the
version a complaint names, else its lot's; a date never picks one (PV-1). None when the sample is removed.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

RUN = "flagship"
CASE = "SAMPLE-INV-001"
CAPA = "SAMPLE-CAPA-02"
CHANGE = "SAMPLE-CHG-014"
BRANCH = "SAMPLE-RV-06"
STEPS = (
    ("signal", "Signal: pressure alarms are rising"),
    ("product", "Product reality"),
    ("evidence", "What is known and what is not"),
    ("ai", "AI investigation"),
    ("brief", "Investigation Brief"),
    ("decision", "Human decision"),
    ("action", "Action and impact"),
)
MARKS = ("signal", "product", "evidence")
# G-06: the OrbitCare 300 Rev B pressure-alarm rise as the trend check computes it on the sample (its last 30 days
# against the expected count). The sample's texts that state the rise use this one number; a test checks it against
# the trend check, so a change to the sample data that moves the trend fails until the texts follow.
SIGNAL_RATIO = 9.3
SIGNAL_TEXT = f"{SIGNAL_RATIO:.1f}× the earlier average in the trend check"
# The short name the story bar reads ("OrbitCare 300 · Rev B"); another product shows its own name.
SHORT_NAMES = {"SAMPLE-ORBIT-300": "OrbitCare 300"}
NO_PROPOSAL = "No AI proposal on this case yet"
TOO_EARLY = "Did it work? Too early: only a signed effectiveness check says an action worked"


def version_state(pairs) -> tuple[object | None, str, int]:
    """(the version most of the case's complaints are on, KNOWN|MIXED|UNVERIFIED, complaints with no version) from
    each complaint's (own version, its lot's version). The complaint's own version first, else its lot's; with neither
    the complaint is unverified: a release date never picks a version. Pure."""
    found = [own or lot for own, lot in pairs]
    known = [value for value in found if value]
    unverified = len(found) - len(known)
    if not known:
        return None, "UNVERIFIED", unverified
    top = Counter(known).most_common(1)[0][0]
    return top, "KNOWN" if len(set(known)) == 1 and not unverified else "MIXED", unverified


def find_case(data: Session, tenant_id):
    from backend.app.db.models.foundation import Investigation
    from backend.app.trial.sample_data import SAMPLE_SOURCE

    return (
        data.query(Investigation)
        .filter(
            Investigation.tenant_id == tenant_id,
            Investigation.investigation_identifier == CASE,
            Investigation.source_system == SAMPLE_SOURCE,
        )
        .first()
    )


def _ai(data: Session, tenant_id, case_id) -> tuple[int, bool]:
    """(AI results saved on the case, whether a person reviewed one of them or of their observations, or judged an
    AI hypothesis)."""
    from backend.app.db.models.ai_records import AiOutputReview
    from backend.app.db.models.evidence_intelligence import EvidenceObservation
    from backend.app.db.models.foundation import AIExecution, Hypothesis

    on_case = (AIExecution.tenant_id == tenant_id, AIExecution.investigation_id == case_id)
    proposals = data.query(func.count(AIExecution.id)).filter(*on_case).scalar() or 0
    if not proposals:
        return 0, False
    executions = select(AIExecution.id).where(*on_case)
    observations = select(cast(EvidenceObservation.id, String)).where(
        EvidenceObservation.tenant_id == tenant_id, EvidenceObservation.ai_execution_id.in_(executions)
    )
    reviewed = (
        data.query(AiOutputReview.id)
        .filter(
            AiOutputReview.tenant_id == tenant_id,
            or_(
                AiOutputReview.subject_id.in_(select(cast(AIExecution.id, String)).where(*on_case)),
                AiOutputReview.subject_id.in_(observations),
            ),
        )
        .first()
        is not None
    )
    judged = (
        reviewed
        or data.query(Hypothesis.id)
        .filter(
            Hypothesis.tenant_id == tenant_id,
            Hypothesis.investigation_id == case_id,
            func.lower(Hypothesis.origin) == "ai",
            Hypothesis.human_status.isnot(None),
        )
        .first()
        is not None
    )
    return proposals, judged


def _decision(data: Session, control_db: Session, tenant_id, case_id) -> tuple[bool, bool | None]:
    """(a signed BRIEF decision on the case, whether its signing checked an authenticator code; None: not recorded)."""
    from backend.app.db.models.foundation import AuditEvent, Decision

    decision = (
        data.query(Decision.id)
        .filter(
            Decision.tenant_id == tenant_id,
            Decision.investigation_id == case_id,
            Decision.decision_kind == "BRIEF",
            Decision.decision_status == "SIGNED",
        )
        .order_by(Decision.decided_at.desc())
        .first()
    )
    if decision is None:
        return False, None
    details = (
        control_db.query(AuditEvent.details)
        .filter(
            AuditEvent.tenant_id == tenant_id,
            AuditEvent.action == "CASE_DECISION_SIGNED",
            AuditEvent.entity_id == decision.id,
        )
        .scalar()
    )
    return True, (details or {}).get("mfa_verified")


def run_progress(data: Session, control_db: Session, tenant_id, request) -> dict | None:
    from backend.app.db.models.capa_effectiveness import CapaEffectivenessCheck
    from backend.app.db.models.foundation import (
        Capa,
        Change,
        Complaint,
        InvestigationComplaint,
        LotBatch,
        Product,
        ProductVersion,
    )
    from backend.app.db.models.reviews import DecisionBriefVersion
    from backend.app.trial import one_story
    from backend.app.trial.sample_data import SAMPLE_SOURCE

    case = find_case(data, tenant_id)
    if case is None:
        return None
    product = data.query(Product.product_identifier, Product.name).filter(
        Product.tenant_id == tenant_id, Product.id == case.product_id
    ).one_or_none() or (None, None)
    pairs = (
        data.query(Complaint.product_version_id, LotBatch.product_version_id)
        .join(
            InvestigationComplaint,
            (InvestigationComplaint.tenant_id == Complaint.tenant_id)
            & (InvestigationComplaint.complaint_id == Complaint.id),
        )
        .outerjoin(LotBatch, (LotBatch.tenant_id == Complaint.tenant_id) & (LotBatch.id == Complaint.lot_batch_id))
        .filter(InvestigationComplaint.tenant_id == tenant_id, InvestigationComplaint.investigation_id == case.id)
        .all()
    )
    version_id, state, unverified = version_state(pairs)
    version = (
        data.query(ProductVersion.version_identifier)
        .filter(ProductVersion.tenant_id == tenant_id, ProductVersion.id == version_id)
        .scalar()
        if version_id
        else None
    )
    change = (
        data.query(Change.change_identifier, Change.description)
        .filter(Change.tenant_id == tenant_id, Change.change_identifier == CHANGE)
        .first()
    )
    proposals, ai_done = _ai(data, tenant_id, case.id)
    approved = (
        data.query(DecisionBriefVersion.id)
        .filter(
            DecisionBriefVersion.tenant_id == tenant_id,
            DecisionBriefVersion.investigation_id == case.id,
            DecisionBriefVersion.status == "APPROVED_FOR_DECISION",
        )
        .first()
        is not None
    )
    signed, mfa = _decision(data, control_db, tenant_id, case.id)
    capas = (
        data.query(Capa.id, Capa.capa_identifier, Capa.title)
        .filter(Capa.tenant_id == tenant_id, Capa.investigation_id == case.id)
        .all()
    )
    checks = (
        data.query(CapaEffectivenessCheck.capa_id, CapaEffectivenessCheck.status, CapaEffectivenessCheck.signed_at)
        .filter(
            CapaEffectivenessCheck.tenant_id == tenant_id,
            CapaEffectivenessCheck.capa_id.in_([row.id for row in capas]),
        )
        .all()
        if capas
        else []
    )
    # D1: SAMPLE-CAPA-02, else the CAPA of the case that has a check, else any of its CAPAs.
    planned = {row.capa_id for row in checks}
    capa = next((row for row in capas if row.capa_identifier == CAPA), None) or next(
        (row for row in capas if row.id in planned), capas[0] if capas else None
    )
    signed_check = next((row for row in checks if capa is not None and row.capa_id == capa.id and row.signed_at), None)
    # W1d (D04): planned -> synthetic follow-up -> signed. The follow-up shows once the check is planned.
    from backend.app.trial import sample_follow_up

    follow_up = bool(capa is not None and capa.id in planned and sample_follow_up.has_record(data, tenant_id))
    branch = (
        data.query(Complaint.id)
        .filter(
            Complaint.tenant_id == tenant_id,
            Complaint.complaint_identifier == BRANCH,
            Complaint.source_system == SAMPLE_SOURCE,
        )
        .scalar()
    )
    marks = one_story.team_marks(request, RUN, case.id)
    raw = [
        *(bool(marks.get(step)) for step in MARKS),
        ai_done,
        approved or signed,
        signed,
        bool(planned),
    ]
    done, earlier = one_story.in_order(raw)
    current = next((index for index, value in enumerate(done) if value is False), len(done))
    notes = [
        None,
        None,
        None,
        NO_PROPOSAL if not proposals else None,
        None,
        ("Signed with password and authenticator code" if mfa else "Signed with password") if signed else None,
        TOO_EARLY if planned and signed_check is None else None,
    ]
    return {
        "run": RUN,
        "product": {
            "id": str(case.product_id),
            "ref": product[0],
            "name": product[1],
            "label": SHORT_NAMES.get(product[0] or "", product[1]),
            "version": version,
            "version_state": state,
            "unverified": unverified,
        },
        "investigation": {"id": str(case.id), "ref": CASE, "question": case.investigation_question},
        "change": {"ref": change[0], "description": change[1]} if change else None,
        "capa": (
            {
                "id": str(capa.id),
                "ref": capa.capa_identifier,
                "title": capa.title,
                "check_planned": capa.id in planned,
                "check_status": signed_check.status if signed_check is not None else None,
                "follow_up": follow_up,
            }
            if capa is not None
            else None
        ),
        "branch": {"complaint_id": str(branch), "ref": BRANCH} if branch else None,
        "ai_proposals": proposals,
        "mfa_verified": mfa,
        "steps": [
            {"key": key, "label": label, "done": value is True, "skipped": False, "earlier": early, "note": note}
            for (key, label), value, early, note in zip(STEPS, done, earlier, notes)
        ],
        "current": current,
        "finished": current == len(STEPS),
    }
