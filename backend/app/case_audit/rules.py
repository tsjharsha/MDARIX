"""Pure rules of the case trust and audit views: timeline items and their titles, the merge of the history sources
(deduplicated, chronological, filtered, paged), "known then" partitioning and statuses as of a moment, the kind and
guardrail summary of an AI run, and the checks of a legacy signature. Nothing here reads the database.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

CATEGORIES = (
    "SIGNAL",
    "CASE",
    "SCOPE",
    "TASK",
    "EVIDENCE",
    "REQUEST",
    "INTELLIGENCE",
    "AI",
    "REVIEW",
    "BRIEF",
    "DECISION",
    "SIGNATURE",
    "FOLLOW_UP",
    "IMPACT",
    "AUDIT",
)
CATEGORY_ORDER = {code: index for index, code in enumerate(CATEGORIES)}
ORIGINS = ("HUMAN", "AI", "SYSTEM")
HUMAN, AI, SYSTEM = ORIGINS

PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 200
# An audit event repeats a history row when both name the same change of the same record within this many seconds.
DEDUPE_WINDOW_SECONDS = 5
DETAIL_KEYS_MAX = 12
DETAIL_TEXT_MAX = 200
REASON_MAX = 500
SYSTEM_NAME = "MDARIX"
UNKNOWN_PERSON = "Unknown user"

# Detail keys never shown, whatever their value (credentials, signing material, request metadata).
SECRET_KEY = re.compile(
    r"pass|secret|token|mfa|otp|cookie|session|credential|api[_-]?key|authorization|fingerprint|signature_hash"
    r"|source_ip|user_agent|prompt",
    re.IGNORECASE,
)
# Audit actions that are noise in a case history.
IGNORED_AUDIT_ACTIONS = frozenset({"REQUEST_MUTATION_COMPLETED"})

# ------------------------------------------------------------------------------------------------- time and text


def as_utc(value: Any) -> datetime | None:
    """A timezone-aware UTC datetime from a datetime or ISO text; None when it is neither."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def iso(value: Any) -> str | None:
    found = as_utc(value)
    return found.isoformat() if found is not None else None


def readable(code: str | None) -> str:
    """``CASE_REVIEW_COMPLETED`` -> ``Case review completed``."""
    words = str(code or "").replace("-", "_").strip("_").lower().split("_")
    text = " ".join(word for word in words if word)
    return text[:1].upper() + text[1:] if text else ""


def shorten(value: Any, limit: int = DETAIL_TEXT_MAX) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def title(label: str, detail: Any = None) -> str:
    """``Label: detail`` (or just the label)."""
    extra = shorten(detail, 160)
    return f"{label}: {extra}" if extra else label


def as_uuid_text(value: Any) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


# ------------------------------------------------------------------------------------------------------- people


def is_system_ref(ref: Any) -> bool:
    text = str(ref or "").strip().lower()
    return not text or text.startswith(("mdarix", "system", "scheduler", "worker"))


def origin_of(ref: Any, *, ai: bool = False) -> str:
    if ai:
        return AI
    return SYSTEM if is_system_ref(ref) else HUMAN


def actor_view(ref: Any, role: str | None, names: Mapping[str, str], role_label=None) -> dict | None:
    """``{name, role_label}`` of who made a change; None when nobody is recorded. An account id is shown by its
    name (never the id itself); MDARIX's own steps as "MDARIX"."""
    text = str(ref or "").strip()
    label = role_label(role) if (role_label is not None and role) else (role or None)
    if not text:
        return {"name": None, "role_label": label} if label else None
    key = as_uuid_text(text)
    if key is not None:
        name = names.get(key) or UNKNOWN_PERSON
    elif is_system_ref(text):
        name = SYSTEM_NAME
    else:
        name = shorten(text, 80)
    return {"name": name, "role_label": label}


# ------------------------------------------------------------------------------------------------------ details


def safe_details(details: Any, allowed: Iterable[str] | None = None) -> dict:
    """A small copy of ``details``: plain values only (text shortened), never a key that could carry a secret, at
    most ``DETAIL_KEYS_MAX`` keys; ``allowed`` keeps only those keys."""
    if not isinstance(details, Mapping):
        return {}
    wanted = set(allowed) if allowed is not None else None
    result: dict[str, Any] = {}
    for key, value in details.items():
        name = str(key)
        if (wanted is not None and name not in wanted) or SECRET_KEY.search(name):
            continue
        if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
            result[name] = value
        elif isinstance(value, str):
            if as_uuid_text(value) is not None and not name.endswith("business_id"):
                continue  # a bare id says nothing to a reader; business ids are added by the readers
            result[name] = shorten(value)
        elif isinstance(value, (list, tuple)) and all(isinstance(item, (str, int, float)) for item in value):
            items = [shorten(item, 60) if isinstance(item, str) else item for item in list(value)[:10]]
            if not any(isinstance(item, str) and as_uuid_text(item) for item in items):
                result[name] = items
        if len(result) >= DETAIL_KEYS_MAX:
            break
    return result


# -------------------------------------------------------------------------------------------------------- items


def item(
    *,
    at: Any,
    category: str,
    event: str,
    title: str,
    actor: dict | None = None,
    obj: dict | None = None,
    reason: Any = None,
    details: Mapping | None = None,
    origin: str = HUMAN,
    match: Iterable[Any] = (),
    aliases: Iterable[str] = (),
    source: str = "domain",
    key: str | None = None,
) -> dict:
    """One timeline item. Keys starting with ``_`` are for merging and are removed by ``public``."""
    return {
        "at": as_utc(at),
        "category": category if category in CATEGORY_ORDER else "AUDIT",
        "event": event,
        "title": title,
        "actor": actor,
        "object": obj,
        "reason": shorten(reason, REASON_MAX),
        "details": dict(details or {}),
        "origin": origin if origin in ORIGINS else SYSTEM,
        "_match": {text for text in (as_uuid_text(value) for value in match) if text},
        "_codes": {event, *aliases},
        "_source": source,
        "_key": key,
    }


def object_ref(kind: str, row_id: Any, business_id: str | None = None, label: str | None = None) -> dict:
    """The record an entry is about. A record without a business id of its own (an observation, a link) carries a
    readable label, so it is never named by its id alone."""
    ref = {"type": kind, "id": as_uuid_text(row_id) or (str(row_id) if row_id else None), "business_id": business_id}
    if label and not business_id:
        ref["label"] = label
    return ref


def public(entry: Mapping) -> dict:
    result = {key: value for key, value in entry.items() if not key.startswith("_")}
    result["at"] = iso(entry.get("at"))
    return result


def _duplicate_of_domain(entry: Mapping, domain: list[Mapping], window: timedelta) -> bool:
    at = entry.get("at")
    for other in domain:
        if entry["event"] not in other["_codes"]:
            continue
        if entry["_match"] and other["_match"] and not (entry["_match"] & other["_match"]):
            continue
        other_at = other.get("at")
        if at is None or other_at is None or abs(at - other_at) <= window:
            return True
    return False


def dedupe(items: Iterable[Mapping], window_seconds: int = DEDUPE_WINDOW_SECONDS) -> list[dict]:
    """Drop repeats: an item whose ``_key`` was already seen (the same audit event read from two planes), and an
    audit event that repeats a history row (same change code, same record, within ``window_seconds``)."""
    window = timedelta(seconds=window_seconds)
    seen: set[str] = set()
    unique: list[dict] = []
    for entry in items:
        key = entry.get("_key")
        if key:
            if key in seen:
                continue
            seen.add(key)
        unique.append(dict(entry))
    domain = [entry for entry in unique if entry.get("_source") != "audit"]
    by_code: dict[str, list[Mapping]] = {}
    for entry in domain:
        for code in entry["_codes"]:
            by_code.setdefault(code, []).append(entry)
    return [
        entry
        for entry in unique
        if entry.get("_source") != "audit" or not _duplicate_of_domain(entry, by_code.get(entry["event"], []), window)
    ]


_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def sort_items(items: Iterable[Mapping]) -> list[dict]:
    """Oldest first; at the same moment in the order of the case's flow, then by event and object."""
    return sorted(
        (dict(entry) for entry in items),
        key=lambda entry: (
            entry.get("at") or _EPOCH,
            CATEGORY_ORDER.get(entry.get("category"), len(CATEGORIES)),
            str(entry.get("event") or ""),
            str(((entry.get("object") or {}).get("business_id")) or ((entry.get("object") or {}).get("id")) or ""),
        ),
    )


def parse_types(value: str | None) -> set[str] | None:
    """``types=AI,decision`` -> {"AI", "DECISION"}; unknown codes are ignored; None when nothing is asked."""
    if not value:
        return None
    wanted = {part.strip().upper() for part in str(value).split(",") if part.strip()}
    return {code for code in wanted if code in CATEGORY_ORDER}


def filter_items(
    items: Iterable[Mapping],
    *,
    types: set[str] | None = None,
    actor: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict]:
    """Items of the given categories, by a person whose name contains ``actor`` (any case), at or after ``since``
    and at or before ``until``."""
    needle = str(actor or "").strip().lower()
    start, end = as_utc(since), as_utc(until)
    result = []
    for entry in items:
        if types is not None and entry.get("category") not in types:
            continue
        if needle and needle not in str(((entry.get("actor") or {}).get("name")) or "").lower():
            continue
        at = entry.get("at")
        if start is not None and (at is None or at < start):
            continue
        if end is not None and (at is None or at > end):
            continue
        result.append(dict(entry))
    return result


def category_counts(items: Iterable[Mapping]) -> dict[str, int]:
    counts = {code: 0 for code in CATEGORIES}
    for entry in items:
        counts[entry.get("category") or "AUDIT"] = counts.get(entry.get("category") or "AUDIT", 0) + 1
    return {code: count for code, count in counts.items() if count}


def page_of(items: list, page: int, page_size: int) -> list:
    size = max(1, min(int(page_size), PAGE_SIZE_MAX))
    start = (max(1, int(page)) - 1) * size
    return items[start : start + size]


def merge(sources: Iterable[Iterable[Mapping]]) -> list[dict]:
    """Every source's items in one deduplicated, chronological list."""
    return sort_items(dedupe(entry for source in sources for entry in source))


# --------------------------------------------------------------------------------------------- audit events

# Prefixes of audit actions and the category of their events (first match wins).
AUDIT_PREFIXES: tuple[tuple[str, str], ...] = (
    ("CASE_AUDIT_", "AUDIT"),
    ("TASK_", "TASK"),
    ("SIGNAL_", "SIGNAL"),
    ("INTELLIGENCE_", "INTELLIGENCE"),
    ("EVIDENCE_REQUEST", "REQUEST"),
    ("CASE_REVIEW_", "REVIEW"),
    ("BRIEF_GENERATED", "AI"),
    ("BRIEF_REGENERATED", "AI"),
    ("BRIEF_", "BRIEF"),
    ("FOLLOW_UP_", "FOLLOW_UP"),
    ("IMPACT_", "IMPACT"),
    ("DECISION_UNDER_RECONSIDERATION", "IMPACT"),
    ("CASE_DECISION_", "DECISION"),
    ("DECISION_ADVISORY", "AI"),
    ("DECISION_", "DECISION"),
    ("SIGNED_", "SIGNATURE"),
    ("SIGNATURE_", "SIGNATURE"),
    ("INVESTIGATION_SCOPE", "SCOPE"),
    ("INVESTIGATION_", "CASE"),
    ("NEXT_STEP", "CASE"),
    ("LATE_EVIDENCE", "EVIDENCE"),
    ("EVIDENCE_", "EVIDENCE"),
    ("GENAI_", "AI"),
    ("AI_", "AI"),
)
AUDIT_TITLES: dict[str, str] = {
    "INVESTIGATION_OPENED": "Case opened",
    "INVESTIGATION_CREATED": "Case opened",
    "INVESTIGATION_STATE_CHANGED": "Case state changed",
    "INVESTIGATION_UPDATED": "Case details updated",
    "INVESTIGATION_SCOPE_CHANGED": "Scope changed",
    "NEXT_STEP_RECORDED": "Next step recorded",
    "LATE_EVIDENCE_RECEIVED": "Evidence arrived after the decision",
    "CASE_DECISION_RETURNED": "Brief returned by the decision maker",
    "CASE_DECISION_SIGNED": "Decision signed",
    "CASE_DECISION_SUPERSEDED": "Decision superseded",
    "DECISION_UNDER_RECONSIDERATION": "Decision under reconsideration",
    "CASE_REVIEW_STARTED": "Review started",
    "CASE_REVIEW_RECUSED": "Reviewer stepped back from a review",
    "EVIDENCE_REQUESTED": "Evidence requested",
    "EVIDENCE_REQUEST_ACKNOWLEDGED": "Evidence request acknowledged",
    "EVIDENCE_REQUEST_RESPONDED": "Evidence request answered",
    "EVIDENCE_REQUEST_CANNOT_PROVIDE": "Evidence request answered: cannot provide",
    "EVIDENCE_REQUEST_CANCELLED": "Evidence request cancelled",
    "EVIDENCE_REQUEST_ATTACHMENT_UPLOADED": "File added to an evidence request",
    "EVIDENCE_REQUEST_REVIEWED": "Evidence request answer reviewed",
    "FOLLOW_UP_STARTED": "Follow-up started",
    "FOLLOW_UP_CAPA_CREATED": "CAPA opened from a follow-up",
    "FOLLOW_UP_TASK_RENEWED": "Follow-up task renewed",
    "GENAI_EXECUTION_RECORDED": "Ask MDARIX answered",
    "DECISION_ADVISORY_CREATED": "AI decision advisory produced",
    "BRIEF_GENERATED": "AI investigation brief generated",
    "BRIEF_REGENERATED": "AI investigation brief regenerated",
    "INVESTIGATION_RECORD_EXPORTED": "Case record exported",
    "CASE_AUDIT_EXPORTED": "Case audit exported",
}
# Keys of audit details worth showing (everything else stays in the audit trail itself).
AUDIT_DETAIL_KEYS = (
    "from_state",
    "to_state",
    "workflow_state",
    "status",
    "previous_status",
    "outcome",
    "conclusion",
    "brief_version",
    "version",
    "format",
    "sha256",
    "event",
    "from_status",
    "to_status",
    "review_type",
    "action_type",
    "trigger",
    "provider",
    "model",
    "disposition",
    "signal_business_id",
    "business_id",
    "decision_business_id",
    "evidence_business_id",
    "request_business_id",
    "counts",
)


def audit_category(action: str | None) -> str:
    code = str(action or "").upper()
    for prefix, category in AUDIT_PREFIXES:
        if code.startswith(prefix):
            return category
    return "AUDIT"


def audit_title(action: str | None, extra: Any = None) -> str:
    code = str(action or "").upper()
    if code.startswith("TASK_"):
        label = f"Task {readable(code[5:]).lower()}"
    elif code.startswith("INTELLIGENCE_"):
        label = f"Case intelligence: {readable(code[13:]).lower()}"
    else:
        label = AUDIT_TITLES.get(code) or readable(code) or "Recorded"
    return title(label, extra)


def audit_origin(actor_ref: Any, action: str | None) -> str:
    code = str(action or "").upper()
    if code in {"DECISION_ADVISORY_CREATED", "BRIEF_GENERATED", "BRIEF_REGENERATED"}:
        return AI
    return origin_of(actor_ref)


# ---------------------------------------------------------------------------------------- known then (replay)


def known_at(record_times: Iterable[Any], link_at: Any = None) -> datetime | None:
    """When the case knew a record: the first known of ``record_times`` (ingestion, recorded, created), and not
    before the record was linked to the case (``link_at``)."""
    record = next((found for found in (as_utc(value) for value in record_times) if found is not None), None)
    link = as_utc(link_at)
    if record is None:
        return link
    if link is None:
        return record
    return max(record, link)


def partition_known(items: Iterable[Mapping], as_of: Any, key: str = "known_at") -> tuple[list[dict], list[dict]]:
    """``(known_then, arrived_later)``: items whose ``key`` time is at or before ``as_of``, and the others (an item
    without a time is never "known then")."""
    moment = as_utc(as_of)
    known, later = [], []
    for entry in items:
        at = as_utc(entry.get(key))
        (known if (moment is not None and at is not None and at <= moment) else later).append(dict(entry))
    return known, later


def value_as_of(
    events: Iterable[tuple[Any, Any, Any]],
    as_of: Any,
    *,
    current: Any,
    current_changed_at: Any = None,
    default: Any = None,
) -> Any:
    """A recorded value (a status, a review status) as it stood at ``as_of``, from its history ``events``
    (``(at, from_value, to_value)``): the last change at or before then; before the first change, the value that
    change started from; without history, the current value when it was set by then (or never dated), else
    ``default``."""
    moment = as_utc(as_of)
    ordered = sorted(((as_utc(at), before, after) for at, before, after in events), key=lambda row: row[0] or _EPOCH)
    if moment is None:
        return current
    passed = [row for row in ordered if row[0] is not None and row[0] <= moment]
    if passed:
        return passed[-1][2]
    if ordered:
        return ordered[0][1] if ordered[0][1] is not None else default
    changed = as_utc(current_changed_at)
    if changed is None or changed <= moment:
        return current
    return default


def evidence_set_hash(items: Iterable[tuple[Any, Any, Any]]) -> str:
    """The evidence set fingerprint of the Decision Brief (backend/app/decision_brief/rules.py)."""
    from backend.app.decision_brief.rules import evidence_set_hash as brief_hash

    return brief_hash(items)


REPLAY_LIMITATIONS = (
    "A record counts as known then when MDARIX had it (ingestion, else recorded, else created time) and it was "
    "linked to the case by then.",
    "Review statuses and relationships of evidence, and statuses of hypotheses and unknowns, are rebuilt from their "
    "recorded history; a change made before that history was kept is shown as the value recorded later.",
    "Records deleted or purged since are not shown; edits that kept no history (titles, descriptions) are shown as "
    "they are now.",
    "The context snapshot is the exact record of what was signed; it is shown only when replaying at the moment of "
    "signing.",
)

# ---------------------------------------------------------------------------------------------------- AI runs

AI_KINDS = (
    "analysis",
    "hypotheses",
    "challenger",
    "unknowns",
    "failure_chain",
    "counterfactual",
    "brief",
    "decision_advisory",
    "ask",
    "scenario",
    "evidence_extraction",
    "other",
)
_PROVIDER_KINDS = {
    "mdarix-controlled-investigator": "analysis",
    "mdarix-controlled-hypothesis-engine": "hypotheses",
    "mdarix-controlled-ai-challenger": "challenger",
    "mdarix-controlled-unknowns-radar": "unknowns",
    "mdarix-controlled-failure-chain": "failure_chain",
    "mdarix-controlled-decision-advisory": "decision_advisory",
}
_TEMPLATE_KINDS = (
    ("investigator", "analysis"),
    ("hypothes", "hypotheses"),
    ("challenger", "challenger"),
    ("unknown", "unknowns"),
    ("failurechain", "failure_chain"),
    ("failure_chain", "failure_chain"),
    ("decisionadvisory", "decision_advisory"),
    ("counterfactual", "counterfactual"),
    ("d16", "counterfactual"),
    ("scenario", "scenario"),
    ("d32", "scenario"),
    ("brief", "brief"),
)


def ai_kind(provider: str | None, model_name: str | None = None, prompt_template_version: str | None = None) -> str:
    """What an AI run did, from its provider (MDARIX's controlled engines), else its model or prompt template."""
    known = _PROVIDER_KINDS.get(str(provider or "").strip().lower())
    if known:
        return known
    text = f"{model_name or ''} {prompt_template_version or ''}".lower()
    for needle, kind in _TEMPLATE_KINDS:
        if needle in text:
            return kind
    if str(prompt_template_version or "").strip().lower() == "v1.0":
        return "evidence_extraction"
    return "other"


def find_value(data: Any, key: str, depth: int = 4) -> Any:
    """The first value stored under ``key`` in nested dictionaries (breadth first, at most ``depth`` levels)."""
    level = [data]
    for _ in range(depth + 1):
        following = []
        for node in level:
            if isinstance(node, Mapping):
                if node.get(key) is not None and not isinstance(node.get(key), (Mapping, list)):
                    return node.get(key)
                following.extend(value for value in node.values() if isinstance(value, Mapping))
        level = following
        if not level:
            break
    return None


def _count(value: Any) -> int:
    return len(value) if isinstance(value, (list, tuple)) else 0


def guardrail_summary(structured_output: Any, validation_status: str | None, error_state: str | None) -> dict:
    """``{validation_status, checks, passed, failed: [names], rejected_items, dropped_statements, error}``."""
    output = structured_output if isinstance(structured_output, Mapping) else {}
    guardrails = output.get("guardrails") if isinstance(output.get("guardrails"), Mapping) else {}
    flags = {str(name): value for name, value in guardrails.items() if isinstance(value, bool)}
    provenance = output.get("model_provenance") if isinstance(output.get("model_provenance"), Mapping) else {}
    return {
        "validation_status": validation_status,
        "checks": len(flags),
        "passed": sum(1 for value in flags.values() if value),
        "failed": sorted(name for name, value in flags.items() if not value),
        "rejected_items": _count(output.get("rejected_items")),
        "dropped_statements": _count(provenance.get("checks_dropped")),
        "error": shorten(error_state, 160),
    }


def run_status(validation_status: str | None, error_state: str | None) -> str:
    code = str(validation_status or "").strip().upper()
    if "FAIL" in code or "ERROR" in code or "REJECT" in code:
        return "FAILED"
    return code or ("FAILED" if error_state else "COMPLETED")


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def usage(structured_output: Any) -> dict:
    """Tokens and cost as the run stored them (absent for MDARIX's rule-based engines)."""
    return {
        "input_tokens": _number(find_value(structured_output, "input_tokens")),
        "output_tokens": _number(find_value(structured_output, "output_tokens")),
        "estimated_cost": _number(find_value(structured_output, "estimated_cost")),
    }


def canonical_hash(value: Any) -> str:
    from backend.app.decision_brief.rules import canonical_json, sha256_text

    return sha256_text(canonical_json(value))


def context_hash(context_refs: Any, evidence_refs: Any) -> str | None:
    """SHA-256 of the canonical JSON of the context and evidence references an AI run was given."""
    if not context_refs and not evidence_refs:
        return None
    return canonical_hash({"context_refs": context_refs or {}, "evidence_refs": evidence_refs or {}})


def run_times(execution_timestamp: Any, latency_ms: Any) -> dict:
    """The run is recorded when it finishes (``execution_timestamp``); its start is that minus its duration."""
    finished = as_utc(execution_timestamp)
    duration = latency_ms if isinstance(latency_ms, int) and not isinstance(latency_ms, bool) else None
    started = finished - timedelta(milliseconds=duration) if finished is not None and duration else None
    return {"started_at": iso(started), "finished_at": iso(finished), "duration_ms": duration}


def ai_counts(runs: Iterable[Mapping]) -> dict:
    runs = list(runs)
    by_kind: dict[str, int] = {}
    for run in runs:
        by_kind[run.get("kind") or "other"] = by_kind.get(run.get("kind") or "other", 0) + 1
    return {
        "total": len(runs),
        "by_kind": by_kind,
        "used_in_signed_decision": sum(1 for run in runs if run.get("used_in_signed_decision")),
        "human_reviewed": sum(1 for run in runs if run.get("human_review")),
        "failed": sum(1 for run in runs if run.get("status") == "FAILED"),
    }


# ------------------------------------------------------------------------------------------------- integrity


def legacy_signature_checks(record: Mapping, decision_id: Any) -> list[dict]:
    """The checks of a signature made before the Decision Brief (governance_router.signature_verification)."""
    version = str(record.get("object_version") or "")
    material = {
        "decision_id": str(decision_id),
        "version": version,
        "type": record.get("decision_type"),
        "decision": record.get("decision"),
        "remarks": record.get("remarks"),
    }
    fingerprint = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
    recorded = str(record.get("content_fingerprint") or "")
    # The signature binds the recorded fingerprint to the signer and version; the fingerprint check catches content
    # changed since (both must hold, as in the governance verification).
    expected = hashlib.sha256((recorded + str(record.get("signer_user_id") or "") + version).encode()).hexdigest()
    fingerprint_ok = bool(recorded) and fingerprint == recorded
    signature_ok = (
        bool(recorded) and expected == record.get("signature_hash") and str(record.get("status") or "") == "SIGNED"
    )
    return [
        {
            "key": "fingerprint",
            "label": "Signed content",
            "ok": fingerprint_ok,
            "detail": "The signed content is unchanged" if fingerprint_ok else "The signed content has changed",
        },
        {
            "key": "signature",
            "label": "Signature",
            "ok": signature_ok,
            "detail": "The signature matches the signed content and the signer"
            if signature_ok
            else "The signature does not match the signed content, the signer or the version",
        },
    ]


def checks_status(checks: list[dict] | None) -> str:
    return "VALID" if checks and all(check.get("ok") for check in checks) else "INVALID"


def combine_chains(planes: list[dict]) -> dict:
    """One audit chain result from the result of each plane checked:
    BROKEN when any broke, NOT_CHECKED when any could not be checked, else VALID."""
    if not planes:
        return {"status": "NOT_CHECKED", "checked_events": 0, "first_break": None, "reason": "NO_PLANE", "planes": []}
    broken = [plane for plane in planes if plane.get("status") == "BROKEN"]
    unchecked = [plane for plane in planes if plane.get("status") == "NOT_CHECKED"]
    status = "BROKEN" if broken else ("NOT_CHECKED" if unchecked else "VALID")
    first = broken[0] if broken else None
    return {
        "status": status,
        "checked_events": sum(int(plane.get("checked_events") or 0) for plane in planes),
        "first_break": {"plane": first.get("plane"), "seq": first.get("first_broken_seq")} if first else None,
        "reason": (unchecked[0].get("reason") if unchecked and not broken else None),
        "planes": planes,
    }


# ---------------------------------------------------------------------------------------------------- export

TIMELINE_CSV_FIELDS = (
    "section",
    "at",
    "category",
    "event",
    "title",
    "actor",
    "actor_role",
    "origin",
    "object_type",
    "object_business_id",
    "reason",
    "details",
)


def csv_rows(timeline: Iterable[Mapping], runs: Iterable[Mapping], integrity: Mapping) -> list[dict]:
    """The export as flat rows: the timeline, then the AI runs, then the integrity results."""
    rows: list[dict] = []
    for entry in timeline:
        actor = entry.get("actor") or {}
        obj = entry.get("object") or {}
        rows.append(
            {
                "section": "TIMELINE",
                "at": entry.get("at"),
                "category": entry.get("category"),
                "event": entry.get("event"),
                "title": entry.get("title"),
                "actor": actor.get("name"),
                "actor_role": actor.get("role_label"),
                "origin": entry.get("origin"),
                "object_type": obj.get("type"),
                "object_business_id": obj.get("business_id"),
                "reason": entry.get("reason"),
                "details": json.dumps(entry.get("details") or {}, sort_keys=True, default=str),
            }
        )
    for run in runs:
        review = run.get("human_review") or {}
        rows.append(
            {
                "section": "AI_RUN",
                "at": run.get("finished_at"),
                "category": "AI",
                "event": run.get("kind"),
                "title": f"{run.get('provider')} {run.get('model')} {run.get('model_version') or ''}".strip(),
                "actor": review.get("by"),
                "actor_role": None,
                "origin": "AI",
                "object_type": "AIExecution",
                "object_business_id": run.get("business_id"),
                "reason": None,
                "details": json.dumps(
                    {
                        "status": run.get("status"),
                        "context_hash": run.get("context_hash"),
                        "used_in_signed_decision": run.get("used_in_signed_decision"),
                        "human_review": review.get("status"),
                    },
                    sort_keys=True,
                ),
            }
        )
    for signature in integrity.get("signatures") or ():
        rows.append(
            {
                "section": "SIGNATURE",
                "at": signature.get("signed_at"),
                "category": "SIGNATURE",
                "event": signature.get("status"),
                "title": f"Signature {signature.get('business_id')} on {signature.get('decision_business_id')}",
                "actor": (signature.get("signer") or {}).get("name"),
                "actor_role": (signature.get("signer") or {}).get("role_label"),
                "origin": "HUMAN",
                "object_type": "SignedApprovalRecord",
                "object_business_id": signature.get("business_id"),
                "reason": None,
                "details": json.dumps(
                    {check.get("key"): check.get("ok") for check in signature.get("checks") or ()}, sort_keys=True
                ),
            }
        )
    for brief in integrity.get("brief_hashes") or ():
        rows.append(
            {
                "section": "BRIEF_HASH",
                "at": None,
                "category": "BRIEF",
                "event": "VERIFIED" if brief.get("hash_verified") else "NOT_VERIFIED",
                "title": f"Brief {brief.get('business_id')} version {brief.get('version')}",
                "actor": None,
                "actor_role": None,
                "origin": "SYSTEM",
                "object_type": "DecisionBriefVersion",
                "object_business_id": brief.get("business_id"),
                "reason": None,
                "details": json.dumps({"hash_verified": brief.get("hash_verified")}),
            }
        )
    chain = integrity.get("audit_chain") or {}
    rows.append(
        {
            "section": "AUDIT_CHAIN",
            "at": None,
            "category": "AUDIT",
            "event": chain.get("status"),
            "title": "Audit trail hash chain",
            "actor": None,
            "actor_role": None,
            "origin": "SYSTEM",
            "object_type": None,
            "object_business_id": None,
            "reason": chain.get("reason"),
            "details": json.dumps(
                {"checked_events": chain.get("checked_events"), "first_break": chain.get("first_break")},
                sort_keys=True,
                default=str,
            ),
        }
    )
    return rows
