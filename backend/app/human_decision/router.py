"""Human decision API (Phase 6): the decision maker's queue, the decision screen, signing a decision on an approved
Decision Brief version, returning the brief without a signature, and the signed decision record.

- ``GET  /api/v1/decisions/queue`` and ``GET /api/v1/decisions/summary`` (``decision.sign``): approved brief versions
  waiting for a decision (most critical first) and the decision maker's dashboard;
- ``GET  /api/v1/investigations/{id}/decision``: the decision screen (the approved brief, its reviewers, the case's
  decisions, the outcomes and follow-up actions, and what the signed-in person may do);
- ``POST /api/v1/investigations/{id}/decision/sign``: the signed decision (checked inside, as legacy signing is: no
  administrator, the controlled-signature entitlement, the approved and unchanged brief version, the case state, the
  supersede rule, approval authority and segregation of duties, then the password and MFA);
- ``POST /api/v1/investigations/{id}/decision/return`` (``decision.sign``): send the brief back without signing;
- ``GET  /api/v1/decisions/{decision_id}/record``: the signed decision record with its verification.

Everything is limited to the signed-in organization (another organization's case or decision is "not found"). The
decision, its context snapshot, follow-ups, tasks and the case and brief changes are written in the tenant data plane
in one transaction; the signature and its audit events in the control database (the same transaction on the shared
plane). A signed decision is never edited: a correction is a new decision that supersedes it.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.access.permissions import DECISION_SIGN, require_permission
from backend.app.business_ids import as_uuid
from backend.app.case_workflow import states
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.decision_outcomes import DecisionFollowUp, ImpactAssessment
from backend.app.db.models.foundation import Decision, Investigation, Product, SignedApprovalRecord
from backend.app.db.models.reviews import BriefReviewAction, DecisionBriefVersion
from backend.app.db.models.stage3 import ContextSnapshot
from backend.app.db.session import get_db
from backend.app.decision_brief import rules as brief_rules
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.inventory import error, load_case
from backend.app.human_decision import rules
from backend.app.human_decision import service
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.role_codes import is_administrator_role, role_code
from backend.app.sorting import sort_rows
from backend.app.workflow import tasks as task_service

logger = logging.getLogger("mdarix.human_decision")

router = APIRouter(tags=["Human Decision"])
CASE_BASE = "/api/v1/investigations/{investigation_id}/decision"
LIST_BASE = "/api/v1/decisions"
QUEUE_STATES = ("READY_FOR_DECISION", *rules.SUPERSEDING_STATES)
DUE_SOON_DAYS = 3
RECENT_DAYS = 30
SUMMARY_LIST_LIMIT = 10


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _tenant_id(ctx: AuthenticatedRequestContext) -> uuid.UUID:
    return uuid.UUID(str(ctx.tenant_id))


def _governance():
    from backend.app import governance_router

    return governance_router


def _is_administrator(actor: dict) -> bool:
    return any(is_administrator_role(role) for role in actor.get("roles") or ())


# ----------------------------------------------------------------------------------------------- who may decide


class Decider:
    """The signed-in person as the decision rules see them, read once per request: their roles, whether they are an
    administrator, the controlled-signature entitlement and their approval authority (``approval_check`` over every
    role they hold). Read-only: nothing is audited and no failed attempt is counted."""

    def __init__(self, control_db: Session, ctx: AuthenticatedRequestContext):
        governance = _governance()
        self.ctx = ctx
        self.control_db = control_db
        self.problem: tuple[str, str] | None = None
        self.actor = governance.session_actor(control_db, ctx)
        self.user_id = str(self.actor["user_id"])
        self.administrator = _is_administrator(self.actor)
        self.tenant = None
        self.entitled = False
        try:
            self.tenant = governance.tenant(control_db, self.actor)
            self.entitled = bool(governance.entitled(control_db, self.tenant))
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            self.problem = (
                str(detail.get("code") or "TENANT_INACTIVE"),
                str(detail.get("message") or "Decisions cannot be signed in this organization"),
            )
        from backend.app.access.permissions import effective_permissions

        try:
            self.may_sign_permission = DECISION_SIGN in effective_permissions(control_db, ctx)
        except Exception:
            logger.warning("The permissions of %s could not be read", self.user_id, exc_info=True)
            self.may_sign_permission = False

    def authority(self, row: DecisionBriefVersion) -> tuple[tuple[str, str] | None, str | None]:
        if self.tenant is None:
            return self.problem, None
        return _governance().approval_check(
            self.control_db, self.tenant.id, self.actor["roles"], service.approval_subject(row), self.user_id
        )

    def evaluate(
        self, data: Session, case: Investigation, row: DecisionBriefVersion | None, current: Decision | None
    ) -> dict:
        """``{can_sign, can_return, reason, supersede_required}`` by the rules of the sign and return endpoints."""
        state = states.case_state(case)
        if self.problem is not None:
            return {
                "can_sign": False,
                "can_return": False,
                "reason": self.problem[1],
                "return_reason": self.problem[1],
                "supersede_required": current is not None,
                "current_decision_id": str(current.id) if current is not None else None,
            }
        if row is None:
            brief = ("NO_APPROVED_BRIEF", "No version of the brief is approved for decision yet")
            author = False
            denial = None
        else:
            brief = None if service.hash_verified(row) else rules.BRIEF_TAMPERED
            author = rules.is_author(self.user_id, service.brief_author_refs(data, row))
            denial = self.authority(row)[0]
        state_ok = rules.state_allows(state, current is not None)
        refusal = rules.sign_refusal(
            administrator=self.administrator,
            entitled=self.entitled,
            brief=brief,
            state_ok=state_ok,
            state_label=states.state_label(state),
            authority_denial=denial,
            author=author,
        )
        decided_here = current is not None and row is not None and current.brief_version_id == row.id
        return_refusal = None
        if not self.may_sign_permission:
            return_refusal = "Your role does not allow deciding on cases"
        elif self.administrator:
            return_refusal = rules.ADMINISTRATOR_DENIED[1]
        elif row is None or brief is not None:
            return_refusal = (brief or rules.STALE_BRIEF)[1]
        elif decided_here:
            return_refusal = "The current decision was signed on this version of the brief"
        elif not state_ok:
            return_refusal = rules.state_refusal(states.state_label(state))[1]
        elif denial is not None:
            return_refusal = denial[1]
        elif author:
            return_refusal = rules.AUTHOR_DENIED[1]
        can_sign = refusal is None
        can_return = return_refusal is None
        return {
            "can_sign": can_sign,
            "can_return": can_return,
            "reason": None if can_sign else refusal[1],
            "return_reason": return_refusal,
            "supersede_required": current is not None,
            "current_decision_id": str(current.id) if current is not None else None,
        }


# ------------------------------------------------------------------------------------------------------- queue


def _queue(data: Session, control_db: Session, tenant_id) -> list[dict]:
    """Approved brief versions waiting for a decision: on cases ready for decision, and newer approved versions of
    decided cases (or cases taken back to work) whose current decision is to be superseded. Most critical first,
    then by priority and by how long they have waited."""
    pairs = (
        data.query(DecisionBriefVersion, Investigation)
        .join(
            Investigation,
            (Investigation.id == DecisionBriefVersion.investigation_id)
            & (Investigation.tenant_id == DecisionBriefVersion.tenant_id),
        )
        .filter(
            DecisionBriefVersion.tenant_id == tenant_id,
            DecisionBriefVersion.status == brief_rules.APPROVED_FOR_DECISION,
            Investigation.workflow_state.in_(QUEUE_STATES),
            func.lower(func.coalesce(Investigation.status, "")) != "closed",
        )
        .all()
    )
    if not pairs:
        return []
    case_ids = list({case.id for _, case in pairs})
    currents: dict = {}
    for decision in (
        data.query(Decision)
        .filter(
            Decision.tenant_id == tenant_id,
            Decision.investigation_id.in_(case_ids),
            Decision.decision_kind == rules.DECISION_KIND,
            Decision.decision_status == rules.SIGNED,
            Decision.superseded_by_decision_id.is_(None),
        )
        .order_by(Decision.decided_at.desc().nulls_last())
    ):
        currents.setdefault(decision.investigation_id, decision)
    decided_briefs = service.briefs_by_id(data, tenant_id, [item.brief_version_id for item in currents.values()])
    waiting = []
    for row, case in pairs:
        state = states.case_state(case)
        current = currents.get(case.id)
        if current is not None and current.brief_version_id == row.id:
            continue  # this version is already decided
        if state != "READY_FOR_DECISION":
            decided = decided_briefs.get(str(current.brief_version_id)) if current is not None else None
            if current is None or (decided is not None and decided.version >= row.version):
                continue
        waiting.append((row, case, current))
    if not waiting:
        return []
    products = {
        str(item.id): item
        for item in data.query(Product.id, Product.business_id, Product.name).filter(
            Product.tenant_id == tenant_id, Product.id.in_(list({case.product_id for _, case, _ in waiting}))
        )
    }
    people = service.names(control_db, tenant_id, [row.reviewed_by for row, _, _ in waiting])
    items = []
    for row, case, current in waiting:
        content = row.content or {}
        product = products.get(str(case.product_id))
        items.append(
            {
                "investigation": {
                    "id": str(case.id),
                    "business_id": case.business_id,
                    "question": case.investigation_question,
                    "priority": case.priority,
                    "due_at": _iso(case.due_at),
                    "workflow_state": states.case_state(case),
                    "workflow_state_label": states.state_label(states.case_state(case)),
                    "product": {
                        "id": str(case.product_id) if case.product_id else None,
                        "business_id": product.business_id if product is not None else None,
                        "name": product.name if product is not None else None,
                    },
                },
                "brief": service.brief_summary(row, people),
                "critical": rules.is_critical(case.priority, service.serious_harm(data, case)),
                "required_reviews": rules.required_reviews(content),
                "awaiting_since": _iso(row.reviewed_at or row.submitted_at or row.updated_at),
                "supersedes": (
                    {"id": str(current.id), "business_id": current.business_id} if current is not None else None
                ),
                "_row": row,
                "_case": case,
                "_current": current,
                "_due_at": case.due_at,
                "_waiting": row.reviewed_at or row.submitted_at or row.updated_at,
            }
        )
    items.sort(
        key=lambda item: (
            not item["critical"],
            states.PRIORITY_RANK.get(str(item["_case"].priority or "").upper(), len(states.PRIORITY_RANK)),
            item["_waiting"] or states.now_utc(),
            item["investigation"]["business_id"] or "",
        )
    )
    return items


def _priority_level(item: dict) -> int | None:
    """The case's priority from low (1) to critical (4), for the queue's Priority column."""
    rank = states.PRIORITY_RANK.get(str(item["_case"].priority or "").upper())
    return None if rank is None else len(states.PRIORITY_RANK) - rank


# What each column of the approvals queue (the screen's queueRow keys) sorts on.
QUEUE_SORTS = {
    "caseId": lambda item: item["investigation"]["business_id"],
    "product": lambda item: item["investigation"]["product"]["name"] or item["investigation"]["product"]["business_id"],
    "brief": lambda item: (item["brief"] or {}).get("business_id"),
    "priority": _priority_level,
    "dueAt": lambda item: item["_due_at"],
    "awaitingSince": lambda item: item["_waiting"],
    "reviews": lambda item: ", ".join(str(review.get("label") or "") for review in item["required_reviews"]),
}


def _public(item: dict, data: Session, decider: Decider | None) -> dict:
    result = {key: value for key, value in item.items() if not key.startswith("_")}
    if decider is not None:
        actions = decider.evaluate(data, item["_case"], item["_row"], item["_current"])
        result["actions"] = {"can_decide": actions["can_sign"], "reason": actions["reason"]}
    return result


@router.get(LIST_BASE + "/queue", dependencies=[Depends(require_permission(DECISION_SIGN))])
def decision_queue(
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: str | None = Query(default=None, max_length=60),
    order: str | None = Query(default=None, max_length=10),
    data: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """One page of the briefs waiting for the decision maker, most critical first; ``sort`` (a column: caseId,
    product, brief, priority, dueAt, awaitingSince, reviews) with ``order`` (asc or desc) orders the whole queue by
    that column before it is cut into pages."""
    decider = Decider(control_db, ctx)
    items = sort_rows(_queue(data, control_db, _tenant_id(ctx)), sort, order, QUEUE_SORTS)
    start = (page - 1) * page_size
    return {
        "items": [_public(item, data, decider) for item in items[start : start + page_size]],
        "total": len(items),
        "page": page,
        "page_size": page_size,
    }


@router.get(LIST_BASE + "/summary", dependencies=[Depends(require_permission(DECISION_SIGN))])
def decision_summary(
    data: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The decision maker's dashboard: what waits for a signature (critical, due soon, overdue), decisions signed and
    briefs sent back in the last 30 days, open and overdue follow-ups, open impact assessments, and the latest
    decisions."""
    tenant_id = _tenant_id(ctx)
    now = states.now_utc()
    since = now - timedelta(days=RECENT_DAYS)
    decider = Decider(control_db, ctx)
    items = _queue(data, control_db, tenant_id)
    due_soon = now + timedelta(days=DUE_SOON_DAYS)
    signed = (
        data.query(Decision)
        .filter(Decision.tenant_id == tenant_id, Decision.decision_kind == rules.DECISION_KIND)
        .filter(Decision.decided_at >= since)
    )
    returned = (
        data.query(BriefReviewAction.id)
        .filter(
            BriefReviewAction.tenant_id == tenant_id,
            BriefReviewAction.action == "RETURN_FOR_ANALYSIS",
            BriefReviewAction.comment.like(rules.RETURN_PREFIX + "%"),
            BriefReviewAction.created_at >= since,
        )
        .count()
    )
    rejected = signed.filter(Decision.outcome == rules.REJECT_CONCLUSION).count()
    open_follow_ups = data.query(DecisionFollowUp).filter(
        DecisionFollowUp.tenant_id == tenant_id, DecisionFollowUp.status.in_(("OPEN", "IN_PROGRESS"))
    )
    recent = (
        data.query(Decision, Investigation.business_id)
        .join(
            Investigation,
            (Investigation.id == Decision.investigation_id) & (Investigation.tenant_id == Decision.tenant_id),
        )
        .filter(Decision.tenant_id == tenant_id, Decision.decision_kind == rules.DECISION_KIND)
        .order_by(Decision.decided_at.desc().nulls_last())
        .limit(SUMMARY_LIST_LIMIT)
        .all()
    )
    people = service.names(control_db, tenant_id, [decision.decided_by_user_id for decision, _ in recent])
    return {
        "counts": {
            "awaiting_signature": len(items),
            "critical": sum(1 for item in items if item["critical"]),
            "due_soon": sum(1 for item in items if item["_due_at"] is not None and now <= item["_due_at"] <= due_soon),
            "overdue": sum(1 for item in items if item["_due_at"] is not None and item["_due_at"] < now),
            "signed_30d": signed.count(),
            # Briefs the decision maker sent back: returned without a signature, or a signed rejection.
            "returned_30d": returned + rejected,
            "follow_ups_open": open_follow_ups.count(),
            "follow_ups_overdue": open_follow_ups.filter(DecisionFollowUp.due_at < now).count(),
            "impact_assessments_open": data.query(ImpactAssessment.id)
            .filter(ImpactAssessment.tenant_id == tenant_id, ImpactAssessment.status == "OPEN")
            .count(),
        },
        "awaiting": [_public(item, data, decider) for item in items[:SUMMARY_LIST_LIMIT]],
        "recent": [
            {
                "id": str(decision.id),
                "decision_id": str(decision.id),
                "business_id": decision.business_id,
                "investigation_id": str(decision.investigation_id),
                "investigation_business_id": case_business_id,
                "outcome": decision.outcome,
                "outcome_label": rules.outcome_label(decision.outcome),
                "decision_status": decision.decision_status,
                "decided_at": _iso(decision.decided_at),
                "signer_name": people.get(str(decision.decided_by_user_id)) if decision.decided_by_user_id else None,
            }
            for decision, case_business_id in recent
        ],
    }


# ------------------------------------------------------------------------------------------------ decision screen


def _screen(data: Session, control_db: Session, ctx: AuthenticatedRequestContext, case: Investigation) -> dict:
    row = service.approved_brief(data, case) or service.latest_brief(data, case)
    current = service.current_decision(data, case)
    decisions = service.case_decisions(data, case)
    people = service.names(
        control_db,
        case.tenant_id,
        [
            *((row.created_by, row.submitted_by, row.reviewed_by) if row is not None else ()),
            *(decision.decided_by_user_id for decision in decisions),
        ],
    )
    briefs = service.briefs_by_id(data, case.tenant_id, [decision.brief_version_id for decision in decisions])
    approved = row if row is not None and row.status == brief_rules.APPROVED_FOR_DECISION else None
    actions = Decider(control_db, ctx).evaluate(data, case, approved, current)
    business_ids = {str(decision.id): decision.business_id for decision in decisions}
    outcomes = rules.outcome_options()
    for option in outcomes:
        # What the signature will say, built here so the screen shows the exact words that are signed.
        option["signature_meaning"] = (
            rules.signature_meaning(approved.business_id, approved.version, option["code"]) if approved else None
        )
    return {
        "investigation": service.investigation_view(data, case),
        "brief": service.brief_view(row, people),
        "reviewers": service.reviewers(data, control_db, row),
        "decisions": [service.decision_view(decision, people, briefs, business_ids) for decision in decisions],
        "legacy_decision_count": service.legacy_decision_count(data, case),
        "current_decision": (
            service.decision_view(current, people, briefs, business_ids) if current is not None else None
        ),
        "outcomes": outcomes,
        "follow_up_options": rules.follow_up_options(),
        "actions": actions,
    }


@router.get(CASE_BASE)
def decision_screen(
    investigation_id: uuid.UUID,
    data: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The decision screen of a case: its approved brief (else its latest version), who reviewed it, the case's
    decisions on briefs, the outcomes and follow-up actions to choose from, and what the signed-in person may do."""
    case = load_case(data, _tenant_id(ctx), investigation_id)
    return _screen(data, control_db, ctx, case)


# --------------------------------------------------------------------------------------------------------- signing


def _resolve_follow_ups(control_db: Session, case: Investigation, payload: rules.SignPayload, now) -> list[dict]:
    """Each chosen follow-up with its owner: the person named (an active colleague), else the role named, else the
    case owner, else the action's role queue; its title (default "<action> for <case>") and due date (default in 30
    days)."""
    from backend.app.role_codes import is_platform_admin_role
    from backend.app.workflow.people import find_user

    owner = None
    if payload.follow_ups and case.owner_ref:
        try:
            found = find_user(control_db, case.tenant_id, case.owner_ref)
        except Exception:
            logger.warning("The owner of case %s could not be read", case.id, exc_info=True)
            found = None
        owner = found.id if found is not None and not is_platform_admin_role(found.role) else None
    resolved = []
    for item in payload.follow_ups:
        assignee = None
        if item.assignee_user_id is not None:
            user = find_user(control_db, case.tenant_id, item.assignee_user_id)
            if user is None or is_platform_admin_role(user.role):
                raise error(
                    422,
                    "FOLLOW_UP_ASSIGNEE_INVALID",
                    "Assign each follow-up to an active colleague of your organization",
                )
            assignee = user.id
        role = None
        if assignee is None:
            if item.assigned_role:
                role = item.assigned_role
            elif owner is not None:
                assignee = owner
            else:
                role = rules.default_follow_up_role(item.action_type)
        label = rules.follow_up_label(item.action_type)
        resolved.append(
            {
                "action_type": item.action_type,
                "title": (item.title or f"{label} for {case.business_id}")[:300],
                "assignee_user_id": assignee,
                "assigned_role": role,
                "due_at": item.due_at or now + timedelta(days=rules.FOLLOW_UP_DUE_DAYS),
            }
        )
    return resolved


def _refusal_event(control_db: Session, tenant_id, actor: dict, case: Investigation, action: str, request, **details):
    control_db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(actor["user_id"]),
            action=action,
            entity_type="Investigation",
            entity_id=case.id,
            details={"attempt": "CASE_DECISION_SIGN", **{key: value for key, value in details.items() if value}},
            request=request,
        )
    )


def _refuse(control_db: Session, tenant_id, actor, case, request, status: int, code: str, message: str, **details):
    """Audit the refused signature (never a secret), commit it, and refuse."""
    _refusal_event(control_db, tenant_id, actor, case, details.pop("action", None) or code, request, **details)
    control_db.commit()
    raise HTTPException(status, detail={"code": code, "message": message})


def _move_case(data: Session, ctx, case: Investigation, target: str, reason: str, now, details: dict) -> None:
    from backend.app.decision_brief.router import _move_case as move

    move(data, ctx, case, target, reason, now, details)


def _author_task(
    data: Session, control_db: Session, case, row, *, title: str, actor: str, role, details: dict, correlation_id
):
    """The author's FOLLOW_UP task (a return) on the brief version; resubmitting a new version completes it."""
    from backend.app.decision_brief.router import _author_user_id

    task_service.create_task(
        data,
        case.tenant_id,
        task_type="FOLLOW_UP",
        title=title,
        source_type=service.BRIEF_SOURCE,
        source_id=row.id,
        investigation_id=case.id,
        assigned_user_id=_author_user_id(control_db, row),
        priority=states.normalize_priority(case.priority),
        created_by=actor,
        is_return=True,
        actor_role=role,
        details={"brief_version": row.version, **details},
        correlation_id=correlation_id,
    )


@router.post(CASE_BASE + "/sign")
def sign_decision(
    investigation_id: uuid.UUID,
    payload: rules.SignPayload,
    request: Request,
    data: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Sign the decision on the case's approved brief version. Refusals are audited (never with the password or
    code). On success the decision, its context snapshot, the signature, the follow-ups with their tasks, the
    supersede link and the case and brief changes are saved together; the response is the signed decision record."""
    governance = _governance()
    problem = rules.payload_problem(
        outcome=payload.outcome,
        rationale=payload.rationale,
        conditions=payload.conditions,
        follow_up_types=[item.action_type for item in payload.follow_ups],
        supersedes_decision_id=payload.supersedes_decision_id,
        supersede_reason=payload.supersede_reason,
    )
    if problem:
        raise error(422, "DECISION_INVALID", problem)
    actor = governance.session_actor(control_db, ctx)
    tenant = governance.tenant(control_db, actor)
    case = load_case(data, tenant.id, investigation_id, lock=True)
    brief_ref = str(payload.brief_version_id)

    def refuse(status: int, code: str, message: str, action: str | None = None):
        _refuse(
            control_db,
            tenant.id,
            actor,
            case,
            request,
            status,
            code,
            message,
            action=action,
            brief_version_id=brief_ref,
        )

    if _is_administrator(actor):
        refuse(403, *rules.ADMINISTRATOR_DENIED)
    if not governance.entitled(control_db, tenant):
        refuse(
            403, "DENIED_NOT_ENTITLED", "Tenant is not entitled to controlled signatures", "ENTITLEMENT_ACCESS_DENIED"
        )
    row = service.brief_version(data, case, payload.brief_version_id, lock=True)
    if row is None:
        refuse(404, "BRIEF_VERSION_NOT_FOUND", "This version of the brief does not belong to this case")
    brief_problem = rules.brief_problem(
        status=row.status,
        stored_hash=row.content_hash,
        sent_hash=payload.brief_content_hash,
        recomputed_hash=brief_rules.content_hash(row.content, row.narrative),
    )
    if brief_problem:
        refuse(409, *brief_problem)
    current = service.current_decision(data, case, lock=True)
    state = states.case_state(case)
    if not rules.state_allows(state, current is not None):
        refuse(409, *rules.state_refusal(states.state_label(state)))
    supersede = rules.supersede_problem(current.id if current is not None else None, payload.supersedes_decision_id)
    if supersede:
        refuse(409, *supersede)
    content = row.content or {}
    residual = rules.residual_unknowns(content)
    if residual and not payload.residual_unknowns_acknowledged:
        raise error(
            422,
            "RESIDUAL_UNKNOWNS_NOT_ACKNOWLEDGED",
            "The brief lists open questions or accepted limitations; acknowledge them before signing",
        )
    denial, signer_role = governance.approval_check(
        control_db, tenant.id, actor["roles"], service.approval_subject(row), actor["user_id"]
    )
    if denial:
        refuse(403, *denial)
    if rules.is_author(actor["user_id"], service.brief_author_refs(data, row)):
        refuse(403, *rules.AUTHOR_DENIED)
    now = states.now_utc()
    planned = _resolve_follow_ups(control_db, case, payload, now)
    governance.verify_signing_credentials(
        control_db,
        ctx,
        password=payload.password,
        mfa_code=payload.mfa_code,
        record_refusal=lambda action: _refusal_event(
            control_db, tenant.id, actor, case, action, request, brief_version_id=brief_ref
        ),
    )

    # ---- the decision, its snapshot and follow-ups (tenant data plane)
    user_id = str(actor["user_id"])
    role = role_code(signer_role)[:60] or None
    decision_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    evidence_hash = rules.evidence_set_hash(content)
    follow_up_actions = brief_rules.jsonable(planned)
    reviews = service.reviewers(data, control_db, row)
    snapshot = brief_rules.jsonable(
        {
            "decision_id": decision_id,
            "brief": {
                "id": row.id,
                "business_id": row.business_id,
                "version": row.version,
                "content_hash": row.content_hash,
            },
            "content": content,
            "narrative": row.narrative or {},
            "readiness": row.readiness or {},
            "evidence_set_hash": evidence_hash,
            "scope_version": row.scope_version,
            "reviews": reviews,
            "as_of": (content.get("context") or {}).get("as_of"),
            "decided_at": now,
            "signer": {"id": user_id, "role": role},
            "outcome": payload.outcome,
        }
    )
    snapshot_digest = rules.snapshot_hash(snapshot)
    conditions = (payload.conditions or None) if payload.outcome == rules.ACCEPT_WITH_CONDITIONS else None
    decision = Decision(
        id=decision_id,
        tenant_id=case.tenant_id,
        investigation_id=case.id,
        decision_identifier=service.next_identifier(data, case),
        decision_type=rules.DECISION_TYPE,
        disposition=payload.outcome,
        rationale=payload.rationale,
        product_id=case.product_id,
        decision_status=rules.SIGNED,
        human_decision=rules.outcome_label(payload.outcome),
        context_snapshot={"snapshot_id": str(snapshot_id), "snapshot_hash": snapshot_digest},
        updated_at=now,
        decision_timestamp=now,
        authorized_by_ref=user_id,
        created_at=now,
        decision_kind=rules.DECISION_KIND,
        brief_version_id=row.id,
        outcome=payload.outcome,
        conditions=conditions,
        follow_up_actions=follow_up_actions,
        residual_unknowns=brief_rules.jsonable(residual),
        decided_by_user_id=as_uuid(user_id),
        decided_under_role=role,
        approval_authority_id=service.authority_id(control_db, tenant.id, signer_role),
        decided_at=now,
        brief_content_hash=row.content_hash,
        evidence_set_hash=evidence_hash,
        context_snapshot_id=snapshot_id,
        ai_execution_refs=rules.ai_execution_refs(content),
        supersedes_decision_id=current.id if current is not None else None,
    )
    data.add(decision)
    data.flush()
    data.add(
        ContextSnapshot(
            id=snapshot_id,
            tenant_id=case.tenant_id,
            decision_id=decision_id,
            decision_version=row.content_hash,
            snapshot=snapshot,
            created_by=user_id,
            created_at=now,
        )
    )
    if current is not None:
        current.decision_status = rules.SUPERSEDED
        current.superseded_by_decision_id = decision_id
        current.superseded_at = now
        current.supersede_reason = payload.supersede_reason
    data.flush()
    priority = states.normalize_priority(case.priority)
    created_follow_ups = []
    for item in planned:
        follow_up = DecisionFollowUp(
            id=uuid.uuid4(),
            tenant_id=case.tenant_id,
            decision_id=decision_id,
            investigation_id=case.id,
            action_type=item["action_type"],
            title=item["title"],
            assignee_user_id=item["assignee_user_id"],
            assigned_role=item["assigned_role"],
            due_at=item["due_at"],
            status="OPEN",
            created_by=user_id,
            created_at=now,
            updated_at=now,
        )
        data.add(follow_up)
        data.flush()
        task = task_service.create_task(
            data,
            case.tenant_id,
            task_type="FOLLOW_UP",
            title=item["title"],
            source_type=service.FOLLOW_UP_SOURCE,
            source_id=follow_up.id,
            investigation_id=case.id,
            assigned_user_id=item["assignee_user_id"],
            assigned_role=item["assigned_role"],
            priority=priority,
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
            correlation_id=ctx.correlation_id,
        )
        follow_up.task_id = task.id
        created_follow_ups.append(follow_up)

    # ---- the case, the brief and the decision tasks
    case_details = {
        "brief_version_id": str(row.id),
        "brief_version": row.version,
        "decision_id": str(decision_id),
        "outcome": payload.outcome,
    }
    if payload.outcome == rules.REJECT_CONCLUSION:
        before = row.status
        row.status = brief_rules.RETURNED
        row.updated_at = now
        from backend.app.decision_brief.router import _audit as brief_audit

        brief_audit(
            data,
            ctx,
            row,
            "BRIEF_CONCLUSION_REJECTED_BY_DECISION",
            now,
            role=role,
            reason=payload.rationale,
            old_values={"status": before},
            new_values={"status": row.status},
            details={"decision_id": str(decision_id)},
        )
        _author_task(
            data,
            control_db,
            case,
            row,
            title=f"{case.business_id} brief v{row.version}: conclusion rejected by the decision maker",
            actor=user_id,
            role=role,
            details={
                "decision_action": rules.REJECT_CONCLUSION,
                "decision_id": str(decision_id),
                "comment": payload.rationale,
            },
            correlation_id=ctx.correlation_id,
        )
    _move_case(
        data,
        ctx,
        case,
        rules.case_state_after(payload.outcome),
        f"Decision on brief version {row.version}: {rules.outcome_label(payload.outcome).lower()}",
        now,
        case_details,
    )
    task_service.complete_tasks(
        data,
        case.tenant_id,
        source_type=service.BRIEF_SOURCE,
        source_id=row.id,
        task_types=["DECISION_APPROVAL"],
        outcome=payload.outcome,
        actor_ref=user_id,
        actor_role=role,
        correlation_id=ctx.correlation_id,
    )
    data.flush()

    # ---- the signature and its audit trail (control database)
    version = row.content_hash
    material = rules.signature_material(
        decision_id=decision_id,
        version=version,
        outcome=payload.outcome,
        remarks=payload.rationale,
        brief_version_id=row.id,
        evidence_set_hash=evidence_hash,
        snapshot_hash=snapshot_digest,
        conditions=conditions,
        follow_up_actions=follow_up_actions,
    )
    content_fingerprint = rules.fingerprint(material)
    record = SignedApprovalRecord(
        id=uuid.uuid4(),
        tenant_id=case.tenant_id,
        object_type="Decision",
        object_id=decision_id,
        object_version=version,
        decision_type=rules.DECISION_TYPE,
        decision=rules.SIGNATURE_CODES[payload.outcome],
        remarks=payload.rationale,
        signer_user_id=user_id,
        signer_role=signer_role,
        signature_meaning=rules.signature_meaning(row.business_id, row.version, payload.outcome),
        content_fingerprint=content_fingerprint,
        signature_hash=rules.signature_hash(content_fingerprint, user_id, version),
        status="SIGNED",
        signed_at=now,
        created_at=now,
    )
    control_db.add(record)
    control_db.add(
        make_audit_event(
            tenant_id=case.tenant_id,
            actor_ref=user_id,
            action="CASE_DECISION_SIGNED",
            entity_type="Decision",
            entity_id=decision_id,
            correlation_id=ctx.correlation_id,
            request=request,
            reason=payload.rationale,
            details={
                "signature_id": str(record.id),
                "fingerprint": content_fingerprint,
                "investigation_id": str(case.id),
                "brief_version_id": str(row.id),
                "brief_version": row.version,
                "brief_content_hash": version,
                "outcome": payload.outcome,
                "follow_ups": rules.follow_up_types(follow_up_actions),
                "supersedes_decision_id": str(current.id) if current is not None else None,
                "signer_role": role,
            },
            created_at=now,
        )
    )
    if current is not None:
        control_db.add(
            make_audit_event(
                tenant_id=case.tenant_id,
                actor_ref=user_id,
                action="CASE_DECISION_SUPERSEDED",
                entity_type="Decision",
                entity_id=current.id,
                correlation_id=ctx.correlation_id,
                request=request,
                reason=payload.supersede_reason,
                old_values={"decision_status": rules.SIGNED},
                new_values={"decision_status": rules.SUPERSEDED},
                details={"superseded_by_decision_id": str(decision_id), "investigation_id": str(case.id)},
                created_at=now,
            )
        )
    if data is control_db:
        control_db.commit()  # the shared plane: everything in one transaction
    else:
        # A dedicated plane: the signature and its audit trail first (as legacy signing does), then the decision.
        control_db.commit()
        try:
            data.commit()
        except Exception:
            logger.exception("Signature %s was saved but its decision %s was not", record.id, decision_id)
            raise
    _after_signing(data, control_db, case, decision, actor=actor, role=role, outcome=payload.outcome)
    return service.record_view(control_db, data, decision)


def _after_signing(data: Session, control_db: Session, case, decision: Decision, *, actor: dict, role, outcome) -> None:
    """What follows a saved signature and never undoes it: the case's signals record the decision (accepted or
    closed), and the case owner is told."""
    if outcome in rules.CONCLUDING:
        try:
            from backend.app.signals.hooks import on_case_decision_signed

            on_case_decision_signed(data, decision, actor_user_id=actor["user_id"], actor_role=role)
        except Exception:
            logger.exception("The signals of case %s could not record the decision", case.id)
    try:
        from backend.app.workflow.hooks import case_business_id

        if _governance()._notify(
            "notify_signoff_completed",
            control_db,
            tenant_id=case.tenant_id,
            decision_id=decision.id,
            investigation_id=case.id,
            decision="REJECT" if outcome == rules.REJECT_CONCLUSION else "APPROVE",
            signer_user_id=actor["user_id"],
            owner_ref=case.owner_ref,
            reference=decision.business_id,
            investigation_business_id=case_business_id(data, case.tenant_id, case.id),
        ):
            control_db.commit()
    except Exception:
        logger.exception("The owner of case %s could not be told about the decision", case.id)
        try:
            control_db.rollback()
        except Exception:
            logger.exception("The session could not be rolled back after a failed notification")


# --------------------------------------------------------------------------------------------------------- return


@router.post(CASE_BASE + "/return", dependencies=[Depends(require_permission(DECISION_SIGN))])
def return_brief(
    investigation_id: uuid.UUID,
    payload: rules.ReturnPayload,
    request: Request,
    data: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Send the approved brief back to its author for more analysis, without a signature: the brief is returned,
    the case goes back to work, the author gets a follow-up task and the decision task is completed."""
    governance = _governance()
    actor = governance.session_actor(control_db, ctx)
    tenant = governance.tenant(control_db, actor)
    case = load_case(data, tenant.id, investigation_id, lock=True)
    if _is_administrator(actor):
        raise error(403, *rules.ADMINISTRATOR_DENIED)
    row = service.brief_version(data, case, payload.brief_version_id, lock=True)
    if row is None:
        raise error(404, "BRIEF_VERSION_NOT_FOUND", "This version of the brief does not belong to this case")
    if row.status != brief_rules.APPROVED_FOR_DECISION:
        raise error(409, *rules.STALE_BRIEF)
    current = service.current_decision(data, case, lock=True)
    if current is not None and current.brief_version_id == row.id:
        raise error(409, "BRIEF_ALREADY_DECIDED", "The current decision was signed on this version of the brief")
    state = states.case_state(case)
    if not rules.state_allows(state, current is not None):
        raise error(409, *rules.state_refusal(states.state_label(state)))
    denial, decider_role = governance.approval_check(
        control_db, tenant.id, actor["roles"], service.approval_subject(row), actor["user_id"]
    )
    if denial:
        raise error(403, *denial)
    if rules.is_author(actor["user_id"], service.brief_author_refs(data, row)):
        raise error(403, *rules.AUTHOR_DENIED)
    from backend.app.decision_brief.router import _record_action

    now = states.now_utc()
    user_id = str(actor["user_id"])
    role = role_code(decider_role)[:60] or None
    before = row.status
    row.status = brief_rules.RETURNED
    row.updated_at = now
    comment = rules.RETURN_PREFIX + payload.comment
    _record_action(
        data,
        ctx,
        row,
        "RETURN_FOR_ANALYSIS",
        comment,
        role,
        now,
        from_status=before,
        to_status=row.status,
        by="DECISION_MAKER",
    )
    if state == "READY_FOR_DECISION":
        _move_case(
            data,
            ctx,
            case,
            "IN_PROGRESS",
            f"Brief version {row.version} returned by the decision maker",
            now,
            {"brief_version_id": str(row.id), "brief_version": row.version, "decision_action": "RETURN"},
        )
    task_service.complete_tasks(
        data,
        case.tenant_id,
        source_type=service.BRIEF_SOURCE,
        source_id=row.id,
        task_types=["DECISION_APPROVAL"],
        outcome="RETURNED",
        actor_ref=user_id,
        actor_role=role,
        reason=payload.comment,
        correlation_id=ctx.correlation_id,
    )
    _author_task(
        data,
        control_db,
        case,
        row,
        title=f"{case.business_id} brief v{row.version}: returned by the decision maker",
        actor=user_id,
        role=role,
        details={"decision_action": "RETURN", "comment": payload.comment},
        correlation_id=ctx.correlation_id,
    )
    data.add(
        make_audit_event(
            tenant_id=case.tenant_id,
            actor_ref=user_id,
            action="CASE_DECISION_RETURNED",
            entity_type="Investigation",
            entity_id=case.id,
            correlation_id=ctx.correlation_id,
            request=request,
            reason=payload.comment,
            details={
                "brief_version_id": str(row.id),
                "brief_version": row.version,
                "brief_content_hash": row.content_hash,
                "actor_role": role,
            },
            created_at=now,
        )
    )
    data.commit()
    return _screen(data, control_db, ctx, case)


# --------------------------------------------------------------------------------------------- the signed record


@router.get(LIST_BASE + "/{decision_id}/record")
def decision_record(
    decision_id: uuid.UUID,
    data: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The signed decision on a brief: the decision with its labels and names, its brief, its signature and the
    server's verification of it, its context snapshot, its follow-ups and its supersede links."""
    decision = data.query(Decision).filter(Decision.tenant_id == _tenant_id(ctx), Decision.id == decision_id).first()
    if decision is None or decision.decision_kind != rules.DECISION_KIND:
        raise error(404, "DECISION_NOT_FOUND", "Decision is not available for this tenant")
    return service.record_view(control_db, data, decision)
