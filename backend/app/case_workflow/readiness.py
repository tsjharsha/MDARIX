"""How far a case is from a decision: its steps (overview to human review) and the checks a decision depends on.

``evaluate`` turns the facts of a case into steps and checks without a database; ``case_facts`` reads those facts.
Reading is defensive: a fact that cannot be read (a table missing on an older organization database) is None and
shows as "could not be checked" instead of failing the page. Nothing here changes data.

The rules for evidence, evidence requests and open questions are shared with the investigator's dashboard
(``evidence_by_case``, ``requests_by_case``, ``unknowns_by_case``). The risk and regulatory review checks follow the
review policy and the case's latest reviews (backend/app/case_reviews/rules.py ``review_check``).
"""

from __future__ import annotations

import logging
from collections import defaultdict

from sqlalchemy.orm import Session

from backend.app.business_ids import as_uuid, wanted_ids

logger = logging.getLogger("mdarix.case_workflow")

STEP_STATUSES = ("DONE", "IN_PROGRESS", "NOT_STARTED", "BLOCKED", "NOT_AVAILABLE")
CHECK_RESULTS = ("PASS", "BLOCKED", "PENDING", "NOT_REQUIRED", "NOT_AVAILABLE")
STEPS = (
    ("overview", "Overview"),
    ("scope", "Scope"),
    ("evidence", "Evidence"),
    ("analysis", "Analysis"),
    ("hypotheses", "Hypotheses"),
    ("gaps", "Gaps and open questions"),
    ("risk_regulatory", "Risk and regulatory review"),
    ("brief", "Investigation brief"),
    ("human_review", "Human review and decision"),
)
CHECKS = (
    ("scope_complete", "Scope is complete"),
    ("evidence_reviewed", "Evidence is reviewed"),
    ("analysis_run", "Analysis has been run"),
    ("hypotheses_present", "Hypotheses are recorded"),
    ("contradictions_documented", "Contradicting evidence is judged"),
    ("unknowns", "Open questions are answered"),
    ("no_blocking_request", "No urgent evidence request is open"),
    ("risk_review", "Risk review"),
    ("regulatory_review", "Regulatory review"),
    ("brief_ready", "Investigation brief"),
    ("decision", "Decision"),
)
# Kept for callers of the earlier build; the review checks are evaluated from the case's reviews now.
NOT_YET_AVAILABLE = "Recorded once risk and regulatory reviews are available"
UNREADABLE = "Could not be checked right now"

# Evidence requests (supplier_evidence_requests), as backend/app/evidence_workflow/rules.py moves them: waiting for the
# answer (OPEN, ACKNOWLEDGED, PENDING_DELIVERY, SENT), answered and waiting for the requester's review (RECEIVED,
# REPLIED), or finished (REVIEWED, CANNOT_PROVIDE, CANCELLED). A request is open until it is finished.
REQUEST_FINISHED_STATUSES = frozenset({"REVIEWED", "CANNOT_PROVIDE", "CANCELLED"})
REQUEST_ANSWERED_STATUSES = frozenset({"RECEIVED", "REPLIED"})
BLOCKING_PRIORITIES = frozenset({"HIGH", "CRITICAL"})
# Unknowns (open questions) that no longer need an answer (accepted_limitation: the case accepts not knowing).
UNKNOWN_CLOSED_STATUSES = frozenset({"resolved", "accepted_limitation", "not_applicable", "superseded", "closed"})
# How many hypotheses a readiness rationale names before it says "and N more".
NAMED_MAX = 5
# A signed decision (approved or rejected by signature).
SIGNED_DECISION_STATUSES = frozenset({"APPROVED", "REJECTED"})


# ------------------------------------------------------------------------------------------------- pure rules


def request_is_open(status: str | None, reviewed_at=None) -> bool:
    return reviewed_at is None and str(status or "").upper() not in REQUEST_FINISHED_STATUSES


def request_is_answered(status: str | None, responded_at=None) -> bool:
    return responded_at is not None or str(status or "").upper() in REQUEST_ANSWERED_STATUSES


def unknown_is_open(status: str | None) -> bool:
    return str(status or "open").strip().lower() not in UNKNOWN_CLOSED_STATUSES


def evidence_counts(linked, direct) -> tuple[int, int]:
    """(total, unreviewed) of a case's evidence: ``linked`` are its ``(evidence_id, review_status)`` links, ``direct``
    the evidence recorded on the case itself. Direct evidence counts as unreviewed unless the case has reviewed it."""
    statuses: dict[str, str] = {}
    for evidence_id, review_status in linked:
        statuses[str(evidence_id)] = str(review_status or "UNREVIEWED").upper()
    everything = set(statuses) | {str(item) for item in direct}
    unreviewed = sum(1 for item in everything if statuses.get(item, "UNREVIEWED") == "UNREVIEWED")
    return len(everything), unreviewed


def _plural(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one if count == 1 else (many or one + 's')}"


def _named(names: list[str]) -> str:
    shown = ", ".join(names[:NAMED_MAX])
    return shown + (f" and {len(names) - NAMED_MAX} more" if len(names) > NAMED_MAX else "")


def _step(key: str, label: str, status: str, detail: str) -> dict:
    return {"key": key, "label": label, "status": status, "detail": detail}


def _check(key: str, label: str, result: str, rationale: str) -> dict:
    return {"key": key, "label": label, "result": result, "rationale": rationale}


def evaluate(facts: dict) -> dict:
    """Steps and checks from the facts of a case (see ``case_facts``; a fact of None could not be read)."""
    labels = dict(STEPS)
    check_labels = dict(CHECKS)
    scope = facts.get("scope")
    evidence = facts.get("evidence")
    requests = facts.get("requests")
    unknowns = facts.get("unknowns")
    analysis = facts.get("analysis_run")
    # Observations and hypotheses people recorded themselves: AI is never required for the analysis.
    people_analysis = int(facts.get("people_analysis") or 0)
    hypotheses = facts.get("hypotheses")
    contradictions = facts.get("contradictions")
    brief = facts.get("brief")
    decision = facts.get("decision")
    brief_decision = facts.get("brief_decision")

    steps: dict[str, dict] = {}
    checks: dict[str, dict] = {}

    question = bool(facts.get("question"))
    steps["overview"] = _step(
        "overview",
        labels["overview"],
        "DONE" if question else "IN_PROGRESS",
        "The case is open with its question" if question else "Write the question this case must answer",
    )

    if scope is None:
        steps["scope"] = _step("scope", labels["scope"], "NOT_STARTED", UNREADABLE)
        checks["scope_complete"] = _check("scope_complete", check_labels["scope_complete"], "PENDING", UNREADABLE)
    else:
        included = int(scope.get("included") or 0)
        complete = bool(scope.get("question")) and included > 0
        version = scope.get("version")
        steps["scope"] = _step(
            "scope",
            labels["scope"],
            "DONE" if complete else ("IN_PROGRESS" if scope.get("question") else "NOT_STARTED"),
            (f"Version {version}: " if version else "") + f"{_plural(included, 'complaint')} included"
            if complete
            else "Add the complaints this case covers",
        )
        checks["scope_complete"] = _check(
            "scope_complete",
            check_labels["scope_complete"],
            "PASS" if complete else "PENDING",
            "The scope has a question and its complaints"
            if complete
            else "Record the question and at least one included complaint",
        )

    blocking = int((requests or {}).get("blocking") or 0)
    if evidence is None:
        steps["evidence"] = _step("evidence", labels["evidence"], "NOT_STARTED", UNREADABLE)
        checks["evidence_reviewed"] = _check(
            "evidence_reviewed", check_labels["evidence_reviewed"], "PENDING", UNREADABLE
        )
    else:
        total, unreviewed = int(evidence.get("total") or 0), int(evidence.get("unreviewed") or 0)
        if blocking:
            status, detail = "BLOCKED", f"Waiting for {_plural(blocking, 'urgent evidence request')}"
        elif total == 0:
            status, detail = "NOT_STARTED", "No evidence on this case yet"
        elif unreviewed:
            status, detail = "IN_PROGRESS", f"{unreviewed} of {total} still to review"
        else:
            status, detail = "DONE", f"All {_plural(total, 'piece')} of evidence reviewed"
        steps["evidence"] = _step("evidence", labels["evidence"], status, detail)
        if total == 0:
            result, rationale = "PENDING", "No evidence on this case yet"
        elif unreviewed:
            result, rationale = "PENDING", f"{unreviewed} of {total} pieces of evidence are not reviewed yet"
        else:
            result, rationale = "PASS", f"All {_plural(total, 'piece')} of evidence are reviewed"
        checks["evidence_reviewed"] = _check("evidence_reviewed", check_labels["evidence_reviewed"], result, rationale)

    if analysis is None and not people_analysis:
        steps["analysis"] = _step("analysis", labels["analysis"], "NOT_STARTED", UNREADABLE)
        checks["analysis_run"] = _check("analysis_run", check_labels["analysis_run"], "PENDING", UNREADABLE)
    elif not analysis and people_analysis:
        steps["analysis"] = _step("analysis", labels["analysis"], "DONE", "People recorded their own analysis")
        checks["analysis_run"] = _check(
            "analysis_run",
            check_labels["analysis_run"],
            "PASS",
            f"People recorded {_plural(people_analysis, 'observation or hypothesis', 'observations and hypotheses')}",
        )
    else:
        steps["analysis"] = _step(
            "analysis",
            labels["analysis"],
            "DONE" if analysis else "NOT_STARTED",
            "An analysis has been run" if analysis else "No analysis yet",
        )
        checks["analysis_run"] = _check(
            "analysis_run",
            check_labels["analysis_run"],
            "PASS" if analysis else "PENDING",
            "An analysis has been run"
            if analysis
            else "Run an analysis of the case, or record observations and hypotheses yourself",
        )

    if hypotheses is None:
        steps["hypotheses"] = _step("hypotheses", labels["hypotheses"], "NOT_STARTED", UNREADABLE)
        checks["hypotheses_present"] = _check(
            "hypotheses_present", check_labels["hypotheses_present"], "PENDING", UNREADABLE
        )
    else:
        count = int(hypotheses)
        steps["hypotheses"] = _step(
            "hypotheses",
            labels["hypotheses"],
            "DONE" if count else "NOT_STARTED",
            f"{_plural(count, 'hypothesis', 'hypotheses')} recorded" if count else "No hypotheses yet",
        )
        checks["hypotheses_present"] = _check(
            "hypotheses_present",
            check_labels["hypotheses_present"],
            "PASS" if count else "PENDING",
            f"{_plural(count, 'hypothesis', 'hypotheses')} recorded" if count else "Record the possible causes",
        )

    if contradictions is None:
        checks["contradictions_documented"] = _check(
            "contradictions_documented", check_labels["contradictions_documented"], "PENDING", UNREADABLE
        )
    else:
        total = int(contradictions.get("total") or 0)
        undocumented = [str(item) for item in contradictions.get("undocumented") or ()]
        if undocumented:
            result = "PENDING"
            rationale = (
                f"Judge {_plural(len(undocumented), 'hypothesis', 'hypotheses')} with contradicting evidence: "
                + _named(undocumented)
            )
        elif total:
            result = "PASS"
            rationale = f"All {_plural(total, 'hypothesis', 'hypotheses')} with contradicting evidence are judged"
        else:
            result, rationale = "PASS", "No hypothesis has contradicting evidence"
        checks["contradictions_documented"] = _check(
            "contradictions_documented", check_labels["contradictions_documented"], result, rationale
        )

    if unknowns is None:
        steps["gaps"] = _step("gaps", labels["gaps"], "NOT_STARTED", UNREADABLE)
        checks["unknowns"] = _check("unknowns", check_labels["unknowns"], "PENDING", UNREADABLE)
    else:
        total, open_count = int(unknowns.get("total") or 0), int(unknowns.get("open") or 0)
        if open_count:
            status, detail = "IN_PROGRESS", f"{_plural(open_count, 'open question')}"
        elif total:
            status, detail = "DONE", f"All {_plural(total, 'question')} answered"
        else:
            status, detail = "NOT_STARTED", "No open questions recorded yet"
        steps["gaps"] = _step("gaps", labels["gaps"], status, detail)
        checks["unknowns"] = _check(
            "unknowns",
            check_labels["unknowns"],
            "PENDING" if open_count else "PASS",
            f"{_plural(open_count, 'open question')} still to answer" if open_count else "No open questions",
        )

    if requests is None:
        checks["no_blocking_request"] = _check(
            "no_blocking_request", check_labels["no_blocking_request"], "PENDING", UNREADABLE
        )
    else:
        checks["no_blocking_request"] = _check(
            "no_blocking_request",
            check_labels["no_blocking_request"],
            "BLOCKED" if blocking else "PASS",
            f"{_plural(blocking, 'high or critical evidence request')} still open"
            if blocking
            else "No high or critical evidence request is open",
        )
    _review_checks(facts.get("reviews"), steps, checks, labels, check_labels)

    if brief is None:
        steps["brief"] = _step("brief", labels["brief"], "NOT_STARTED", UNREADABLE)
        checks["brief_ready"] = _check("brief_ready", check_labels["brief_ready"], "PENDING", UNREADABLE)
    else:
        latest = brief.get("latest_version")
        steps["brief"] = _step(
            "brief",
            labels["brief"],
            "DONE" if latest else "NOT_STARTED",
            f"Version {latest} generated" if latest else "No brief yet",
        )
        checks["brief_ready"] = _check(
            "brief_ready",
            check_labels["brief_ready"],
            "PENDING",
            f"Brief version {latest} waits for its review" if latest else "No brief generated yet",
        )

    if brief_decision and int(brief_decision.get("briefs") or 0):
        # A case with a Decision Brief is decided by a signed decision on an approved brief version (Phase 6).
        status, result, text = _brief_decision_result(brief_decision)
        steps["human_review"] = _step("human_review", labels["human_review"], status, text)
        checks["decision"] = _check("decision", check_labels["decision"], result, text)
    elif decision is None:
        steps["human_review"] = _step("human_review", labels["human_review"], "NOT_STARTED", UNREADABLE)
        checks["decision"] = _check("decision", check_labels["decision"], "PENDING", UNREADABLE)
    else:
        count, signed = int(decision.get("count") or 0), int(decision.get("signed") or 0)
        if signed:
            status, result, text = "DONE", "PASS", "A decision is signed"
        elif count:
            status, result, text = "IN_PROGRESS", "PENDING", "A decision is recorded and waits for its signature"
        else:
            status, result, text = "NOT_STARTED", "PENDING", "No decision recorded yet"
        steps["human_review"] = _step("human_review", labels["human_review"], status, text)
        checks["decision"] = _check("decision", check_labels["decision"], result, text)

    return {
        "workflow_state": facts.get("workflow_state"),
        "steps": [steps[key] for key, _ in STEPS],
        "checks": [checks[key] for key, _ in CHECKS],
    }


# Outcomes of a signed decision on a brief that decide the case (a rejection sends it back to work).
DECIDING_OUTCOMES = frozenset({"ACCEPT_CONCLUSION", "ACCEPT_WITH_CONDITIONS", "CLOSE_NO_FURTHER_ACTION"})


def _brief_decision_result(fact: dict) -> tuple[str, str, str]:
    """``(step status, check result, text)`` of the decision on a case with a Decision Brief: PASS once its current
    signed decision accepts the conclusion or closes the case; PENDING otherwise."""
    outcome = str(fact.get("current_outcome") or "").upper()
    if outcome in DECIDING_OUTCOMES:
        from backend.app.human_decision.rules import outcome_label

        return "DONE", "PASS", f"A decision is signed: {outcome_label(outcome)}"
    if outcome == "REJECT_CONCLUSION":
        return "IN_PROGRESS", "PENDING", "The decision maker rejected the proposed conclusion; a new brief is needed"
    if fact.get("approved_waiting"):
        return "IN_PROGRESS", "PENDING", "The approved brief waits for the decision maker's signature"
    return "IN_PROGRESS", "PENDING", "No version of the brief is approved for decision yet"


def _review_checks(reviews, steps: dict, checks: dict, labels: dict, check_labels: dict) -> None:
    """The risk and regulatory review checks and their step, from ``{"RISK": fact, "REGULATORY": fact}`` (see
    ``case_reviews.rules.review_check``); None when the reviews could not be read."""
    from backend.app.case_reviews.rules import REGULATORY, RISK, review_check, review_step

    keys = {RISK: "risk_review", REGULATORY: "regulatory_review"}
    if reviews is None:
        steps["risk_regulatory"] = _step("risk_regulatory", labels["risk_regulatory"], "NOT_STARTED", UNREADABLE)
        for key in keys.values():
            checks[key] = _check(key, check_labels[key], "PENDING", UNREADABLE)
        return
    results = {}
    for review_type, key in keys.items():
        fact = reviews.get(review_type)
        if fact is None:
            result, rationale = "PENDING", UNREADABLE
        else:
            result, rationale = review_check(review_type, fact)
        results[review_type] = result
        checks[key] = _check(key, check_labels[key], result, rationale)
    status, detail = review_step(results)
    steps["risk_regulatory"] = _step("risk_regulatory", labels["risk_regulatory"], status, detail)


# ---------------------------------------------------------------------------------------------------- reading


def safely(db: Session, name: str, read, default=None):
    """``read(db)`` inside a SAVEPOINT; a failure (a missing table on an older database) is logged, rolled back to
    the savepoint and ``default`` returned."""
    try:
        with db.begin_nested():
            return read(db)
    except Exception:
        logger.warning("Case fact %s could not be read", name, exc_info=True)
        return default


def evidence_by_case(db: Session, tenant_id, case_ids) -> dict[str, tuple[int, int]]:
    """``{case id: (total, unreviewed)}`` of the cases' evidence (links and evidence recorded on the case)."""
    from backend.app.db.models.foundation import Evidence, InvestigationEvidence

    ids = list(wanted_ids(case_ids))
    if not ids:
        return {}
    tenant = as_uuid(tenant_id)
    linked: dict[str, list] = defaultdict(list)
    for case_id, evidence_id, review_status in db.query(
        InvestigationEvidence.investigation_id, InvestigationEvidence.evidence_id, InvestigationEvidence.review_status
    ).filter(InvestigationEvidence.tenant_id == tenant, InvestigationEvidence.investigation_id.in_(ids)):
        linked[str(case_id)].append((evidence_id, review_status))
    direct: dict[str, list] = defaultdict(list)
    for case_id, evidence_id in db.query(Evidence.investigation_id, Evidence.id).filter(
        Evidence.tenant_id == tenant, Evidence.investigation_id.in_(ids)
    ):
        direct[str(case_id)].append(evidence_id)
    return {str(case_id): evidence_counts(linked[str(case_id)], direct[str(case_id)]) for case_id in ids}


def requests_by_case(db: Session, tenant_id, case_ids) -> dict[str, tuple[int, int]]:
    """``{case id: (open, blocking)}`` of the cases' evidence requests; blocking are the open HIGH and CRITICAL ones."""
    from backend.app.db.models.stage3 import SupplierEvidenceRequest as Request

    ids = list(wanted_ids(case_ids))
    if not ids:
        return {}
    counts = {str(case_id): [0, 0] for case_id in ids}
    for case_id, status, priority, reviewed_at in db.query(
        Request.investigation_id, Request.status, Request.priority, Request.reviewed_at
    ).filter(Request.tenant_id == as_uuid(tenant_id), Request.investigation_id.in_(ids)):
        if not request_is_open(status, reviewed_at):
            continue
        counts[str(case_id)][0] += 1
        if str(priority or "").upper() in BLOCKING_PRIORITIES:
            counts[str(case_id)][1] += 1
    return {key: (value[0], value[1]) for key, value in counts.items()}


def unknowns_by_case(db: Session, tenant_id, case_ids) -> dict[str, tuple[int, int]]:
    """``{case id: (total, open)}`` of the cases' open questions (unknowns)."""
    from backend.app.db.models.foundation import Unknown

    ids = list(wanted_ids(case_ids))
    if not ids:
        return {}
    counts = {str(case_id): [0, 0] for case_id in ids}
    for case_id, status in db.query(Unknown.investigation_id, Unknown.status).filter(
        Unknown.tenant_id == as_uuid(tenant_id), Unknown.investigation_id.in_(ids)
    ):
        counts[str(case_id)][0] += 1
        if unknown_is_open(status):
            counts[str(case_id)][1] += 1
    return {key: (value[0], value[1]) for key, value in counts.items()}


def _scope_fact(db: Session, case) -> dict:
    from backend.app.case_workflow import scope

    data = scope.current_scope(db, case)
    return {
        "version": data.get("version") or None,
        "question": bool(" ".join(str(data.get("question") or "").split())),
        "included": len(data.get("included_complaint_ids") or ()),
    }


def _analysis_fact(db: Session, case) -> bool:
    from backend.app.db.models.foundation import AIExecution
    from investigator.provider import ORCHESTRATION_VERSION, PROVIDER

    return (
        db.query(AIExecution.id)
        .filter(
            AIExecution.tenant_id == case.tenant_id,
            AIExecution.investigation_id == case.id,
            AIExecution.provider == PROVIDER,
            AIExecution.orchestration_version == ORCHESTRATION_VERSION,
            AIExecution.structured_output.isnot(None),
        )
        .first()
        is not None
    )


def _hypotheses_fact(db: Session, case) -> int:
    """The case's hypotheses (the AI's and people's) that are neither superseded by a newer AI run nor retired."""
    from backend.app.case_intelligence.rules import counts_toward_case
    from backend.app.db.models.foundation import Hypothesis

    return sum(
        1
        for status, human_status in db.query(Hypothesis.status, Hypothesis.human_status).filter(
            Hypothesis.tenant_id == case.tenant_id, Hypothesis.investigation_id == case.id
        )
        if counts_toward_case(status, human_status)
    )


def _people_analysis_fact(db: Session, case) -> int:
    """Observations people recorded in the case and hypotheses they added (not superseded or retired)."""
    from backend.app.case_intelligence.rules import counts_toward_case
    from backend.app.db.models.evidence_intelligence import EvidenceObservation
    from backend.app.db.models.foundation import Hypothesis

    hypotheses = sum(
        1
        for status, human_status in db.query(Hypothesis.status, Hypothesis.human_status).filter(
            Hypothesis.tenant_id == case.tenant_id,
            Hypothesis.investigation_id == case.id,
            Hypothesis.origin == "human",
        )
        if counts_toward_case(status, human_status)
    )
    observations = (
        db.query(EvidenceObservation.id)
        .filter(
            EvidenceObservation.tenant_id == case.tenant_id,
            EvidenceObservation.investigation_id == case.id,
            EvidenceObservation.origin == "HUMAN",
        )
        .count()
    )
    return hypotheses + observations


def _contradictions_fact(db: Session, case) -> dict:
    """``{"total", "undocumented"}``: how many current hypotheses of the case have contradicting evidence that is not
    withdrawn, and the business ids of those no person has judged yet."""
    from backend.app.db.models.foundation import Hypothesis, HypothesisEvidence

    rows = (
        db.query(Hypothesis.business_id, Hypothesis.human_status)
        .join(
            HypothesisEvidence,
            (HypothesisEvidence.hypothesis_id == Hypothesis.id)
            & (HypothesisEvidence.tenant_id == Hypothesis.tenant_id),
        )
        .filter(
            Hypothesis.tenant_id == case.tenant_id,
            Hypothesis.investigation_id == case.id,
            Hypothesis.status != "superseded",
            HypothesisEvidence.relation_type == "contradict",
            HypothesisEvidence.retracted_at.is_(None),
        )
        .distinct()
        .all()
    )
    undocumented = sorted({business_id for business_id, human_status in rows if not human_status})
    return {"total": len({business_id for business_id, _ in rows}), "undocumented": undocumented}


def _brief_fact(db: Session, case) -> dict:
    from sqlalchemy import func

    from backend.app.db.models.foundation import InvestigationBrief

    latest = (
        db.query(func.max(InvestigationBrief.brief_version))
        .filter(InvestigationBrief.tenant_id == case.tenant_id, InvestigationBrief.investigation_id == case.id)
        .scalar()
    )
    return {"latest_version": int(latest) if latest else None}


def _decision_fact(db: Session, case) -> dict:
    from backend.app.db.models.foundation import Decision

    statuses = [
        str(row[0] or "").upper()
        for row in db.query(Decision.decision_status).filter(
            Decision.tenant_id == case.tenant_id, Decision.investigation_id == case.id
        )
    ]
    return {"count": len(statuses), "signed": sum(1 for item in statuses if item in SIGNED_DECISION_STATUSES)}


def _brief_decision_fact(db: Session, case) -> dict:
    """``{"briefs", "approved_waiting", "current_outcome"}``: how many Decision Brief versions the case has, whether
    an approved version waits for a decision, and the outcome of its current signed decision on a brief (None)."""
    from backend.app.db.models.foundation import Decision
    from backend.app.db.models.reviews import DecisionBriefVersion

    versions = (
        db.query(DecisionBriefVersion.id, DecisionBriefVersion.status)
        .filter(DecisionBriefVersion.tenant_id == case.tenant_id, DecisionBriefVersion.investigation_id == case.id)
        .all()
    )
    current = None
    if versions:
        current = (
            db.query(Decision.outcome, Decision.brief_version_id)
            .filter(
                Decision.tenant_id == case.tenant_id,
                Decision.investigation_id == case.id,
                Decision.decision_kind == "BRIEF",
                Decision.decision_status == "SIGNED",
                Decision.superseded_by_decision_id.is_(None),
            )
            .order_by(Decision.decided_at.desc().nulls_last())
            .first()
        )
    decided = current.brief_version_id if current is not None else None
    return {
        "briefs": len(versions),
        "approved_waiting": any(
            status == "APPROVED_FOR_DECISION" and version_id != decided for version_id, status in versions
        ),
        "current_outcome": current.outcome if current is not None else None,
    }


def _reviews_fact(db: Session, case) -> dict:
    from backend.app.case_reviews.service import review_facts

    return review_facts(db, case)


def case_facts(db: Session, case) -> dict:
    """The facts ``evaluate`` needs, each read on its own (None when it could not be read)."""
    from backend.app.case_workflow.states import case_state

    key = str(case.id)

    def one(table: dict, default):
        value = table.get(key) if table is not None else None
        return default if value is None else value

    evidence = safely(db, "evidence", lambda session: evidence_by_case(session, case.tenant_id, [case.id]))
    requests = safely(db, "evidence requests", lambda session: requests_by_case(session, case.tenant_id, [case.id]))
    unknowns = safely(db, "unknowns", lambda session: unknowns_by_case(session, case.tenant_id, [case.id]))
    evidence_counts_ = one(evidence, (0, 0)) if evidence is not None else None
    request_counts = one(requests, (0, 0)) if requests is not None else None
    unknown_counts = one(unknowns, (0, 0)) if unknowns is not None else None
    return {
        "workflow_state": case_state(case),
        "question": bool(" ".join(str(case.investigation_question or "").split())),
        "scope": safely(db, "scope", lambda session: _scope_fact(session, case)),
        "evidence": (
            {"total": evidence_counts_[0], "unreviewed": evidence_counts_[1]} if evidence_counts_ is not None else None
        ),
        "requests": {"open": request_counts[0], "blocking": request_counts[1]} if request_counts is not None else None,
        "unknowns": {"total": unknown_counts[0], "open": unknown_counts[1]} if unknown_counts is not None else None,
        "analysis_run": safely(db, "analysis", lambda session: _analysis_fact(session, case)),
        "people_analysis": safely(db, "people's analysis", lambda session: _people_analysis_fact(session, case)),
        "hypotheses": safely(db, "hypotheses", lambda session: _hypotheses_fact(session, case)),
        "contradictions": safely(db, "contradictions", lambda session: _contradictions_fact(session, case)),
        "brief": safely(db, "brief", lambda session: _brief_fact(session, case)),
        "decision": safely(db, "decision", lambda session: _decision_fact(session, case)),
        "brief_decision": safely(db, "brief decision", lambda session: _brief_decision_fact(session, case)),
        "reviews": safely(db, "reviews", lambda session: _reviews_fact(session, case)),
    }
