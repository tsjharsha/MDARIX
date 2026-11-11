"""The rule register, read-only (B4 step 8, R-D2, R-D13): every signed-in member reads every rule, its source, version
and dates; there is no write route. The register holds no organization's data. Answers 404 while
``MDARIX_RULE_REGISTER`` is off (``feature_set.serves_path``)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app import standards
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.rule_register import register

router = APIRouter(prefix="/api/v1/rule-register", tags=["Rule register"])

MARKET_LABELS = {
    "US": "United States (FDA)",
    "EU_NI": "EU and Northern Ireland (EU MDR)",
    "GB": "Great Britain (MHRA)",
    "IN": "India (CDSCO)",
    "CA": "Canada (Health Canada)",
}
ANSWER_WORDS = {"is_yes": "is Yes", "is_no": "is No", "is_unknown": "is Unknown", "maybe": "is not No"}


def _words(condition, content: dict) -> str:
    """A floor condition as a person reads it: question ids with their text, AND, OR, and the answer tests."""
    if isinstance(condition, str):
        text = next((q["text"] for q in content["question_set"]["questions"] if q["id"] == condition), "")
        return f"{condition} ({text})" if text else condition
    (operator, argument), *_ = condition.items()
    if operator in ("any", "all"):
        joined = (" OR " if operator == "any" else " AND ").join(_words(part, content) for part in argument)
        return f"({joined})"
    if operator == "ref":
        return "the event is reportable" if argument == "reportable" else argument.replace("_", " ")
    if operator == "type":
        return f"the report is {content['report_types'][argument]['label']}"
    return f"{_words(argument, content)} {ANSWER_WORDS[operator]}"


def _logic(content: dict) -> dict:
    """The floor's logic as readable IF ... THEN ... lines (the detail drawer)."""
    label = {code: kind["label"] for code, kind in content["report_types"].items()}
    return {
        "defined": [f"{name.replace('_', ' ')} = {_words(c, content)}" for name, c in content["defs"].items()],
        "reportable": [
            f"{r['id']}: IF {_words(r['if'], content)} THEN reportable ({r['cite']})" for r in content["rules"]
        ],
        "report_type": [
            f"{row['id']}: IF {_words(row['if'], content)} THEN {label[row['type']]}"
            if "if" in row
            else f"{row['id']}: OTHERWISE {label[row['type']]}"
            for row in content["type_rows"]
        ],
        "not_asked": [
            f"IF {_words(row['if'], content)} THEN {', '.join(row['fold'])}: {row['why']}" for row in content["folding"]
        ],
        "report_types": [
            {"code": code, "label": kind["label"], "days": kind["days"], "basis": kind["basis"]}
            for code, kind in content["report_types"].items()
        ],
        "counting": content["counting"],
        "questions": [
            {"id": q["id"], "text": q["text"], "clause": q["clause"]} for q in content["question_set"]["questions"]
        ],
    }


def view(entry: dict, day: date | None = None) -> dict:
    fingerprint = entry.get("content_hash") or entry.get("code_hash")
    return {
        "code": entry["code"],
        "rule": entry["rule"],
        "version": entry["version"],
        "version_words": f"version {entry['version']}",
        "kind": entry["kind"],
        "kind_label": register.KINDS[entry["kind"]],
        "market": entry["market"],
        "market_label": MARKET_LABELS.get(entry["market"] or "", "Every market"),
        "title": entry["title"],
        "plain": entry["plain"],
        "source": [{**standards.BY_ID[s["catalog"]].chip(), "clause": s["clause"]} for s in entry["source"]],
        "effective_from": entry["effective_from"],
        "effective_to": entry["effective_to"],
        "state": register.state(entry, day),
        "law_in_force_from": entry["law_in_force_from"],
        "change": entry["change"],
        "approved_by": entry["approval"].get("approved_by"),
        "approved_on": entry["approval"].get("approved_on"),
        "held_as": entry["held_as"],
        "pinned": bool(entry.get("pinned")),
        "fingerprint": fingerprint[7:19] if fingerprint else None,
        "starter_mark": entry["review"]["note"],
    }


@router.get("")
def rules(
    market: str | None = Query(default=None, max_length=10),
    kind: str | None = Query(default=None, max_length=40),
    as_at: date | None = Query(default=None),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Every rule. ``as_at``: only the version of each rule in force on that day (for auditors); otherwise every version
    with its state today."""
    entries = [entry for entry in register.load().values() if register.offered(entry)]
    if as_at is not None:
        entries = [entry for entry in entries if register.pick(entry["rule"], as_at) is entry]
    found = [
        view(entry, as_at)
        for entry in entries
        if (market is None or entry["market"] == market) and (kind is None or entry["kind"] == kind)
    ]
    found.sort(key=lambda item: (list(register.KINDS).index(item["kind"]), item["market"] or "", item["code"]))
    every = [entry for entry in register.load().values() if register.offered(entry)]  # an off switch's rule hides
    return {
        "summary": {
            "rules": len({entry["rule"] for entry in every}),
            "markets": len(register.FLOOR_RULES),
            "held_as_data": len({entry["rule"] for entry in every if entry["held_as"] == register.DATA_HELD}),
            "starter_mark": standards.STARTER_MARK,
        },
        "kinds": [{"code": code, "label": label} for code, label in register.KINDS.items()],
        "as_at": as_at.isoformat() if as_at else None,
        "items": found,
    }


@router.get("/{code}")
def rule(code: str, ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    """One version: its view, the floor's logic in words (data rules), and every version of the rule."""
    entry = register.get(code)
    if entry is None:
        raise HTTPException(status_code=404, detail={"code": "RULE_NOT_FOUND", "message": "No rule has this code"})
    floor = entry["kind"] == "REPORTABILITY_FLOOR"
    return {
        **view(entry),
        "implementation_held": "MDARIX's code" if entry["held_as"] == register.CODE_HELD else "Data in the register",
        "logic": _logic(entry["content"]) if floor else None,
        "history": [view(item) for item in register.versions(entry["rule"])],
    }
