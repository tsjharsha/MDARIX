"""What other actions do to signals. Each function is called after its action is saved, runs inside a SAVEPOINT on
the same data-plane session and commits its own changes; a failure is logged and swallowed, so a signal can never
block or undo the action that caused it (the pattern of backend/app/workflow/tasks.run_hook).

- complaints imported (CSV import, trial import, connector sync): detection runs for that organization; after a CSV or
  trial import it runs after the response, in a session of its own (``detect_after_import``), and
  ``detection_pending`` says whether it is still to finish, so a screen can say "Finding signals" meanwhile; the
  import's embeddings are queued for the background service only once it has finished (trial/imports.py after_import);
- a decision signed on a case opened for signals: those signals record DECISION_RECORDED;
- a case closed: a signal whose cases are all closed is CLOSED; reopening the case opens its signals again;
- the demo workspace seeded or reset: detection runs so the demo has signals.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import Integer, func, or_
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


def detect_after_import(open_session, tenant_id, *, source: str, records: int = 0) -> dict | None:
    """``after_complaints_saved`` once the import has answered (a background task of the route): in a session of its
    own on the organization's data plane, bound to the organization exactly as the request's session
    (``backend.app.db.data_plane.open_tenant_data_session``), so row-level security applies as before. Never raises:
    a failure is logged and the next scheduled run catches up, as when detection ran before the answer. The log line
    gives the import's size (``records``, its rows) and detection's time, counts only."""
    started = time.monotonic()
    try:
        with open_session(tenant_id) as db:
            result = after_complaints_saved(db, tenant_id, source=source)
        logger.info(
            "Signals after %s found in %.1f s (%d records imported, %s signals created, %s updated, tenant %s)",
            source,
            time.monotonic() - started,
            int(records or 0),
            len(result["created"]) if result else "no",
            len(result["updated"]) if result else "no",
            tenant_id,
        )
        return result
    except Exception:
        logger.exception("Signal detection after %s failed; the import itself is saved", source)
        return None


# The audit actions of an import (backend/app/data_import_router.py, backend/app/trial/router.py), and how long after
# one its detection is waited for: a run that failed is not announced for ever (the scheduled run catches up).
IMPORT_AUDIT_ACTIONS = ("DATA_IMPORTED", "TRIAL_DATA_IMPORTED")
PENDING_AT_MOST = timedelta(minutes=5)


def detection_pending(control_db: Session, data_db: Session, tenant_id, now: datetime | None = None) -> bool:
    """True while complaints imported in the last few minutes wait for the detection run that follows the import:
    the newest import that created or changed complaints (its audit record) is later than the organization's last
    detection run (``SignalRule.last_run_at``, written by every run, also when the rule is switched off)."""
    from backend.app.db.models.foundation import AuditEvent
    from backend.app.db.models.signals import SignalRule
    from backend.app.signals.labels import THRESHOLD_RULE

    tenant = as_uuid(tenant_id)
    if tenant is None:
        return False
    now = now or datetime.now(timezone.utc)
    details = AuditEvent.details
    try:
        imported = (
            control_db.query(func.max(AuditEvent.created_at))
            .filter(
                AuditEvent.tenant_id == tenant,
                AuditEvent.action.in_(IMPORT_AUDIT_ACTIONS),
                AuditEvent.created_at >= now - PENDING_AT_MOST,
                details["entity"].astext == "complaints",
                or_(
                    func.coalesce(details["created"].astext.cast(Integer), 0) > 0,
                    func.coalesce(details["updated"].astext.cast(Integer), 0) > 0,
                ),
            )
            .scalar()
        )
        if imported is None:
            return False
        last_run = (
            data_db.query(SignalRule.last_run_at)
            .filter(SignalRule.tenant_id == tenant, SignalRule.rule_code == THRESHOLD_RULE)
            .scalar()
        )
    except Exception:  # a status line must never fail the screen that shows it
        logger.exception("Whether signal detection is pending could not be read")
        control_db.rollback()
        data_db.rollback()
        return False
    return last_run is None or last_run < imported


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
