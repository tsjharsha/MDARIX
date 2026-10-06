"""The rules of the controlled Decision Brief, without a database: statuses and quality actions with their labels, how
a version moves, the submission gate, the author's narrative, the canonical fingerprint (SHA-256) of a version, the
evidence-set fingerprint, which hypothesis leads, and how AI assistance is disclosed. Imported by the composition, the
router and the unit tests.

A brief never chooses a conclusion for people: the leading hypothesis is the one a person judged best supported
(never chosen from the AI's own status), and every AI statement stays labelled as an AI interpretation.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.db.models.reviews import BRIEF_STATUSES, QUALITY_ACTIONS

# --------------------------------------------------------------------------------------------------- statuses

DRAFT = "DRAFT"
READY_FOR_REVIEW = "READY_FOR_REVIEW"
UNDER_REVIEW = "UNDER_REVIEW"
RETURNED = "RETURNED"
APPROVED_FOR_DECISION = "APPROVED_FOR_DECISION"
SUPERSEDED = "SUPERSEDED"

STATUS_LABELS: dict[str, str] = {
    DRAFT: "Draft",
    READY_FOR_REVIEW: "Ready for quality review",
    UNDER_REVIEW: "Under quality review",
    RETURNED: "Returned to the author",
    APPROVED_FOR_DECISION: "Approved for decision",
    SUPERSEDED: "Superseded",
}
# A case has at most one brief on its way: being written or being reviewed.
IN_PROGRESS_STATUSES = frozenset({DRAFT, READY_FOR_REVIEW, UNDER_REVIEW})
# A new version starts from the latest one once that one is finished (returned, approved or replaced).
RESTART_STATUSES = frozenset({RETURNED, APPROVED_FOR_DECISION, SUPERSEDED})
# Quality review acts on a submitted version.
REVIEWABLE_STATUSES = frozenset({READY_FOR_REVIEW, UNDER_REVIEW})

START_REVIEW = "START_REVIEW"
ACCEPT_FOR_DECISION = "ACCEPT_FOR_DECISION"
ESCALATE = "ESCALATE"
REJECT_PROPOSED_CONCLUSION = "REJECT_PROPOSED_CONCLUSION"
RETURN_FOR_RISK_REVIEW = "RETURN_FOR_RISK_REVIEW"
RETURN_FOR_REGULATORY_REVIEW = "RETURN_FOR_REGULATORY_REVIEW"
ACTION_LABELS: dict[str, str] = {
    START_REVIEW: "Quality review started",
    ACCEPT_FOR_DECISION: "Accepted for decision",
    "RETURN_FOR_EVIDENCE": "Returned for more evidence",
    "RETURN_FOR_ANALYSIS": "Returned for more analysis",
    RETURN_FOR_RISK_REVIEW: "Returned for a risk review",
    RETURN_FOR_REGULATORY_REVIEW: "Returned for a regulatory review",
    REJECT_PROPOSED_CONCLUSION: "Proposed conclusion rejected",
    ESCALATE: "Escalated",
}
# What a reviewer decides (starting a review has its own endpoint).
REVIEW_ACTIONS = tuple(action for action in QUALITY_ACTIONS if action != START_REVIEW)
# Actions that send the version back to its author.
RETURN_ACTIONS = frozenset(
    {
        "RETURN_FOR_EVIDENCE",
        "RETURN_FOR_ANALYSIS",
        RETURN_FOR_RISK_REVIEW,
        RETURN_FOR_REGULATORY_REVIEW,
        REJECT_PROPOSED_CONCLUSION,
    }
)
# Returns that also ask for a new risk or regulatory review of the case.
REVIEW_REQUESTS: dict[str, str] = {RETURN_FOR_RISK_REVIEW: "RISK", RETURN_FOR_REGULATORY_REVIEW: "REGULATORY"}
COMMENT_MIN = 10
COMMENT_MAX = 5000
# The task an escalated review lands in (a QUALITY_REVIEW task for the leaders' queue).
ESCALATION_ROLE = "LEADER"


def status_label(code: str | None) -> str | None:
    return STATUS_LABELS.get(str(code or "").upper(), code) if code else None


def action_label(code: str | None) -> str | None:
    return ACTION_LABELS.get(str(code or "").upper(), code) if code else None


def status_after(current: str | None, action: str) -> str | None:
    """The status a version moves to when ``action`` is taken on it in ``current``; None when it cannot be taken."""
    current = str(current or "").upper()
    action = str(action or "").upper()
    if action == START_REVIEW:
        return UNDER_REVIEW if current == READY_FOR_REVIEW else None
    if current not in REVIEWABLE_STATUSES:
        return None
    if action == ACCEPT_FOR_DECISION:
        return APPROVED_FOR_DECISION
    if action in RETURN_ACTIONS:
        return RETURNED
    if action == ESCALATE:
        return UNDER_REVIEW
    return None


def case_state_after(action: str) -> str | None:
    """Where the case goes after a quality action: ready for decision on acceptance, back in progress on a return;
    None when it stays where it is."""
    action = str(action or "").upper()
    if action == ACCEPT_FOR_DECISION:
        return "READY_FOR_DECISION"
    if action in RETURN_ACTIONS:
        return "IN_PROGRESS"
    return None


def comment_problem(action: str, comment: str | None) -> str | None:
    """Why the reviewer's comment does not do for ``action``; None when it does. Every action but accepting needs
    a comment of 10 to 5000 characters; accepting may carry one of at most 5000."""
    text = " ".join(str(comment or "").split())
    if len(text) > COMMENT_MAX:
        return f"Keep the comment to at most {COMMENT_MAX} characters"
    if str(action or "").upper() == ACCEPT_FOR_DECISION:
        return None
    if len(text) < COMMENT_MIN:
        return f"Say in at least {COMMENT_MIN} characters why"
    return None


def sod_denied(actor_ref, *, created_by, submitted_by, contributors: Iterable = ()) -> bool:
    """Segregation of duties: whoever wrote, edited or submitted a version never reviews it."""
    actor = str(actor_ref or "").strip().lower()
    if not actor:
        return True
    people = {str(item or "").strip().lower() for item in (created_by, submitted_by, *(contributors or ()))}
    return actor in people


# -------------------------------------------------------------------------------------------------- narrative

NARRATIVE_TEXT_FIELDS = ("problem_statement", "proposed_conclusion", "author_notes")
NARRATIVE_TEXT_MAX = 10000
ACTIONS_MAX = 20
ACTION_TEXT_MAX = 1000
AI_DRAFT_LABEL = "AI draft: written by AI, not reviewed; use it only as a starting point"
REQUIRED_NARRATIVE = (
    ("problem_statement", "Problem statement", "Write the problem statement"),
    ("proposed_conclusion", "Proposed conclusion", "Write the proposed conclusion"),
)


def _clean(value) -> str:
    return str(value or "").strip()


def empty_narrative() -> dict:
    return {
        "problem_statement": "",
        "proposed_conclusion": "",
        "recommended_actions": [],
        "author_notes": "",
        "ai_draft_used": False,
        "ai_draft_text": None,
        "ai_draft_label": None,
        "ai_draft_source": None,
        "contributors": [],
    }


def normalize_narrative(data: dict | None) -> dict:
    """The narrative with every field present (older or partial narratives read the same way)."""
    narrative = empty_narrative()
    source = dict(data or {}) if isinstance(data, dict) else {}
    for key in NARRATIVE_TEXT_FIELDS:
        narrative[key] = _clean(source.get(key))
    narrative["recommended_actions"] = [
        _clean(item) for item in source.get("recommended_actions") or () if _clean(item)
    ][:ACTIONS_MAX]
    narrative["ai_draft_used"] = bool(source.get("ai_draft_used"))
    if narrative["ai_draft_used"]:
        narrative["ai_draft_text"] = _clean(source.get("ai_draft_text")) or None
        narrative["ai_draft_label"] = source.get("ai_draft_label") or AI_DRAFT_LABEL
        narrative["ai_draft_source"] = (
            source.get("ai_draft_source") if isinstance(source.get("ai_draft_source"), dict) else None
        )
    narrative["contributors"] = sorted({_clean(item) for item in source.get("contributors") or () if _clean(item)})
    return narrative


def with_contributor(narrative: dict, actor_ref) -> dict:
    """The narrative with ``actor_ref`` among the people who wrote it (kept for segregation of duties)."""
    result = normalize_narrative(narrative)
    actor = _clean(actor_ref)
    if actor:
        result["contributors"] = sorted({*result["contributors"], actor})
    return result


def merge_narrative(current: dict | None, changes: dict) -> tuple[dict, list[str]]:
    """``current`` with the author's ``changes`` applied (only the fields given), and the names of the fields that
    changed. Turning ``ai_draft_used`` off drops the AI draft text; it is never turned on here (only composing
    from an AI brief does that)."""
    result = normalize_narrative(current)
    changed: list[str] = []
    for key in NARRATIVE_TEXT_FIELDS:
        if key in changes and changes[key] is not None:
            value = _clean(changes[key])
            if value != result[key]:
                result[key] = value
                changed.append(key)
    if "recommended_actions" in changes and changes["recommended_actions"] is not None:
        actions = [_clean(item) for item in changes["recommended_actions"] if _clean(item)][:ACTIONS_MAX]
        if actions != result["recommended_actions"]:
            result["recommended_actions"] = actions
            changed.append("recommended_actions")
    if changes.get("ai_draft_used") is False and result["ai_draft_used"]:
        result.update({"ai_draft_used": False, "ai_draft_text": None, "ai_draft_label": None, "ai_draft_source": None})
        changed.append("ai_draft_used")
    return result, changed


def narrative_problems(narrative: dict | None) -> list[dict]:
    """The narrative fields a submission needs that are still empty, as blocking checks."""
    data = normalize_narrative(narrative)
    return [
        {"key": key, "label": label, "result": "BLOCKED", "rationale": message}
        for key, label, message in REQUIRED_NARRATIVE
        if not data[key]
    ]


def ai_draft_text(ai_brief_content: dict | None) -> str | None:
    """Plain text of an AI brief (investigation_briefs.content) for the author to start from: the language model's
    headline and sections when it drafted the brief, else the rule-assembled summary. None when there is nothing."""
    content = ai_brief_content if isinstance(ai_brief_content, dict) else {}
    lines: list[str] = []
    model = content.get("ai_brief") if isinstance(content.get("ai_brief"), dict) else {}
    sections = model.get("sections") if isinstance(model.get("sections"), dict) else None
    if model.get("headline") and sections is not None:
        lines.append(_clean(model.get("headline")))
        titles = (
            ("what_we_know", "What we know"),
            ("what_conflicts", "What conflicts"),
            ("what_is_missing", "What is missing"),
            ("leading_hypotheses", "Leading hypotheses (AI interpretation)"),
            ("next_steps", "Possible next steps"),
        )
        for key, title in titles:
            items = [_clean(item.get("statement")) for item in sections.get(key) or () if isinstance(item, dict)]
            items = [item for item in items if item]
            if items:
                lines.append("")
                lines.append(f"{title}:")
                lines.extend(f"- {item}" for item in items)
    else:
        summary = content.get("executive_summary") if isinstance(content.get("executive_summary"), dict) else {}
        if _clean(summary.get("text")):
            lines.append(_clean(summary.get("text")))
        for item in summary.get("uncertainty") or ():
            if _clean(item):
                lines.append(f"- {_clean(item)}")
    text = "\n".join(lines).strip()
    return text[:NARRATIVE_TEXT_MAX] or None


# ------------------------------------------------------------------------------------------------------- gate

# Checks of the case's readiness the brief itself answers (its own review, the decision after it).
GATE_IGNORED_CHECKS = frozenset({"brief_ready", "decision"})
# Checks that must pass before a brief goes to quality review: a pending one blocks as a blocked one does.
GATE_REQUIRED_CHECKS = frozenset(
    {"scope_complete", "evidence_reviewed", "no_blocking_request", "risk_review", "regulatory_review"}
)
CONTENT_CHECK = {
    "key": "content_complete",
    "label": "The brief could be composed",
    "result": "BLOCKED",
    "rationale": "Some records of the case could not be read; refresh the brief and try again",
}


def check_blocks(check: dict) -> bool:
    key = str(check.get("key") or "")
    result = str(check.get("result") or "").upper()
    if key in GATE_IGNORED_CHECKS:
        return False
    return result == "BLOCKED" or (key in GATE_REQUIRED_CHECKS and result == "PENDING")


def evaluate_gate(
    checks: Iterable[dict], narrative: dict | None, *, content_complete: bool = True, check_narrative: bool = True
) -> dict:
    """Whether a brief may go to quality review: ``{"can_submit", "blocking", "warnings"}``. Blocking are the
    readiness checks that are BLOCKED (and the required ones still pending), the empty problem statement or proposed
    conclusion, and a brief whose records could not all be read; warnings are the other pending checks."""
    blocking: list[dict] = []
    warnings: list[dict] = []
    for check in checks or ():
        item = {key: check.get(key) for key in ("key", "label", "result", "rationale")}
        if check_blocks(check):
            blocking.append(item)
        elif str(check.get("key") or "") not in GATE_IGNORED_CHECKS and str(check.get("result") or "") == "PENDING":
            warnings.append(item)
    if check_narrative:
        blocking.extend(narrative_problems(narrative))
    if not content_complete:
        blocking.append(dict(CONTENT_CHECK))
    return {"can_submit": not blocking, "blocking": blocking, "warnings": warnings}


def blocked_checks(checks: Iterable[dict]) -> list[dict]:
    """``[{key, label}]`` of the readiness checks that are BLOCKED (the quality dashboard's blocked cases)."""
    return [
        {"key": check.get("key"), "label": str(check.get("label") or check.get("key"))}
        for check in checks or ()
        if check.get("result") == "BLOCKED"
    ]


# ------------------------------------------------------------------------------------------------ fingerprints


def jsonable(value: Any) -> Any:
    """``value`` as plain JSON data: dates as ISO text, UUIDs as text, tuples as lists, sets as sorted lists. What
    is stored in a JSONB column reads back the same, so the fingerprint can be checked later."""
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((jsonable(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def canonical_json(value: Any) -> str:
    """One text for the same data, whatever the order of its keys."""
    return json.dumps(jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_hash(content: dict | None, narrative: dict | None) -> str:
    """The fingerprint of a version: SHA-256 of the canonical JSON of its content and narrative."""
    return sha256_text(canonical_json({"content": content or {}, "narrative": narrative or {}}))


def evidence_set_hash(items: Iterable[tuple[Any, Any, Any]]) -> str:
    """SHA-256 over the case's evidence as sorted ``id|review status|relationship`` lines: it changes when evidence
    is added or judged differently, not when it is read in another order."""
    lines = sorted(
        f"{str(evidence_id).lower()}|{str(status or 'UNREVIEWED').upper()}|{str(relationship or 'UNREVIEWED').upper()}"
        for evidence_id, status, relationship in items or ()
    )
    return sha256_text("\n".join(lines))


# ----------------------------------------------------------------------------------------------- hypotheses

# A person's judgements that make a hypothesis a candidate to lead, strongest first.
LEADING_HUMAN_STATUSES: dict[str, int] = {"STRONGLY_SUPPORTED": 0, "PARTIALLY_SUPPORTED": 1}


def considered(hypothesis: dict) -> bool:
    """A hypothesis the case still considers: neither replaced by a newer AI run nor retired by a person."""
    return (
        str(hypothesis.get("ai_status") or "").lower() != "superseded"
        and str(hypothesis.get("human_status") or "").upper() != "RETIRED"
    )


def leading_hypothesis(hypotheses: Iterable[dict]) -> dict | None:
    """The hypothesis a person judged strongly (else partially) supported with the most supporting evidence (then
    the least contradicting); None when no person judged one so. The AI's own status never makes one lead."""
    candidates = [
        item
        for item in hypotheses or ()
        if considered(item) and str(item.get("human_status") or "").upper() in LEADING_HUMAN_STATUSES
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            LEADING_HUMAN_STATUSES[str(item.get("human_status")).upper()],
            -int(item.get("supporting_count") or 0),
            int(item.get("contradicting_count") or 0),
            str(item.get("business_id") or item.get("id") or ""),
        ),
    )


def alternative_hypotheses(hypotheses: Iterable[dict], leading: dict | None) -> list[dict]:
    """Every other hypothesis the case still considers, in a stable order."""
    lead = (leading or {}).get("id")
    return sorted(
        (item for item in hypotheses or () if considered(item) and (lead is None or item.get("id") != lead)),
        key=lambda item: str(item.get("business_id") or item.get("id") or ""),
    )


# ----------------------------------------------------------------------------------------------- AI disclosure

AI_KIND_LABELS: dict[str, str] = {
    "mdarix-controlled-investigator": "Case analysis",
    "mdarix-controlled-hypothesis-engine": "Hypotheses",
    "mdarix-controlled-ai-challenger": "Challenge of the hypotheses",
    "mdarix-controlled-failure-chain": "Failure chain",
    "mdarix-controlled-decision-advisory": "Decision advisory",
    "deterministic-r1": "Rule-based analysis",
}
AI_JUDGEMENT_SENTENCE = "Every AI statement is labelled AI interpretation; people made the judgements."
NO_AI_STATEMENT = "No AI was used in this case. People made the judgements."


def ai_kind(provider: str | None, prompt_template_version: str | None = None) -> str:
    known = AI_KIND_LABELS.get(str(provider or "").strip().lower())
    if known:
        return known
    return str(prompt_template_version or "").strip() or "AI run"


def ai_statement(executions: list[dict], *, ai_draft_used: bool = False) -> str:
    """The disclosure of AI assistance printed with the brief."""
    if not executions and not ai_draft_used:
        return NO_AI_STATEMENT
    parts: list[str] = []
    if executions:
        kinds = sorted({str(item.get("kind") or "AI run") for item in executions})
        models = sorted({str(item.get("model") or "") for item in executions if item.get("model")})
        run_text = f"{len(executions)} AI run" + ("" if len(executions) == 1 else "s")
        parts.append(
            f"{run_text} ({', '.join(kinds)})" + (f" with {', '.join(models)}" if models else "") + " in this case"
        )
    if ai_draft_used:
        parts.append("the author started the narrative from an AI draft")
    return "AI assisted: " + "; ".join(parts) + ". " + AI_JUDGEMENT_SENTENCE


# ------------------------------------------------------------------------------------------------ reviews

NOT_REQUIRED_TEXT = "Not required by policy"
NOT_DONE_TEXT = "Not done"


def review_section(review: dict | None, check: dict | None) -> dict:
    """A risk or regulatory review as the brief shows it: the latest review that is not superseded, else whether
    policy requires one (from the case's readiness check)."""
    result = str((check or {}).get("result") or "").upper()
    if review:
        completed = str(review.get("status") or "").upper() == "COMPLETED"
        return {
            "state": "COMPLETED" if completed else "IN_PROGRESS",
            "text": None if completed else "Requested, not completed yet",
            "review": review,
            "check": result or None,
        }
    if result == "NOT_REQUIRED":
        return {"state": "NOT_REQUIRED", "text": NOT_REQUIRED_TEXT, "review": None, "check": result}
    return {"state": "NOT_DONE", "text": NOT_DONE_TEXT, "review": None, "check": result or None}


# ------------------------------------------------------------------------------------------------- actions


def brief_actions(
    *,
    status: str | None,
    can_work: bool,
    can_quality_review: bool,
    is_author: bool,
    case_open: bool,
    gate_ok: bool,
) -> dict[str, bool]:
    """What the signed-in person may do with the case's latest version (``status`` None: no version yet)."""
    status = str(status or "").upper() or None
    editable = case_open and can_work and status == DRAFT
    reviewer = case_open and can_quality_review and not is_author
    return {
        "can_compose": case_open and can_work and (status is None or status in RESTART_STATUSES),
        "can_edit": editable,
        "can_submit": editable and gate_ok,
        "can_start_review": reviewer and status == READY_FOR_REVIEW,
        "can_review": reviewer and status in REVIEWABLE_STATUSES,
    }


# ------------------------------------------------------------------------------------------------- requests


def _text(value) -> str | None:
    text = str(value or "").strip()
    return text or None


class ComposePayload(BaseModel):
    """Start a version. ``use_ai_draft`` copies the latest AI brief's text into the narrative as an AI draft."""

    use_ai_draft: bool = False


class DraftPayload(BaseModel):
    """The author's narrative of a draft; only the fields given change."""

    problem_statement: str | None = Field(default=None, max_length=NARRATIVE_TEXT_MAX)
    proposed_conclusion: str | None = Field(default=None, max_length=NARRATIVE_TEXT_MAX)
    recommended_actions: list[str] | None = Field(default=None, max_length=ACTIONS_MAX)
    author_notes: str | None = Field(default=None, max_length=NARRATIVE_TEXT_MAX)
    ai_draft_used: bool | None = None

    @field_validator("recommended_actions")
    @classmethod
    def _actions(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if any(len(str(item or "")) > ACTION_TEXT_MAX for item in value):
            raise ValueError(f"Write each recommended action in at most {ACTION_TEXT_MAX} characters")
        return [str(item).strip() for item in value if str(item or "").strip()]

    @model_validator(mode="after")
    def _something(self):
        if not self.model_fields_set:
            raise ValueError("Give at least one field of the narrative")
        return self


class SubmitPayload(BaseModel):
    comment: str | None = Field(default=None, max_length=COMMENT_MAX)

    @field_validator("comment")
    @classmethod
    def _comment(cls, value: str | None) -> str | None:
        return _text(value)


class StartReviewPayload(SubmitPayload):
    pass


class ReviewPayload(BaseModel):
    action: str = Field(pattern="^(" + "|".join(REVIEW_ACTIONS) + ")$")
    comment: str | None = Field(default=None, max_length=COMMENT_MAX)

    @field_validator("comment")
    @classmethod
    def _comment(cls, value: str | None) -> str | None:
        return _text(value)

    @model_validator(mode="after")
    def _comment_needed(self):
        problem = comment_problem(self.action, self.comment)
        if problem:
            raise ValueError(problem)
        return self


REVIEW_REASON_MAX = 2000


def shorten(text: str | None, limit: int = REVIEW_REASON_MAX) -> str:
    """One line of at most ``limit`` characters (the reason a review request carries)."""
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def known_status(code: str | None) -> bool:
    return str(code or "").upper() in BRIEF_STATUSES
