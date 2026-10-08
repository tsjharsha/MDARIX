"""The Regulatory copilot: the language model drafts the document's sections from the organization's own records.

The rules draft (service.py) stays the controlled result: its sections, citation verification and traceability are
what MDARIX vouches for. The model is asked, through ``genai.grounding.advisory`` (workflow ``regulatory_draft``),
to write draft text for each required section from authorized context only:

* the request itself - document type, the sections the template requires, what the author already wrote, the
  claims and the citations that verified against the official source catalog (never the rejected ones);
* the organization's evidence - the authorized investigation context (``genai.grounding.build_authorized_context``,
  allowlisted fields, tenant- and case-scoped) when a case is named, otherwise the tenant-scoped evidence search
  (``genai.ask.search_evidence``), so nothing from another organization can reach the model.

Every section the model writes is checked like an Ask answer (``genai.ask.check_answer``): citations of evidence it
was not given and causal or decision wording are flagged on the section. The draft is never authoritative and always
needs human review. When the model may not or cannot answer (AI switched off, budget used, provider not allowed or
unavailable, or no provider configured) the layout-only rules draft is returned as ``RULES_ONLY`` with the reason.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from .service import AUTHORING_SECTIONS, TEMPLATES, RegulatoryDraft

WORKFLOW = "regulatory_draft"
AI_DRAFTED, RULES_ONLY = "AI_DRAFTED", "RULES_ONLY"
NOT_CONFIGURED = {
    "code": "GENAI_PROVIDER_NOT_CONFIGURED",
    "user_message": "No AI service is configured for MDARIX here, so the draft is the section layout only.",
}
EMPTY_ANSWER = {
    "code": "GENAI_UNAVAILABLE",
    "user_message": "The AI service returned no draft, so the draft is the section layout only; please try again.",
}
_HEADING = re.compile(r"(?m)^\s*#{1,4}\s*([A-Za-z_ ]+?)\s*$")


def drafting_question(document_type: str, title: str | None) -> str:
    """The drafting request sent as the advisory's question: one Markdown section per required section id."""
    sections = ", ".join(AUTHORING_SECTIONS[document_type])
    return (
        f"Draft the text of a {TEMPLATES[document_type]}"
        + (f" titled '{title}'" if title else "")
        + ". Write one Markdown section per required section, headed exactly '## <section_id>' using these ids in "
        f"this order: {sections}. Under each heading write at most 150 words of plain draft text built only from the "
        "authorized context and evidence records; cite evidence identifiers in square brackets, for example "
        "[EV-001], and cite only identifiers you were given. Where the records do not support a section, write "
        "'Not supported by the available records.' and name what is missing. Keep the author's own text and claims; "
        "do not state compliance, equivalence, safety or effectiveness as established, and do not claim causality."
    )


def _evidence_context_from_search(found: dict[str, Any]) -> list[dict[str, Any]]:
    """Search results in the shape of an authorized evidence context (identifier, title, type, date, excerpt)."""
    return [
        {
            "evidence_identifier": item.get("id"),
            "title": item.get("title"),
            "evidence_type": item.get("type"),
            "temporal": {"effective_timestamp": item.get("date")},
            "chunks": [{"excerpt": item.get("text")}] if item.get("text") else [],
        }
        for item in found.get("evidence") or []
    ]


def grounded_context(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    document_type: str,
    request: dict[str, Any],
    rules_draft: RegulatoryDraft,
    investigation_id: uuid.UUID | None = None,
    product_version_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """The only context the model sees (see the module docstring). The caller has checked that the investigation
    and version, when given, belong to ``tenant_id``."""
    from genai.grounding import CONTEXT_POLICY_VERSION, build_authorized_context

    context: dict[str, Any] = {
        "policy_version": CONTEXT_POLICY_VERSION,
        "tenant_scope_enforced": True,
        "field_policy": "SERVER_ALLOWLIST_FAIL_CLOSED",
        "document": {
            "document_type": document_type,
            "template": TEMPLATES[document_type],
            "title": request.get("title"),
            "required_sections": list(AUTHORING_SECTIONS[document_type]),
            "authored_sections": {
                key: str(value)[:2000]
                for key, value in (request.get("authoring_sections") or {}).items()
                if key in AUTHORING_SECTIONS[document_type] and value
            },
            "claims": [
                {"claim_id": item.get("claim_id"), "text": str(item.get("text", ""))[:1000]}
                for item in (request.get("claims") or [])[:50]
            ],
            # Only citations that verified against the official source catalog; rejected ones never reach the model.
            "verified_citations": [
                {
                    "citation_id": item.get("citation_id"),
                    "claim_id": item.get("claim_id"),
                    "traceability_key": item.get("traceability_key"),
                }
                for item in rules_draft.citations.get("verified", [])[:100]
            ],
        },
    }
    if investigation_id is not None:
        authorized = build_authorized_context(
            db, tenant_id=tenant_id, investigation_id=investigation_id, product_version_id=product_version_id
        )
        context.update({key: value for key, value in authorized.items() if key not in context})
    else:
        from genai.ask import search_evidence

        question = " ".join(
            [
                TEMPLATES[document_type],
                str(request.get("title") or ""),
                *context["document"]["authored_sections"].values(),
            ]
        )
        found = search_evidence(db, tenant_id=tenant_id, question=question, product_version_id=product_version_id)
        context["evidence_context"] = _evidence_context_from_search(found)
        context["limitations"] = list(found.get("limitations") or [])
    return context


def split_sections(answer: str, section_ids: tuple[str, ...]) -> dict[str, str]:
    """The model's text per required section ('## section_id' headings); text under other headings is dropped."""
    wanted = {section_id.lower(): section_id for section_id in section_ids}
    found: dict[str, str] = {}
    matches = list(_HEADING.finditer(answer or ""))
    for index, match in enumerate(matches):
        key = match.group(1).strip().lower().replace(" ", "_")
        if key not in wanted:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(answer)
        text = answer[match.end() : end].strip()
        if text:
            found[wanted[key]] = text
    return found


def _rules_only(reason: dict[str, Any], advisory_result: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": RULES_ONLY,
        "reason_code": reason["code"],
        "user_message": reason["user_message"],
        "provider": (advisory_result or {}).get("provider"),
        "model": (advisory_result or {}).get("model"),
        "sections_drafted": [],
        "checks": None,
        "human_review_required": True,
        "authoritative": False,
    }


def _refusal(result: dict[str, Any]) -> dict[str, Any] | None:
    """Why the advisory has no model draft, or None when it has one."""
    if result.get("status") == "REFUSED":
        return {"code": result.get("code") or "GENAI_UNAVAILABLE", "user_message": result.get("user_message")}
    if result.get("status") != "PROVIDER_COMPLETED":
        # An advisory without a refusal code (older genai): the provider failed.
        from genai.provider import REFUSAL_MESSAGES

        return {"code": "GENAI_UNAVAILABLE", "user_message": REFUSAL_MESSAGES["GENAI_UNAVAILABLE"]}
    output = result.get("provider_output") or {}
    if output.get("status") == "PROVIDER_NOT_CONFIGURED":
        return NOT_CONFIGURED
    if not str(output.get("answer") or "").strip():
        return EMPTY_ANSWER
    return None


def draft_with_model(
    *,
    document_type: str,
    title: str | None,
    rules_draft: RegulatoryDraft,
    context: dict[str, Any],
    provider=None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The rules draft's sections with the model's text added (``ai_draft`` and its ``ai_checks``) and the summary of
    the AI assistance (status AI_DRAFTED or RULES_ONLY with ``reason_code``)."""
    from genai.ask import check_answer
    from genai.grounding import advisory
    from genai.provider import GenAIUnavailable

    controlled = {
        "document_type": rules_draft.document_type,
        "sections": [
            {"section_id": item.get("section_id"), "status": item.get("status")}
            for item in rules_draft.sections
            if item.get("section_id")
        ],
        "traceability": rules_draft.citations.get("traceability"),
        "limitations": rules_draft.limitations,
    }
    try:
        result = advisory(
            workflow=WORKFLOW,
            deterministic_result=controlled,
            grounded_context=context,
            question=drafting_question(document_type, title),
            provider=provider,
        )
    except GenAIUnavailable as exc:  # an advisory that lets a refusal through
        refusal = exc.refusal() if callable(getattr(exc, "refusal", None)) else {"code": "GENAI_UNAVAILABLE"}
        result = {"status": "REFUSED", **refusal}
    sections = [dict(item) for item in rules_draft.sections]
    reason = _refusal(result)
    if reason is not None:
        if not reason.get("user_message"):
            from genai.provider import REFUSAL_MESSAGES

            reason = {**reason, "user_message": REFUSAL_MESSAGES.get(reason["code"], EMPTY_ANSWER["user_message"])}
        return sections, _rules_only(reason, result)

    answer = str(result["provider_output"]["answer"])
    known = {
        str(item.get("evidence_identifier"))
        for item in context.get("evidence_context") or []
        if item.get("evidence_identifier")
    }
    drafted = split_sections(answer, AUTHORING_SECTIONS[document_type])
    for section in sections:
        text = drafted.get(section.get("section_id") or "")
        if not text:
            continue
        checks = check_answer(text, known)
        section["ai_draft"] = text
        section["ai_checks"] = {
            "cited": checks["cited"],
            "unverified_citations": checks["unverified_citations"],
            "causal_or_decision_wording": checks["causal_or_decision_wording"],
            "notes": checks["notes"],
            "flagged": bool(checks["unverified_citations"] or checks["causal_or_decision_wording"]),
        }
        section["human_review_required"] = True
    whole = check_answer(answer, known)
    summary = {
        "status": AI_DRAFTED,
        "reason_code": None,
        "user_message": "The model drafted the sections from your organization's records; review every section.",
        "provider": result.get("provider"),
        "model": result.get("model"),
        "sections_drafted": [key for key in AUTHORING_SECTIONS[document_type] if key in drafted],
        "checks": {
            "unverified_citations": whole["unverified_citations"],
            "causal_or_decision_wording": whole["causal_or_decision_wording"],
            "notes": list(dict.fromkeys(whole["notes"] + list((result.get("checks") or {}).get("notes") or []))),
            "evidence_available": sorted(known),
            "flagged_sections": [
                section["section_id"] for section in sections if (section.get("ai_checks") or {}).get("flagged")
            ],
        },
        "unplaced_text": None if drafted else answer[:4000],
        "human_review_required": True,
        "authoritative": False,
    }
    return sections, summary
