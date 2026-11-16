"""AI code suggestions on a report's IMDRF code fields (AI-R part D, step 10; WHIF story step 5).

On request, the language model proposes IMDRF codes for the report's code fields from the complaint's own words, each
with a confidence and the words it rests on. MDARIX keeps a proposal only when its code is in the newest loaded IMDRF
release, in an annex this form asks for, still selectable, and its quoted words are in the complaint's description;
everything else is dropped with the reason. Nothing is stored as a code: the proposals are saved as an AI result
(``ai_executions``) and shown as "AI suggestion". A person enters one, field by field, through the code field's own
step (``PUT /fields/{id}`` with ``codes`` and ``ai_execution_id``), audited with the suggestion it came from. "Confirm
all codes" confirms the approved mapping's suggestions only, never an AI one.

The feature is ``code_suggestions`` (MEDIUM): off unless the platform, the organization and its feature switch allow
it; in a free trial, on the sample data only (``genai/sample_gate.py``); when AI is off the field keeps the mapping's
suggestion, as before.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

VERSION = "code-suggestions-1"
SUGGESTIONS_MAX = 6
QUOTE_MIN = 3
LABEL = "AI suggestion: proposed by AI from the complaint's own words; a person enters each code"
SYSTEM = (
    "You help a medical device complaint-handling specialist code a complaint with IMDRF adverse event terminology "
    "(Annex A: medical device problem; B: cause investigation, type of investigation; C: investigation findings; D: "
    "investigation conclusion; E: health effect, clinical signs; F: health effect, health impact; G: component). "
    "Propose at most 6 codes, only for the annexes listed, only codes from the IMDRF terminology, each with a "
    "confidence between 0 and 1 and the exact words of the description it rests on. Never guess a cause or a "
    'conclusion the description does not state. Reply as JSON: {"suggestions": [{"annex": "A", "code": "A0101", '
    '"confidence": 0.7, "quote": "exact words"}]}.'
)


def _normal(text: object) -> str:
    return " ".join(str(text or "").split()).lower()


def check(control: Session, release: str, annexes: set[str], description: str, parsed: dict) -> tuple[list, list]:
    """(kept, dropped) proposals: a kept one names a selectable code of an asked annex in the loaded release, a
    confidence between 0 and 1, and words found in the description."""
    from backend.app.db.models.regulatory_reference import ImdrfCode
    from backend.app.regulatory_reference import selectable

    items = [item for item in (parsed.get("suggestions") or []) if isinstance(item, dict)]
    asked = {
        (str(item.get("annex") or "").strip().upper(), str(item.get("code") or "").strip().upper()) for item in items
    }
    known = {
        (row.annex, row.code): row
        for row in control.query(ImdrfCode).filter(
            ImdrfCode.release == release, ImdrfCode.code.in_([code for _, code in asked if code])
        )
    }
    text = _normal(description)
    kept, dropped, seen = [], [], set()
    for item in items:
        annex = str(item.get("annex") or "").strip().upper()
        code = str(item.get("code") or "").strip().upper()
        quote = " ".join(str(item.get("quote") or "").split())
        try:
            confidence = float(item.get("confidence"))
        except (TypeError, ValueError):
            confidence = -1.0
        row = known.get((annex, code))
        if annex not in annexes:
            reason = "ANNEX_NOT_ON_FORM"
        elif row is None:
            reason = "NOT_IN_RELEASE"
        elif not selectable(row.status):
            reason = "NOT_SELECTABLE"
        elif not 0.0 <= confidence <= 1.0:
            reason = "NO_CONFIDENCE"
        elif len(quote) < QUOTE_MIN or _normal(quote) not in text:
            reason = "QUOTE_NOT_IN_COMPLAINT"
        elif (annex, code) in seen:
            reason = "DUPLICATE"
        elif len(kept) >= SUGGESTIONS_MAX:
            reason = "OVER_LIMIT"
        else:
            reason = None
        if reason:
            dropped.append({"annex": annex, "code": code, "reason": reason})
            continue
        seen.add((annex, code))
        kept.append(
            {"annex": annex, "code": code, "term": row.term, "confidence": round(confidence, 2), "quote": quote}
        )
    kept.sort(key=lambda item: -item["confidence"])
    return kept, dropped


def _refused(status: str, reason: str, message: str | None = None) -> dict:
    return {"suggestions": [], "ai": {"status": status, "reason": reason, "message": message}}


def suggest(
    db: Session, control: Session, obligation, code_fields: dict[str, str], complaint, *, actor_ref: str, provider=None
) -> dict:
    """The model's checked proposals for ``code_fields`` ({field id: annex}), saved as an AI result; why not, when it
    cannot. Nothing is written to the report."""
    from ai.execution import record_ai_execution
    from backend.app.regulatory_reference import newest_release
    from genai.provider import GenAIProvider, GenAIUnavailable
    from investigator.model_provider import ModelAnalysisUnavailable, parse_json_reply

    description = " ".join(str(complaint.description or "").split())
    if not code_fields:
        return _refused("NOT_RUN", "NO_CODE_FIELDS", "This report has no IMDRF code fields.")
    if not description:
        return _refused("NOT_RUN", "NOTHING_TO_CODE", "The complaint has no description to code from.")
    release = newest_release(control)
    if not release:
        return _refused("NOT_RUN", "NO_IMDRF_RELEASE", "No IMDRF release is loaded yet.")
    annexes = set(code_fields.values())
    provider = provider or GenAIProvider()
    try:
        result = provider.complete(
            "Propose IMDRF codes for this complaint.",
            {"annexes": sorted(annexes), "imdrf_release": release},
            feature="code_suggestions",
            # The complaint's own description (the free-trial sample check re-reads it).
            records=[{"table": "complaints", "id": str(complaint.id), "evidence_id": "description"}],
            evidence=[{"id": "description", "text": f"Description: {description}"}],
            system=SYSTEM,
            json_output=True,
            max_output_tokens=600,
        )
    except GenAIUnavailable as exc:
        return _refused("REFUSED", exc.code, exc.user_message)
    answer = (result.output or {}).get("answer")
    if not answer:
        return _refused((result.output or {}).get("status") or "NO_ANSWER", "PROVIDER_NOT_CONFIGURED")
    try:
        parsed = parse_json_reply(answer)
    except ModelAnalysisUnavailable as exc:
        return _refused("UNREADABLE", exc.reason)
    kept, dropped = check(control, release, annexes, description, parsed)
    fields = {annex: [field for field, asked in code_fields.items() if asked == annex] for annex in annexes}
    for item in kept:
        item["field_ids"] = fields[item["annex"]]
    execution = record_ai_execution(
        db,
        obligation.tenant_id,
        provider=result.provider or "unknown",
        model_name=result.model or "unknown",
        model_version=result.model_version,
        prompt_template_version=VERSION,
        orchestration_version=VERSION,
        context_refs={"obligation_id": str(obligation.id), "complaint_id": str(complaint.id)},
        evidence_refs={"fields": ["description"]},
        structured_output={"release": release, "suggestions": kept, "dropped": dropped},
        validation_status="VALIDATED" if kept else "REJECTED",
        latency_ms=result.latency_ms,
        requestor_ref=str(actor_ref),
    )
    return {
        "suggestions": kept,
        "ai": {
            "status": "COMPLETED" if kept else "NOTHING_KEPT",
            "ai_execution_id": str(execution.id),
            "release": release,
            "dropped": dropped,
            "label": LABEL,
            "provider": result.provider,
            "model": result.model,
        },
    }


def suggested(db: Session, tenant_id, obligation_id, execution_id: uuid.UUID) -> dict[tuple[str, str], dict]:
    """{(annex, code): proposal} of one saved suggestion run of this report, or {} when it is not one."""
    from backend.app.db.models.foundation import AIExecution

    row = (
        db.query(AIExecution)
        .filter(
            AIExecution.tenant_id == tenant_id,
            AIExecution.id == execution_id,
            AIExecution.orchestration_version == VERSION,
        )
        .one_or_none()
    )
    if row is None or (row.context_refs or {}).get("obligation_id") != str(obligation_id):
        return {}
    return {(item["annex"], item["code"]): item for item in (row.structured_output or {}).get("suggestions") or []}
