"""The Decision Brief's Challenge and Sources sections (B5 spec 2.5), composed with the rest of a new brief.

- ``challenge``: the drafts offered at composition (rule, version, adopted as HYP-n / dismissed with the reason / not
  acted on) and every question with its answer, who answered and when. The answers themselves are in the narrative
  (``challenge_answers``), which the content hash covers.
- ``sources``: every record the brief relies on, grouped by type, each with its ID, origin and the as-of time, and the
  rules (H-n, C-n, P-1) with their versions. Every statement of the challenge section cites records listed here, or is
  the rule's own statement of what is missing (its rule is listed).

Briefs already submitted or signed keep the content they were frozen with; only a brief composed now has the sections.
Material questions not answered block "Submit for review" (B5-D3) while the switch is on.
"""

from __future__ import annotations

from backend.app.case_challenge import rules

GROUPS = {
    "complaint": "complaints",
    "lot": "lots",
    "version": "versions",
    "component": "components",
    "supplier": "suppliers",
    "change": "changes",
    "evidence": "evidence",
    "hypothesis": "hypotheses",
    "unknown": "open_questions",
    "signal": "signals",
}
RULE_NAMES = {
    "H-0": "Not enough records",
    "H-1": "Component or supplier change",
    "H-2": "Lot or manufacturing",
    "H-3": "Design of the version",
    "H-4": "Use, setting or environment",
    "H-5": "Supplier part across products",
    "C-1": "Unlinked contradiction",
    "C-2": "One explanation only",
    "C-3": "Timing",
    "C-4": "Unknowns in the data",
    "C-5": "Open question on the leading hypothesis",
    "C-6": "Supplier assertion",
    "C-7": "Outside the scope",
    "C-8": "Small numbers",
    "C-9": "Strong words",
    "P-1": "Supplier part pattern (Supplier 360)",
}
# Records listed per group at most (the count says how many there are), as the brief caps its other lists.
GROUP_MAX = 200


def challenge_section(view: dict) -> dict:
    drafts = [
        {
            **{
                key: draft[key]
                for key in ("rule", "rule_version", "key", "label", "title", "statement", "duplicate_of")
            },
            "for": draft["for"],
            "against": draft["against"],
            "missing": draft["missing"],
            "action": {
                "state": (draft.get("action") or {}).get("state") or "NOT_ACTED_ON",
                "hypothesis": (draft.get("action") or {}).get("hypothesis"),
                "reason": (draft.get("action") or {}).get("reason"),
            },
        }
        for draft in view["drafts"]
    ]
    asked = [
        {
            **{key: item[key] for key in ("rule", "rule_version", "key", "label", "text", "material")},
            "answer": item.get("answer"),
        }
        for item in view["questions"]
    ]
    return {
        "rule_version": view["rule_version"],
        "notice": view["notice"],
        "scope_version": view["scope_version"],
        "fingerprint": view["fingerprint"],
        "drafts": drafts,
        "questions": asked,
        "blocking": view["blocking"],
    }


def sources_section(view: dict, evidence_rows: list[dict], signals: list[dict], as_of) -> dict:
    facts = view["facts"]
    origins = {
        item["id"]: item.get("origin")
        for item in [
            *facts["complaints"],
            *facts["outside"],
            *facts["lots"].values(),
            *facts["changes"],
            *facts["versions"].values(),
        ]
    }
    groups: dict[str, dict[str, dict]] = {name: {} for name in GROUPS.values()}

    def add(kind: str, record_id: str, ref: str) -> None:
        group = groups.setdefault(GROUPS.get(kind, kind), {})
        group.setdefault(
            str(record_id), {"id": str(record_id), "ref": ref, "origin": origins.get(str(record_id)) or "MDARIX"}
        )

    for item in facts["complaints"]:
        add("complaint", item["id"], item["ref"])
    for version in facts["versions"].values():
        if version["in_scope"]:
            add("version", version["id"], version["ref"])
    for row in evidence_rows:
        add("evidence", row["id"], row["business_id"] or row.get("evidence_identifier"))
    for row in signals:
        add("signal", row["id"], row["business_id"])
    used = []
    for draft in view["drafts"]:
        used.append(draft["rule"])
        for fact in [*draft["for"], *draft["against"], *draft["missing"]]:
            for record in fact["records"]:
                add(record["type"], record["id"], record["ref"])
    for item in view["questions"]:
        used.append(item["rule"])
        for record in item["records"]:
            add(record["type"], record["id"], record["ref"])
    if (facts.get("pattern") or {}).get("found"):
        used.append("P-1")
    listed = {
        name: sorted(items.values(), key=lambda item: str(item["ref"])) for name, items in groups.items() if items
    }
    count = sum(len(items) for items in listed.values())
    rule_rows = [
        {"rule": rule, "version": rules.RULE_VERSION, "name": RULE_NAMES.get(rule, rule)} for rule in sorted(set(used))
    ]
    return {
        "as_of": as_of,
        "count": count,
        "summary": f"{count} records, {len(rule_rows)} rules",
        "groups": {name: {"count": len(items), "items": items[:GROUP_MAX]} for name, items in listed.items()},
        "rules": rule_rows,
    }


def gate_items(challenge: dict | None) -> list[dict]:
    """Blocking gate items for the material questions not answered (as readiness checks read)."""
    if not challenge:
        return []
    asked = {item["key"]: item for item in challenge.get("questions") or ()}
    return [
        {
            "key": f"challenge:{key}",
            "label": f"Answer the challenge question ({asked[key]['rule']}): {asked[key]['text']}",
            "result": "BLOCKED",
            "rationale": f"{asked[key]['label']}. Answer it, or mark it not applicable with a reason.",
        }
        for key in challenge.get("blocking") or ()
        if key in asked
    ]
