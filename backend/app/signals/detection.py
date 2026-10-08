"""The complaint threshold rule, run for one organization at a time.

Complaints of the rule's window (event time, else received, else recorded, within the last ``window_days``) are grouped
by product, version and problem (backend/app/signals/logic.py). For each group, complaints not yet linked to a signal
about the same group are new: they are added to the group's open signal (a MONITOR signal goes back to TRIAGE with a
new triage task), or, without an open signal, ``min_complaints`` new ones raise a signal with a triage task in the
triage leads' queue. Monitored signals whose review date has come go back to TRIAGE too.

It is idempotent (a second run on the same data changes nothing) and serialized per organization by a transaction
advisory lock, so the scheduler, an import and the API can run it at the same time. One transaction per organization:
``detect`` does not commit; ``run_for_all_tenants`` (the scheduler job) commits each organization on its own.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import and_, text
from sqlalchemy.orm import Session

from backend.app.business_ids import as_uuid
from backend.app.db.models.foundation import Complaint, Product, ProductVersion
from backend.app.db.models.signals import OPEN_SIGNAL_STATUSES, Signal, SignalComplaint
from backend.app.signals import logic, service
from backend.app.signals.labels import DETECTION_ACTOR, THRESHOLD_RULE

logger = logging.getLogger("mdarix.signals")
LOCK_KEY = "mdarix-signal-detection:"


def _lock(db: Session, tenant_id) -> None:
    """Serialize detection runs of one organization until the transaction ends."""
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"{LOCK_KEY}{tenant_id}"})


def _linked_keys(db: Session, tenant_id, start) -> dict:
    """For each complaint of the window, the (product, version, problem) of every signal it is linked to."""
    rows = (
        db.query(SignalComplaint.complaint_id, Signal.product_id, Signal.product_version_id, Signal.problem_key)
        .join(Signal, and_(Signal.tenant_id == SignalComplaint.tenant_id, Signal.id == SignalComplaint.signal_id))
        .join(
            Complaint,
            and_(Complaint.tenant_id == SignalComplaint.tenant_id, Complaint.id == SignalComplaint.complaint_id),
        )
        .filter(SignalComplaint.tenant_id == tenant_id, service.COMPLAINT_EVENT_AT >= start)
    )
    linked: dict = {}
    for complaint_id, product_id, version_id, key in rows:
        linked.setdefault(complaint_id, set()).add((product_id, version_id, key))
    return linked


def _open_signals(db: Session, tenant_id) -> dict:
    """The open signal of each (product, version, problem): the oldest when several are open."""
    found: dict = {}
    for row in (
        db.query(Signal.id, Signal.product_id, Signal.product_version_id, Signal.problem_key)
        .filter(
            Signal.tenant_id == tenant_id,
            Signal.status.in_(OPEN_SIGNAL_STATUSES),
            Signal.product_id.isnot(None),
            Signal.problem_key.isnot(None),
        )
        .order_by(Signal.created_at, Signal.id)
    ):
        found.setdefault((row.product_id, row.product_version_id, row.problem_key), row.id)
    return found


def _names(db: Session, tenant_id, plans) -> tuple[dict, dict]:
    """Product names and version identifiers for the titles of new signals."""
    product_ids = {plan.key[0] for plan in plans if plan.key[0] is not None}
    if not product_ids:
        return {}, {}
    products = {
        str(key): name
        for key, name in db.query(Product.id, Product.name).filter(
            Product.tenant_id == tenant_id, Product.id.in_(product_ids)
        )
    }
    version_ids = {plan.key[1] for plan in plans if plan.key[1] is not None}
    versions = {}
    if version_ids:
        versions = {
            str(key): value
            for key, value in db.query(ProductVersion.id, ProductVersion.version_identifier).filter(
                ProductVersion.tenant_id == tenant_id, ProductVersion.id.in_(version_ids)
            )
        }
    return products, versions


def _back_to_triage(db: Session, signal: Signal, event_type: str, *, actor_ref, actor_role, details, now) -> None:
    """A monitored signal needs a new look: TRIAGE again, a fresh due date and a triage task in the queue."""
    service.set_status(
        db,
        signal,
        "TRIAGE",
        event_type,
        actor_ref=actor_ref,
        actor_role=actor_role,
        details=details,
        now=now,
    )
    signal.due_at = logic.due_at(logic.effective_priority(signal.confirmed_priority, signal.suggested_priority), now)
    service.queue_triage_task(db, signal, actor_ref=actor_ref, actor_role=actor_role, details={"reason": event_type})


def detect(
    db: Session,
    tenant_id,
    *,
    apply: bool = True,
    actor_ref: str | None = None,
    actor_role: str | None = None,
    correlation_id: str | None = None,
) -> dict:
    """Run the threshold rule for one organization. With ``apply`` the changes are written (not committed); without
    it nothing is written and the result says what a run would do (titles of the signals it would create).

    Returns ``{"created": [...], "updated": [...], "monitor_reopened": [...], "enabled", "rule_version",
    "min_complaints", "window_days"}`` with the business ids of the signals concerned."""
    tenant = as_uuid(tenant_id)
    if tenant is None:
        raise ValueError("Signal detection needs the organization's id")
    actor = str(actor_ref or DETECTION_ACTOR)
    if apply:
        _lock(db, tenant)
    settings = service.rule_settings(db, tenant)
    now = service.now_utc()
    result = {
        "created": [],
        "updated": [],
        "monitor_reopened": [],
        "enabled": settings["enabled"],
        "rule_version": settings["version"],
        "min_complaints": settings["min_complaints"],
        "window_days": settings["window_days"],
        "applied": apply,
    }
    if settings["enabled"]:
        _threshold(
            db,
            tenant,
            settings,
            result,
            apply=apply,
            actor=actor,
            actor_role=actor_role,
            now=now,
            correlation_id=correlation_id,
        )
    _monitor_reviews(db, tenant, result, apply=apply, actor=actor, actor_role=actor_role, now=now)
    if apply:
        service.rule_row(db, tenant).last_run_at = now
        db.flush()
    return result


def _threshold(db: Session, tenant, settings: dict, result: dict, *, apply, actor, actor_role, now, correlation_id):
    minimum, window = settings["min_complaints"], settings["window_days"]
    start = now - timedelta(days=window)
    facts = service.complaint_facts(
        service.complaint_facts_query(db, tenant).filter(
            Complaint.product_id.isnot(None), service.COMPLAINT_EVENT_AT >= start
        )
    )
    if not facts:
        return
    plans = [
        plan
        for plan in logic.plan_detection(facts, _linked_keys(db, tenant, start), _open_signals(db, tenant), minimum)
        if plan.action
    ]
    if not plans:
        return
    products, versions = _names(db, tenant, [plan for plan in plans if plan.action == "CREATE"])
    rule = {
        "code": THRESHOLD_RULE,
        "version": settings["version"],
        "parameters": {"min_complaints": minimum, "window_days": window},
    }
    for plan in plans:
        new_ids = [row.id for row in plan.new]
        if plan.action == "LINK":
            signal = service.load(db, tenant, plan.signal_id, lock=apply)
            if not apply:
                target = "monitor_reopened" if signal.status == "MONITOR" else "updated"
                result[target].append(signal.business_id)
                continue
            added = service.link_complaints(db, signal, new_ids, how="RULE", actor_ref=actor)
            if not added:
                continue
            service.recompute(db, signal, now=now)
            service.record(
                db,
                signal,
                "COMPLAINTS_ADDED",
                actor_ref=actor,
                actor_role=actor_role,
                details={"how": "RULE", "complaints": len(added), "rule_code": THRESHOLD_RULE},
                correlation_id=correlation_id,
                now=now,
            )
            if signal.status == "MONITOR":
                _back_to_triage(
                    db,
                    signal,
                    "MONITOR_TRIGGERED",
                    actor_ref=actor,
                    actor_role=actor_role,
                    details={"complaints": len(added)},
                    now=now,
                )
                result["monitor_reopened"].append(signal.business_id)
            else:
                service.update_open_task_schedule(db, signal)
                result["updated"].append(signal.business_id)
            continue
        product_id, version_id, key = plan.key
        title = logic.rule_title(
            len(plan.new), key, products.get(str(product_id)), versions.get(str(version_id)), window
        )
        if not apply:
            result["created"].append(title)
            continue
        signal = service.create_signal(
            db,
            tenant,
            title=title,
            origin="THRESHOLD_RULE",
            product_id=product_id,
            product_version_id=version_id,
            problem_key=key,
            complaint_ids=new_ids,
            added_how="RULE",
            actor_ref=actor,
            actor_role=actor_role,
            rule=rule,
            min_complaints=minimum,
            correlation_id=correlation_id,
        )
        result["created"].append(signal.business_id)


def _monitor_reviews(db: Session, tenant, result: dict, *, apply, actor, actor_role, now) -> None:
    query = db.query(Signal).filter(
        Signal.tenant_id == tenant,
        Signal.status == "MONITOR",
        Signal.monitor_review_date.isnot(None),
        Signal.monitor_review_date <= now.date(),
    )
    if apply:
        query = query.with_for_update()
    for signal in query.order_by(Signal.monitor_review_date, Signal.id).all():
        if apply:
            _back_to_triage(
                db,
                signal,
                "MONITOR_REVIEW_DUE",
                actor_ref=actor,
                actor_role=actor_role,
                details={"monitor_review_date": service.iso(signal.monitor_review_date)},
                now=now,
            )
        result["monitor_reopened"].append(signal.business_id)


# ------------------------------------------------------------------------------------------- every organization


def run_for_all_tenants(control_db: Session) -> dict:
    """The scheduler job: detection for every active organization, on the shared plane or its dedicated database
    (``open_tenant_data_session``), each committed on its own. A failing organization is logged and reported, and
    the others still run; the job then fails so the scheduler alerts after repeated failures."""
    from backend.app.customer_lifecycle import customer_allows_access_clause
    from backend.app.db.data_plane import open_tenant_data_session
    from backend.app.db.models.customer_lifecycle import TenantDataPlane
    from backend.app.db.models.foundation import Tenant

    totals = {"tenants": 0, "created": 0, "updated": 0, "monitor_reopened": 0, "failed": []}
    tenant_ids = [
        row.id
        for row in control_db.query(Tenant.id)
        .join(TenantDataPlane, TenantDataPlane.tenant_id == Tenant.id)
        .filter(
            Tenant.status.in_(["ACTIVE", "active"]),
            TenantDataPlane.status == "ACTIVE",
            # A suspended customer's tenants are skipped too (their own status is left as it is).
            customer_allows_access_clause(),
        )
        .order_by(Tenant.id)
        .all()
    ]
    for tenant_id in tenant_ids:
        try:
            with open_tenant_data_session(tenant_id) as data:
                try:
                    outcome = detect(data, tenant_id, apply=True)
                    data.commit()
                except Exception:
                    data.rollback()
                    raise
        except Exception as exc:
            logger.exception("Signal detection failed for organization %s", tenant_id)
            totals["failed"].append({"tenant_id": str(tenant_id), "error": type(exc).__name__})
            continue
        totals["tenants"] += 1
        for key in ("created", "updated", "monitor_reopened"):
            totals[key] += len(outcome[key])
    if totals["failed"]:
        raise RuntimeError(f"Signal detection failed for {len(totals['failed'])} organization(s): {totals['failed']}")
    return totals
