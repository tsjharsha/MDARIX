"""The rules of the human decision, without a database: the outcomes and follow-up actions with their labels, what a
signing request must hold, which case states take a decision, the supersede rules, what the signer is refused and why,
the signed material (fingerprint, signature hash, snapshot hash) and how a signed decision is verified.

Imported by the router, the readiness checks (``outcome_label``) and the unit tests.

A decision is signed on one approved Decision Brief version: the signature binds the outcome, the rationale, the
conditions, the follow-up actions, the brief version, its evidence-set fingerprint and the context snapshot. A signed
decision is never edited; a correction is a new decision that supersedes it.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

from backend.app.db.models.decision_outcomes import DECISION_OUTCOMES, FOLLOW_UP_ACTIONS
from backend.app.decision_brief.rules import canonical_json, sha256_text

# ---------------------------------------------------------------------------------------------------- outcomes

ACCEPT_CONCLUSION = "ACCEPT_CONCLUSION"
ACCEPT_WITH_CONDITIONS = "ACCEPT_WITH_CONDITIONS"
REJECT_CONCLUSION = "REJECT_CONCLUSION"
CLOSE_NO_FURTHER_ACTION = "CLOSE_NO_FURTHER_ACTION"

OUTCOMES: dict[str, tuple[str, str]] = {
    ACCEPT_CONCLUSION: (
        "Accept the conclusion",
        "The proposed conclusion of the brief becomes the conclusion of the case.",
    ),
    ACCEPT_WITH_CONDITIONS: (
        "Accept with conditions",
        "The proposed conclusion is accepted on the conditions written with the decision.",
    ),
    REJECT_CONCLUSION: (
        "Reject the conclusion",
        "The proposed conclusion is not accepted: the brief goes back to its author and the case back to work.",
    ),
    CLOSE_NO_FURTHER_ACTION: (
        "Close with no further action",
        "The case needs no further action and can be closed.",
    ),
}

# Outcomes that accept the conclusion (follow-up actions go with these only).
ACCEPTING = frozenset({ACCEPT_CONCLUSION, ACCEPT_WITH_CONDITIONS})
# Outcomes that decide the case (it becomes DECIDED); a rejection sends it back to work.
CONCLUDING = frozenset({ACCEPT_CONCLUSION, ACCEPT_WITH_CONDITIONS, CLOSE_NO_FURTHER_ACTION})

FOLLOW_UP_LABELS: dict[str, str] = {
    "CAPA_REQUIRED": "CAPA required",
    "PRODUCT_CHANGE_REQUIRED": "Product change required",
    "FIELD_ACTION_REVIEW_REQUIRED": "Field action review required",
    "RISK_REASSESSMENT_REQUIRED": "Risk reassessment required",
    "REGULATORY_ACTION_REQUIRED": "Regulatory action required",
}
# The role queue a follow-up lands in when nobody in particular is asked (and the case has no owner to ask).
FOLLOW_UP_ROLES: dict[str, str] = {
    "CAPA_REQUIRED": "REVIEWER",
    "PRODUCT_CHANGE_REQUIRED": "REVIEWER",
    "FIELD_ACTION_REVIEW_REQUIRED": "REVIEWER",
    "RISK_REASSESSMENT_REQUIRED": "RISK_REVIEWER",
    "REGULATORY_ACTION_REQUIRED": "REGULATORY_REVIEWER",
}
FOLLOW_UP_DUE_DAYS = 30
FOLLOW_UPS_MAX = 10

# signed_approval_records.decision holds at most 12 characters: each outcome is signed under a short code.
SIGNATURE_CODES: dict[str, str] = {
    ACCEPT_CONCLUSION: "ACCEPT",
    ACCEPT_WITH_CONDITIONS: "ACCEPT_COND",
    REJECT_CONCLUSION: "REJECT",
    CLOSE_NO_FURTHER_ACTION: "CLOSE_NFA",
}
OUTCOME_BY_CODE: dict[str, str] = {code: outcome for outcome, code in SIGNATURE_CODES.items()}

# What a decision on a brief is recorded as (decisions.decision_type, signed_approval_records.decision_type).
DECISION_TYPE = "CASE_DECISION"
DECISION_KIND = "BRIEF"
SIGNED = "SIGNED"
SUPERSEDED = "SUPERSEDED"
DECISION_STATUS_LABELS: dict[str, str] = {SIGNED: "Signed", SUPERSEDED: "Superseded"}

RATIONALE_MIN, RATIONALE_MAX = 20, 5000
CONDITIONS_MIN, CONDITIONS_MAX = 10, 5000
SUPERSEDE_REASON_MIN, SUPERSEDE_REASON_MAX = 10, 2000
RETURN_COMMENT_MIN, RETURN_COMMENT_MAX = 10, 5000
RETURN_PREFIX = "Returned by the decision maker: "

# The case states a decision is taken in: ready for decision; when a signed decision is to be superseded, also a
# decided case or one taken back to work.
DECIDING_STATE = "READY_FOR_DECISION"
SUPERSEDING_STATES = frozenset({"DECIDED", "IN_PROGRESS"})


def outcome_label(code: str | None) -> str | None:
    found = OUTCOMES.get(str(code or "").upper())
    return found[0] if found else code


def follow_up_label(code: str | None) -> str | None:
    return FOLLOW_UP_LABELS.get(str(code or "").upper(), code) if code else None


def decision_status_label(code: str | None) -> str | None:
    return DECISION_STATUS_LABELS.get(str(code or "").upper(), code) if code else None


def outcome_options() -> list[dict]:
    return [{"code": code, "label": label, "description": text} for code, (label, text) in OUTCOMES.items()]


def follow_up_options() -> list[dict]:
    return [{"code": code, "label": label} for code, label in FOLLOW_UP_LABELS.items()]


def default_follow_up_role(action_type: str) -> str:
    return FOLLOW_UP_ROLES.get(str(action_type or "").upper(), "INVESTIGATOR")


def case_state_after(outcome: str) -> str:
    """Where the case goes once the decision is signed: decided, or back in progress after a rejection."""
    return "DECIDED" if str(outcome or "").upper() in CONCLUDING else "IN_PROGRESS"


def decision_identifier(investigation_identifier: str | None, number: int) -> str:
    """``<case identifier>-D<n>`` (decisions.decision_identifier, at most 120 characters)."""
    suffix = f"-D{int(number)}"
    base = str(investigation_identifier or "CASE").strip() or "CASE"
    return base[: 120 - len(suffix)] + suffix


def is_critical(priority: str | None, serious_harm: bool) -> bool:
    return str(priority or "").strip().upper() == "CRITICAL" or bool(serious_harm)


# ----------------------------------------------------------------------------------------------------- requests


def _text(value) -> str | None:
    text = str(value or "").strip()
    return text or None


class FollowUpRequest(BaseModel):
    """One follow-up action chosen while signing. Nobody named: the case owner, else the action's role queue."""

    action_type: str = Field(pattern="^(" + "|".join(FOLLOW_UP_ACTIONS) + ")$")
    title: str | None = Field(default=None, max_length=300)
    assignee_user_id: uuid.UUID | None = None
    assigned_role: str | None = Field(default=None, max_length=60)
    due_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return _text(value)

    @field_validator("assigned_role")
    @classmethod
    def _role(cls, value: str | None) -> str | None:
        from backend.app.role_codes import role_code
        from backend.app.workflow.labels import known_role

        value = _text(value)
        if value is None:
            return None
        if not known_role(value):
            raise ValueError("Choose a workflow role for the follow-up")
        return role_code(value)

    @field_validator("due_at")
    @classmethod
    def _due(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class SignPayload(BaseModel):
    """The signing request. Only single fields are checked here; what depends on several fields is checked by
    ``payload_problem`` in the endpoint, so a refusal never echoes the password back."""

    brief_version_id: uuid.UUID
    brief_content_hash: str = Field(min_length=64, max_length=64, pattern="^[0-9a-fA-F]{64}$")
    outcome: str = Field(pattern="^(" + "|".join(DECISION_OUTCOMES) + ")$")
    rationale: str = Field(max_length=RATIONALE_MAX + 1000)
    conditions: str | None = Field(default=None, max_length=CONDITIONS_MAX + 1000)
    follow_ups: list[FollowUpRequest] = Field(default_factory=list, max_length=FOLLOW_UPS_MAX)
    residual_unknowns_acknowledged: bool = False
    supersedes_decision_id: uuid.UUID | None = None
    supersede_reason: str | None = Field(default=None, max_length=SUPERSEDE_REASON_MAX + 1000)
    # The root-cause attribution (tr02, T-G36): required for every new signature; "undetermined" needs its reason.
    root_cause_attribution: str | None = Field(default=None, max_length=30)
    attribution_reason: str | None = Field(default=None, max_length=4000)
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, min_length=6, max_length=12)

    @field_validator("brief_content_hash")
    @classmethod
    def _hash(cls, value: str) -> str:
        return value.lower()

    @field_validator("rationale", "conditions", "supersede_reason")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


def request_hash(tenant_id, signer_id, case_id, payload: SignPayload) -> str:
    """The canonical identity of one signing request: the organization, the signer, the case and everything signed,
    never the password or the authenticator code. A retry with the same identity is the same signing (DEV-07)."""
    import hashlib
    import json

    signed = payload.model_dump(mode="json", exclude={"password", "mfa_code"})
    material = {"tenant": str(tenant_id), "signer": str(signer_id), "case": str(case_id), "request": signed}
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ReturnPayload(BaseModel):
    brief_version_id: uuid.UUID
    comment: str = Field(max_length=RETURN_COMMENT_MAX + 1000)

    @field_validator("comment")
    @classmethod
    def _comment(cls, value: str) -> str:
        text = str(value or "").strip()
        if len(text) < RETURN_COMMENT_MIN:
            raise ValueError(f"Say in at least {RETURN_COMMENT_MIN} characters what the brief needs")
        if len(text) > RETURN_COMMENT_MAX:
            raise ValueError(f"Keep the comment to at most {RETURN_COMMENT_MAX} characters")
        return text


def payload_problem(
    *,
    outcome: str,
    rationale: str | None,
    conditions: str | None,
    follow_up_types: Iterable[str],
    supersedes_decision_id,
    supersede_reason: str | None,
) -> str | None:
    """Why a signing request does not hold together (in words people read); None when it does.

    - the rationale has 20 to 5000 characters;
    - "Accept with conditions" needs conditions of 10 to 5000 characters; other outcomes take none;
    - follow-up actions go with an accepting outcome only;
    - a decision that supersedes another says why in 10 to 2000 characters, and a reason needs a decision to
      supersede.
    """
    outcome = str(outcome or "").upper()
    if outcome not in OUTCOMES:
        return "Choose one of the decision outcomes"
    rationale = str(rationale or "").strip()
    if len(rationale) < RATIONALE_MIN:
        return f"Write the rationale of the decision in at least {RATIONALE_MIN} characters"
    if len(rationale) > RATIONALE_MAX:
        return f"Keep the rationale to at most {RATIONALE_MAX} characters"
    conditions = str(conditions or "").strip()
    if outcome == ACCEPT_WITH_CONDITIONS:
        if len(conditions) < CONDITIONS_MIN:
            return f"Write the conditions in at least {CONDITIONS_MIN} characters"
        if len(conditions) > CONDITIONS_MAX:
            return f"Keep the conditions to at most {CONDITIONS_MAX} characters"
    elif conditions:
        return "Conditions go only with the outcome 'Accept with conditions'"
    if list(follow_up_types or ()) and outcome not in ACCEPTING:
        return f"'{outcome_label(outcome)}' takes no follow-up actions"
    reason = str(supersede_reason or "").strip()
    if supersedes_decision_id is not None:
        if len(reason) < SUPERSEDE_REASON_MIN:
            return f"Say in at least {SUPERSEDE_REASON_MIN} characters why this decision replaces the earlier one"
        if len(reason) > SUPERSEDE_REASON_MAX:
            return f"Keep the reason for replacing the earlier decision to at most {SUPERSEDE_REASON_MAX} characters"
    elif reason:
        return "A reason for superseding goes only with the decision it supersedes"
    return None


# ------------------------------------------------------------------------------------------------------ refusals

STALE_BRIEF = ("STALE_BRIEF", "This is no longer the approved version of the brief; open the current one")
BRIEF_TAMPERED = (
    "BRIEF_TAMPERED",
    "The stored brief no longer matches its fingerprint; it cannot be signed. Tell your quality lead",
)
SUPERSEDE_REQUIRED = (
    "SUPERSEDE_REQUIRED",
    "This case already has a signed decision; a new decision must name it as the decision it supersedes",
)
SUPERSEDE_MISMATCH = (
    "SUPERSEDE_REQUIRED",
    "A new decision supersedes only the case's current signed decision; name that decision",
)
SUPERSEDE_NOT_ALLOWED = ("SUPERSEDE_NOT_ALLOWED", "This case has no signed decision to supersede")
AUTHOR_DENIED = ("SOD_DENIED", "You wrote or submitted this brief; another authorized person decides on it")
NOT_ENTITLED = ("DENIED_NOT_ENTITLED", "Your organization's plan does not include controlled signatures")
ADMINISTRATOR_DENIED = (
    "ADMINISTRATOR_CANNOT_SIGN",
    "Administrators do not approve or sign; an approver of your organization must do this",
)


def brief_problem(
    *, status: str | None, stored_hash: str | None, sent_hash: str | None, recomputed_hash: str | None
) -> tuple[str, str] | None:
    """Why this brief version cannot be signed: not the approved version, or not the content the signer saw
    (STALE_BRIEF), or stored content that no longer matches its own fingerprint (BRIEF_TAMPERED)."""
    from backend.app.decision_brief.rules import APPROVED_FOR_DECISION

    if str(status or "").upper() != APPROVED_FOR_DECISION:
        return STALE_BRIEF
    if not stored_hash or str(sent_hash or "").lower() != str(stored_hash).lower():
        return STALE_BRIEF
    if recomputed_hash != stored_hash:
        return BRIEF_TAMPERED
    return None


def state_allows(state: str | None, has_current_decision: bool) -> bool:
    """A decision is taken on a case ready for decision; superseding a signed decision may also happen on a decided
    case or one taken back to work."""
    state = str(state or "").upper()
    return state == DECIDING_STATE or (has_current_decision and state in SUPERSEDING_STATES)


def state_refusal(state_label: str | None) -> tuple[str, str]:
    return (
        "CASE_NOT_READY_FOR_DECISION",
        f"The case is {str(state_label or 'not ready').lower()}; a decision is taken once its brief is approved",
    )


def supersede_problem(current_decision_id, supersedes_decision_id) -> tuple[str, str] | None:
    """A case has at most one current signed decision on a brief: a new one must name it (SUPERSEDE_REQUIRED), and
    without one nothing is superseded (SUPERSEDE_NOT_ALLOWED)."""
    current = str(current_decision_id) if current_decision_id else None
    named = str(supersedes_decision_id) if supersedes_decision_id else None
    if current is None:
        return SUPERSEDE_NOT_ALLOWED if named else None
    if named is None:
        return SUPERSEDE_REQUIRED
    if named != current:
        return SUPERSEDE_MISMATCH
    return None


def is_author(user_id, author_refs: Iterable) -> bool:
    """Segregation of duties: whoever wrote, edited or submitted the brief never decides on it."""
    actor = str(user_id or "").strip().lower()
    if not actor:
        return True
    return actor in {str(ref or "").strip().lower() for ref in author_refs or ()}


def sign_refusal(
    *,
    administrator: bool,
    entitled: bool,
    brief: tuple[str, str] | None,
    state_ok: bool,
    state_label: str | None,
    authority_denial: tuple[str, str] | None,
    author: bool,
) -> tuple[str, str] | None:
    """Why the person may not sign (the first reason, in the order the endpoint checks); None when they may. The
    supersede rule is not a refusal here: the screen offers the decision to supersede."""
    if administrator:
        return ADMINISTRATOR_DENIED
    if not entitled:
        return NOT_ENTITLED
    if brief is not None:
        return brief
    if not state_ok:
        return state_refusal(state_label)
    if authority_denial is not None:
        return authority_denial
    if author:
        return AUTHOR_DENIED
    return None


# ------------------------------------------------------------------------------------------------------ the brief


def residual_unknowns(content: Mapping | None) -> list[dict]:
    """The open questions and accepted limitations of a brief (what the decision maker acknowledges), as stored with
    the decision."""
    unknowns = (content or {}).get("unknowns") if isinstance(content, Mapping) else None
    unknowns = unknowns if isinstance(unknowns, Mapping) else {}
    result: list[dict] = []
    for kind, key in (("OPEN", "open"), ("ACCEPTED_LIMITATION", "accepted_limitations")):
        for item in unknowns.get(key) or ():
            if not isinstance(item, Mapping):
                continue
            result.append(
                {
                    "kind": kind,
                    "business_id": item.get("business_id"),
                    "description": item.get("description"),
                    "status": item.get("status"),
                    "resolution": item.get("resolution"),
                }
            )
    return result


def ai_execution_refs(content: Mapping | None) -> list[str]:
    """The business ids of the AI runs the brief discloses."""
    ai = (content or {}).get("ai_assistance") if isinstance(content, Mapping) else None
    executions = ai.get("executions") if isinstance(ai, Mapping) else None
    return [
        str(item["business_id"]) for item in executions or () if isinstance(item, Mapping) and item.get("business_id")
    ]


def evidence_set_hash(content: Mapping | None) -> str | None:
    context = (content or {}).get("context") if isinstance(content, Mapping) else None
    value = context.get("evidence_set_hash") if isinstance(context, Mapping) else None
    return str(value) if value else None


def required_reviews(content: Mapping | None) -> list[dict]:
    """The risk and regulatory reviews of the brief that were done or required, with their outcomes."""
    result = []
    for key, review_type, label in (
        ("risk_review", "RISK", "Risk review"),
        ("regulatory_review", "REGULATORY", "Regulatory review"),
    ):
        section = (content or {}).get(key) if isinstance(content, Mapping) else None
        if not isinstance(section, Mapping) or str(section.get("state") or "") == "NOT_REQUIRED":
            continue
        review = section.get("review") if isinstance(section.get("review"), Mapping) else {}
        result.append(
            {
                "review_type": review_type,
                "label": label,
                "state": section.get("state"),
                "outcome": review.get("outcome"),
                "business_id": review.get("business_id"),
                "reviewer_name": review.get("reviewer_name"),
                "completed_at": review.get("completed_at"),
            }
        )
    return result


# ------------------------------------------------------------------------------------------------- the signature


def signature_meaning(
    brief_business_id: str | None,
    brief_version: int | None,
    outcome: str,
    signer_name: str | None = None,
    signer_role_label: str | None = None,
) -> str:
    """The meaning of the signature, in the signer's words: "I, Asha Rao, Leader (Quality Manager), have reviewed
    Decision Brief DBV000001 version 1 and decide: Accept the conclusion" (without a name: "I have reviewed ...")."""
    name = str(signer_name or "").strip()
    role = str(signer_role_label or "").strip()
    subject = f"I, {name}{f', {role}' if role else ''}," if name else "I"
    return (
        f"{subject} have reviewed Decision Brief {brief_business_id} version {brief_version} and decide: "
        f"{outcome_label(outcome)}"
    )


def follow_up_types(follow_up_actions: Iterable) -> list[str]:
    """The sorted action types of a decision's follow-up actions (stored as dicts, or plain codes)."""
    types = []
    for item in follow_up_actions or ():
        code = item.get("action_type") if isinstance(item, Mapping) else item
        if code:
            types.append(str(code))
    return sorted(types)


def signature_material(
    *,
    decision_id,
    version: str,
    outcome: str,
    remarks: str | None,
    brief_version_id,
    evidence_set_hash: str | None,
    snapshot_hash: str | None,
    conditions: str | None,
    follow_up_actions: Iterable,
) -> dict:
    """What a decision maker signs: the decision, the brief version and its fingerprint (``version``), the outcome,
    the rationale (``remarks``), the evidence-set fingerprint, the context snapshot's hash, the conditions and the
    follow-up action types."""
    return {
        "decision_id": str(decision_id),
        "version": str(version),
        "type": DECISION_TYPE,
        "decision": str(outcome),
        "remarks": remarks,
        "brief_version_id": str(brief_version_id) if brief_version_id else None,
        "evidence_set_hash": evidence_set_hash or None,
        "snapshot_hash": snapshot_hash or None,
        "conditions": (str(conditions).strip() or None) if conditions else None,
        "follow_ups": follow_up_types(follow_up_actions),
    }


def fingerprint(material: Mapping) -> str:
    """SHA-256 of the canonical JSON of the signed material."""
    return sha256_text(canonical_json(dict(material)))


def signature_hash(content_fingerprint: str, signer_user_id: str, version: str) -> str:
    """The signature: SHA-256 of fingerprint, signer and version (as legacy signatures are made)."""
    return hashlib.sha256((str(content_fingerprint) + str(signer_user_id) + str(version)).encode()).hexdigest()


def snapshot_hash(snapshot: Any) -> str:
    """SHA-256 of the canonical JSON of a context snapshot (what is stored reads back the same)."""
    return sha256_text(canonical_json(snapshot if snapshot is not None else {}))


def short_fingerprint(value: str | None) -> str | None:
    return f"{value[:8]}…{value[-8:]}" if value and len(value) > 16 else value


CHECK_LABELS: dict[str, str] = {
    "fingerprint": "Signed content",
    "signature": "Signature",
    "brief_hash": "Decision Brief fingerprint",
    "snapshot": "Context snapshot",
    "authority": "Approval authority",
    "separation": "Segregation of duties",
}


def _check(key: str, ok: bool, detail: str) -> dict:
    return {"key": key, "label": CHECK_LABELS[key], "ok": bool(ok), "detail": detail}


def verification_checks(
    *,
    record: Mapping,
    decision: Mapping,
    snapshot: Any,
    snapshot_found: bool,
    stored_snapshot_hash: str | None,
    brief_stored_hash: str | None,
    brief_recomputed_hash: str | None,
) -> list[dict]:
    """The checks of a signed decision on a brief: ``[{key, ok, detail}]`` for

    - ``fingerprint``: the signed material, recomputed from the signature record, the decision and the snapshot as
      stored now, still gives the recorded fingerprint, and the decision still holds the signed outcome and rationale;
    - ``signature``: the signature hash still binds that fingerprint to the signer and version, and is SIGNED;
    - ``brief_hash``: the brief version still recomputes to the fingerprint the decision was signed on;
    - ``snapshot``: the context snapshot is there and still has the hash recorded with the decision.

    ``record`` holds the signature (decision, remarks, object_version, content_fingerprint, signature_hash,
    signer_user_id, status); ``decision`` holds id, outcome, rationale, conditions, follow_up_actions,
    brief_version_id, evidence_set_hash, brief_content_hash."""
    outcome = OUTCOME_BY_CODE.get(str(record.get("decision") or ""), str(record.get("decision") or ""))
    version = str(record.get("object_version") or "")
    recomputed_snapshot = snapshot_hash(snapshot) if snapshot_found else None
    material = signature_material(
        decision_id=decision.get("id"),
        version=version,
        outcome=outcome,
        remarks=record.get("remarks"),
        brief_version_id=decision.get("brief_version_id"),
        evidence_set_hash=decision.get("evidence_set_hash"),
        snapshot_hash=recomputed_snapshot,
        conditions=decision.get("conditions"),
        follow_up_actions=decision.get("follow_up_actions") or (),
    )
    recorded = str(record.get("content_fingerprint") or "")
    consistent = outcome == str(decision.get("outcome") or "") and str(record.get("remarks") or "") == str(
        decision.get("rationale") or ""
    )
    fingerprint_ok = bool(recorded) and fingerprint(material) == recorded and consistent
    signature_ok = (
        bool(recorded)
        and signature_hash(recorded, str(record.get("signer_user_id") or ""), version) == record.get("signature_hash")
        and str(record.get("status") or "") == "SIGNED"
    )
    signed_brief = str(decision.get("brief_content_hash") or "")
    brief_ok = (
        bool(signed_brief)
        and signed_brief == version
        and brief_stored_hash == signed_brief
        and brief_recomputed_hash == signed_brief
    )
    snapshot_ok = snapshot_found and bool(stored_snapshot_hash) and recomputed_snapshot == stored_snapshot_hash
    return [
        _check(
            "fingerprint",
            fingerprint_ok,
            "The signed content is unchanged"
            if fingerprint_ok
            else "The decision, its rationale or its context no longer match what was signed",
        ),
        _check(
            "signature",
            signature_ok,
            "The signature matches the signed content and the signer"
            if signature_ok
            else "The signature does not match the signed content, the signer or the version",
        ),
        _check(
            "brief_hash",
            brief_ok,
            "The brief version still matches the fingerprint it was signed on"
            if brief_ok
            else "The brief version no longer matches the fingerprint it was signed on",
        ),
        _check(
            "snapshot",
            snapshot_ok,
            "The context snapshot is unchanged"
            if snapshot_ok
            else ("The context snapshot has changed" if snapshot_found else "The context snapshot is missing"),
        ),
    ]


def signer_checks(*, signer_user_id, signer_role_label: str | None, authority_id, author_refs) -> list[dict]:
    """The two rules enforced when signing, read back from what was recorded:

    - ``authority``: the decision records the approval authority the signer decided under (set only when one granted
      their role at signing);
    - ``separation``: the signer is not among the people who wrote, edited or submitted the brief."""
    role = f" as {signer_role_label}" if signer_role_label else ""
    separated = not is_author(signer_user_id, author_refs)
    return [
        _check(
            "authority",
            authority_id is not None,
            f"The signer held approval authority{role} when signing"
            if authority_id is not None
            else "No approval authority is recorded for the signer",
        ),
        _check(
            "separation",
            separated,
            "The signer did not write, edit or submit the brief"
            if separated
            else "The signer also wrote, edited or submitted the brief",
        ),
    ]


def verification_status(checks: list[dict] | None, signed: bool = True) -> str:
    if not signed:
        return "NOT_SIGNED"
    return "VALID" if checks and all(item["ok"] for item in checks) else "INVALID"
