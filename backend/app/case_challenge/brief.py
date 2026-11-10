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
            "records": item.get("records") or [],
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


def with_answers(content: dict, narrative: dict | None) -> dict:
    """The brief's ``challenge`` (each question with its answer from the narrative) and ``sources``, for the case
    record download; empty for a brief composed before B5 (its content is left as it was signed)."""
    if "challenge" not in (content or {}):
        return {}
    answers = (narrative or {}).get("challenge_answers") or {}
    challenge = {
        **content["challenge"],
        "questions": [
            {**item, "answer": answers.get(item["key"]) or item.get("answer")}
            for item in content["challenge"].get("questions") or ()
        ],
    }
    return {"challenge": challenge, "sources": content.get("sources") or {}}


KINDS = {group: kind for kind, group in GROUPS.items()}


def _kind(kind: str) -> str:
    """The document's source type ("Complaint", "Lot"...), which the screen opens."""
    return str(kind).capitalize()


ACTION_WORDS = {
    "ADOPTED": "adopted as {hypothesis}",
    "DISMISSED": "dismissed: {reason}",
    "NOT_ACTED_ON": "not acted on",
}


def document_sections(content: dict, narrative: dict | None, case_id, src, row, data) -> list[dict]:
    """The Challenge and Sources sections of the investigation report document (qms_documents), each row with the
    records it cites; none for a brief composed before B5. ``src``/``row``/``data`` are that module's builders."""
    found = with_answers(content, narrative)
    if not found:
        return []
    challenge, sources = found["challenge"], found["sources"]

    def cited(records) -> list[dict]:
        return [src(_kind(record["type"]), record["id"], record["ref"], case_id) for record in records]

    rows = []
    for draft in challenge["drafts"]:
        action = draft.get("action") or {}
        done = ACTION_WORDS.get(action.get("state") or "NOT_ACTED_ON", "not acted on").format(
            hypothesis=action.get("hypothesis") or "a hypothesis", reason=action.get("reason") or "no reason"
        )
        records = [
            record for fact in [*draft["for"], *draft["against"], *draft["missing"]] for record in fact["records"]
        ]
        rows.append(
            row(
                f"Drafted by rule {draft['rule']} (version {draft['rule_version']}), {draft['label']}: "
                f"{draft['statement']} For: {len(draft['for'])}; against: {len(draft['against'])}; missing: "
                f"{len(draft['missing'])}. {done[0].upper()}{done[1:]}.",
                cited(records),
            )
        )
    for item in challenge["questions"]:
        answer = item.get("answer") or {}
        reply = (
            ("Not applicable: " if answer.get("not_applicable") else "Answer: ") + answer["text"]
            if answer.get("text")
            else "Not answered."
        )
        rows.append(
            row(
                f"Question from rule {item['rule']} (version {item['rule_version']})"
                + (", material" if item["material"] else "")
                + f": {item['text']} {reply}",
                cited(item.get("records") or ()),
            )
        )
    source_rows = [
        row(
            f"{name.replace('_', ' ').capitalize()} ({group['count']}): "
            + ", ".join(f"{item['ref']} ({item['origin']})" for item in group["items"])
            + ".",
            [src(_kind(KINDS.get(name, name)), item["id"], item["ref"], case_id) for item in group["items"]],
        )
        for name, group in (sources.get("groups") or {}).items()
    ]
    source_rows.append(
        row("Rules: " + "; ".join(f"{r['rule']} v{r['version']} {r['name']}" for r in sources.get("rules") or ()) + ".")
    )
    return [
        data(
            "CHALLENGE",
            "Challenge",
            rows or [row("No draft or question followed from the records.")],
            note=challenge.get("notice"),
        ),
        data(
            "SOURCES",
            f"Sources ({sources.get('summary') or ''})",
            source_rows,
            note=f"Records as of {sources.get('as_of') or 'composition'}.",
        ),
    ]


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
