"""The decision record and the decision-and-impact summary of a signed investigation decision (E3 + W6).

One read, built only from what was recorded: the signed decision record (service.record_view), the brief version it
was signed on (the evidence, hypotheses and AI disclosure the signer saw, its scope: versions, lots, markets), the
signing audit event (whether an authenticator code was checked), the case's AI proposals with their latest reviews,
the case's CAPAs with their effectiveness checks, and the product's risk file entries. Nothing is stored or derived
beyond counting and ordering: a part with no record says ``None`` or an empty list, and the screen says
"Not recorded". MDARIX never says an action worked: only a signed effectiveness check does (``worked``).
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy.orm import Session

from backend.app.human_decision import service

# Hypotheses a person judged against the evidence: rejected at the time the brief was composed.
REJECTED_STATUSES = ("CONTRADICTED", "RETIRED")
NO_CHECK = "No effectiveness check is planned yet."
TOO_EARLY = "Too early: the effectiveness check is planned for {on}. Only a signed check says an action worked."
NO_ACTION = "No CAPA or effectiveness check is recorded on this investigation yet."


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _mfa(control_db: Session, decision) -> bool | None:
    """Whether the signing checked an authenticator code, as its CASE_DECISION_SIGNED audit event says (None: the event
    does not say)."""
    from backend.app.db.models.foundation import AuditEvent

    details = (
        control_db.query(AuditEvent.details)
        .filter(
            AuditEvent.tenant_id == decision.tenant_id,
            AuditEvent.action == "CASE_DECISION_SIGNED",
            AuditEvent.entity_id == decision.id,
        )
        .scalar()
    )
    value = (details or {}).get("mfa_verified")
    return value if isinstance(value, bool) else None


def _ai_proposals(db: Session, case) -> list[dict]:
    """The case's saved AI results, each with the latest review of the result and of each observation it proposed:
    {ref, label, recorded, reviews: {ACCEPTED|EDITED|REJECTED|NOT_REVIEWED: count}}."""
    from backend.app import ai_review
    from backend.app.db.models.evidence_intelligence import EvidenceObservation
    from backend.app.db.models.foundation import AIExecution
    from backend.app.decision_brief import rules as brief_rules
    from backend.app.trial.sample_ai import PROVIDER as RECORDED

    runs = (
        db.query(AIExecution.id, AIExecution.business_id, AIExecution.provider, AIExecution.prompt_template_version)
        .filter(AIExecution.tenant_id == case.tenant_id, AIExecution.investigation_id == case.id)
        .order_by(AIExecution.execution_timestamp)
        .all()
    )
    if not runs:
        return []
    observations = (
        db.query(EvidenceObservation.id, EvidenceObservation.ai_execution_id)
        .filter(
            EvidenceObservation.tenant_id == case.tenant_id,
            EvidenceObservation.ai_execution_id.in_([run.id for run in runs]),
        )
        .all()
    )
    states = ai_review.review_states(db, case.tenant_id, ai_review.SUBJECT_EXECUTION, [run.id for run in runs])
    states.update(
        ai_review.review_states(db, case.tenant_id, ai_review.SUBJECT_OBSERVATION, [row.id for row in observations])
    )
    result = []
    for run in runs:
        mine = [str(row.id) for row in observations if row.ai_execution_id == run.id]
        # A run that proposed observations is reviewed one observation at a time; otherwise as a whole.
        counts = Counter(states.get(item, "NOT_REVIEWED") for item in (mine or [str(run.id)]))
        result.append(
            {
                "ref": run.business_id,
                "label": brief_rules.ai_kind(run.provider, run.prompt_template_version),
                "recorded": run.provider == RECORDED,
                "reviews": dict(counts),
            }
        )
    return result


def _capas(db: Session, case) -> list[dict]:
    """The case's CAPAs with their latest effectiveness check (round, status, planned day, signed time)."""
    from backend.app.db.models.capa_effectiveness import CapaEffectivenessCheck
    from backend.app.db.models.foundation import Capa

    capas = (
        db.query(Capa.id, Capa.capa_identifier, Capa.business_id, Capa.title, Capa.status, Capa.due_at)
        .filter(Capa.tenant_id == case.tenant_id, Capa.investigation_id == case.id)
        .order_by(Capa.capa_identifier)
        .all()
    )
    latest: dict = {}
    if capas:
        for check in (
            db.query(CapaEffectivenessCheck)
            .filter(
                CapaEffectivenessCheck.tenant_id == case.tenant_id,
                CapaEffectivenessCheck.capa_id.in_([row.id for row in capas]),
            )
            .order_by(CapaEffectivenessCheck.round)
        ):
            latest[check.capa_id] = check
    rows = []
    for capa in capas:
        check = latest.get(capa.id)
        rows.append(
            {
                "id": str(capa.id),
                "ref": capa.capa_identifier or capa.business_id,
                "title": capa.title,
                "status": capa.status,
                "due_at": _iso(capa.due_at),
                "check": (
                    {
                        "round": check.round,
                        "status": check.status,
                        "planned_on": _iso(check.planned_on),
                        "signed_at": _iso(check.signed_at),
                        "result_summary": check.result_summary,
                    }
                    if check is not None
                    else None
                ),
            }
        )
    return rows


def _risks(db: Session, case) -> list[dict]:
    from backend.app.db.models.foundation import Risk

    if not case.product_id:
        return []
    return [
        {"ref": row.risk_identifier, "description": row.description, "status": row.status}
        for row in db.query(Risk.risk_identifier, Risk.description, Risk.status)
        .filter(Risk.tenant_id == case.tenant_id, Risk.product_id == case.product_id)
        .order_by(Risk.risk_identifier)
    ]


def worked(capas: list[dict]) -> dict:
    """Whether it worked so far, from the CAPAs' checks only. Pure. A signed check gives its result; a planned one is
    too early; nothing planned says so."""
    checks = [(capa, capa["check"]) for capa in capas if capa["check"]]
    signed = [(capa, check) for capa, check in checks if check["signed_at"] and check["status"] != "PLANNED"]
    if signed:
        capa, check = max(signed, key=lambda pair: pair[1]["signed_at"])
        effective = check["status"] == "EFFECTIVE"
        return {
            "state": "EFFECTIVE" if effective else "NOT_EFFECTIVE",
            "text": f"{capa['ref']}: signed {'effective' if effective else 'not effective'} (round {check['round']}).",
            "on": check["signed_at"][:10],
        }
    planned = sorted((check["planned_on"], capa) for capa, check in checks if check["planned_on"])
    if planned:
        return {"state": "TOO_EARLY", "text": TOO_EARLY.format(on=planned[0][0]), "on": planned[0][0]}
    return {"state": "NOT_PLANNED", "text": NO_CHECK if capas else NO_ACTION, "on": None}


def next_steps(follow_ups: list[dict], capas: list[dict]) -> list[dict]:
    """What happens next, with dates, soonest first (undated last): open follow-ups and planned, unsigned checks. Pure."""
    items = [
        {
            "what": item.get("title") or item.get("action_label") or "Follow-up",
            "ref": item.get("business_id"),
            "kind": item.get("action_type"),
            "due": (item.get("due_at") or "")[:10] or None,
            "who": item.get("assignee_name") or item.get("assigned_role_label"),
        }
        for item in follow_ups
        if item.get("status") in ("OPEN", "IN_PROGRESS")
    ]
    for capa in capas:
        check = capa["check"]
        if check and check["status"] == "PLANNED" and not check["signed_at"]:
            items.append(
                {
                    "what": f"Effectiveness check of {capa['ref']} (round {check['round']})",
                    "ref": capa["ref"],
                    "kind": "EFFECTIVENESS_CHECK",
                    "due": check["planned_on"],
                    "who": None,
                }
            )
        elif capa["status"] and str(capa["status"]).lower() not in ("closed", "cancelled") and not check:
            items.append(
                {
                    "what": f"{capa['ref']}: {capa['title']}",
                    "ref": capa["ref"],
                    "kind": "CAPA",
                    "due": (capa["due_at"] or "")[:10] or None,
                    "who": None,
                }
            )
    return sorted(items, key=lambda item: (item["due"] is None, item["due"] or ""))


def _hypothesis(item: dict) -> dict:
    return {
        "ref": item.get("business_id"),
        "statement": item.get("statement"),
        "origin": item.get("origin"),
        "status_label": item.get("human_status_label") or item.get("ai_status_label"),
    }


def summary(control_db: Session, db: Session, case, decision) -> dict:
    """The decision record and the decision-and-impact summary of one signed decision on a brief."""
    from backend.app.db.models.reviews import DecisionBriefVersion

    record = service.record_view(control_db, db, decision)
    brief = (
        db.query(DecisionBriefVersion.content, DecisionBriefVersion.narrative)
        .filter(DecisionBriefVersion.tenant_id == case.tenant_id, DecisionBriefVersion.id == decision.brief_version_id)
        .first()
        if decision.brief_version_id
        else None
    )
    content = brief.content if brief is not None and isinstance(brief.content, dict) else {}
    narrative = brief.narrative if brief is not None and isinstance(brief.narrative, dict) else {}
    scope = content.get("scope") if isinstance(content.get("scope"), dict) else {}
    product = content.get("product") if isinstance(content.get("product"), dict) else {}
    ai = content.get("ai_assistance") if isinstance(content.get("ai_assistance"), dict) else {}
    alternatives = [item for item in content.get("alternative_hypotheses") or () if isinstance(item, dict)]
    signed = record["decision"]
    signature = record["signature"] or {}
    snapshot = record["snapshot"] or {}
    capas = _capas(db, case)
    follow_ups = record["follow_ups"]
    outcome = worked(capas)
    planned_checks = sorted(
        capa["check"]["planned_on"] for capa in capas if capa["check"] and capa["check"]["planned_on"]
    )
    leading = content.get("leading_hypothesis") if isinstance(content.get("leading_hypothesis"), dict) else None
    return {
        "investigation": {
            "id": str(case.id),
            "ref": case.investigation_identifier,
            "question": case.investigation_question,
        },
        "decision": {
            "id": signed["id"],
            "ref": signed["business_id"],
            "status": signed["decision_status"],
            "status_label": signed["decision_status_label"],
            "superseded_by": record["superseded_by"],
            "supersedes": record["supersedes"],
            "outcome": signed["outcome"],
            "outcome_label": signed["outcome_label"],
            "conclusion": narrative.get("proposed_conclusion") or None,
            "rationale": signed["rationale"] or None,
            "conditions": signed["conditions"],
            "root_cause_category_label": signed["root_cause_category_label"],
            "root_cause_attribution_label": signed["root_cause_attribution_label"],
            "brief_ref": signed["brief_business_id"],
            "brief_version": signed["brief_version"],
            "effective_on": (signed["decided_at"] or "")[:10] or None,
            # Not a field of the decision: the first planned effectiveness check is when the decision is looked at
            # again. None: not recorded.
            "review_on": planned_checks[0] if planned_checks else None,
        },
        "owner": {
            "name": signature.get("signer_name") or signed["decided_by_name"],
            "role_label": signature.get("signer_role_label") or signed["decided_under_role_label"],
            "authority_recorded": bool(signed["approval_authority_id"]),
        },
        "signature": {
            "ref": signature.get("business_id"),
            "name": signature.get("signer_name"),
            "role_label": signature.get("signer_role_label"),
            "signed_at": signature.get("signed_at"),
            "meaning": signature.get("signature_meaning"),
            "mfa_verified": _mfa(control_db, decision),
            "verification": (record["verification"] or {}).get("status"),
        }
        if signature
        else None,
        "evidence": {
            "supporting": [
                {"ref": item.get("evidence_business_id"), "title": item.get("title")}
                for item in content.get("supporting_evidence") or ()
                if isinstance(item, dict)
            ],
            "contradicting": [
                {"ref": item.get("evidence_business_id"), "title": item.get("title")}
                for item in content.get("contradicting_evidence") or ()
                if isinstance(item, dict)
            ],
            "fingerprint": snapshot.get("evidence_set_hash") or signed["evidence_set_hash"],
        },
        "ai": {
            "statement": ai.get("statement"),
            "in_brief": list(signed["ai_execution_refs"]),
            "proposals": _ai_proposals(db, case),
        },
        "hypotheses": {
            # What the signer ticked as the root cause, as bound into the signed snapshot.
            "accepted": [
                {"ref": item.get("business_id"), "statement": item.get("statement")}
                for item in (snapshot.get("root_cause") or {}).get("hypotheses") or ()
                if isinstance(item, dict)
            ],
            "leading": _hypothesis(leading) if leading else None,
            "rejected": [
                _hypothesis(item)
                for item in alternatives
                if str(item.get("human_status") or "").upper() in REJECTED_STATUSES
            ],
            "alternatives": [
                _hypothesis(item)
                for item in alternatives
                if str(item.get("human_status") or "").upper() not in REJECTED_STATUSES
            ],
        },
        "affects": {
            "product": {"ref": product.get("business_id"), "name": product.get("name")} if product else None,
            "versions": [
                item.get("version_identifier") for item in scope.get("product_versions") or () if isinstance(item, dict)
            ],
            "lots": sorted(item.get("lot_number") or "" for item in scope.get("lots") or () if isinstance(item, dict)),
            "markets": list(scope.get("markets") or ()),
            "complaints": scope.get("included_count"),
            "risks": _risks(db, case),
        },
        "follow_ups": follow_ups,
        "capas": capas,
        "next": next_steps(follow_ups, capas),
        "worked": outcome,
    }


def for_case(control_db: Session, db: Session, case) -> dict:
    """The case's current signed decision's summary, else ``{"investigation": ..., "decision": None}``."""
    decision = service.current_decision(db, case)
    if decision is None:
        return {
            "investigation": {
                "id": str(case.id),
                "ref": case.investigation_identifier,
                "question": case.investigation_question,
            },
            "decision": None,
        }
    return summary(control_db, db, case, decision)
