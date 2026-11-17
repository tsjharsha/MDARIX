"""AI governance on one screen (E1): what MDARIX AI may use, what it produced, and what people decided about it.

- ``GET /api/v1/admin/ai-governance``: the organization's own view, for a customer administrator or, in a free trial,
  the person who started it (``admin_or_trial_owner``, as the AI settings; everyone else 403). Read only: the approved
  providers from the vetted register (``genai/vetted_providers.json``) and the ones not used, the AI switches (changed
  on the AI settings screen, not here), the saved AI results and model calls with provider, model, prompt version,
  sources and review state, and the reviewers' agreement with every disagreement and its reason. Answers recorded
  with the sample (no model called) are counted apart from live ones.
- ``GET /api/v1/platform-admin/ai-governance``: the same register, and counts per organization (no record content).

``lock_for_signing`` is U7: the AI results of an investigation as they stand when a decision is signed (model,
provider, prompt version, sources, the reviewers' verdicts with reasons). The signing stores it in the decision's
context snapshot, whose hash the signature binds, so a later model or review change does not alter the signed record.

Nothing here is a claim about AI quality: counts and records only, "Not recorded" (None) where nothing was recorded.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, not_, or_
from sqlalchemy.orm import Session

from backend.app.ai_review import (
    NOT_A_MODEL,
    RULE_PROVIDER_PREFIXES,
    SUBJECT_CALL,
    SUBJECT_EXECUTION,
    SUBJECT_OBSERVATION,
    latest_reviews,
)
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.ai_records import AiCall, AiOutputReview
from backend.app.db.models.foundation import AIExecution
from backend.app.db.session import get_db
from backend.app.trial.sample_ai import PROVIDER as RECORDED_PROVIDER
from genai import vetted

router = APIRouter(prefix="/api/v1", tags=["AI governance"])

STATEMENT = "MDARIX never trains models on your data. AI proposals are never decisions: a person accepts, edits or rejects each one."
RECORDED_LABEL = "Recorded with the sample · no model was called"
DISAGREEMENTS = ("EDITED", "REJECTED")
LIST_MAX = 50
TRAINING_WORDS = {"no": "No", "opt_out_confirmed": "No (opt-out confirmed)"}
# From docs/compliance/AI_PROVIDER_REGISTER.md: never used for customer content.
NEVER_USED = (
    ("Paid-plan AI providers", "None approved yet: each needs a contract, no training and confirmed retention first."),
    ("Free models that may keep or train on requests", "Refused: they may keep requests or use them to train."),
    ("OpenRouter models ending :free", "Refused even when listed."),
)


# ------------------------------------------------------------------------------------------------- register


def providers(register: dict | None = None, today: date | None = None) -> dict:
    """The vetted register in plain words: approved providers (with why) and the ones not used (with why not)."""
    from genai.provider import trial_chain_names

    register = register if register is not None else vetted.load()
    chain = set(trial_chain_names())
    approved, not_used = [], []
    for row in register.get("providers") or ():
        name = str(row.get("provider") or "")
        if row.get("kind") == "gateway":
            approved.append(
                {
                    "name": name,
                    "kind": "Gateway on the MDARIX server",
                    "terms": row.get("terms_link"),
                    "checked_on": row.get("date_checked"),
                    "region": row.get("region"),
                    "trains_on_data": "No (forwards only to approved providers)",
                    "why": "Self-hosted software; passes a request only to an approved provider, which it must name.",
                    "in_trial_chain": name in chain,
                }
            )
            continue
        problem = vetted.upstream_problem(row, register, today)
        if problem:
            not_used.append({"name": name, "why": f"Not used: {problem}."})
            continue
        approved.append(
            {
                "name": name,
                "kind": "AI model provider",
                "terms": row.get("terms_link"),
                "checked_on": row.get("date_checked"),
                "region": row.get("region"),
                "trains_on_data": TRAINING_WORDS.get(row.get("trains_on_data"), "Not recorded"),
                "why": f"Commercial use allowed and no training on the data, from its terms checked on "
                f"{row.get('date_checked')}.",
                "warning": vetted.stale_warning(row, register, today),
                "in_trial_chain": name in chain,
            }
        )
    not_used += [{"name": name, "why": why} for name, why in NEVER_USED]
    return {"approved": approved, "not_used": not_used, "trial_chain": sorted(chain)}


# -------------------------------------------------------------------------------------------- shared reads


def _by_model():
    """Saved results a language model wrote (or the sample recorded): MDARIX's own rule engines left out."""
    return not_(
        or_(
            func.lower(func.coalesce(AIExecution.provider, "")).in_(sorted(NOT_A_MODEL)),
            *(func.lower(AIExecution.provider).like(f"{prefix}%") for prefix in RULE_PROVIDER_PREFIXES),
        )
    )


def sources(refs) -> list[str]:
    """The records a saved result names as its sources (``evidence_refs``: lists of identifiers). Pure."""
    found: list[str] = []
    for value in (refs or {}).values() if isinstance(refs, dict) else ():
        for item in value if isinstance(value, list) else ():
            if isinstance(item, (str, int)) and str(item) not in found:
                found.append(str(item))
    return found


def _observations(db: Session, tenant_id, run_ids) -> list:
    from backend.app.db.models.evidence_intelligence import EvidenceObservation

    if not run_ids:
        return []
    return (
        db.query(EvidenceObservation.id, EvidenceObservation.ai_execution_id, EvidenceObservation.statement)
        .filter(EvidenceObservation.tenant_id == tenant_id, EvidenceObservation.ai_execution_id.in_(list(run_ids)))
        .all()
    )


def _verdict(review: AiOutputReview | None, names: dict[str, str], about: str) -> dict:
    if review is None:
        return {"about": about, "state": "NOT_REVIEWED", "reason": None, "reviewer": None, "at": None}
    return {
        "about": about,
        "state": review.decision,
        "reason": review.reason,
        "reviewer": names.get(str(review.reviewer)),
        "at": review.created_at.isoformat() if review.created_at else None,
    }


def run_verdicts(db: Session, control_db: Session, tenant_id, runs) -> dict[str, list[dict]]:
    """Each saved result's latest verdicts: one per observation it proposed (each is reviewed on its own), else one
    for the result as a whole."""
    from backend.app.workflow.people import names_by_id

    observations = _observations(db, tenant_id, [run.id for run in runs])
    reviews = latest_reviews(db, tenant_id, SUBJECT_EXECUTION, [run.id for run in runs])
    reviews.update(latest_reviews(db, tenant_id, SUBJECT_OBSERVATION, [row.id for row in observations]))
    names = names_by_id(control_db, tenant_id, {row.reviewer for row in reviews.values()})
    result = {}
    for run in runs:
        mine = [row for row in observations if row.ai_execution_id == run.id]
        result[str(run.id)] = (
            [_verdict(reviews.get(str(row.id)), names, f"Observation: {row.statement}") for row in mine]
            if mine
            else [_verdict(reviews.get(str(run.id)), names, "The result as a whole")]
        )
    return result


def _states(verdicts: list[dict]) -> dict[str, int]:
    return dict(Counter(item["state"] for item in verdicts))


def lock_for_signing(db: Session, control_db: Session, case, in_brief) -> list[dict]:
    """U7: the case's AI results as they are now, for the signed decision's snapshot (never read back live)."""
    from backend.app.decision_brief import rules as brief_rules

    runs = (
        db.query(AIExecution)
        .filter(AIExecution.tenant_id == case.tenant_id, AIExecution.investigation_id == case.id, _by_model())
        .order_by(AIExecution.execution_timestamp, AIExecution.business_id)
        .all()
    )
    verdicts = run_verdicts(db, control_db, case.tenant_id, runs) if runs else {}
    return [
        {
            "ref": run.business_id,
            "what": brief_rules.ai_kind(run.provider, run.prompt_template_version),
            "provider": run.provider,
            "model": run.model_name,
            "model_version": run.model_version,
            "prompt_version": run.prompt_template_version,
            "at": run.execution_timestamp.isoformat() if run.execution_timestamp else None,
            "sources": sources(run.evidence_refs),
            "recorded": run.provider == RECORDED_PROVIDER,
            "in_signed_brief": run.business_id in set(in_brief or ()),
            "verdicts": verdicts[str(run.id)],
        }
        for run in runs
    ]


# ------------------------------------------------------------------------------------------ organization view


def _all_latest(sessions, tenant_id) -> dict[tuple[str, str], AiOutputReview]:
    """The latest review of every reviewed output, across the planes (a shared plane is one session: deduplicated)."""
    rows: dict = {}
    for session in {id(item): item for item in sessions}.values():
        for row in (
            session.query(AiOutputReview)
            .filter(AiOutputReview.tenant_id == tenant_id)
            .order_by(AiOutputReview.created_at.asc())
        ):
            rows[row.id] = row
    latest: dict = {}
    for row in sorted(rows.values(), key=lambda item: item.created_at):
        latest[(row.subject_type, row.subject_id)] = row
    return latest


def organization_view(db: Session, control_db: Session, tenant_id) -> dict:
    from backend.app.ai_settings import _settings
    from backend.app.decision_brief import rules as brief_rules
    from backend.app.db.models.foundation import AuthUser
    from backend.app.workflow.people import display_name, names_by_id

    tenant_id = uuid.UUID(str(tenant_id))
    settings = _settings(control_db, tenant_id)
    base = db.query(AIExecution).filter(AIExecution.tenant_id == tenant_id, _by_model())
    recorded_ids = {
        str(row.id) for row in base.filter(AIExecution.provider == RECORDED_PROVIDER).with_entities(AIExecution.id)
    }
    total = base.count()
    runs = base.order_by(AIExecution.execution_timestamp.desc()).limit(LIST_MAX).all()
    verdicts = run_verdicts(db, control_db, tenant_id, runs) if runs else {}
    calls = (
        control_db.query(AiCall)
        .filter(AiCall.tenant_id == tenant_id)
        .order_by(AiCall.created_at.desc())
        .limit(LIST_MAX)
    ).all()
    call_outcomes = dict(
        control_db.query(AiCall.outcome, func.count(AiCall.id))
        .filter(AiCall.tenant_id == tenant_id)
        .group_by(AiCall.outcome)
        .all()
    )

    latest = _all_latest((db, control_db), tenant_id)
    recorded_observations = {
        str(row.id) for row in _observations(db, tenant_id, [uuid.UUID(item) for item in recorded_ids])
    }
    recorded_subjects = recorded_ids | recorded_observations
    agreement = {"live": Counter(), "recorded": Counter()}
    disagreements = []
    by_id = {str(run.id): run for run in runs}
    names = names_by_id(control_db, tenant_id, {row.reviewer for row in latest.values()})
    for (subject_type, subject_id), row in latest.items():
        recorded = subject_id in recorded_subjects
        agreement["recorded" if recorded else "live"][row.decision] += 1
        if row.decision in DISAGREEMENTS:
            run = by_id.get(subject_id)
            disagreements.append(
                {
                    "subject_type": subject_type,
                    "ref": run.business_id if run is not None else None,
                    "decision": row.decision,
                    "reason": row.reason,
                    "reviewer": names.get(str(row.reviewer)),
                    "at": row.created_at.isoformat() if row.created_at else None,
                    "recorded": recorded,
                }
            )
    disagreements.sort(key=lambda item: item["at"] or "", reverse=True)

    people = None
    if settings["free_trial"]:
        # The per-person AI switch applies to free trials only (genai/governance.py).
        people = [
            {"name": display_name(user), "ai": "Active" if user.ai_access == "ACTIVE" else "Inactive"}
            for user in control_db.query(AuthUser)
            .filter(AuthUser.tenant_id == tenant_id, AuthUser.status == "ACTIVE")
            .order_by(AuthUser.display_name)
        ]
    return {
        "statement": STATEMENT,
        "recorded_label": RECORDED_LABEL,
        "providers": providers(),
        "controls": {
            "organization_on": bool(settings.get("ai_processing_allowed")),
            "free_trial": settings["free_trial"],
            "trial_chain_on": settings["trial_chain_on"],
            "features": [
                {"key": item.get("key"), "label": item.get("label"), "enabled": item.get("enabled")}
                for item in settings["features"]
            ],
            "people": people,
        },
        "outputs": {
            "live": total - len(recorded_ids),
            "recorded": len(recorded_ids),
            "items": [
                {
                    "id": str(run.id),
                    "ref": run.business_id,
                    "what": brief_rules.ai_kind(run.provider, run.prompt_template_version),
                    "at": run.execution_timestamp.isoformat() if run.execution_timestamp else None,
                    "provider": run.provider,
                    "model": run.model_name,
                    "prompt_version": run.prompt_template_version,
                    "sources": len(sources(run.evidence_refs)),
                    "reviews": _states(verdicts[str(run.id)]),
                    "recorded": run.provider == RECORDED_PROVIDER,
                }
                for run in runs
            ],
        },
        "calls": {
            "total": sum(call_outcomes.values()),
            "by_outcome": call_outcomes,
            "items": [
                {
                    "id": str(call.id),
                    "feature": call.feature,
                    "at": call.created_at.isoformat() if call.created_at else None,
                    "provider": call.upstream_provider or call.provider,
                    "model": call.upstream_model or call.model,
                    "prompt_version": call.prompt_version,
                    "sources": len(call.records or ()),
                    "outcome": call.outcome,
                    "review": (latest.get((SUBJECT_CALL, str(call.id))).decision)
                    if (SUBJECT_CALL, str(call.id)) in latest
                    else "NOT_REVIEWED",
                }
                for call in calls
            ],
        },
        "agreement": {
            "live": {key: agreement["live"].get(key, 0) for key in ("ACCEPTED", "EDITED", "REJECTED")},
            "recorded": {key: agreement["recorded"].get(key, 0) for key in ("ACCEPTED", "EDITED", "REJECTED")},
            "disagreements": disagreements[:LIST_MAX],
        },
    }


@router.get("/admin/ai-governance")
def organization_governance(
    request: Request, db: Session = Depends(get_data_plane_db), control_db: Session = Depends(get_db)
):
    from backend.app.access.authz import admin_or_trial_owner

    admin = admin_or_trial_owner(request, control_db)
    return organization_view(db, control_db, admin.tenant_id)


# ------------------------------------------------------------------------------------------- platform view


@router.get("/platform-admin/ai-governance")
def platform_governance(request: Request, db: Session = Depends(get_db)):
    """Every organization's AI switch, outputs (live and recorded apart) and review counts. No record content."""
    from backend.app.access.authz import _require_platform_admin
    from backend.app.db.models.foundation import Tenant

    _require_platform_admin(request, db)
    outputs: dict = {}
    for tenant_id, provider, count in (
        db.query(AIExecution.tenant_id, AIExecution.provider, func.count(AIExecution.id))
        .filter(_by_model())
        .group_by(AIExecution.tenant_id, AIExecution.provider)
    ):
        outputs.setdefault(tenant_id, Counter())["recorded" if provider == RECORDED_PROVIDER else "live"] += count
    for tenant_id, count in db.query(AiCall.tenant_id, func.count(AiCall.id)).group_by(AiCall.tenant_id):
        outputs.setdefault(tenant_id, Counter())["calls"] += count
    for tenant_id, decision in (
        db.query(AiOutputReview.tenant_id, AiOutputReview.decision)
        .distinct(AiOutputReview.tenant_id, AiOutputReview.subject_type, AiOutputReview.subject_id)
        .order_by(
            AiOutputReview.tenant_id,
            AiOutputReview.subject_type,
            AiOutputReview.subject_id,
            AiOutputReview.created_at.desc(),
        )
    ):
        outputs.setdefault(tenant_id, Counter())[decision] += 1
    tenants = {
        row.id: row
        for row in db.query(Tenant.id, Tenant.display_name.label("name"), Tenant.ai_processing_allowed).filter(
            Tenant.id.in_(list(outputs))
        )
    }
    rows = [
        {
            "tenant_id": str(tenant_id),
            "organization": tenants[tenant_id].name if tenant_id in tenants else None,
            "organization_on": bool(tenants[tenant_id].ai_processing_allowed) if tenant_id in tenants else None,
            **{key: counts.get(key, 0) for key in ("live", "recorded", "calls", "ACCEPTED", "EDITED", "REJECTED")},
        }
        for tenant_id, counts in outputs.items()
    ]
    rows.sort(key=lambda item: (-(item["live"] + item["calls"]), item["organization"] or ""))
    return {"statement": STATEMENT, "recorded_label": RECORDED_LABEL, "providers": providers(), "organizations": rows}
