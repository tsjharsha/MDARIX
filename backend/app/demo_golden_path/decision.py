"""The signed decision, the CAPA it calls for and the evidence that arrives afterwards. (Part of the demo golden path; see __init__.py.)"""

from __future__ import annotations
import uuid
from datetime import datetime, timedelta

from backend.app.demo_golden_path.context import SEEDED_ACTION, SEED_ACTOR, Story
from backend.app.demo_golden_path.evidence import _ctx


# --------------------------------------------------------------------------------------------- the decision

DECISION_RATIONALE = (
    "The evidence supports a membrane above the drawing tolerance on cassettes from tool T-4 as the cause of the flow "
    "interruptions; use error is retired. Risk and regulatory reviews are complete. The Rev 1 limitation is accepted."
)
DECISION_CONDITIONS = (
    "Cassette lots C-301 to C-303 stay on hold until the corrected incoming inspection releases them, and tool T-4 "
    "cassettes are verified for flow continuity before release."
)
CAPA_TITLE = "Correct incoming inspection of cassette membranes and rework moulding tool T-4"


def sign_decision(s: Story, brief, moment: datetime):
    """Day 6: Ana signs ACCEPT_WITH_CONDITIONS on the approved brief with a CAPA_REQUIRED follow-up. The decision,
    its context snapshot, the follow-up with its task, the case and task changes and the signature are written as
    ``POST .../decision/sign`` writes them, with the signing code's own material, fingerprint, signature hash and
    snapshot hash, so verification reports VALID. No password is checked (seeding is a system action): the signature
    is audited as DEMO_SEEDED, never as CASE_DECISION_SIGNED."""
    from backend.app import governance_router as governance
    from backend.app.case_workflow import states
    from backend.app.db.models.decision_outcomes import DecisionFollowUp
    from backend.app.db.models.foundation import Decision, SignedApprovalRecord, Tenant
    from backend.app.db.models.stage3 import ContextSnapshot
    from backend.app.decision_brief import router as brief_api
    from backend.app.decision_brief import rules as brief_rules
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.human_decision import rules, service
    from backend.app.role_codes import role_code
    from backend.app.workflow import tasks as task_service

    case = s.case
    ana = s.person("APPROVER")
    problem = rules.brief_problem(
        status=brief.status,
        stored_hash=brief.content_hash,
        sent_hash=brief.content_hash,
        recomputed_hash=brief_rules.content_hash(brief.content, brief.narrative),
    )
    if problem:
        raise ValueError(f"The golden brief cannot be signed: {problem[1]}")
    if service.current_decision(s.db, case) is not None or not rules.state_allows(states.case_state(case), False):
        raise ValueError("The golden case is not waiting for its first decision")
    tenant = s.db.query(Tenant).filter(Tenant.id == s.tenant_id).one()
    if not governance.entitled(s.db, tenant):
        raise ValueError("The demo plan does not include controlled signatures")
    denial, signer_role = governance.approval_check(
        s.db, s.tenant_id, ana.roles or [s.user("APPROVER").role], service.approval_subject(brief), ana.user_id
    )
    if denial:
        raise ValueError(f"The demo approver may not sign: {denial[1]}")
    if rules.is_author(ana.user_id, service.brief_author_refs(s.db, brief)):
        raise ValueError("The demo approver wrote the brief")

    ines = s.user("INVESTIGATOR")
    planned = [
        {
            "action_type": "CAPA_REQUIRED",
            "title": CAPA_TITLE,
            "assignee_user_id": ines.id,
            "assigned_role": None,
            "due_at": moment + timedelta(days=rules.FOLLOW_UP_DUE_DAYS),
        }
    ]
    user_id = ana.user_id
    role = role_code(signer_role)[:60] or None
    decision_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    content = brief.content or {}
    residual = rules.residual_unknowns(content)
    evidence_hash = rules.evidence_set_hash(content)
    follow_up_actions = brief_rules.jsonable(planned)
    reviews = service.reviewers(s.db, s.db, brief)
    snapshot = brief_rules.jsonable(
        {
            "decision_id": decision_id,
            "brief": {
                "id": brief.id,
                "business_id": brief.business_id,
                "version": brief.version,
                "content_hash": brief.content_hash,
            },
            "content": content,
            "narrative": brief.narrative or {},
            "readiness": brief.readiness or {},
            "evidence_set_hash": evidence_hash,
            "scope_version": brief.scope_version,
            "reviews": reviews,
            "as_of": (content.get("context") or {}).get("as_of"),
            "decided_at": moment,
            "signer": {"id": user_id, "role": role},
            "outcome": rules.ACCEPT_WITH_CONDITIONS,
        }
    )
    snapshot_digest = rules.snapshot_hash(snapshot)
    decision = Decision(
        id=decision_id,
        tenant_id=s.tenant_id,
        investigation_id=case.id,
        decision_identifier=service.next_identifier(s.db, case),
        decision_type=rules.DECISION_TYPE,
        disposition=rules.ACCEPT_WITH_CONDITIONS,
        rationale=DECISION_RATIONALE,
        product_id=case.product_id,
        decision_status=rules.SIGNED,
        human_decision=rules.outcome_label(rules.ACCEPT_WITH_CONDITIONS),
        context_snapshot={"snapshot_id": str(snapshot_id), "snapshot_hash": snapshot_digest},
        updated_at=moment,
        decision_timestamp=moment,
        authorized_by_ref=user_id,
        created_at=moment,
        decision_kind=rules.DECISION_KIND,
        brief_version_id=brief.id,
        outcome=rules.ACCEPT_WITH_CONDITIONS,
        conditions=DECISION_CONDITIONS,
        follow_up_actions=follow_up_actions,
        residual_unknowns=brief_rules.jsonable(residual),
        decided_by_user_id=ana.user_uuid,
        decided_under_role=role,
        approval_authority_id=service.authority_id(s.db, s.tenant_id, signer_role),
        decided_at=moment,
        brief_content_hash=brief.content_hash,
        evidence_set_hash=evidence_hash,
        context_snapshot_id=snapshot_id,
        ai_execution_refs=rules.ai_execution_refs(content),
        supersedes_decision_id=None,
    )
    s.db.add(decision)
    s.db.flush()
    s.db.add(
        ContextSnapshot(
            id=snapshot_id,
            tenant_id=s.tenant_id,
            decision_id=decision_id,
            decision_version=brief.content_hash,
            snapshot=snapshot,
            created_by=user_id,
            created_at=moment,
        )
    )
    s.db.flush()
    follow_ups = []
    for item in planned:
        follow_up = DecisionFollowUp(
            id=uuid.uuid4(),
            tenant_id=s.tenant_id,
            decision_id=decision_id,
            investigation_id=case.id,
            action_type=item["action_type"],
            title=item["title"],
            assignee_user_id=item["assignee_user_id"],
            assigned_role=item["assigned_role"],
            due_at=item["due_at"],
            status="OPEN",
            created_by=user_id,
            created_at=moment,
            updated_at=moment,
        )
        s.db.add(follow_up)
        s.db.flush()
        task = task_service.create_task(
            s.db,
            s.tenant_id,
            task_type="FOLLOW_UP",
            title=item["title"],
            source_type=service.FOLLOW_UP_SOURCE,
            source_id=follow_up.id,
            investigation_id=case.id,
            assigned_user_id=item["assignee_user_id"],
            assigned_role=item["assigned_role"],
            priority=states.normalize_priority(case.priority),
            due_at=item["due_at"],
            created_by=user_id,
            actor_role=role,
            details={
                "follow_up_id": str(follow_up.id),
                "follow_up_business_id": follow_up.business_id,
                "action_type": item["action_type"],
                "decision_id": str(decision_id),
                "decision_business_id": decision.business_id,
            },
        )
        follow_up.task_id = task.id
        follow_ups.append(follow_up)
    brief_api._move_case(
        s.db,
        _ctx(ana),
        case,
        rules.case_state_after(rules.ACCEPT_WITH_CONDITIONS),
        f"Decision on brief version {brief.version}: {rules.outcome_label(rules.ACCEPT_WITH_CONDITIONS).lower()}",
        moment,
        {
            "brief_version_id": str(brief.id),
            "brief_version": brief.version,
            "decision_id": str(decision_id),
            "outcome": rules.ACCEPT_WITH_CONDITIONS,
        },
    )
    task_service.complete_tasks(
        s.db,
        s.tenant_id,
        source_type=service.BRIEF_SOURCE,
        source_id=brief.id,
        task_types=["DECISION_APPROVAL"],
        outcome=rules.ACCEPT_WITH_CONDITIONS,
        actor_ref=user_id,
        actor_role=role,
    )
    s.db.flush()

    version = brief.content_hash
    material = rules.signature_material(
        decision_id=decision_id,
        version=version,
        outcome=rules.ACCEPT_WITH_CONDITIONS,
        remarks=DECISION_RATIONALE,
        brief_version_id=brief.id,
        evidence_set_hash=evidence_hash,
        snapshot_hash=snapshot_digest,
        conditions=DECISION_CONDITIONS,
        follow_up_actions=follow_up_actions,
    )
    content_fingerprint = rules.fingerprint(material)
    record = SignedApprovalRecord(
        id=uuid.uuid4(),
        tenant_id=s.tenant_id,
        object_type="Decision",
        object_id=decision_id,
        object_version=version,
        decision_type=rules.DECISION_TYPE,
        decision=rules.SIGNATURE_CODES[rules.ACCEPT_WITH_CONDITIONS],
        remarks=DECISION_RATIONALE,
        signer_user_id=user_id,
        signer_role=signer_role,
        signature_meaning=rules.signature_meaning(brief.business_id, brief.version, rules.ACCEPT_WITH_CONDITIONS),
        content_fingerprint=content_fingerprint,
        signature_hash=rules.signature_hash(content_fingerprint, user_id, version),
        status="SIGNED",
        signed_at=moment,
        created_at=moment,
    )
    s.db.add(record)
    s.db.flush()
    s.db.add(
        make_audit_event(
            tenant_id=s.tenant_id,
            actor_ref=SEED_ACTOR,
            action=SEEDED_ACTION,
            entity_type="Decision",
            entity_id=decision_id,
            reason="Demo workspace golden path: a signed decision written by the seeding, no credentials checked",
            details={
                "seeded": "CASE_DECISION_SIGNED",
                # Not "credentials_…": the audit trail drops keys that look secret (enterprise_audit.SECRET_TERMS).
                "signer_reauthenticated": False,
                "signature_id": str(record.id),
                "signature_business_id": record.business_id,
                "fingerprint": content_fingerprint,
                "investigation_id": str(case.id),
                "brief_version_id": str(brief.id),
                "brief_version": brief.version,
                "brief_content_hash": version,
                "outcome": rules.ACCEPT_WITH_CONDITIONS,
                "follow_ups": rules.follow_up_types(follow_up_actions),
                "signer_user_id": user_id,
                "signer_role": role,
                "story_signed_at": moment.isoformat(),
            },
        )
    )
    s.settle(moment)
    s.made.update(decision=decision, signature=record, follow_ups=follow_ups)
    return decision


def record_decision_on_signal(s: Story, signal, decision, moment: datetime) -> None:
    """The case's signal records the signed decision (DECISION_RECORDED), as the signing hook does."""
    from backend.app.signals import service as signals

    signals.set_status(
        s.db,
        signal,
        "DECISION_RECORDED",
        "DECISION_RECORDED",
        actor_ref=s.person("APPROVER").user_id,
        actor_role=decision.decided_under_role,
        details={
            "decision_business_id": decision.business_id,
            "investigation_business_id": s.case.business_id,
            "decision_status": decision.decision_status,
        },
        now=moment,
    )
    s.settle(moment)


def open_capa(s: Story, follow_up, decision, moment: datetime):
    """Day 5: Ines opens the CAPA the follow-up asks for, as ``POST /api/v1/follow-ups/{id}/capa`` writes it."""
    from backend.app.access.permissions import INVESTIGATION_WORK
    from backend.app.db.models.foundation import Capa
    from backend.app.decision_followups import common
    from backend.app.decision_followups import rules as followup_rules

    ines = s.person("INVESTIGATOR")
    taken = {
        value
        for (value,) in s.db.query(Capa.capa_identifier).filter(
            Capa.tenant_id == s.tenant_id, Capa.capa_identifier.like(f"CAPA-{s.case.business_id}-%")
        )
    }
    identifier = followup_rules.capa_identifier(s.case.business_id, taken)
    due = moment + timedelta(days=60)
    capa = Capa(
        id=uuid.uuid4(),
        tenant_id=s.tenant_id,
        capa_identifier=identifier,
        title=CAPA_TITLE,
        action_type=followup_rules.CAPA_ACTION_TYPE,
        source_type=followup_rules.CAPA_SOURCE_TYPE,
        source_reference=decision.business_id,
        source_system=followup_rules.CAPA_SOURCE_SYSTEM,
        source_identifier=identifier,
        product_id=s.case.product_id,
        investigation_id=s.case.id,
        status=followup_rules.CAPA_STATUS,
        opened_at=moment,
        due_at=due,
        source_timestamp=moment,
        effective_timestamp=moment,
        recorded_timestamp=moment,
        ingestion_timestamp=moment,
        created_at=moment,
        updated_at=moment,
    )
    s.db.add(capa)
    s.db.flush()
    follow_up.capa_id = capa.id
    follow_up.updated_at = moment
    role = ines.role_for(INVESTIGATION_WORK)
    common.audit(
        s.db,
        tenant_id=s.tenant_id,
        actor_ref=ines.user_id,
        action="FOLLOW_UP_CAPA_CREATED",
        entity_type=followup_rules.FOLLOW_UP_ENTITY,
        entity_id=follow_up.id,
        new_values={"capa_id": str(capa.id), "capa_identifier": identifier},
        details={
            "investigation_id": str(follow_up.investigation_id),
            "decision_id": str(follow_up.decision_id),
            "action_type": follow_up.action_type,
            "actor_role": role,
            "capa_id": str(capa.id),
            "capa_identifier": identifier,
            "title": CAPA_TITLE,
            "due_at": common.iso(due),
        },
        now=moment,
    )
    s.db.flush()
    s.made["capa"] = capa
    return capa


LATE_LINK_REASON = "Field service report on the flow interruption reported after the decision was signed."


def link_late_evidence(s: Story, moment: datetime):
    """Day 1: Ines links the field service report on the late complaint to the decided case; it asks for an impact
    assessment (OPEN, with its task), as linking evidence to a decided case does. The signed decision never
    changes."""
    from backend.app.access.permissions import EVIDENCE_REVIEW
    from backend.app.db.models.foundation import InvestigationEvidence
    from backend.app.decision_followups.impact import on_late_evidence
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.evidence_workflow.inventory import review_event
    from backend.app.evidence_workflow.rules import UNREVIEWED

    ines = s.person("INVESTIGATOR")
    ev = s.evidence["ACD-EV-4017"]
    link = InvestigationEvidence(
        id=uuid.uuid4(),
        tenant_id=s.tenant_id,
        investigation_id=s.case.id,
        evidence_id=ev.id,
        relevance=LATE_LINK_REASON,
        created_at=moment,
        review_status=UNREVIEWED,
        relationship="UNRESOLVED",
        linked_by=ines.user_id,
    )
    s.db.add(link)
    s.db.flush()
    review_event(
        s.db,
        tenant_id=s.tenant_id,
        case_id=s.case.id,
        evidence_id=ev.id,
        event_type="LINKED",
        actor=ines,
        permission=EVIDENCE_REVIEW,
        to_status=UNREVIEWED,
        to_relationship="UNRESOLVED",
        reason=LATE_LINK_REASON,
        now=moment,
    )
    s.db.add(
        make_audit_event(
            tenant_id=s.tenant_id,
            actor_ref=ines.user_id,
            action="EVIDENCE_LINKED",
            entity_type="InvestigationEvidence",
            entity_id=link.id,
            reason=LATE_LINK_REASON,
            details={
                "investigation_id": str(s.case.id),
                "evidence_id": str(ev.id),
                "relationship": "UNRESOLVED",
                "actor_role": ines.role_for(EVIDENCE_REVIEW),
            },
            created_at=moment,
        )
    )
    s.db.flush()
    assessment = on_late_evidence(s.db, s.db, s.case, ev.id, trigger="EVIDENCE_LINKED", actor_ref=ines.user_id)
    if assessment is None:
        raise ValueError("The late evidence did not ask for an impact assessment")
    s.settle(moment)
    s.made["impact_assessment"] = assessment
    return assessment
