"""CAPA effectiveness check API: every CAPA's check, its plan, and its signed result.

Reading is open to every signed-in member of the organization. Planning a check (or re-planning it, with a reason)
needs investigation.work or quality.review; signing the result needs quality.review or decision.sign, the person's
current password and, when signatures require it, an authenticator code. Administrators never sign. The signature is
a signed approval record in the control database with the SHA-256 of exactly what was signed; every step is in the
audit trail.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.access.permissions import DECISION_SIGN, INVESTIGATION_WORK, QUALITY_REVIEW
from backend.app.capa_effectiveness import rules, service
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.capa_effectiveness import CapaEffectivenessCheck
from backend.app.db.models.foundation import SignedApprovalRecord
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import current_person, require_any_permission
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

logger = logging.getLogger("mdarix.capa_effectiveness")
router = APIRouter(prefix="/api/v1/capas", tags=["CAPA effectiveness"])

REMINDER_TASK = "EFFECTIVENESS_CHECK"
CAPA_SOURCE = "Capa"
ADMINISTRATOR_ROLES = frozenset({"PLATFORM_ADMIN", "ADMIN", "ADMINISTRATOR", "CUSTOMER_ADMIN"})


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def _collapse(value) -> str:
    return " ".join(str(value or "").split())


class PlanRequest(BaseModel):
    criteria: str = Field(max_length=rules.CRITERIA_MAX * 2)
    planned_on: date
    measured_from: date
    # Needed to change a plan already made (not for the first plan of a round).
    reason: str | None = Field(default=None, max_length=2000)

    @field_validator("criteria")
    @classmethod
    def _criteria(cls, value: str) -> str:
        return _collapse(value)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        return _collapse(value) or None


class ResultRequest(BaseModel):
    result: str = Field(max_length=20)
    summary: str = Field(max_length=rules.SUMMARY_MAX)
    # The plan the person read: a plan changed meanwhile is refused, so nobody signs what they did not see.
    plan_version: int = Field(ge=1)
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, max_length=12)

    @field_validator("result")
    @classmethod
    def _known(cls, value: str) -> str:
        result = str(value or "").strip().upper()
        if result not in rules.RESULTS:
            raise ValueError("result must be EFFECTIVE or NOT_EFFECTIVE")
        return result

    @field_validator("summary")
    @classmethod
    def _summary(cls, value: str) -> str:
        text = _collapse(value)
        if len(text) < rules.SUMMARY_MIN:
            raise ValueError(f"Say in at least {rules.SUMMARY_MIN} characters what you found")
        return text


@router.get("/effectiveness")
def effectiveness_board(
    show: str = Query("attention", pattern="^(attention|scheduled|done|all)$"),
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Every CAPA's effectiveness check, the ones needing attention first (overdue, due soon, never planned)."""
    return service.board(db, control_db, uuid.UUID(ctx.tenant_id), show=show, page=page, page_size=page_size)


@router.get("/{capa_id}/effectiveness")
def effectiveness_detail(
    capa_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    found = service.detail(db, control_db, uuid.UUID(ctx.tenant_id), capa_id)
    if found is None:
        raise _error(404, "CAPA_NOT_FOUND", "No such CAPA in your organization")
    return found


@router.put(
    "/{capa_id}/effectiveness/plan",
    dependencies=[Depends(require_any_permission(INVESTIGATION_WORK, QUALITY_REVIEW))],
)
def plan_check(
    capa_id: uuid.UUID,
    payload: PlanRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Plan the CAPA's effectiveness check, or change the plan of the current round (with a reason). After a
    NOT_EFFECTIVE result this plans the next round; after EFFECTIVE the check is done."""
    tenant_id = uuid.UUID(ctx.tenant_id)
    today = service.today_utc()
    capa = service.load_capa(db, tenant_id, capa_id, lock=True)
    if capa is None:
        raise _error(404, "CAPA_NOT_FOUND", "No such CAPA in your organization")
    if rules.is_excluded(capa.status):
        raise _error(409, "CAPA_NOT_ACTIVE", "This CAPA was cancelled or rejected; it needs no effectiveness check")
    problem = rules.plan_problem(payload.criteria, payload.planned_on, payload.measured_from, today)
    if problem:
        raise _error(422, "PLAN_INVALID", problem)
    rounds = service.rounds_of(db, tenant_id, capa_id)
    current = rounds[-1] if rounds else None
    if current is not None and current.status == rules.EFFECTIVE:
        raise _error(409, "CHECK_DONE", "This CAPA's effectiveness check is signed as effective")
    now = datetime.now(timezone.utc)
    if current is not None and current.status == rules.PLANNED:
        old = {
            "criteria": current.criteria,
            "planned_on": current.planned_on.isoformat(),
            "measured_from": current.measured_from.isoformat(),
        }
        new = {
            "criteria": payload.criteria,
            "planned_on": payload.planned_on.isoformat(),
            "measured_from": payload.measured_from.isoformat(),
        }
        if old == new:
            raise _error(422, "NOTHING_TO_CHANGE", "This is already the plan")
        if not payload.reason or len(payload.reason) < rules.REASON_MIN:
            raise _error(422, "REASON_REQUIRED", f"Say in at least {rules.REASON_MIN} characters why the plan changes")
        current.criteria, current.planned_on, current.measured_from = (
            payload.criteria,
            payload.planned_on,
            payload.measured_from,
        )
        current.plan_version = int(current.plan_version or 1) + 1
        current.planned_by, current.planned_at, current.updated_at = ctx.user_id, now, now
        row, action = current, "CAPA_EFFECTIVENESS_REPLANNED"
        old_values = {key: value for key, value in old.items() if old[key] != new[key]}
        new_values = {key: value for key, value in new.items() if old[key] != new[key]}
    else:
        row = CapaEffectivenessCheck(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            capa_id=capa_id,
            round=(current.round + 1) if current is not None else 1,
            status=rules.PLANNED,
            criteria=payload.criteria,
            planned_on=payload.planned_on,
            measured_from=payload.measured_from,
            plan_version=1,
            planned_by=ctx.user_id,
            planned_at=now,
            evidence={},
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        action, old_values = "CAPA_EFFECTIVENESS_PLANNED", None
        new_values = {
            "criteria": payload.criteria,
            "planned_on": payload.planned_on.isoformat(),
            "measured_from": payload.measured_from.isoformat(),
        }
    db.flush()
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action=action,
            entity_type="Capa",
            entity_id=capa_id,
            correlation_id=ctx.correlation_id,
            reason=payload.reason,
            details={"capa": capa.business_id or capa.capa_identifier, "round": row.round, "check_id": str(row.id)},
            old_values=old_values,
            new_values=new_values,
            created_at=now,
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _error(409, "CHANGED_MEANWHILE", "The check was changed a moment ago; reload and try again") from exc
    _refresh_reminder(db, capa, row, today, replanned=action == "CAPA_EFFECTIVENESS_REPLANNED", actor=ctx.user_id)
    return service.detail(db, control_db, tenant_id, capa_id)


def ensure_reminder(db: Session, capa, check: CapaEffectivenessCheck, today: date, actor: str = "system"):
    """The check's reminder task for the quality reviewers, once its day is near (DUE_SOON_DAYS) or past. It is not
    tied to the case, so closing the case leaves it open. Does not commit; idempotent."""
    from backend.app.workflow import tasks as task_service

    if check.status != rules.PLANNED or (check.planned_on - today).days > rules.DUE_SOON_DAYS:
        return None
    ref = capa.business_id or capa.capa_identifier
    return task_service.create_task(
        db,
        capa.tenant_id,
        task_type=REMINDER_TASK,
        title=f"Check the effectiveness of {ref}: {capa.title}",
        source_type=CAPA_SOURCE,
        source_id=capa.id,
        priority="HIGH" if check.planned_on < today else "MEDIUM",
        due_at=datetime.combine(check.planned_on, datetime.max.time().replace(microsecond=0), tzinfo=timezone.utc),
        created_by=actor,
        details={"capa_id": str(capa.id), "capa_business_id": ref, "check_id": str(check.id), "round": check.round},
    )


def _refresh_reminder(db: Session, capa, check, today: date, *, replanned: bool, actor: str) -> None:
    """After a plan: a changed day replaces the open reminder; a near day gets one now (the daily sweep does the rest)."""
    from backend.app.workflow import tasks as task_service

    def step(session: Session):
        if replanned:
            task_service.cancel_tasks(
                session,
                capa.tenant_id,
                source_type=CAPA_SOURCE,
                source_id=capa.id,
                task_types=[REMINDER_TASK],
                outcome="REPLANNED",
                actor_ref=actor,
                reason="The effectiveness check was re-planned",
            )
        return ensure_reminder(session, capa, check, today, actor)

    task_service.run_hook(db, "effectiveness check planned", step)


@router.post(
    "/{capa_id}/effectiveness/result",
    dependencies=[Depends(require_any_permission(QUALITY_REVIEW, DECISION_SIGN))],
)
def sign_result(
    capa_id: uuid.UUID,
    payload: ResultRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Sign the result of the current round: EFFECTIVE or NOT_EFFECTIVE, with what the person found. The recurrence
    shown at that moment is kept with the result and is part of what is signed."""
    from backend.app.governance_router import verify_signing_credentials
    from backend.app.human_decision.rules import fingerprint, signature_hash

    tenant_id = uuid.UUID(ctx.tenant_id)
    today = service.today_utc()
    capa = service.load_capa(db, tenant_id, capa_id)
    if capa is None:
        raise _error(404, "CAPA_NOT_FOUND", "No such CAPA in your organization")
    rounds = service.rounds_of(db, tenant_id, capa_id)
    current = rounds[-1] if rounds else None
    if current is None or current.status != rules.PLANNED:
        raise _error(409, "NO_PLANNED_CHECK", "Plan the effectiveness check before signing its result")
    if current.plan_version != payload.plan_version:
        raise _error(409, "PLAN_CHANGED", "The plan changed since you opened it; reload and read it again")
    person = current_person(control_db, ctx)
    role = person.role_for(QUALITY_REVIEW if person.holds(QUALITY_REVIEW) else DECISION_SIGN)
    if (role or "").upper() in ADMINISTRATOR_ROLES:
        raise _error(403, "ADMINISTRATOR_CANNOT_SIGN", "Administrators cannot sign effectiveness results")
    ref = capa.business_id or capa.capa_identifier
    check_id = current.id

    def refused(action: str) -> None:
        control_db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=ctx.user_id,
                action=action,
                entity_type="Capa",
                entity_id=capa_id,
                correlation_id=ctx.correlation_id,
                details={"attempt": "CAPA_EFFECTIVENESS_SIGN", "capa": ref, "check_id": str(check_id)},
            )
        )

    # Re-authenticate first: a refusal commits the control session, so nothing else may be pending in it yet.
    verify_signing_credentials(
        control_db, ctx, password=payload.password, mfa_code=payload.mfa_code, record_refusal=refused
    )

    now = datetime.now(timezone.utc)
    current = (
        db.query(CapaEffectivenessCheck)
        .filter(CapaEffectivenessCheck.tenant_id == tenant_id, CapaEffectivenessCheck.id == check_id)
        .with_for_update()
        .first()
    )
    if current is None or current.status != rules.PLANNED or current.plan_version != payload.plan_version:
        raise _error(409, "PLAN_CHANGED", "The check changed a moment ago; reload and read it again")
    evidence = service.measure(db, capa, current.measured_from, today)
    material = rules.signature_material(
        capa_id=str(capa.id),
        capa_ref=ref,
        check_id=str(current.id),
        round_number=current.round,
        criteria=current.criteria,
        planned_on=current.planned_on.isoformat(),
        measured_from=current.measured_from.isoformat(),
        result=payload.result,
        summary=payload.summary,
        evidence=evidence,
    )
    content_fingerprint = fingerprint(material)
    version = str(current.round)
    record = SignedApprovalRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        object_type=rules.OBJECT_TYPE,
        object_id=current.id,
        object_version=version,
        decision_type=rules.DECISION_TYPE,
        decision=rules.SIGNATURE_CODES[payload.result],
        remarks=payload.summary,
        signer_user_id=str(ctx.user_id),
        signer_role=role or "UNKNOWN",
        signature_meaning=rules.signature_meaning(ref, current.round, payload.result),
        content_fingerprint=content_fingerprint,
        signature_hash=signature_hash(content_fingerprint, str(ctx.user_id), version),
        status="SIGNED",
        signed_at=now,
        created_at=now,
    )
    control_db.add(record)
    control_db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="CAPA_EFFECTIVENESS_SIGNED",
            entity_type="Capa",
            entity_id=capa_id,
            correlation_id=ctx.correlation_id,
            reason=payload.summary,
            details={
                "capa": ref,
                "check_id": str(current.id),
                "round": current.round,
                "result": payload.result,
                "signature_id": str(record.id),
                "fingerprint": content_fingerprint,
                "signer_role": role,
                "signed_before_planned_day": current.planned_on > today,
            },
            new_values={"status": payload.result},
            created_at=now,
        )
    )
    current.status = payload.result
    current.result_summary = payload.summary
    current.evidence = evidence
    current.signature_id = record.id
    current.content_fingerprint = content_fingerprint
    current.signed_by, current.signer_role, current.signed_at = str(ctx.user_id), role, now
    current.updated_at = now
    try:
        if db is control_db:
            control_db.commit()  # the shared plane: everything in one transaction
        else:
            # A dedicated plane: the signature and its audit trail first (as decision signing does), then the result.
            control_db.commit()
            try:
                db.commit()
            except Exception:
                logger.exception(
                    "Signature %s was saved but its effectiveness result %s was not", record.id, current.id
                )
                raise
    except IntegrityError as exc:
        db.rollback()
        control_db.rollback()
        raise _error(409, "SIGNED_MEANWHILE", "This check was signed a moment ago; reload to see it") from exc
    _finish_reminder(db, capa, payload.result, ctx)
    return service.detail(db, control_db, tenant_id, capa_id)


def _finish_reminder(db: Session, capa, result: str, ctx) -> None:
    from backend.app.workflow import tasks as task_service

    task_service.run_hook(
        db,
        "effectiveness signed",
        lambda session: task_service.complete_tasks(
            session,
            capa.tenant_id,
            source_type=CAPA_SOURCE,
            source_id=capa.id,
            task_types=[REMINDER_TASK],
            outcome=result,
            actor_ref=ctx.user_id,
            correlation_id=ctx.correlation_id,
        ),
    )


def sweep_tenant(db: Session, tenant_id: uuid.UUID, today: date | None = None) -> int:
    """Reminder tasks for every planned check whose day is near or past (idempotent). Does not commit."""
    today = today or service.today_utc()
    horizon = today + timedelta(days=rules.DUE_SOON_DAYS)
    rows = (
        db.query(CapaEffectivenessCheck)
        .filter(
            CapaEffectivenessCheck.tenant_id == tenant_id,
            CapaEffectivenessCheck.status == rules.PLANNED,
            CapaEffectivenessCheck.planned_on <= horizon,
        )
        .all()
    )
    made = 0
    for check in rows:
        capa = service.load_capa(db, tenant_id, check.capa_id)
        if capa is None or rules.is_excluded(capa.status):
            continue
        # Only the latest round of a CAPA is current (an older PLANNED round cannot exist, but stay safe).
        if service.rounds_of(db, tenant_id, capa.id)[-1].id != check.id:
            continue
        from backend.app.workflow import tasks as task_service

        if task_service.has_open_task(
            db, tenant_id, task_type=REMINDER_TASK, source_type=CAPA_SOURCE, source_id=capa.id
        ):
            continue
        with db.begin_nested():
            if ensure_reminder(db, capa, check, today, "system:scheduler") is not None:
                made += 1
    return made
