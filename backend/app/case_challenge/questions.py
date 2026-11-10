"""Challenge questions, rules C-1 to C-9, rule version 1 (B5 spec 2.4). Pure: computed on read from the facts, the
drafts and the current hypotheses.

Material questions (C-1, C-2, C-3, C-4 above 20%, C-5) block "Submit for review" until answered or marked not
applicable with a reason (owner decision B5-D3); the others are warnings. Each question says which rule asked it.
"""

from __future__ import annotations

from backend.app.case_challenge.rules import (
    RULE_VERSION,
    SMALL_NUMBERS,
    STRONG_WORDS,
    UNKNOWN_SHARE_MATERIAL,
    _considered,
    _group,
    _n,
    _rec,
    _units_unknown,
    _versions_lots,
    question_label,
)
from backend.app.decision_brief import rules as brief_rules

# An answer, or the reason a question does not apply, is at least this long.
ANSWER_MIN = 10
ANSWER_MAX = 4000
NOT_APPLICABLE = "NOT_APPLICABLE"


def _question(rule: str, key: str, text: str, material: bool, records: list[dict] | None = None) -> dict:
    return {
        "rule": rule,
        "rule_version": RULE_VERSION,
        "key": key,
        "label": question_label(rule),
        "text": text,
        "material": material,
        "records": records or [],
    }


def _hyp(item: dict) -> dict:
    return {"type": "hypothesis", "id": item["id"], "ref": item["business_id"]}


def _from_supplier(link: dict) -> bool:
    """Evidence that is the supplier's own statement: its type or source names the supplier (fields only, IV-10)."""
    words = f"{link.get('evidence_type') or ''} {link.get('source_reference') or ''}".lower()
    return "supplier" in words


def c1_unlinked_contradiction(facts, leading, mine) -> list[dict]:
    if not leading or int(leading.get("contradicting_count") or 0):
        return []
    asked = []
    for draft in mine:
        if draft["against"]:
            records = [r for fact in draft["against"] for r in fact["records"]]
            asked.append(
                _question(
                    "C-1",
                    f"C-1:{leading['id']}:{draft['key']}",
                    f"{draft['against'][0]['text']} Does your leading explanation ({leading['business_id']}) account "
                    "for them?",
                    True,
                    [_hyp(leading), *records],
                )
            )
    return asked


def c2_one_explanation(hypotheses) -> list[dict]:
    if len(hypotheses) != 1:
        return []
    (only,) = hypotheses
    return [
        _question(
            "C-2",
            f"C-2:{only['id']}",
            "What else could explain this? Name one alternative and why the records speak against it.",
            True,
            [_hyp(only)],
        )
    ]


def c3_timing(facts, found) -> list[dict]:
    """Scope complaints before a suspected change: one a person's hypothesis already names (the H-1 duplicate)."""
    asked = []
    for draft in found:
        if draft["rule"] != "H-1" or not draft["duplicate_of"]:
            continue
        change = next(item for item in facts["changes"] if f"H-1:{item['id']}" == draft["key"])
        early = [c for c in facts["complaints"] if c["event_on"] and c["event_on"] < change["effective_on"]]
        if early:
            asked.append(
                _question(
                    "C-3",
                    f"C-3:{change['id']}",
                    f"{_n(len(early), 'complaint')} happened before {change['ref']} took effect "
                    f"({change['effective_on'].isoformat()}). What explains them?",
                    True,
                    [_rec("change", change), *(_rec("complaint", c) for c in early)],
                )
            )
    return asked


def c4_unknowns(facts) -> list[dict]:
    complaints = facts["complaints"]
    if not complaints:
        return []
    gaps = [c for c in complaints if c["version_id"] is None or c["lot_id"] is None]
    no_units = _units_unknown(_versions_lots(facts, {c["version_id"] for c in complaints if c["version_id"]}))
    if not gaps and not no_units:
        return []
    parts = []
    if gaps:
        no_version = sum(1 for c in gaps if c["version_id"] is None)
        parts.append(
            f"{len(gaps)} of {len(complaints)} complaints have no version or no lot ({no_version} without a version). "
            f"Conclusions about a version cover {len(complaints) - no_version} of {len(complaints)}."
        )
    if no_units:
        parts.append(f"Units are unknown for {_n(len(no_units), 'lot')}: rates cannot be compared per unit.")
    return [
        _question(
            "C-4",
            "C-4",
            " ".join(parts),
            len(gaps) / len(complaints) > UNKNOWN_SHARE_MATERIAL,
            [*(_rec("complaint", c) for c in gaps), *(_rec("lot", lot) for lot in no_units)],
        )
    ]


def c5_open_question(facts, leading) -> list[dict]:
    if not leading:
        return []
    return [
        _question(
            "C-5",
            f"C-5:{unknown['id']}",
            f"{unknown['ref']} is still open on your leading explanation: {unknown['description']} Wait for it, or "
            "accept it as a limitation with a reason.",
            True,
            [_hyp(leading), {"type": "unknown", "id": unknown["id"], "ref": unknown["ref"]}],
        )
        for unknown in facts["unknowns"]
        if unknown["open"] and unknown["hypothesis_id"] == leading["id"]
    ]


def c6_supplier_assertion(facts, leading) -> list[dict]:
    if not leading:
        return []
    support = [
        link for link in facts["links"] if link["hypothesis_id"] == leading["id"] and link["relation"] == "support"
    ]
    if not support or not all(_from_supplier(link) for link in support):
        return []
    return [
        _question(
            "C-6",
            f"C-6:{leading['id']}",
            "Only the supplier's statement supports this. What independent evidence is there?",
            False,
            [_hyp(leading), *({"type": "evidence", "id": item["evidence_id"], "ref": item["ref"]} for item in support)],
        )
    ]


def c7_outside_scope(facts) -> list[dict]:
    asked = []
    scope_versions = {v for v, item in facts["versions"].items() if item["in_scope"]}
    outside = [c for c in facts["outside"] if c["version_id"] and c["version_id"] not in scope_versions]
    for version_id, items in sorted(_group(outside, "version_id").items()):
        version = facts["versions"].get(version_id)
        if version is not None:
            asked.append(
                _question(
                    "C-7",
                    f"C-7:{version_id}",
                    f"{version['ref']} also has {_n(len(items), 'complaint')} with the same problem. Should the scope "
                    "include it?",
                    False,
                    [_rec("version", version), *(_rec("complaint", c) for c in items)],
                )
            )
    box = facts.get("pattern") or {}
    for row in box.get("versions", []) if box.get("found") else []:
        if row["version_id"] not in facts["versions"]:
            ref = f"{row['product']} {row['version']}"
            asked.append(
                _question(
                    "C-7",
                    f"C-7:{row['version_id']}",
                    f"{ref} (another product with {box['supplier']} parts) has {_n(row['recent'], 'complaint')} with "
                    "the same problem. Should it be looked at?",
                    False,
                    [{"type": "version", "id": row["version_id"], "ref": ref}],
                )
            )
    return asked


def c8_small_numbers(facts) -> list[dict]:
    complaints = facts["complaints"]
    lots = _versions_lots(facts, {v for v, item in facts["versions"].items() if item["in_scope"]})
    if not complaints or (len(complaints) >= SMALL_NUMBERS and lots and not _units_unknown(lots)):
        return []
    why = (
        f"The scope holds {_n(len(complaints), 'complaint')}."
        if len(complaints) < SMALL_NUMBERS
        else "Units are unknown, so rates rest on calendar days."
    )
    return [_question("C-8", "C-8", f"{why} Is this enough to conclude?", False)]


def c9_strong_words(facts, leading) -> list[dict]:
    conclusion = str(facts.get("conclusion") or "").lower()
    strong = [word for word in STRONG_WORDS if word in conclusion]
    if not strong or str((leading or {}).get("human_status") or "").upper() == "STRONGLY_SUPPORTED":
        return []
    judged = str((leading or {}).get("human_status_label") or "not judged strongly supported").lower()
    return [
        _question(
            "C-9",
            "C-9",
            f"Your conclusion says '{strong[0]}'; the leading hypothesis is {judged}.",
            False,
            [_hyp(leading)] if leading else [],
        )
    ]


def questions(facts: dict, found: list[dict]) -> list[dict]:
    """Every question whose condition is met, in rule order (C-1 to C-9)."""
    hypotheses = _considered(facts)
    leading = brief_rules.leading_hypothesis(hypotheses)
    mine = [d for d in found if leading and d["duplicate_of"] == leading["business_id"]]
    return [
        *c1_unlinked_contradiction(facts, leading, mine),
        *c2_one_explanation(hypotheses),
        *c3_timing(facts, found),
        *c4_unknowns(facts),
        *c5_open_question(facts, leading),
        *c6_supplier_assertion(facts, leading),
        *c7_outside_scope(facts),
        *c8_small_numbers(facts),
        *c9_strong_words(facts, leading),
    ]


def answered(answer: dict | None) -> bool:
    """An answer, or "not applicable" with a reason, long enough to stand."""
    return bool(answer) and len(str(answer.get("text") or "").strip()) >= ANSWER_MIN


def blocking(asked: list[dict], answers: dict) -> list[dict]:
    """Material questions not yet answered (or marked not applicable with a reason): they block submit (B5-D3)."""
    return [item for item in asked if item["material"] and not answered((answers or {}).get(item["key"]))]
