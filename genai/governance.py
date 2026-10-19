"""Per-organization AI controls, applied to every model request in ``GenAIProvider.complete``.

* **Whose request.** Each HTTP request gets a scope (``begin_request_scope``, API middleware); the authenticated
  request context fills in the organization (``set_request_tenant``). Background code names it explicitly with
  ``tenant_scope``. In staging and production a model request with no organization is refused, so content is never
  sent without its owner's controls being checked.
* **Switch.** ``tenants.ai_processing_allowed`` off: no model is called and the features answer from rules.
* **Free trials.** An organization on the Free Trial plan never reaches a model during the product validation phase,
  whatever its switch says (the trial agreement, terms and privacy policy promise it; ``backend/app/ai_settings.py``
  also refuses to switch it on).
* **Budget.** Tokens used this calendar month (``ai_usage_monthly``) may not exceed the organization's
  ``ai_monthly_token_budget``, or ``MDARIX_GENAI_TENANT_MONTHLY_TOKENS`` when it has none.
* **Rest periods.** A provider that rate-limits or fails is skipped by every process until ``genai_provider_rest``
  says otherwise (``MDARIX_GENAI_SHARED_REST=false`` keeps rest periods per process, for tests).

Every refusal raises ``GenAIUnavailable``; callers already fall back to rule-based answers on it.
"""

from __future__ import annotations

import contextvars
import logging
import os
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger("mdarix.genai")

DEFAULT_MONTHLY_TOKENS = 2_000_000
# Holds {"tenant_id": ...} for the current request. A dict, so the authenticated request context (which FastAPI runs in
# a worker thread with a copy of the request's context) can fill it in for the handler that runs afterwards.
_scope: contextvars.ContextVar[dict | None] = contextvars.ContextVar("mdarix_genai_scope", default=None)


# ------------------------------------------------------------------------------------------------------- scope


def begin_request_scope() -> contextvars.Token:
    return _scope.set({})


def end_request_scope(token: contextvars.Token) -> None:
    _scope.reset(token)


def set_request_tenant(tenant_id) -> None:
    """Record the signed-in organization for this request's model calls (called by the request context)."""
    holder = _scope.get()
    if holder is not None and tenant_id:
        holder["tenant_id"] = str(tenant_id)


@contextmanager
def tenant_scope(tenant_id):
    """Model calls inside run for ``tenant_id`` (background jobs, scripts and tests)."""
    token = _scope.set({"tenant_id": str(tenant_id)} if tenant_id else {})
    try:
        yield
    finally:
        _scope.reset(token)


def current_tenant() -> str | None:
    holder = _scope.get()
    return (holder or {}).get("tenant_id")


# ------------------------------------------------------------------------------------------------------ checks


def monthly_budget(tenant_budget: int | None) -> int:
    if tenant_budget is not None:
        return int(tenant_budget)
    raw = os.getenv("MDARIX_GENAI_TENANT_MONTHLY_TOKENS", "").strip()
    return int(raw) if raw.isdigit() else DEFAULT_MONTHLY_TOKENS


def _month(now: datetime | None = None) -> date:
    now = now or datetime.now(timezone.utc)
    return date(now.year, now.month, 1)


def _session(tenant_id: str):
    from backend.app.db.session import RuntimeSessionLocal
    from backend.app.db.tenant_scope import bind_tenant

    # The least-privilege runtime role, so row-level security limits this to the organization's own rows.
    db = RuntimeSessionLocal()
    bind_tenant(db, uuid.UUID(tenant_id))
    return db


def usage(db, tenant_id, now: datetime | None = None) -> dict:
    """This month's AI use for one organization, with its switch and budget (for administrators)."""
    from backend.app.db.models.foundation import Tenant
    from backend.app.db.models.stage2 import AiUsageMonthly

    tenant = db.get(Tenant, uuid.UUID(str(tenant_id)))
    row = db.get(AiUsageMonthly, (uuid.UUID(str(tenant_id)), _month(now)))
    used = int(row.input_tokens + row.output_tokens) if row else 0
    budget = monthly_budget(tenant.ai_monthly_token_budget if tenant else None)
    return {
        "ai_processing_allowed": bool(tenant.ai_processing_allowed) if tenant else False,
        "monthly_token_budget": budget,
        "budget_is_default": tenant is None or tenant.ai_monthly_token_budget is None,
        "month": _month(now).isoformat(),
        "tokens_used": used,
        "requests": int(row.requests) if row else 0,
        "refused": int(row.refused) if row else 0,
        "estimated_cost": float(row.estimated_cost) if row else 0.0,
    }


def is_free_trial(db, tenant_id) -> bool:
    """Whether the organization is on the Free Trial plan, whose AI stays off during the product validation phase."""
    from backend.app.trial.service import trial_subscription

    return trial_subscription(db, uuid.UUID(str(tenant_id))) is not None


def check_allowed(estimated_tokens: int) -> str | None:
    """Raise GenAIUnavailable when this request's organization may not use a model now; returns its id (or None)."""
    from backend.app.runtime_env import is_production_like
    from genai.provider import GenAIUnavailable

    tenant_id = current_tenant()
    if tenant_id is None:
        if is_production_like():
            logger.error("A model request had no organization scope; refused")
            raise GenAIUnavailable("GENAI_NO_TENANT_SCOPE")
        return None
    db = _session(tenant_id)
    try:
        state = usage(db, tenant_id)
        if is_free_trial(db, tenant_id):
            refusal = "GENAI_OFF_FOR_FREE_TRIAL"
        elif not state["ai_processing_allowed"]:
            refusal = "GENAI_DISABLED_FOR_ORGANIZATION"
        elif state["tokens_used"] + estimated_tokens > state["monthly_token_budget"]:
            refusal = "GENAI_MONTHLY_BUDGET_REACHED"
        else:
            return tenant_id
        _add_usage(db, tenant_id, refused=1)
        db.commit()
    finally:
        db.close()
    logger.info("Model request refused for an organization: %s", refusal)
    if refusal == "GENAI_MONTHLY_BUDGET_REACHED":
        check_budget_thresholds(tenant_id, budget_refused=True)
    raise GenAIUnavailable(refusal)


def record_usage(tenant_id: str | None, input_tokens: int, output_tokens: int, cost: float) -> None:
    """Add one completed model request to the organization's monthly usage (never fails the request)."""
    if tenant_id is None:
        return
    try:
        db = _session(tenant_id)
        try:
            _add_usage(db, tenant_id, requests=1, input_tokens=input_tokens, output_tokens=output_tokens, cost=cost)
            db.commit()
        finally:
            db.close()
    except Exception:
        logger.exception("AI usage could not be recorded")
        return
    check_budget_thresholds(tenant_id)


# ------------------------------------------------------------------------------------------------ budget alerts

BUDGET_THRESHOLDS = (80, 100)
BUDGET_ALERT_ACTION = "AI_BUDGET_THRESHOLD_REACHED"


def _thresholds_due(tokens_used: int, budget: int, budget_refused: bool) -> list[int]:
    """Thresholds this month's use has reached. A request refused for the budget counts as 100% reached, even when
    the tokens already used are a little under it (the request would have gone over)."""
    if budget <= 0:
        return [100]
    due = [percent for percent in BUDGET_THRESHOLDS if tokens_used * 100 >= percent * budget]
    if budget_refused and 100 not in due:
        due.append(100)
    return due


def check_budget_thresholds(tenant_id: str, *, budget_refused: bool = False, now: datetime | None = None) -> list[int]:
    """Tell the organization's administrators (and, at 100%, the operators) once per month per threshold that its
    AI allowance is 80% or 100% used. Returns the thresholds announced now (empty when nothing new was reached).

    The "already announced" marker is an audit event (``AI_BUDGET_THRESHOLD_REACHED`` with the month and percent),
    so the announcement is part of the organization's record and no schema change is needed; an advisory lock per
    organization, month and threshold makes two concurrent requests announce it once. Never fails the request."""
    try:
        announced = _record_thresholds(tenant_id, budget_refused, now)
    except Exception:
        logger.exception("AI budget thresholds could not be checked")
        return []
    for percent, state in announced:
        _notify_threshold(tenant_id, percent, state)
    return [percent for percent, _ in announced]


def _record_thresholds(tenant_id: str, budget_refused: bool, now: datetime | None) -> list[tuple[int, dict]]:
    from sqlalchemy import text

    from backend.app.db.models.foundation import AuditEvent
    from backend.app.enterprise_audit import make_audit_event

    db = _session(tenant_id)
    try:
        state = usage(db, tenant_id, now)
        due = _thresholds_due(state["tokens_used"], state["monthly_token_budget"], budget_refused)
        announced = []
        organization = uuid.UUID(tenant_id)
        for percent in due:
            marker = {"month": state["month"], "percent": percent}
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": f"ai-budget:{tenant_id}:{state['month']}:{percent}"},
            )
            seen = (
                db.query(AuditEvent.id)
                .filter(
                    AuditEvent.tenant_id == organization,
                    AuditEvent.action == BUDGET_ALERT_ACTION,
                    AuditEvent.details.contains(marker),
                )
                .first()
            )
            if seen is not None:
                continue
            db.add(
                make_audit_event(
                    tenant_id=organization,
                    actor_ref="system:ai-governance",
                    action=BUDGET_ALERT_ACTION,
                    entity_type="Tenant",
                    entity_id=organization,
                    details={
                        **marker,
                        "tokens_used": state["tokens_used"],
                        "monthly_token_budget": state["monthly_token_budget"],
                    },
                )
            )
            announced.append((percent, state))
        db.commit()
        return announced
    finally:
        db.close()


def _notify_threshold(tenant_id: str, percent: int, state: dict) -> None:
    """The customer administrators' notice (backend/app/notifications.py) and, at 100%, an operator alert."""
    try:
        from backend.app.notifications import notify_ai_budget_threshold
    except ImportError:
        notify_ai_budget_threshold = None
        logger.warning("AI budget notice for administrators is not available (notifications helper missing)")
    if notify_ai_budget_threshold is not None:
        db = _session(tenant_id)
        try:
            notify_ai_budget_threshold(db, uuid.UUID(tenant_id), percent=percent)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("AI budget notice for administrators could not be queued")
        finally:
            db.close()
    if percent >= 100:
        try:
            from backend.app.alerts import send_alert

            # Counts only: alerts never carry customer records.
            send_alert(
                "AI monthly allowance used up",
                f"Organization {tenant_id} has used {state['tokens_used']} of {state['monthly_token_budget']} AI "
                f"tokens for {state['month']}; its model requests are refused until the allowance is raised or the "
                "month ends.",
            )
        except Exception:
            logger.exception("AI budget operator alert could not be sent")


def _add_usage(db, tenant_id, *, requests=0, refused=0, input_tokens=0, output_tokens=0, cost=0.0) -> None:
    from sqlalchemy.dialects.postgresql import insert

    from backend.app.db.models.stage2 import AiUsageMonthly

    now = datetime.now(timezone.utc)
    values = {
        "tenant_id": uuid.UUID(str(tenant_id)),
        "month": _month(now),
        "requests": requests,
        "refused": refused,
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "estimated_cost": round(float(cost), 4),
        "updated_at": now,
    }
    table = AiUsageMonthly.__table__
    statement = insert(table).values(**values)
    db.execute(
        statement.on_conflict_do_update(
            index_elements=[table.c.tenant_id, table.c.month],
            set_={
                "requests": table.c.requests + requests,
                "refused": table.c.refused + refused,
                "input_tokens": table.c.input_tokens + int(input_tokens),
                "output_tokens": table.c.output_tokens + int(output_tokens),
                "estimated_cost": table.c.estimated_cost + round(float(cost), 4),
                "updated_at": now,
            },
        )
    )


# -------------------------------------------------------------------------------------------- rest periods


def shared_rest_enabled() -> bool:
    return os.getenv("MDARIX_GENAI_SHARED_REST", "true").strip().lower() not in {"0", "false", "no", "off"}


def shared_rest_until() -> dict[str, float]:
    """Providers resting for every process: name -> epoch seconds (empty when disabled or unreadable)."""
    if not shared_rest_enabled():
        return {}
    try:
        from sqlalchemy import text

        from backend.app.db.session import runtime_engine

        with runtime_engine.connect() as connection:
            rows = connection.execute(
                text("SELECT provider, rest_until FROM genai_provider_rest WHERE rest_until > now()")
            ).all()
        return {row.provider: row.rest_until.timestamp() for row in rows}
    except Exception:
        logger.warning("Shared AI provider rest periods could not be read; using this process's only")
        return {}


def share_rest(provider: str, seconds: float, reason: str) -> None:
    """Tell every process to skip ``provider`` for ``seconds`` (best effort)."""
    if not shared_rest_enabled():
        return
    try:
        from sqlalchemy import text

        from backend.app.db.session import runtime_engine

        until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        with runtime_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO genai_provider_rest (provider, rest_until, reason, updated_at) "
                    "VALUES (:provider, :until, :reason, now()) ON CONFLICT (provider) DO UPDATE SET "
                    "rest_until = GREATEST(genai_provider_rest.rest_until, EXCLUDED.rest_until), "
                    "reason = EXCLUDED.reason, updated_at = now()"
                ),
                {"provider": provider[:40], "until": until, "reason": reason[:40]},
            )
    except Exception:
        logger.warning("Shared AI provider rest period could not be recorded for %s", provider)
