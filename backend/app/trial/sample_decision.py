"""The sample decision of a free trial: the guided investigation arrives ready for its decision.

On the sample case (SAMPLE-INV-001) a sample author, not the trial's people, has saved the scope, reviewed the three
pieces of evidence, recorded by hand (no AI) two competing hypotheses with the evidence for and against them, two open
questions and a failure chain with one link still unknown, and written and submitted the Decision Brief for quality
review. The trial user then does what a
quality lead does: reviews the brief, accepts it for decision and signs the decision with password and authenticator
code. Segregation of duties is kept as on every case: the person who wrote a brief never reviews or signs it, and the
sample author is that other person. On the organization's own cases a colleague writes or reviews.

The sample author is an account of the trial organization that cannot sign in (status DISABLED, an unknown password,
no membership) and holds no seat. Every step is written as the product's own endpoints write it (scope version,
evidence review history, brief version, quality-review task, audit trail), inside a savepoint: if the brief would not
pass the submission gate, nothing is kept. Idempotent; flushes but never commits (the caller owns the transaction).
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy.orm import Session

from backend.app.trial.flagship import SIGNAL_TEXT

logger = logging.getLogger("mdarix.trial.sample_decision")

SAMPLE_CASE = "SAMPLE-INV-001"
SAMPLE_AUTHOR_NAME = "MDARIX sample author"
SAMPLE_AUTHOR_ROLE = "Investigator"

# The three pieces of evidence the sample case holds (sample_data.py), as the sample author reviewed them.
EVIDENCE_RELATIONSHIPS = {
    "SAMPLE-EV-001": "SUPPORTING",  # the supplier change record
    "SAMPLE-EV-002": "SUPPORTING",  # incoming inspection results, lots 003-004
    "SAMPLE-EV-003": "CONTEXTUAL",  # the complaint trend summary: quantifies the signal, not the cause
}

NARRATIVE = {
    "problem_statement": (
        f"Pressure-alarm complaints on OrbitCare 300 Rev B are at {SIGNAL_TEXT}, mostly from lots 003 and 004."
    ),
    # W1d (D03): an association, never a proven cause. New seeds and restarts only; a sealed brief is never edited.
    "proposed_conclusion": (
        "The evidence shows a time and lot association after the supplier and inspection changes: the rise sits in "
        "lots 003 and 004, the first with NovaSense pressure sensors accepted under incoming inspection cut from 32 to "
        "13 units per lot; sampled sensors in those lots read 4-6% high at the upper pressure range, and the earlier "
        "supplier's lots show none. The cause is not yet confirmed: a bench test of returned pumps is still open. "
        "Contain the affected lots, start a CAPA to restore 32-unit incoming inspection, and verify the supplier and "
        "inspection controls with an effectiveness check."
    ),
    "recommended_actions": [
        "Contain OrbitCare 300 lots 003 and 004",
        "Restore incoming inspection to 32 units per lot for NovaSense pressure sensors",
        "Bench-test returned pumps from lots 003 and 004 at the upper pressure range",
        # W1 (D8): new seeds and restarts only; a sealed brief is never edited.
        "Reassess risk file entries SAMPLE-RSK-01 and SAMPLE-RSK-02 for the NovaSense pressure sensor",
    ],
    "author_notes": (
        "Sample Decision Brief, written for the free trial: review it as the quality reviewer, then sign the decision."
    ),
}


# What the sample author recorded by hand on the case before writing the brief (INTELLIGENCE in the module docstring):
# the hypothesis the brief proposes, an alternative the evidence speaks against, what is still unknown about each, and
# the failure chain with the bench test still open. Evidence is named by its sample identifier (sample_data.py).
SAMPLE_HYPOTHESES = (
    {
        "key": "supplier",
        "statement": "The NovaSense pressure sensors fitted from Rev B (supplier change SAMPLE-CHG-014) read high at "
        "the upper pressure range and set off pressure alarms during infusion. (Sample)",
        "human_status": "PARTIALLY_SUPPORTED",
        # RCA fishbone category (spec 8.6): the sensor is a material.
        "cause_category": "MATERIAL",
        "reason": "The change record and the incoming inspection of lots 003 and 004 support it; the bench test of "
        "returned pumps that would confirm it is still to be done.",
        "evidence": (
            (
                "SAMPLE-EV-001",
                "SUPPORTING",
                "The sensor supplier changed for Rev B and inspection was cut to 13 units.",
            ),
            ("SAMPLE-EV-002", "SUPPORTING", "Sampled sensors in lots 003 and 004 read 4-6% high; lots 001-002 none."),
        ),
    },
    {
        "key": "settings",
        "statement": "Ward pressure-limit settings or use of the pump, not the pump itself, set off the alarms "
        "(for example occlusion limits set too low). (Sample)",
        "human_status": "WEAKLY_SUPPORTED",
        "cause_category": "ENVIRONMENT",
        "reason": "The rise sits in lots 003 and 004 and not in lots 001 and 002 used on the same wards, which speaks "
        "against a ward setting; the alarm settings of the returned pumps have not been checked yet.",
        "evidence": (
            ("SAMPLE-EV-002", "CONTRADICTING", "Lots 001-002 on the same wards show no high readings."),
            (
                "SAMPLE-EV-003",
                "CONTRADICTING",
                "The complaints concentrate in lots 003 and 004, not in particular wards.",
            ),
        ),
    },
)
SAMPLE_UNKNOWNS = (
    {
        "hypothesis": "supplier",
        "category": "Test result",
        "description": "Do returned pumps from lots 003 and 004 read high at the upper pressure range on the bench?",
        "evidence_needed": "Bench test of returned pumps from lots 003 and 004 against a reference pressure gauge.",
    },
    {
        "hypothesis": "settings",
        "category": "Field information",
        "description": "Were the occlusion pressure limits on the reporting wards changed when Rev B arrived?",
        "evidence_needed": "The alarm-limit settings and alarm logs of the returned pumps.",
    },
)
SAMPLE_CHAIN = {
    "name": "Pressure alarms on OrbitCare 300 Rev B (Sample)",
    "nodes": (
        "Supplier change SAMPLE-CHG-014: NovaSense pressure sensors from Rev B",
        "Incoming inspection cut from 32 to 13 sensors per lot",
        "Sensors reading 4-6% high reach lots 003 and 004",
        "The pump reads pressure above its limit during infusion",
        "Pressure alarms interrupt infusion",
    ),
    # (from, to, state, evidence, why)
    "links": (
        (0, 1, "SUPPORTED", "SAMPLE-EV-001", "The change record states both."),
        (1, 2, "PARTIALLY_SUPPORTED", "SAMPLE-EV-002", "Inspection found high readings in lots 003 and 004."),
        (2, 3, "UNKNOWN", None, "Not shown until returned pumps are bench-tested."),
        (3, 4, "PARTIALLY_SUPPORTED", "SAMPLE-EV-003", "Alarm complaints rose in lots 003 and 004 after Rev B."),
    ),
}


# RCA tools (spec 8.6): the sample author's 5 Whys from the problem down, with the bench test still unknown. Its last
# why names the supplier hypothesis; it is not a root cause (only a signed decision confirms one).
SAMPLE_FIVE_WHYS = {
    "problem": "Pressure alarms interrupt infusion on OrbitCare 300 Rev B (Sample)",
    # (why, state, evidence, rationale)
    "whys": (
        (
            "The pump reads pressure above its limit during infusion",
            "UNKNOWN",
            None,
            "Not shown until returned pumps are bench-tested.",
        ),
        (
            "Sensors reading 4-6% high reach lots 003 and 004",
            "PARTIALLY_SUPPORTED",
            "SAMPLE-EV-002",
            "Inspection found high readings in lots 003 and 004.",
        ),
        (
            "Incoming inspection was cut from 32 to 13 sensors per lot",
            "SUPPORTED",
            "SAMPLE-EV-001",
            "The change record.",
        ),
        (
            "The supplier change SAMPLE-CHG-014 was accepted with reduced sampling",
            "SUPPORTED",
            "SAMPLE-EV-001",
            "The change record states both.",
        ),
    ),
    "last_why_is": "supplier",
}


def _author_email(tenant_id: uuid.UUID) -> str:
    return f"sample-author+{tenant_id.hex[:12]}@sample.invalid"


def sample_author(db: Session, tenant_id: uuid.UUID, now: datetime):
    """The trial's sample author: an account that cannot sign in and holds no seat (created once)."""
    from backend.app.db.models.foundation import AuthUser
    from backend.app.trial.service import _hash

    email = _author_email(tenant_id)
    user = db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id, AuthUser.username == email).first()
    if user is not None:
        return user
    user = AuthUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        username=email,
        display_name=SAMPLE_AUTHOR_NAME,
        company="MDARIX sample data",
        # A password nobody knows; DISABLED refuses sign-in, activation and reset in any case.
        password_hash=_hash(secrets.token_urlsafe(32)),
        role=SAMPLE_AUTHOR_ROLE,
        status="DISABLED",
        email_verified=False,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    return user


def is_sample_author(user) -> bool:
    return bool(user is not None and str(user.username or "").startswith("sample-author+"))


def has_sample_decision(db: Session, tenant_id: uuid.UUID) -> bool:
    from backend.app.db.models.foundation import Investigation
    from backend.app.db.models.reviews import DecisionBriefVersion

    return (
        db.query(DecisionBriefVersion.id)
        .join(Investigation, Investigation.id == DecisionBriefVersion.investigation_id)
        .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == SAMPLE_CASE)
        .first()
        is not None
    )


def _review_evidence(db: Session, case, person, now: datetime) -> int:
    """The sample author's review of each piece of the case's evidence, as the evidence review endpoint writes it."""
    from backend.app.access.permissions import EVIDENCE_REVIEW
    from backend.app.db.models.foundation import Evidence, InvestigationEvidence
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.evidence_workflow.inventory import review_event

    reviewed = 0
    links = (
        db.query(InvestigationEvidence, Evidence)
        .join(Evidence, Evidence.id == InvestigationEvidence.evidence_id)
        .filter(InvestigationEvidence.tenant_id == case.tenant_id, InvestigationEvidence.investigation_id == case.id)
        .all()
    )
    for link, evidence in links:
        relationship = EVIDENCE_RELATIONSHIPS.get(evidence.evidence_identifier or "", "CONTEXTUAL")
        if link.review_status not in (None, "UNREVIEWED"):
            continue
        before = {"review_status": link.review_status, "relationship": link.relationship}
        link.review_status = "ACCEPTED"
        link.relationship = relationship
        link.reviewed_by = person.user_id
        link.reviewed_at = now
        review_event(
            db,
            tenant_id=case.tenant_id,
            case_id=case.id,
            evidence_id=evidence.id,
            event_type="REVIEWED",
            actor=person,
            permission=EVIDENCE_REVIEW,
            from_status=before["review_status"],
            to_status="ACCEPTED",
            from_relationship=before["relationship"],
            to_relationship=relationship,
            now=now,
        )
        db.add(
            make_audit_event(
                tenant_id=case.tenant_id,
                actor_ref=person.user_id,
                action="EVIDENCE_REVIEWED",
                entity_type="InvestigationEvidence",
                entity_id=link.id,
                old_values=before,
                new_values={"review_status": "ACCEPTED", "relationship": relationship},
                details={
                    "investigation_id": str(case.id),
                    "evidence_id": str(evidence.id),
                    "actor_role": person.role_for(EVIDENCE_REVIEW),
                    "sample": True,
                },
                created_at=now,
            )
        )
        reviewed += 1
    db.flush()
    return reviewed


def _record_intelligence(db: Session, case, person, now: datetime) -> dict:
    """The sample author's hypotheses, evidence links, judgements, open questions and failure chain, written as the
    case's intelligence endpoints write them (backend/app/case_intelligence/router.py): origin "human", each change in
    the intelligence history and the audit trail. Steps a minute apart, links before the judgement that reads them."""
    from backend.app.access.permissions import EVIDENCE_REVIEW, INVESTIGATION_WORK
    from backend.app.case_intelligence import router as intelligence
    from backend.app.case_intelligence import rules
    from backend.app.db.models.foundation import Evidence, FailureChainNode, Hypothesis, HypothesisEvidence, Unknown
    from backend.app.trial.sample_data import SAMPLE_SOURCE

    ctx = SimpleNamespace(correlation_id=None)
    evidence = {
        row.evidence_identifier: row
        for row in db.query(Evidence).filter(Evidence.tenant_id == case.tenant_id, Evidence.investigation_id == case.id)
    }
    clock = iter(now + timedelta(seconds=10 * step) for step in range(100))

    def record(**kwargs):
        intelligence._record(db, ctx=ctx, person=person, case=case, now=next(clock), **kwargs)

    hypotheses: dict[str, Hypothesis] = {}
    links = 0
    for item in SAMPLE_HYPOTHESES:
        created = next(clock)
        row = Hypothesis(
            id=uuid.uuid4(),
            tenant_id=case.tenant_id,
            investigation_id=case.id,
            statement=item["statement"],
            status=rules.PROPOSED.lower(),
            origin=rules.ORIGIN_HUMAN,
            human_status=rules.PROPOSED,
            status_changed_by=person.user_id,
            status_changed_at=created,
            created_by=person.user_id,
            cause_category=item["cause_category"],
            created_at=created,
            updated_at=created,
            # The sample's own, so its clock moves it (sample_clock.py moves only rows of the sample's source).
            source_system=SAMPLE_SOURCE,
        )
        db.add(row)
        db.flush()
        hypotheses[item["key"]] = row
        record(
            permission=INVESTIGATION_WORK,
            object_type=rules.OBJECT_HYPOTHESIS,
            object_id=row.id,
            entity_type="Hypothesis",
            event_type=rules.EVENT_CREATED,
            to_value=rules.PROPOSED,
            details={"business_id": row.business_id, "statement": row.statement, "origin": "HUMAN", "sample": True},
            new_values={"statement": row.statement, "human_status": rules.PROPOSED},
        )
        for identifier, relation, why in item["evidence"]:
            source = evidence.get(identifier)
            if source is None:
                continue
            linked = next(clock)
            link = HypothesisEvidence(
                id=uuid.uuid4(),
                tenant_id=case.tenant_id,
                hypothesis_id=row.id,
                evidence_id=source.id,
                relation_type=rules.relation_type(relation),
                rationale=why,
                created_by_type=rules.CREATED_BY_HUMAN,
                created_by=person.user_id,
                created_at=linked,
            )
            db.add(link)
            db.flush()
            links += 1
            record(
                permission=INVESTIGATION_WORK if person.holds(INVESTIGATION_WORK) else EVIDENCE_REVIEW,
                object_type=rules.OBJECT_HYPOTHESIS_EVIDENCE,
                object_id=link.id,
                entity_type="HypothesisEvidence",
                event_type=rules.EVENT_EVIDENCE_LINKED,
                to_value=relation,
                reason=why,
                details={
                    "business_id": row.business_id,
                    "hypothesis_id": str(row.id),
                    "evidence_id": str(source.id),
                    "evidence_business_id": source.business_id,
                    "relation": relation,
                    "sample": True,
                },
                new_values={"relation_type": link.relation_type, "rationale": why},
            )
        # The judgement comes after the links it weighs (readiness reads a link newer than it as not yet judged).
        judged = next(clock)
        row.human_status = item["human_status"]
        row.status_reason = item["reason"]
        row.status_changed_at = judged
        row.reviewer_disposition = rules.HUMAN_JUDGED
        row.updated_at = judged
        record(
            permission=INVESTIGATION_WORK,
            object_type=rules.OBJECT_HYPOTHESIS,
            object_id=row.id,
            entity_type="Hypothesis",
            event_type=rules.EVENT_STATUS_CHANGED,
            from_value=rules.PROPOSED,
            to_value=item["human_status"],
            reason=item["reason"],
            details={"business_id": row.business_id, "origin": "HUMAN", "sample": True},
            old_values={"human_status": rules.PROPOSED},
            new_values={"human_status": item["human_status"], "status_reason": item["reason"]},
        )
    for item in SAMPLE_UNKNOWNS:
        about = hypotheses.get(item["hypothesis"])
        created = next(clock)
        row = Unknown(
            id=uuid.uuid4(),
            tenant_id=case.tenant_id,
            investigation_id=case.id,
            hypothesis_id=about.id if about is not None else None,
            category=item["category"],
            description=item["description"],
            evidence_needed=item["evidence_needed"],
            status=rules.UNKNOWN_OPEN,
            origin=rules.ORIGIN_HUMAN,
            created_by=person.user_id,
            created_at=created,
            updated_at=created,
        )
        db.add(row)
        db.flush()
        record(
            permission=INVESTIGATION_WORK,
            object_type=rules.OBJECT_UNKNOWN,
            object_id=row.id,
            entity_type="Unknown",
            event_type=rules.EVENT_CREATED,
            to_value=rules.UNKNOWN_OPEN,
            details={
                "business_id": row.business_id,
                "description": row.description,
                "hypothesis_business_id": about.business_id if about is not None else None,
                "sample": True,
            },
            new_values={"description": row.description, "category": row.category},
        )
    chain = intelligence._store_chain(
        db,
        tenant_id=case.tenant_id,
        case=case,
        person=person,
        name=SAMPLE_CHAIN["name"],
        origin=rules.CHAIN_ORIGIN_HUMAN,
        labels=list(SAMPLE_CHAIN["nodes"]),
        links=[
            {
                "from_index": start,
                "to_index": end,
                "state": state,
                "evidence_id": evidence[identifier].id if identifier in evidence else None,
                "rationale": why,
            }
            for start, end, state, identifier, why in SAMPLE_CHAIN["links"]
        ],
        now=next(clock),
    )
    record(
        permission=INVESTIGATION_WORK,
        object_type=rules.OBJECT_FAILURE_CHAIN,
        object_id=chain.id,
        entity_type="FailureChain",
        event_type=rules.EVENT_CREATED,
        to_value=rules.CHAIN_STATUS_DRAFT,
        details={
            "business_id": chain.business_id,
            "name": chain.name,
            "origin": "HUMAN",
            "nodes": len(SAMPLE_CHAIN["nodes"]),
            "links": len(SAMPLE_CHAIN["links"]),
            "sample": True,
        },
        new_values={"name": chain.name, "nodes": list(SAMPLE_CHAIN["nodes"])},
    )
    whys = list(SAMPLE_FIVE_WHYS["whys"])
    five_whys = intelligence._store_chain(
        db,
        tenant_id=case.tenant_id,
        case=case,
        person=person,
        name=f"5 Whys: {SAMPLE_FIVE_WHYS['problem']}",
        origin=rules.CHAIN_ORIGIN_HUMAN,
        labels=[SAMPLE_FIVE_WHYS["problem"], *(why for why, *_ in whys)],
        links=[
            {
                "from_index": index,
                "to_index": index + 1,
                "state": state,
                "evidence_id": evidence[identifier].id if identifier in evidence else None,
                "rationale": why,
            }
            for index, (_, state, identifier, why) in enumerate(whys)
        ],
        now=next(clock),
        method="FIVE_WHYS",
    )
    last = (
        db.query(FailureChainNode)
        .filter(FailureChainNode.tenant_id == case.tenant_id, FailureChainNode.failure_chain_id == five_whys.id)
        .order_by(FailureChainNode.sequence_number.desc())
        .first()
    )
    last.lifecycle_object_type = "HYPOTHESIS"
    last.lifecycle_object_id = hypotheses[SAMPLE_FIVE_WHYS["last_why_is"]].id
    record(
        permission=INVESTIGATION_WORK,
        object_type=rules.OBJECT_FAILURE_CHAIN,
        object_id=five_whys.id,
        entity_type="FailureChain",
        event_type=rules.EVENT_CREATED,
        to_value=rules.CHAIN_STATUS_DRAFT,
        details={"business_id": five_whys.business_id, "method": "FIVE_WHYS", "whys": len(whys), "sample": True},
        new_values={"problem": SAMPLE_FIVE_WHYS["problem"], "whys": [why for why, *_ in whys]},
    )
    db.flush()
    return {
        "hypotheses": len(hypotheses),
        "evidence_links": links,
        "unknowns": len(SAMPLE_UNKNOWNS),
        "failure_chains": 1,
        "five_whys": 1,
    }


# B5a: the sample author's answers to the material challenge questions the sample case raises, by rule (the
# questions' keys hold record IDs, so they are matched by rule). A question of another rule stays unanswered, and the
# gate then refuses the sample brief, so a new material rule cannot slip through unanswered.
SAMPLE_CHALLENGE_ANSWERS = {
    "C-1": (
        "The Rev A pressure-alarm complaints came before the change, on the earlier supplier's sensors: they are part of "
        "the earlier average that the rise after Rev B is measured against. (Sample)"
    ),
    "C-5": (
        "The bench test of returned pumps is still open. Containment of lots 003 and 004 and the restored inspection "
        "go ahead now; the bench test result is a condition of this decision. (Sample)"
    ),
}


def _answer_challenge(content: dict, text: dict, author_ref: str, now: datetime) -> None:
    """The sample author answers the material challenge questions, in the narrative (signed with the brief) and in
    the composed challenge section. Nothing when the challenge is off."""
    challenge = content.get("challenge")
    if not challenge:
        return
    answers = {}
    for item in challenge["questions"]:
        if item["material"] and item["rule"] in SAMPLE_CHALLENGE_ANSWERS:
            item["answer"] = answers[item["key"]] = {
                "rule": item["rule"],
                "rule_version": item["rule_version"],
                "question": item["text"],
                "text": SAMPLE_CHALLENGE_ANSWERS[item["rule"]],
                "not_applicable": False,
                "answered_by": author_ref,
                "answered_at": now.isoformat(),
            }
    challenge["blocking"] = [key for key in challenge["blocking"] if key not in answers]
    if answers:
        text["challenge_answers"] = answers


def _submit_brief(db: Session, case, person, now: datetime):
    """Version 1 of the brief, composed from the case and submitted for quality review, as ``POST
    .../decision-brief`` and ``.../submit`` write it. Returns (row, gate)."""
    from backend.app.access.permissions import INVESTIGATION_WORK
    from backend.app.db.models.reviews import DecisionBriefVersion
    from backend.app.decision_brief import compose as composer
    from backend.app.decision_brief import router as brief_api
    from backend.app.decision_brief import rules as brief_rules
    from backend.app.workflow import tasks as task_service

    ctx = SimpleNamespace(correlation_id=None, user_id=person.user_id)
    role = person.role_for(INVESTIGATION_WORK)
    text = brief_rules.with_contributor(dict(NARRATIVE), person.user_id)
    content, state = composer.compose(db, db, case, now=now)
    _answer_challenge(content, text, person.user_id, now)
    gate = brief_rules.evaluate_gate(state.get("checks") or [], text, content_complete=not content.get("unavailable"))
    gate = brief_api._with_challenge(gate, content.get("challenge"))
    row = DecisionBriefVersion(
        id=uuid.uuid4(),
        tenant_id=case.tenant_id,
        investigation_id=case.id,
        version=1,
        status=brief_rules.READY_FOR_REVIEW,
        title=f"Decision brief {case.business_id} v1",
        content=content,
        narrative=text,
        readiness=state,
        content_hash=brief_rules.content_hash(content, text),
        scope_version=content["context"]["scope_version"] or None,
        created_by=person.user_id,
        created_role=role,
        submitted_by=person.user_id,
        submitted_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    brief_api._audit(db, ctx, row, "BRIEF_CREATED", now, role=role, details={"ai_draft_used": False, "sample": True})
    brief_api._move_case(
        db,
        ctx,
        case,
        "BRIEF_IN_REVIEW",
        f"Brief version {row.version} submitted for quality review",
        now,
        {"brief_version_id": str(row.id), "brief_version": row.version},
    )
    task_service.create_task(
        db,
        case.tenant_id,
        task_type="QUALITY_REVIEW",
        title=brief_api._quality_task_title(case, row),
        source_type=brief_api.SOURCE_TYPE,
        source_id=row.id,
        investigation_id=case.id,
        priority=case.priority,
        created_by=person.user_id,
        actor_role=role,
        details={
            "brief_version": row.version,
            "brief_author_ref": person.user_id,
            "brief_author_refs": brief_api._all_author_refs(row, person.user_id),
        },
    )
    brief_api._audit(
        db,
        ctx,
        row,
        "BRIEF_SUBMITTED",
        now,
        role=role,
        old_values={"status": brief_rules.DRAFT},
        new_values={"status": brief_rules.READY_FOR_REVIEW},
        details={
            "evidence_set_hash": content["context"]["evidence_set_hash"],
            "scope_version": row.scope_version,
            "superseded_versions": [],
            "warnings": [item["key"] for item in gate["warnings"]],
            "sample": True,
        },
    )
    db.flush()
    return row, gate


def stage_sample_decision(db: Session, tenant_id: uuid.UUID, now: datetime | None = None) -> dict:
    """Bring the sample case to "brief submitted for quality review" (see the module docstring). Returns what was done;
    ``{"created": False, ...}`` when the case is missing, already has a brief, or the brief would not pass the gate."""
    from backend.app.access.permissions import INVESTIGATION_WORK
    from backend.app.case_workflow import scope
    from backend.app.db.models.foundation import Investigation, InvestigationComplaint
    from backend.app.demo_golden_path.context import _person

    now = now or datetime.now(timezone.utc)
    case = (
        db.query(Investigation)
        .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == SAMPLE_CASE)
        .first()
    )
    if case is None:
        return {"created": False, "why": "NO_SAMPLE_CASE"}
    if has_sample_decision(db, tenant_id):
        return {"created": False, "why": "ALREADY_STAGED"}
    savepoint = db.begin_nested()
    try:
        author = sample_author(db, tenant_id, now)
        person = _person(db, author)
        # The steps a few minutes apart, in the order an investigator takes them.
        steps = [now - timedelta(minutes=minutes) for minutes in (40, 30, 25, 10)]
        if scope.latest_version(db, tenant_id, case.id) is None:
            complaint_ids = [
                row.complaint_id
                for row in db.query(InvestigationComplaint).filter(
                    InvestigationComplaint.tenant_id == tenant_id, InvestigationComplaint.investigation_id == case.id
                )
            ]
            scope.first_version(
                db,
                case,
                complaint_ids=complaint_ids,
                actor_ref=person.user_id,
                actor_role=person.role_for(INVESTIGATION_WORK),
                now=steps[0],
                with_lots=True,
            )
        reviewed = _review_evidence(db, case, person, steps[1])
        intelligence = _record_intelligence(db, case, person, steps[2])
        row, gate = _submit_brief(db, case, person, steps[3])
        if not gate["can_submit"]:
            savepoint.rollback()
            blocking = [item.get("key") for item in gate["blocking"]]
            logger.warning("Trial sample decision not staged: the brief would not pass the gate: %s", blocking)
            return {"created": False, "why": "GATE", "blocking": blocking}
        savepoint.commit()
    except Exception:
        savepoint.rollback()
        logger.exception("Trial sample decision could not be staged")
        return {"created": False, "why": "ERROR"}
    return {
        "created": True,
        "brief_version": row.version,
        "evidence_reviewed": reviewed,
        "intelligence": intelligence,
        "author": str(author.id),
    }
