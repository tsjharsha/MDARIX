"""The automatic trust check: every AI result is checked as it is saved, not only when someone asks the API.

``ai.execution.record_ai_execution`` (the one place AI results are saved) calls :func:`check_saved`, so every AI run
the application saves gets its check: the case's AI run (analysis, explanations, challenges, unknowns, brief), the
signal summary and the second look's explanation. Ask answers are not AI executions; :func:`assess_answer` gives them
the same verdict from the checks Ask already makes.

The checks (policy ``MDARIX_AI_TRUST_POLICY_R1_V2``) look only at what the reader sees, not at statements the feature's
own checks already removed:

- ``EVIDENCE_GROUNDING``: every source the output cites exists (the case's evidence, the signal's complaints, the
  complaint explained). An invented source blocks the output.
- ``RESTRICTED_CLAIMS``: no stated root cause, causal proof, probability, or decision that belongs to people
  (reporting, recall, approval, closure). Blocks a language-model output.
- ``CERTAINTY_WORDING``: no asserted certainty ("proves", "definitively"). A warning.
- ``PROVENANCE``: a language-model output names its provider and model; a rules output says it came from the rules.
- ``TENANT_INTEGRITY``: the output belongs to the organization and case it is checked for.

A rules output (AI off, unavailable, over budget) is checked for grounding and provenance; its wording is MDARIX's own
and may quote the records, so the wording checks do not apply. A passed check means the output is grounded and worded
within policy, not that it is true: a person decides. The check never stops the save it belongs to: a failure is
logged and the result says it was not checked.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("mdarix.trust")

POLICY = "MDARIX_AI_TRUST_POLICY_R1_V2"
AI, RULES = "AI", "RULES"
PASS, WARNING, BLOCKED = "PASS", "WARNING", "BLOCKED"
STATUS_PASS, STATUS_LIMITED, STATUS_BLOCKED, NOT_CHECKED = "PASS", "PASS_WITH_LIMITATIONS", "BLOCKED", "NOT_CHECKED"
STATUS_LABELS = {
    STATUS_PASS: "Trust check passed",
    STATUS_LIMITED: "Trust check passed with limitations",
    STATUS_BLOCKED: "Trust check blocked",
    NOT_CHECKED: "Not checked",
}
LIMITATION = (
    "A passed trust check means the output is grounded and worded within policy, not that it is true; a person decides."
)
EXAMPLES_MAX = 3

# Results the application saves under its own provider name, and what their sources are.
SIGNAL_SUMMARY = "mdarix-signal-summary"
SECOND_LOOK = "mdarix-second-look-explainer"
INVESTIGATION_BRIEF = "mdarix-investigation-brief"
OUTPUT_TYPES = {
    SIGNAL_SUMMARY: "SIGNAL_SUMMARY",
    SECOND_LOOK: "SECOND_LOOK_EXPLANATION",
    INVESTIGATION_BRIEF: "INVESTIGATION_BRIEF",
}

# Decisions that belong to people, stated as made. Hedged wording ("whether a CAPA is required") is allowed.
AUTHORITY = re.compile(
    r"(?i)\b(mdarix approves|ai approves|approved the (investigation|decision|release)|recall (is |was )?required"
    r"|capa (is |was )?required|(is|are) reportable|(must|shall) be reported|close (the )?(case|investigation|capa))\b"
)

# Parts of a saved output that the reader does not see as the AI's statements: what its checks removed, and its
# provenance, snapshots and anchors.
_SKIPPED = frozenset(
    {
        "rejected_items",
        "rejected_hypotheses",
        "rejected",
        "dropped",
        "checks_dropped",
        "model_provenance",
        "provenance",
        "validation_summary",
        "context_snapshot",
        "temporal_context",
        "source_anchor",
        "live_provider_advisory",
        "guardrails",
        "model",
    }
)
_TEXT_KEYS = frozenset({"statement", "summary", "rationale", "why_it_matters", "chain_statement", "headline", "text"})
_REFERENCE_KEYS = frozenset({"source_references", "evidence_references", "contradiction_references"})


CHECKS = (
    {
        "check": "EVIDENCE_GROUNDING",
        "title": "Every cited source exists",
        "what": "Each source the result cites must exist in the case's evidence, the signal's complaints or the "
        "complaint explained.",
        "on_failure": BLOCKED,
    },
    {
        "check": "RESTRICTED_CLAIMS",
        "title": "No cause, probability or decision stated as fact",
        "what": "No stated root cause, causal proof, probability, or decision that belongs to people (reporting, "
        "recall, approval, closure). Hedged wording is allowed.",
        "on_failure": BLOCKED,
    },
    {
        "check": "CERTAINTY_WORDING",
        "title": "No asserted certainty",
        "what": "Words such as 'proves' or 'definitively' are flagged so the reader treats them as interpretation.",
        "on_failure": WARNING,
    },
    {
        "check": "PROVENANCE",
        "title": "Provider and model recorded",
        "what": "A language-model result names its provider and model; a rules result says it came from the rules.",
        "on_failure": BLOCKED,
    },
    {
        "check": "TENANT_INTEGRITY",
        "title": "Belongs to this organization",
        "what": "The result belongs to the organization and case it is shown in.",
        "on_failure": BLOCKED,
    },
)


def describe() -> dict:
    """The policy as people read it: each check, what it looks at and what happens when it fails."""
    return {
        "policy": POLICY,
        "applies_to": [
            "The case's AI run (analysis, competing explanations, challenges, unknowns, brief)",
            "Signal summaries",
            "Second-look explanations",
            "Ask answers",
        ],
        "checks": [dict(item) for item in CHECKS],
        "statuses": dict(STATUS_LABELS),
        "limitation": LIMITATION,
    }


@dataclass
class Output:
    """What one AI result says, for the checks: who wrote it, the statements the reader sees, the sources cited."""

    author: str
    provider: str | None = None
    model: str | None = None
    statements: list[str] = field(default_factory=list)
    cited: list[str] = field(default_factory=list)
    # The sources that exist for this result; None when the result cites no records (nothing to resolve).
    known: set[str] | None = None
    sources: str = "evidence"
    dropped: int = 0


def _hedged(statement: str, start: int) -> bool:
    from investigator.model_provider import HEDGES

    return bool(HEDGES.search(statement[max(0, start - 60) : start]))


def asserts_authority(statement: str) -> bool:
    return any(not _hedged(statement, match.start()) for match in AUTHORITY.finditer(statement))


def _restricted(statement: str) -> bool:
    from investigator.model_provider import asserts_causality_or_decision

    return asserts_causality_or_decision(statement) or asserts_authority(statement)


def _certain(statement: str) -> bool:
    from genai.ask import asserts_certainty

    return asserts_certainty(statement)


def _check(check_type: str, status: str, severity: str, message: str, details: dict | None = None) -> dict:
    return {
        "check_type": check_type,
        "status": status,
        "severity": severity,
        "message": message,
        "details": details or {},
    }


def _examples(statements: list[str]) -> list[str]:
    return [statement[:240] for statement in statements[:EXAMPLES_MAX]]


def assess(output: Output, *, tenant_matches: bool = True) -> dict:
    """The checks and the verdict for one output (pure: no database)."""
    checks: list[dict] = []
    limitations = [LIMITATION]
    cited = list(dict.fromkeys(ref for ref in output.cited if ref))
    if output.known is None:
        checks.append(
            _check("EVIDENCE_GROUNDING", PASS, "INFO", "This result cites no records, so there is nothing to resolve.")
        )
    else:
        missing = sorted(set(cited) - output.known)
        if missing:
            checks.append(
                _check(
                    "EVIDENCE_GROUNDING",
                    BLOCKED,
                    "CRITICAL",
                    f"Cites {len(missing)} source{'s' if len(missing) != 1 else ''} that do not exist in this "
                    f"{output.sources}: {', '.join(missing[:5])}.",
                    {"missing": missing, "cited": len(cited)},
                )
            )
        elif cited:
            checks.append(
                _check(
                    "EVIDENCE_GROUNDING",
                    PASS,
                    "INFO",
                    f"All {len(cited)} cited source{'s' if len(cited) != 1 else ''} exist in this {output.sources}.",
                    {"cited": len(cited)},
                )
            )
        else:
            checks.append(
                _check("EVIDENCE_GROUNDING", WARNING, "LOW", "Nothing is cited, so nothing can be traced to a record.")
            )
            limitations.append("The result cites no records.")
    if output.author == AI:
        restricted = [statement for statement in output.statements if _restricted(statement)]
        checks.append(
            _check(
                "RESTRICTED_CLAIMS",
                BLOCKED if restricted else PASS,
                "HIGH" if restricted else "INFO",
                f"{len(restricted)} statement{'s' if len(restricted) != 1 else ''} state a cause, a probability or a "
                "decision that belongs to people."
                if restricted
                else "No stated root cause, causal proof, probability or decision that belongs to people.",
                {"examples": _examples(restricted)} if restricted else {},
            )
        )
        certain = [statement for statement in output.statements if _certain(statement)]
        checks.append(
            _check(
                "CERTAINTY_WORDING",
                WARNING if certain else PASS,
                "MEDIUM" if certain else "INFO",
                f"{len(certain)} statement{'s' if len(certain) != 1 else ''} assert certainty; read them as "
                "interpretations."
                if certain
                else "No asserted certainty.",
                {"examples": _examples(certain)} if certain else {},
            )
        )
        if certain:
            limitations.append("Some statements assert certainty the evidence may not support.")
        named = bool(output.provider and output.model)
        checks.append(
            _check(
                "PROVENANCE",
                PASS if named else BLOCKED,
                "INFO" if named else "CRITICAL",
                f"Written by {output.provider} {output.model}." if named else "The provider or model is not recorded.",
                {"provider": output.provider, "model": output.model},
            )
        )
    else:
        rules = "Written by MDARIX rules from the records; no language-model wording to check."
        checks.append(_check("RESTRICTED_CLAIMS", PASS, "INFO", rules))
        checks.append(_check("CERTAINTY_WORDING", PASS, "INFO", rules))
        checks.append(
            _check("PROVENANCE", PASS, "INFO", "Written by MDARIX rules (no language model).", {"author": RULES})
        )
    checks.append(
        _check(
            "TENANT_INTEGRITY",
            PASS if tenant_matches else BLOCKED,
            "INFO" if tenant_matches else "CRITICAL",
            "The result belongs to this organization and case."
            if tenant_matches
            else "The result does not belong to this organization or case.",
        )
    )
    if output.dropped:
        limitations.append(
            f"The feature's own checks already removed {output.dropped} statement{'s' if output.dropped != 1 else ''}."
        )
    statuses = {check["status"] for check in checks}
    status = STATUS_BLOCKED if BLOCKED in statuses else STATUS_LIMITED if WARNING in statuses else STATUS_PASS
    return {"status": status, "policy": POLICY, "author": output.author, "checks": checks, "limitations": limitations}


# --------------------------------------------------------------------------------------------- reading outputs


def _reference_id(reference: Any) -> str | None:
    if not isinstance(reference, dict):
        return None
    value = reference.get("evidence_identifier") or reference.get("evidence_id")
    return str(value) if value else None


def _walk(value: Any, statements: list[str], cited: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _SKIPPED:
                continue
            if key in _REFERENCE_KEYS and isinstance(item, list):
                cited.extend(ref for ref in (_reference_id(reference) for reference in item) if ref)
            elif key in _TEXT_KEYS and isinstance(item, str):
                if item.strip():
                    statements.append(item.strip())
            else:
                _walk(item, statements, cited)
    elif isinstance(value, list):
        for item in value:
            _walk(item, statements, cited)


def read_case_output(output: dict) -> Output:
    """A case step's saved output (analysis, competing explanations, challenges, unknowns, failure chains)."""
    output = output if isinstance(output, dict) else {}
    provenance = output.get("model_provenance") or output.get("provenance") or {}
    provenance = provenance if isinstance(provenance, dict) else {}
    model_written = "LANGUAGE_MODEL" in (
        output.get("analysis_author"),
        provenance.get("analysis_author"),
        provenance.get("author"),
    )
    model = provenance.get("model_analysis") if isinstance(provenance.get("model_analysis"), dict) else {}
    statements: list[str] = []
    cited: list[str] = []
    _walk(output, statements, cited)
    dropped = sum(
        len(value) if isinstance(value, list) else 0
        for value in (
            output.get("rejected_items"),
            output.get("rejected_hypotheses"),
            provenance.get("checks_dropped"),
        )
    )
    return Output(
        author=AI if model_written else RULES,
        provider=model.get("provider"),
        model=model.get("model"),
        statements=statements,
        cited=cited,
        dropped=dropped,
    )


def read_cited_sentences(output: dict, *, cite_key: str) -> Output:
    """An output of cited sentences (signal summary, second-look explanation): ``{"sentences": [{"text", <cite_key>:
    [...]}], "dropped": [...], "model": {"provider", "model"}}``."""
    output = output if isinstance(output, dict) else {}
    model = output.get("model") if isinstance(output.get("model"), dict) else {}
    sentences = [item for item in output.get("sentences") or [] if isinstance(item, dict)]
    return Output(
        author=AI,
        provider=model.get("provider"),
        model=model.get("model"),
        statements=[str(item.get("text") or "").strip() for item in sentences if str(item.get("text") or "").strip()],
        cited=[str(ref) for item in sentences for ref in item.get(cite_key) or [] if str(ref).strip()],
        dropped=len(output.get("dropped") or []),
    )


def read_brief(output: dict) -> Output:
    """The language model's investigation brief draft (``briefs.model_writer``)."""
    output = output if isinstance(output, dict) else {}
    model = output.get("model") if isinstance(output.get("model"), dict) else {}
    sections = output.get("sections") if isinstance(output.get("sections"), dict) else {}
    items = [
        item for values in sections.values() if isinstance(values, list) for item in values if isinstance(item, dict)
    ]
    headline = output.get("headline")
    statements = ([headline.strip()] if isinstance(headline, str) and headline.strip() else []) + [
        str(item.get("statement") or "").strip() for item in items if str(item.get("statement") or "").strip()
    ]
    return Output(
        author=AI,
        provider=model.get("provider"),
        model=model.get("model"),
        statements=statements,
        cited=[str(ref) for item in items for ref in item.get("evidence") or [] if str(ref).strip()],
        dropped=len(output.get("checks_dropped") or []),
    )


def _case_evidence(db, tenant_id, investigation_id) -> set[str]:
    """The case's evidence (its own and the records linked to it), as the investigation workspace reads it."""
    from sqlalchemy import or_, text

    from backend.app.db.models.foundation import Evidence

    linked = (
        text(
            "SELECT evidence_id FROM investigation_evidence "
            "WHERE tenant_id=CAST(:tenant_id AS uuid) AND investigation_id=CAST(:investigation_id AS uuid)"
        )
        .bindparams(tenant_id=tenant_id, investigation_id=investigation_id)
        .columns(evidence_id=Evidence.id.type)
    )
    rows = (
        db.query(Evidence.id, Evidence.evidence_identifier)
        .filter(
            Evidence.tenant_id == tenant_id, or_(Evidence.investigation_id == investigation_id, Evidence.id.in_(linked))
        )
        .all()
    )
    return {str(row.id) for row in rows} | {row.evidence_identifier for row in rows if row.evidence_identifier}


def read_execution(db, execution) -> tuple[str, Output]:
    """The output type and what the saved AI result says, with the sources that exist for it."""
    output = execution.structured_output or {}
    refs = execution.evidence_refs if isinstance(execution.evidence_refs, dict) else {}
    provider = execution.provider
    if provider == SIGNAL_SUMMARY:
        read = read_cited_sentences(output, cite_key="complaints")
        read.known, read.sources = {str(ref) for ref in refs.get("complaints") or []}, "signal's complaints"
        return OUTPUT_TYPES[provider], read
    if provider == SECOND_LOOK:
        read = read_cited_sentences(output, cite_key="fields")
        read.known, read.sources = {str(ref) for ref in refs.get("fields") or []}, "complaint record"
        return OUTPUT_TYPES[provider], read
    if provider == INVESTIGATION_BRIEF:
        read = read_brief(output)
    else:
        read = read_case_output(output)
    if execution.investigation_id is not None:
        read.known, read.sources = (
            _case_evidence(db, execution.tenant_id, execution.investigation_id),
            "case's evidence",
        )
    return OUTPUT_TYPES.get(provider, "AI_EXECUTION"), read


def summary(result_id, verdict: dict) -> dict:
    """The short form a step, a summary or an answer carries: the verdict and each check's outcome."""
    return {
        "id": str(result_id) if result_id else None,
        "status": verdict["status"],
        "label": STATUS_LABELS[verdict["status"]],
        "policy": verdict.get("policy", POLICY),
        "author": verdict.get("author"),
        "checks": [
            {"check": check["check_type"], "status": check["status"], "message": check["message"]}
            for check in verdict.get("checks", [])
        ],
        "limitations": verdict.get("limitations", []),
    }


def _record(db, execution, output_type: str, verdict: dict, output: Output):
    from backend.app.db.models.foundation import AssuranceCheck, AssuranceResult

    now = datetime.now(timezone.utc)
    configuration = {
        "provider": output.provider or execution.provider,
        "model": output.model or execution.model_name,
        "model_version": execution.model_version,
        "prompt": execution.prompt_template_version,
        "policy": POLICY,
    }
    previous = (
        db.query(AssuranceResult.id)
        .filter(AssuranceResult.tenant_id == execution.tenant_id, AssuranceResult.ai_execution_id == execution.id)
        .count()
    )
    context = execution.context_refs if isinstance(execution.context_refs, dict) else {}
    result = AssuranceResult(
        id=uuid.uuid4(),
        tenant_id=execution.tenant_id,
        investigation_id=execution.investigation_id,
        ai_execution_id=execution.id,
        output_type=output_type,
        output_id=str(execution.id),
        assurance_version=previous + 1,
        status=verdict["status"],
        generated_at=now,
        trust_policy_version=POLICY,
        temporal_mode=context.get("temporal_mode"),
        temporal_cutoff=None,
        human_review_required=True,
        revalidation_required=False,
        limitations={"items": verdict["limitations"], "author": output.author, "automatic": True},
        configuration_hash=hashlib.sha256(json.dumps(configuration, sort_keys=True, default=str).encode()).hexdigest(),
        created_at=now,
    )
    db.add(result)
    db.flush()
    for check in verdict["checks"]:
        db.add(
            AssuranceCheck(
                id=uuid.uuid4(),
                tenant_id=execution.tenant_id,
                assurance_result_id=result.id,
                check_type=check["check_type"],
                status=check["status"],
                severity=check["severity"],
                message=check["message"],
                details=check["details"],
                created_at=now,
            )
        )
    db.flush()
    return result


def check_saved(db, execution) -> dict:
    """Check a saved AI result and save the verdict with it (no commit; the caller's transaction keeps both or
    neither). Never raises: a failure is logged and the result says it was not checked."""
    try:
        with db.begin_nested():
            output_type, output = read_execution(db, execution)
            verdict = assess(output)
            result = _record(db, execution, output_type, verdict, output)
        return summary(result.id, verdict)
    except Exception:  # the check must never stop the save it belongs to
        logger.exception("Trust check of AI execution %s failed", getattr(execution, "id", None))
        return {"id": None, "status": NOT_CHECKED, "label": STATUS_LABELS[NOT_CHECKED], "policy": POLICY, "checks": []}


def latest(db, tenant_id, execution_id) -> dict | None:
    """The latest automatic check of a saved AI result, in its short form, or None."""
    from backend.app.db.models.foundation import AssuranceCheck, AssuranceResult

    if not execution_id:
        return None
    try:
        execution_id = uuid.UUID(str(execution_id))
    except ValueError:
        return None
    result = (
        db.query(AssuranceResult)
        .filter(
            AssuranceResult.tenant_id == tenant_id,
            AssuranceResult.ai_execution_id == execution_id,
            AssuranceResult.trust_policy_version == POLICY,
        )
        .order_by(AssuranceResult.assurance_version.desc(), AssuranceResult.created_at.desc())
        .first()
    )
    if result is None:
        return None
    checks = (
        db.query(AssuranceCheck)
        .filter(AssuranceCheck.tenant_id == tenant_id, AssuranceCheck.assurance_result_id == result.id)
        .order_by(AssuranceCheck.created_at, AssuranceCheck.check_type)
        .all()
    )
    limitations = result.limitations if isinstance(result.limitations, dict) else {}
    return summary(
        result.id,
        {
            "status": result.status,
            "policy": result.trust_policy_version,
            "author": limitations.get("author"),
            "checks": [{"check_type": row.check_type, "status": row.status, "message": row.message} for row in checks],
            "limitations": limitations.get("items", []),
        },
    )


def assess_answer(answer_check: dict, *, provider: str | None, model: str | None, model_written: bool) -> dict:
    """Ask's verdict, from the checks Ask already makes on every answer (``genai.ask.check_answer``): unverified
    citations block, causal or decision wording blocks, certainty wording warns. A records-only answer is the rules'."""
    answer_check = answer_check if isinstance(answer_check, dict) else {}
    if not model_written:
        return summary(None, assess(Output(author=RULES, known=None)))
    unverified = [str(ref) for ref in answer_check.get("unverified_citations") or []]
    cited = [str(ref) for ref in answer_check.get("cited") or []]
    causal = bool(answer_check.get("causal_or_decision_wording"))
    certain = bool(answer_check.get("certainty_wording"))
    verdict = assess(
        Output(
            author=AI,
            provider=provider,
            model=model,
            # Ask reports what its wording checks found; the statements themselves stay in the answer.
            statements=[],
            cited=cited + unverified,
            known=set(cited) - set(unverified),
            sources="organization's records",
        )
    )
    for check in verdict["checks"]:
        if check["check_type"] == "RESTRICTED_CLAIMS" and causal:
            check.update(
                status=BLOCKED,
                severity="HIGH",
                message="The answer states a cause or a decision that belongs to people.",
            )
        if check["check_type"] == "CERTAINTY_WORDING" and certain:
            check.update(
                status=WARNING, severity="MEDIUM", message="The answer asserts certainty; read it as an interpretation."
            )
    statuses = {check["status"] for check in verdict["checks"]}
    verdict["status"] = (
        STATUS_BLOCKED if BLOCKED in statuses else STATUS_LIMITED if WARNING in statuses else STATUS_PASS
    )
    return summary(None, verdict)
