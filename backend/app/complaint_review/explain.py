"""The second look's AI explanation: why a record the rules flagged may meet the definition of a complaint.

The rules select the records (rules.flag) and a person decides (CONFIRMED or DISMISSED). On request, the language model
explains in at most three short sentences why a cancelled record, an inquiry or a recurring No Fault Found looks like a
complaint, and every sentence must quote the record's own fields word for word. MDARIX checks each sentence before it is
shown: every quote must be in the field it names; a sentence that says the record is or is not a complaint, that it is
reportable, or that states a cause is dropped. The result is saved as an AI result (with its automatic trust check) and
shown beside the rules' reasons; when AI is off, unavailable or over budget, the reasons stand alone with why.

The record is sent masked like every AI request (genai.provider). The explanation never changes the record or the
decision.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy.orm import Session

PROVIDER = "mdarix-second-look-explainer"
VERSION = "R1-MVP-P6-SecondLookExplain-v1"
SENTENCES_MAX = 3
SENTENCE_MAX = 320
QUOTE_MIN = 3
# The record's fields the model may quote, with how they are named to it and on screen.
FIELDS = {
    "description": "Description",
    "status": "Status",
    "complaint_type": "Type",
    "problem_code": "Problem code",
    "severity": "Severity",
    "harm": "Harm and failure flags",
}
SYSTEM = (
    "You help a medical device complaint-handling specialist decide whether a record deserves to be handled as a "
    "complaint. The record was cancelled, logged as an inquiry or service record, or coded No Fault Found or User "
    "Error, and MDARIX rules flagged it. A complaint is any communication that alleges a deficiency in a device's "
    "identity, quality, durability, reliability, usability, safety, effectiveness or performance (ISO 13485:2016, 3.4). "
    "Explain, in at most 3 short sentences, what in the record looks like such an allegation. Use only the fields "
    "given. Every sentence must quote, word for word, at least one field it rests on, naming the field. Never say "
    "that the record is or is not a complaint, never say whether it is reportable, and never state a cause: a person "
    'decides. Reply as JSON: {"sentences": [{"text": "...", "quotes": [{"field": "description", "text": "exact '
    'words"}]}]}.'
)
# Decisions that belong to the person reading: the record's status as a complaint, reportability, recall. Hedged
# wording ("may meet the definition", "may be a complaint") is the point of the explanation and stays.
DECISION_WORDING = re.compile(
    r"(?i)\b((is|was|are|were) (not |clearly |definitely )?(a |an )?(valid |real |reportable )?complaints?\b"
    r"|(should|must|shall) be (treated|handled|logged|classified|reopened|recorded) as|reportab\w*"
    r"|(mdr|vigilance) (report|reporting|filing)|file (an? )?(mdr|vigilance)|recall(ed)? (is |was )?(required|needed))"
)
# A stated cause of the device problem. Reasoning words ("because the description says ...") are allowed.
CAUSE_WORDING = re.compile(
    r"(?i)\b(caus(e|es|ed|ing)|root[- ]cause|resulted in|led to|attributabl[ey] to|responsible for)\b"
)
LABEL = "AI interpretation: written by AI from this record's own words, every quote checked; a person decides"


def _normal(text: object) -> str:
    return " ".join(str(text or "").split()).casefold()


def record_fields(record: dict) -> dict[str, str]:
    """The fields of a flagged record the model sees (and may quote), empty ones left out."""
    harm = " ".join(
        sentence
        for flag, sentence in (
            ("death", "Death reported."),
            ("serious_injury", "Serious injury reported."),
            ("patient_involved", "Patient involved."),
            ("malfunction", "Malfunction reported."),
        )
        if record.get(flag)
    )
    values = {
        "description": record.get("description"),
        "status": record.get("status"),
        "complaint_type": record.get("complaint_type"),
        "problem_code": record.get("problem_code"),
        "severity": record.get("severity"),
        "harm": harm,
    }
    return {name: " ".join(str(value).split()) for name, value in values.items() if str(value or "").strip()}


def check_sentences(parsed: dict, fields: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """The sentences that pass (each with its checked quotes and the fields they rest on) and those dropped, why."""
    kept, dropped = [], []
    normal_fields = {name: _normal(value) for name, value in fields.items()}
    for item in (parsed.get("sentences") if isinstance(parsed, dict) else None) or []:
        item = item if isinstance(item, dict) else {}
        text = " ".join(str(item.get("text") or "").split())
        quotes = [quote for quote in item.get("quotes") or [] if isinstance(quote, dict)]
        checked = []
        reason = None
        if not text or len(text) > SENTENCE_MAX:
            reason = "EMPTY_OR_TOO_LONG"
        elif not quotes:
            reason = "NO_QUOTE"
        else:
            for quote in quotes:
                field = str(quote.get("field") or "").strip()
                words = " ".join(str(quote.get("text") or "").split())
                if field not in normal_fields or len(words) < QUOTE_MIN or _normal(words) not in normal_fields[field]:
                    reason = "QUOTE_NOT_IN_RECORD"
                    break
                checked.append({"field": field, "label": FIELDS[field], "text": words})
        if reason is None and DECISION_WORDING.search(text):
            reason = "DECISION_CLAIM"
        if reason is None:
            from investigator.model_provider import asserts_causality_or_decision

            if CAUSE_WORDING.search(text) or asserts_causality_or_decision(text):
                reason = "CAUSAL_CLAIM"
        if reason is None and len(kept) >= SENTENCES_MAX:
            reason = "OVER_LIMIT"
        if reason:
            dropped.append({"text": text[:SENTENCE_MAX], "reason": reason})
            continue
        kept.append({"text": text, "quotes": checked, "fields": sorted({quote["field"] for quote in checked})})
    return kept, dropped


def _refused(status: str, reason: str, message: str | None = None) -> dict:
    return {"author": "RULES", "sentences": [], "ai": {"status": status, "reason": reason, "message": message}}


def explain(db: Session, tenant_id: uuid.UUID, record: dict, flagged: dict, *, actor_ref: str, provider=None) -> dict:
    """The model's checked explanation of one flagged record, saved as an AI result; why not, when it cannot."""
    from ai.execution import record_ai_execution
    from genai.provider import GenAIProvider, GenAIUnavailable
    from investigator.model_provider import ModelAnalysisUnavailable, parse_json_reply

    fields = record_fields(record)
    if not fields.get("description") and not fields.get("harm"):
        return _refused("NOT_RUN", "NOTHING_TO_EXPLAIN", "The record has no description or harm flags to explain.")
    reasons = [reason.get("label") for reason in flagged.get("reasons") or [] if reason.get("label")]
    signs = [sign.get("label") for sign in flagged.get("signs") or [] if sign.get("label")]
    provider = provider or GenAIProvider()
    try:
        result = provider.complete(
            "Explain what in this record looks like a complaint allegation.",
            {"flagged_because": reasons, "complaint_signs": signs},
            system=SYSTEM,
            json_output=True,
            max_output_tokens=600,
            evidence=[{"id": name, "text": f"{FIELDS[name]}: {value}"} for name, value in fields.items()],
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
    kept, dropped = check_sentences(parsed, fields)
    execution = record_ai_execution(
        db,
        tenant_id,
        provider=PROVIDER,
        model_name=result.model,
        model_version=result.model_version,
        prompt_template_version=VERSION,
        orchestration_version=VERSION,
        context_refs={"complaint_id": record["id"], "complaint": record.get("business_id")},
        evidence_refs={"fields": sorted(fields)},
        structured_output={
            "sentences": kept,
            "dropped": dropped,
            "model": {"provider": result.provider, "model": result.model},
        },
        validation_status="VALIDATED" if kept else "REJECTED",
        latency_ms=result.latency_ms,
        requestor_ref=str(actor_ref),
    )
    trust = getattr(execution, "trust", None)
    if not kept:
        return {
            **_refused("NOTHING_KEPT", "Every sentence failed a check"),
            "ai": {
                "status": "NOTHING_KEPT",
                "reason": "Every sentence failed a check",
                "dropped": dropped,
                "trust": trust,
            },
        }
    return {
        "author": "AI",
        "sentences": kept,
        "ai": {
            "status": "COMPLETED",
            "provider": result.provider,
            "model": result.model,
            "ai_execution_id": str(execution.id),
            "explained_at": execution.execution_timestamp.isoformat() if execution.execution_timestamp else None,
            "dropped": dropped,
            "trust": trust,
            "label": LABEL,
        },
    }


def latest(db: Session, tenant_id: uuid.UUID, complaint_ids: list[str]) -> dict[str, dict]:
    """``{complaint id: its latest kept explanation}`` for the records on one page (two queries)."""
    from backend.app.db.models.foundation import AIExecution, AssuranceResult
    from trust_engine.auto import POLICY, STATUS_LABELS

    ids = [str(value) for value in complaint_ids if value]
    if not ids:
        return {}
    rows = (
        db.query(AIExecution)
        .filter(
            AIExecution.tenant_id == tenant_id,
            AIExecution.provider == PROVIDER,
            AIExecution.validation_status == "VALIDATED",
            AIExecution.context_refs["complaint_id"].astext.in_(ids),
        )
        .order_by(AIExecution.execution_timestamp.desc())
        .all()
    )
    found: dict[str, object] = {}
    for row in rows:
        found.setdefault(str((row.context_refs or {}).get("complaint_id")), row)
    if not found:
        return {}
    verdicts: dict[uuid.UUID, str] = {}
    for result in (
        db.query(AssuranceResult)
        .filter(
            AssuranceResult.tenant_id == tenant_id,
            AssuranceResult.ai_execution_id.in_([row.id for row in found.values()]),
            AssuranceResult.trust_policy_version == POLICY,
        )
        .order_by(AssuranceResult.assurance_version)
    ):
        verdicts[result.ai_execution_id] = result.status
    views = {}
    for complaint_id, row in found.items():
        output = row.structured_output or {}
        model = output.get("model") or {}
        status = verdicts.get(row.id)
        views[complaint_id] = {
            "author": "AI",
            "sentences": output.get("sentences") or [],
            "ai": {
                "status": "COMPLETED",
                "provider": model.get("provider"),
                "model": model.get("model") or row.model_name,
                "ai_execution_id": str(row.id),
                "explained_at": row.execution_timestamp.isoformat() if row.execution_timestamp else None,
                "dropped": output.get("dropped") or [],
                "trust": {"status": status, "label": STATUS_LABELS.get(status, "Not checked")} if status else None,
                "label": LABEL,
            },
        }
    return views
