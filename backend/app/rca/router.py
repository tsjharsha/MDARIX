"""Root-cause tools on a case (RCA spec Parts A and C). No AI call anywhere.

Under ``/api/v1``:

- ``GET  /investigations/{id}/rca/fishbone``: the case's possible causes (hypotheses) in category columns, ruled-out
  ones kept with their reason, each with its failure mode and the risks it can lead to, and "Named as root cause in
  decision ..." only when a signed decision ticked it.
- ``POST /investigations/{id}/rca/causes``: a fishbone quick add (a PROPOSED hypothesis of origin human).
- ``POST /investigations/{id}/rca/causes/{hypothesis_id}``: a cause's category or failure mode, with the reason.
- ``GET  /investigations/{id}/rca/five-whys``; ``POST`` one (2 to 7 whys); ``POST .../{chain_id}/link`` names the
  hypothesis the last why is. Link states change on the existing failure-chain route.
- ``GET  /rca/pareto``: confirmed causes, counts only.
- ``GET  /investigations/{id}/rca/event-versions``: each in-scope complaint's version at its event date.

Writes need ``investigation.work``, refuse a closed case, and are recorded in the case's intelligence history and the
audit trail. Another organization's case, hypothesis, chain or failure mode is "not found". Switches:
``MDARIX_RCA_METHODS`` and ``MDARIX_RCA_INTELLIGENCE`` (``feature_set.py``; off, these routes answer 404).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.access.permissions import INVESTIGATION_WORK, require_permission
from backend.app.case_intelligence import router as ci
from backend.app.case_intelligence import rules as ci_rules
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import (
    Complaint,
    Decision,
    FailureChain,
    FailureChainNode,
    FailureMode,
    Hypothesis,
    HypothesisEvidence,
    InvestigationComplaint,
    LotBatch,
    Product,
    ProductVersion,
    RealityRelationship,
    Risk,
)
from backend.app.db.session import get_db
from backend.app.evidence_workflow.people import current_person
from backend.app.rca import pareto, rules
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1", tags=["Root-cause tools"])

CASE = "/investigations/{investigation_id}/rca"
EVENT_CAUSE_SET = "CAUSE_SET"
EVENT_WHY_LINKED = "WHY_LINKED"
ci_rules.EVENT_LABELS.setdefault(EVENT_CAUSE_SET, "Cause category or failure mode set")
ci_rules.EVENT_LABELS.setdefault(EVENT_WHY_LINKED, "Why linked to a hypothesis")


def _failure_mode(db: Session, tenant_id, failure_mode_id) -> FailureMode | None:
    if failure_mode_id is None:
        return None
    row = db.query(FailureMode).filter(FailureMode.tenant_id == tenant_id, FailureMode.id == failure_mode_id).first()
    if row is None:
        raise ci._error(404, "FAILURE_MODE_NOT_FOUND", "This failure mode is not in your organization's FMEA")
    return row


def _risks_by_failure_mode(db: Session, tenant_id, ids: set) -> dict[uuid.UUID, list[dict]]:
    """The risks each failure mode CAN_LEAD_TO (either direction of the imported relationship)."""
    if not ids:
        return {}
    pairs = []
    for row in db.query(RealityRelationship).filter(
        RealityRelationship.tenant_id == tenant_id,
        (
            (RealityRelationship.source_entity_type == "FailureMode")
            & (RealityRelationship.source_entity_id.in_(list(ids)))
            & (RealityRelationship.target_entity_type == "Risk")
        )
        | (
            (RealityRelationship.target_entity_type == "FailureMode")
            & (RealityRelationship.target_entity_id.in_(list(ids)))
            & (RealityRelationship.source_entity_type == "Risk")
        ),
    ):
        if row.source_entity_type == "FailureMode":
            pairs.append((row.source_entity_id, row.target_entity_id))
        else:
            pairs.append((row.target_entity_id, row.source_entity_id))
    risk_ids = {risk for _, risk in pairs}
    risks = (
        {row.id: row for row in db.query(Risk).filter(Risk.tenant_id == tenant_id, Risk.id.in_(list(risk_ids)))}
        if risk_ids
        else {}
    )
    found: dict[uuid.UUID, list[dict]] = {}
    for mode, risk in pairs:
        if risk in risks:
            found.setdefault(mode, []).append(
                {
                    "id": str(risk),
                    "business_id": risks[risk].business_id,
                    "identifier": risks[risk].risk_identifier,
                    "description": risks[risk].description,
                }
            )
    return found


def _named_in(db: Session, tenant_id, case_id) -> dict[str, dict]:
    """``{hypothesis id: decision}`` for the hypotheses the case's current signed decision ticked."""
    from backend.app.human_decision.rules import DECISION_KIND, SIGNED

    decision = (
        db.query(Decision)
        .filter(
            Decision.tenant_id == tenant_id,
            Decision.investigation_id == case_id,
            Decision.decision_kind == DECISION_KIND,
            Decision.decision_status == SIGNED,
            Decision.superseded_by_decision_id.is_(None),
        )
        .order_by(Decision.decided_at.desc().nulls_last())
        .first()
    )
    if decision is None:
        return {}
    view = {
        "id": str(decision.id),
        "business_id": decision.business_id,
        "decision_identifier": decision.decision_identifier,
        "signed_by_ref": str(decision.decided_by_user_id) if decision.decided_by_user_id else None,
        "signed_at": ci._iso(decision.decided_at),
        "category": decision.root_cause_category,
    }
    return {str(item): view for item in decision.root_cause_hypothesis_ids or ()}


def _fishbone(db: Session, control_db: Session, tenant_id, case, person) -> dict:
    rows = [
        row
        for row in ci._hypothesis_rows(db, tenant_id, case.id)
        if str(row.status or "").lower() != ci_rules.SUPERSEDED
    ]
    links = (
        db.query(HypothesisEvidence.hypothesis_id, HypothesisEvidence.relation_type)
        .filter(
            HypothesisEvidence.tenant_id == tenant_id,
            HypothesisEvidence.hypothesis_id.in_([row.id for row in rows]),
            HypothesisEvidence.retracted_at.is_(None),
        )
        .all()
        if rows
        else []
    )
    counts: dict[uuid.UUID, dict[str, int]] = {row.id: {"supporting": 0, "contradicting": 0} for row in rows}
    for hypothesis_id, relation in links:
        bucket = ci_rules.relation_bucket(relation)
        if bucket in counts[hypothesis_id]:
            counts[hypothesis_id][bucket] += 1
    modes = {
        row.id: row
        for row in db.query(FailureMode).filter(FailureMode.tenant_id == tenant_id).order_by(FailureMode.name)
    }
    risks = _risks_by_failure_mode(db, tenant_id, {row.failure_mode_id for row in rows if row.failure_mode_id})
    named = _named_in(db, tenant_id, case.id)
    signers = ci._names(control_db, tenant_id, [item["signed_by_ref"] for item in named.values()])
    can_work = ci._is_open(case) and person.holds(INVESTIGATION_WORK)

    def cause(row: Hypothesis) -> dict:
        status = str(row.human_status or "").upper()
        ruled_out = status in rules.RULED_OUT
        mode = modes.get(row.failure_mode_id) if row.failure_mode_id else None
        decision = named.get(str(row.id))
        confirmed = {**decision, "signed_by_name": ci._name(signers, decision["signed_by_ref"])} if decision else None
        return {
            "id": str(row.id),
            "business_id": row.business_id,
            "statement": row.statement,
            "origin": ci_rules.origin_code(row.origin),
            "cause_category": row.cause_category,
            "human_status": row.human_status,
            "human_status_label": ci_rules.human_status_label(row.human_status),
            "ruled_out": ruled_out,
            "ruled_out_reason": row.status_reason if ruled_out else None,
            "evidence_for": counts[row.id]["supporting"],
            "evidence_against": counts[row.id]["contradicting"],
            "failure_mode": (
                {
                    "id": str(mode.id),
                    "identifier": mode.failure_mode_identifier,
                    "name": mode.name,
                    "risks": risks.get(mode.id, []),
                }
                if mode
                else None
            ),
            "confirmed_in": confirmed,
            # A cause a signed decision names with no failure mode: a prompt to a person, never a change.
            "fmea_prompt": rules.NOT_IN_FMEA if confirmed and mode is None else None,
            "can_change": can_work,
        }

    used = {row.cause_category for row in rows if row.cause_category}
    product = db.query(Product).filter(Product.tenant_id == tenant_id, Product.id == case.product_id).first()
    shown = [
        code
        for code in rules.CAUSE_CATEGORIES
        if code != rules.SOFTWARE or rules.shows_software(getattr(product, "device_category", None), used)
    ]
    return {
        "investigation_id": str(case.id),
        "categories": [
            {
                "code": code,
                "label": rules.CATEGORY_LABELS[code],
                "causes": [cause(row) for row in rows if row.cause_category == code],
            }
            for code in shown
        ],
        "all_categories": [{"code": code, "label": rules.CATEGORY_LABELS[code]} for code in rules.CAUSE_CATEGORIES],
        "uncategorised": [cause(row) for row in rows if not row.cause_category],
        "failure_modes": [
            {"id": str(row.id), "identifier": row.failure_mode_identifier, "name": row.name} for row in modes.values()
        ],
        "actions": {"can_add": can_work},
        "note": "Each possible cause is a hypothesis. Only a signed decision confirms a cause.",
    }


@router.get(CASE + "/fishbone")
def fishbone(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = ci._tenant(ctx)
    case = ci._case(db, tenant_id, investigation_id)
    return _fishbone(db, control_db, tenant_id, case, current_person(control_db, ctx))


@router.post(CASE + "/causes", status_code=201, dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def add_cause(
    investigation_id: uuid.UUID,
    payload: rules.CauseCreatePayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """A fishbone quick add: a hypothesis a person proposes (PROPOSED, origin human) in a category."""
    tenant_id = ci._tenant(ctx)
    person = current_person(control_db, ctx)
    case = ci._case(db, tenant_id, investigation_id, lock=True)
    ci._refuse_closed(case)
    mode = _failure_mode(db, tenant_id, payload.failure_mode_id)
    duplicate = (
        db.query(Hypothesis.id)
        .filter(
            Hypothesis.tenant_id == tenant_id,
            Hypothesis.investigation_id == case.id,
            func.lower(Hypothesis.statement) == payload.statement.lower(),
            Hypothesis.status != ci_rules.SUPERSEDED,
        )
        .first()
    )
    if duplicate is not None:
        raise ci._error(409, "HYPOTHESIS_EXISTS", "The investigation already has this possible cause")
    now = ci.now_utc()
    row = Hypothesis(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        investigation_id=case.id,
        statement=payload.statement,
        status=ci_rules.PROPOSED.lower(),
        origin=ci_rules.ORIGIN_HUMAN,
        human_status=ci_rules.PROPOSED,
        status_changed_by=person.user_id,
        status_changed_at=now,
        created_by=person.user_id,
        cause_category=payload.cause_category,
        failure_mode_id=mode.id if mode else None,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    ci._record(
        db,
        ctx=ctx,
        person=person,
        permission=INVESTIGATION_WORK,
        case=case,
        object_type=ci_rules.OBJECT_HYPOTHESIS,
        object_id=row.id,
        entity_type="Hypothesis",
        event_type=ci_rules.EVENT_CREATED,
        to_value=ci_rules.PROPOSED,
        details={
            "business_id": row.business_id,
            "statement": payload.statement,
            "origin": "HUMAN",
            "cause_category": payload.cause_category,
            "failure_mode_id": str(mode.id) if mode else None,
            "via": "FISHBONE",
        },
        new_values={"statement": payload.statement, "human_status": ci_rules.PROPOSED},
        now=now,
    )
    db.commit()
    return _fishbone(db, control_db, tenant_id, case, person)


@router.post(CASE + "/causes/{hypothesis_id}", dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def set_cause(
    investigation_id: uuid.UUID,
    hypothesis_id: uuid.UUID,
    payload: rules.CauseUpdatePayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """A cause's category and failure mode, set by a person with the reason. Its status never changes here."""
    tenant_id = ci._tenant(ctx)
    person = current_person(control_db, ctx)
    case = ci._case(db, tenant_id, investigation_id, lock=True)
    ci._refuse_closed(case)
    row = ci._locked_hypothesis(db, tenant_id, case, hypothesis_id)
    mode = _failure_mode(db, tenant_id, payload.failure_mode_id)
    after = {"cause_category": payload.cause_category, "failure_mode_id": str(mode.id) if mode else None}
    before = {
        "cause_category": row.cause_category,
        "failure_mode_id": str(row.failure_mode_id) if row.failure_mode_id else None,
    }
    if before == after:
        raise ci._error(409, "CAUSE_UNCHANGED", "The cause already has this category and failure mode")
    now = ci.now_utc()
    row.cause_category = payload.cause_category
    row.failure_mode_id = mode.id if mode else None
    row.updated_at = now
    ci._record(
        db,
        ctx=ctx,
        person=person,
        permission=INVESTIGATION_WORK,
        case=case,
        object_type=ci_rules.OBJECT_HYPOTHESIS,
        object_id=row.id,
        entity_type="Hypothesis",
        event_type=EVENT_CAUSE_SET,
        from_value=before["cause_category"],
        to_value=payload.cause_category,
        reason=payload.reason,
        details={"business_id": row.business_id},
        old_values=before,
        new_values=after,
        now=now,
    )
    db.commit()
    return _fishbone(db, control_db, tenant_id, case, person)


# ------------------------------------------------------------------------------------------------------ 5 Whys


def _five_whys(db, control_db, tenant_id, case, person) -> dict:
    chains = (
        db.query(FailureChain)
        .filter(
            FailureChain.tenant_id == tenant_id,
            FailureChain.investigation_id == case.id,
            FailureChain.method == rules.FIVE_WHYS,
        )
        .order_by(FailureChain.created_at.desc(), FailureChain.business_id)
        .all()
    )
    views = ci._chain_views(db, control_db, tenant_id, case, chains)
    can_work = ci._is_open(case) and person.holds(INVESTIGATION_WORK)
    hypotheses = {str(row.id): row for row in ci._hypothesis_rows(db, tenant_id, case.id, include_superseded=False)}
    for view in views:
        view["actions"]["can_change_links"] = view["actions"]["can_change_links"] and can_work
        last = view["nodes"][-1]["id"] if view["nodes"] else None
        for node in view["nodes"]:
            linked = hypotheses.get(node["hypothesis_id"] or "")
            node["kind"] = "PROBLEM" if node["sequence"] == 1 else "WHY"
            node["is_last"] = node["id"] == last
            node["hypothesis"] = (
                {"id": str(linked.id), "business_id": linked.business_id, "statement": linked.statement}
                if linked
                else None
            )
        for link in view["links"]:
            link["unknown_prompt"] = rules.UNKNOWN_WHY if link["evidence"] is None else None
    return {
        "items": views,
        "actions": {"can_add": can_work},
        "note": "The last why is not a root cause. Only a signed decision confirms a cause.",
    }


@router.get(CASE + "/five-whys")
def list_five_whys(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = ci._tenant(ctx)
    case = ci._case(db, tenant_id, investigation_id)
    return _five_whys(db, control_db, tenant_id, case, current_person(control_db, ctx))


@router.post(CASE + "/five-whys", status_code=201, dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def create_five_whys(
    investigation_id: uuid.UUID,
    payload: rules.FiveWhysPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """A 5 Whys: the problem, then each why answering the step before, each link with its state and evidence."""
    tenant_id = ci._tenant(ctx)
    person = current_person(control_db, ctx)
    case = ci._case(db, tenant_id, investigation_id, lock=True)
    ci._refuse_closed(case)
    for why in payload.whys:
        if why.evidence_id is not None:
            ci._case_evidence(db, tenant_id, case, why.evidence_id)
    now = ci.now_utc()
    labels = [payload.problem, *(why.text for why in payload.whys)]
    chain = ci._store_chain(
        db,
        tenant_id=tenant_id,
        case=case,
        person=person,
        name=f"5 Whys: {payload.problem}",
        origin=ci_rules.CHAIN_ORIGIN_HUMAN,
        labels=labels,
        links=[
            {"from_index": index, "to_index": index + 1, "state": why.state, "evidence_id": why.evidence_id}
            for index, why in enumerate(payload.whys)
        ],
        now=now,
        method=rules.FIVE_WHYS,
    )
    ci._record(
        db,
        ctx=ctx,
        person=person,
        permission=INVESTIGATION_WORK,
        case=case,
        object_type=ci_rules.OBJECT_FAILURE_CHAIN,
        object_id=chain.id,
        entity_type="FailureChain",
        event_type=ci_rules.EVENT_CREATED,
        to_value=ci_rules.CHAIN_STATUS_DRAFT,
        details={"business_id": chain.business_id, "method": rules.FIVE_WHYS, "whys": len(payload.whys)},
        new_values={"problem": payload.problem, "whys": [why.text for why in payload.whys]},
        now=now,
    )
    db.commit()
    return _five_whys(db, control_db, tenant_id, case, person)


@router.post(CASE + "/five-whys/{chain_id}/link", dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def link_last_why(
    investigation_id: uuid.UUID,
    chain_id: uuid.UUID,
    payload: rules.WhyLinkPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Name the hypothesis the last why is. Nothing more: the hypothesis's status never changes."""
    tenant_id = ci._tenant(ctx)
    person = current_person(control_db, ctx)
    case = ci._case(db, tenant_id, investigation_id, lock=True)
    ci._refuse_closed(case)
    chain = ci._chain_of_case(db, tenant_id, case, chain_id)
    if chain.method != rules.FIVE_WHYS:
        raise ci._error(404, "FIVE_WHYS_NOT_FOUND", "This 5 Whys is not available in this investigation")
    hypothesis = ci._locked_hypothesis(db, tenant_id, case, payload.hypothesis_id)
    last = (
        db.query(FailureChainNode)
        .filter(FailureChainNode.tenant_id == tenant_id, FailureChainNode.failure_chain_id == chain.id)
        .order_by(FailureChainNode.sequence_number.desc())
        .with_for_update()
        .first()
    )
    if last.lifecycle_object_type == rules.WHY_LINK_OBJECT and last.lifecycle_object_id == hypothesis.id:
        raise ci._error(409, "WHY_ALREADY_LINKED", "The last why already names this hypothesis")
    now = ci.now_utc()
    before = str(last.lifecycle_object_id) if last.lifecycle_object_id else None
    last.lifecycle_object_type = rules.WHY_LINK_OBJECT
    last.lifecycle_object_id = hypothesis.id
    chain.updated_at = now
    ci._record(
        db,
        ctx=ctx,
        person=person,
        permission=INVESTIGATION_WORK,
        case=case,
        object_type=ci_rules.OBJECT_FAILURE_CHAIN,
        object_id=chain.id,
        entity_type="FailureChain",
        event_type=EVENT_WHY_LINKED,
        to_value=hypothesis.business_id,
        details={"business_id": chain.business_id, "hypothesis_business_id": hypothesis.business_id},
        old_values={"hypothesis_id": before},
        new_values={"hypothesis_id": str(hypothesis.id)},
        now=now,
    )
    db.commit()
    return _five_whys(db, control_db, tenant_id, case, person)


# ------------------------------------------------------------------------------------------------------ Pareto


def _day(value: date | None, end: bool = False) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(value, time.max if end else time.min, tzinfo=timezone.utc)


@router.get("/rca/pareto")
def confirmed_cause_pareto(
    group_by: str = Query("category"),
    product_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    if group_by not in pareto.GROUPS:
        raise ci._error(422, "GROUP_UNKNOWN", f"Group by one of {', '.join(pareto.GROUPS)}")
    result = pareto.read(
        db,
        ci._tenant(ctx),
        group_by=group_by,
        product_id=product_id,
        date_from=_day(date_from),
        date_to=_day(date_to, end=True),
    )
    result["products"] = [
        {"id": str(row.id), "name": row.name}
        for row in db.query(Product).filter(Product.tenant_id == ci._tenant(ctx)).order_by(Product.name)
    ]
    return result


# --------------------------------------------------------------------------------------- version at the event


def _version_view(version: ProductVersion | None) -> dict | None:
    if version is None:
        return None
    return {
        "id": str(version.id),
        "version_identifier": version.version_identifier,
        "released_at": ci._iso(version.release_timestamp),
    }


@router.get(CASE + "/event-versions")
def event_versions(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Each in-scope complaint's version at its event date (else its awareness date): the version the complaint names,
    else its lot's (device history). A date never chooses a version (PV-1): with neither, it stays unknown."""
    from backend.app.product360.service import Product360Service

    tenant_id = ci._tenant(ctx)
    case = ci._case(db, tenant_id, investigation_id)
    complaints = (
        db.query(Complaint)
        .join(
            InvestigationComplaint,
            (InvestigationComplaint.tenant_id == Complaint.tenant_id)
            & (InvestigationComplaint.complaint_id == Complaint.id),
        )
        .filter(InvestigationComplaint.tenant_id == tenant_id, InvestigationComplaint.investigation_id == case.id)
        .order_by(Complaint.business_id)
        .all()
    )
    versions = {row.id: row for row in db.query(ProductVersion).filter(ProductVersion.tenant_id == tenant_id)}
    lots = {
        row.id: row
        for row in db.query(LotBatch).filter(
            LotBatch.tenant_id == tenant_id, LotBatch.id.in_([c.lot_batch_id for c in complaints if c.lot_batch_id])
        )
    }
    service = Product360Service()
    items = []
    for complaint in complaints:
        anchor, anchor_source = complaint.event_timestamp, "EVENT"
        if anchor is None:
            anchor, anchor_source = complaint.awareness_timestamp, "AWARENESS"
        lot = lots.get(complaint.lot_batch_id) if complaint.lot_batch_id else None
        version, source = None, None
        if complaint.product_version_id:
            version, source = versions.get(complaint.product_version_id), "COMPLAINT"
        elif lot is not None and lot.product_version_id:
            version, source = versions.get(lot.product_version_id), "LOT"
        flags = []
        if (
            version is not None
            and anchor is not None
            and version.release_timestamp
            and version.release_timestamp > anchor
        ):
            flags.append({"code": "RELEASED_AFTER_EVENT", "label": "Version released after the event: check"})
        released = sorted(
            (v for v in versions.values() if v.product_id == complaint.product_id),
            key=lambda v: (
                v.release_timestamp is None,
                v.release_timestamp or datetime.min.replace(tzinfo=timezone.utc),
            ),
        )
        candidates = (
            [
                {"id": str(v.id), "version_identifier": v.version_identifier}
                for v in released
                if anchor is None or v.release_timestamp is None or v.release_timestamp <= anchor
            ]
            if version is None
            else []
        )
        components = (
            [
                {"identifier": row["component_identifier"], "name": row["name"], "revision": row["revision"]}
                for row in service.components(db.connection(), str(tenant_id), str(version.id))
            ]
            if version is not None
            else []
        )
        items.append(
            {
                "complaint": {
                    "id": str(complaint.id),
                    "business_id": complaint.business_id,
                    "identifier": complaint.complaint_identifier,
                },
                "anchor_date": ci._iso(anchor),
                "anchor_source": anchor_source if anchor is not None else None,
                "anchor_label": {"EVENT": "Event date", "AWARENESS": "Awareness date (no event date)"}.get(
                    anchor_source if anchor is not None else "", "No event or awareness date"
                ),
                "lot": {"id": str(lot.id), "identifier": lot.lot_identifier} if lot is not None else None,
                "version": _version_view(version),
                "version_source": source,
                "version_label": (
                    {"COMPLAINT": "Named on the complaint", "LOT": "From the lot's device history"}[source]
                    if version is not None
                    else "Version unknown"
                ),
                "candidate_versions": candidates,
                "components": components,
                "flags": flags,
            }
        )
    return {
        "investigation_id": str(case.id),
        "items": items,
        "note": "A date never chooses a version: without one on the complaint or its lot, it stays unknown.",
    }
