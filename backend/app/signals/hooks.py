"""What other actions do to signals. Each function is called after its action is saved, runs inside a SAVEPOINT on
the same data-plane session and commits its own changes; a failure is logged and swallowed, so a signal can never
block or undo the action that caused it (the pattern of backend/app/workflow/tasks.run_hook).

- complaints imported (CSV import, trial import, connector sync): detection runs for that organization;
- a decision signed on a case opened for signals: those signals record DECISION_RECORDED;
- a case closed: a signal whose cases are all closed is CLOSED; reopening the case opens its signals again;
- the demo workspace seeded or reset: detection runs so the demo has signals.
"""

from __future__ import annotations

import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.business_ids import as_uuid

logger = logging.getLogger("mdarix.signals")

# Signals that follow their case: closed with it, reopened with it, and told when its decision is signed.
FOLLOWS_CASE = ("INVESTIGATION_OPEN", "DECISION_RECORDED")
INVESTIGATION_WORK_PERMISSION = "investigation.work"


def _run(db: Session | None, name: str, step, *args, **kwargs):
    """Run ``step`` in a SAVEPOINT, then commit; a failure is logged, the session rolled back to a clean state and
    None returned."""
    if db is None:
        return None
    try:
        with db.begin_nested():
            result = step(db, *args, **kwargs)
        db.commit()
        return result
    except Exception:
        logger.exception("Signal hook %s failed; the action itself is saved", name)
        try:
            db.rollback()
        except Exception:
            logger.exception("Signal hook %s: the session could not be rolled back", name)
        return None


# ------------------------------------------------------------------------------------------------- detection


def after_complaints_saved(db: Session | None, tenant_id, *, source: str) -> dict | None:
    """Run detection for the organization once imported complaints are committed (``source`` names the import for
    the log). Returns the detection result, or None when it failed (the next scheduled run catches up)."""
    from backend.app.signals.detection import detect

    if as_uuid(tenant_id) is None:
        return None
    return _run(db, f"detection after {source}", lambda session: detect(session, tenant_id, apply=True))


def imported_complaints(result: dict | None) -> bool:
    """True when an import result (backend/app/trial/imports.py) created or changed complaints."""
    if not isinstance(result, dict) or result.get("entity") != "complaints":
        return False
    return bool(result.get("created") or result.get("updated"))


def seed_demo_signals(db: Session, tenant_id) -> None:
    """Detection for the demo workspace after its story is loaded, in a session of its own bound to the demo tenant
    (same database). Idempotent; a failure is logged and never fails the setup or the reset."""
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.signals.detection import detect

    try:
        with Session(bind=db.get_bind(), autoflush=False) as session:
            bind_tenant(session, tenant_id)
            detect(session, tenant_id, apply=True)
            session.commit()
    except Exception:
        logger.exception("The demo workspace's signals were not detected")


# --------------------------------------------------------------------------------------------------- cases


def _linked(session: Session, tenant_id, investigation_id, statuses, *, lock: bool = True):
    from backend.app.db.models.signals import InvestigationSignal, Signal

    linked = session.query(InvestigationSignal.signal_id).filter(
        InvestigationSignal.tenant_id == tenant_id, InvestigationSignal.investigation_id == investigation_id
    )
    query = session.query(Signal).filter(
        Signal.tenant_id == tenant_id, Signal.id.in_(linked), Signal.status.in_(statuses)
    )
    if lock:
        query = query.with_for_update()
    return query.order_by(Signal.id).all()


def on_case_decision_signed(db: Session | None, decision, *, actor_user_id, actor_role=None) -> None:
    """A decision signed on a case opened for signals: those signals still open on it record DECISION_RECORDED."""
    from backend.app.signals import service
    from backend.app.workflow.hooks import case_business_id

    def step(session):
        if decision.investigation_id is None:
            return
        case_reference = case_business_id(session, decision.tenant_id, decision.investigation_id)
        for signal in _linked(session, decision.tenant_id, decision.investigation_id, ("INVESTIGATION_OPEN",)):
            service.set_status(
                session,
                signal,
                "DECISION_RECORDED",
                "DECISION_RECORDED",
                actor_ref=str(actor_user_id),
                actor_role=actor_role,
                details={
                    "decision_business_id": decision.business_id,
                    "investigation_business_id": case_reference,
                    "decision_status": decision.decision_status,
                },
            )

    _run(db, "decision signed", step)


def on_investigation_status_changed(db: Session | None, control_db, case, *, actor_user_id, before_status) -> None:
    """Closing a case closes each signal it was opened for once all of that signal's cases are closed; reopening it
    moves its closed (or decided) signals back to INVESTIGATION_OPEN."""
    from backend.app.db.models.foundation import Investigation
    from backend.app.db.models.signals import InvestigationSignal
    from backend.app.signals import service
    from backend.app.workflow.people import acting_role

    was_closed = str(before_status or "").lower() == "closed"
    closed = str(case.status or "").lower() == "closed"
    if was_closed == closed:
        return

    def step(session):
        actor = str(actor_user_id)
        role = acting_role(control_db, case.tenant_id, actor, INVESTIGATION_WORK_PERMISSION)
        details = {"investigation_business_id": case.business_id}
        if not closed:
            for signal in _linked(session, case.tenant_id, case.id, ("CLOSED", "DECISION_RECORDED")):
                service.set_status(
                    session, signal, "INVESTIGATION_OPEN", "REOPENED", actor_ref=actor, actor_role=role, details=details
                )
            return
        for signal in _linked(session, case.tenant_id, case.id, FOLLOWS_CASE):
            still_open = (
                session.query(Investigation.id)
                .join(
                    InvestigationSignal,
                    (InvestigationSignal.tenant_id == Investigation.tenant_id)
                    & (InvestigationSignal.investigation_id == Investigation.id),
                )
                .filter(
                    InvestigationSignal.tenant_id == case.tenant_id,
                    InvestigationSignal.signal_id == signal.id,
                    func.lower(func.coalesce(Investigation.status, "")) != "closed",
                )
                .first()
            )
            if still_open is None:
                service.set_status(
                    session, signal, "CLOSED", "CLOSED", actor_ref=actor, actor_role=role, details=details
                )

    _run(db, "investigation status changed", step)
