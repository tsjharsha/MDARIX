"""The rule register (B4): every rule MDARIX applies, one JSON file per rule version in ``rule_register/data``.

The files are the single source (R-D1): they ship in a release and change only as a new version file, written by one
person and approved by the owner or a named regulatory approver, both recorded in the file (R-D2). There is no write
path. Signed records name a version by its code.

**Effective dating** (spec section 4): a version is in force from ``effective_from`` (a day, or None: from the start)
up to, not including, ``effective_to`` (a day, or None: open). For a day, the version used is the **highest version
number whose period contains it**. A law change is a new version from the law's day (the old one ends that day); a
correction (``change.kind`` CORRECTION, ``change.corrects``) has the same period as the version it corrects and, being
higher, replaces it at once. A reportability floor is picked by the **awareness day** in the authority's time zone
(the organization's where the floor names none: Canada).

``load`` checks the whole register once per process and refuses it with every problem named: a missing field, a
duplicate code or version, an unknown catalog id, a content hash that does not match, a version whose period overlaps
another's (other than a correction's), a gap in coverage, or an end before a start.
"""

from __future__ import annotations

import functools
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from backend.app import standards
from backend.app.rule_register import engine

DATA = Path(__file__).parent / "data"
# Tests point this at a fixture register (a test-only US-floor-2); production never changes it.
_DIRECTORY = DATA

DATA_HELD, CODE_HELD = "DATA", "CODE"
KINDS = {
    "REPORTABILITY_FLOOR": "Reportability floor",
    "DEADLINE_COUNTING": "Deadline counting",
    "REPORTABILITY": "Reportability",
    "TRIAGE": "Triage",
    "INTAKE": "Intake",
    "ROUTINE_PATH": "Routine path",
    "DISPOSITION": "Disposition",
    "GUIDE_GOVERNANCE": "Guide governance",
    "REPORT_FORM": "Report form",
    "INVESTIGATION": "Investigation",
    "ANALYTICS": "Analytics",
}
CHANGE_KINDS = ("INITIAL", "LAW_CHANGE", "CORRECTION")
REQUIRED = (
    "code", "rule", "version", "kind", "market", "held_as", "title", "plain", "source",
    "effective_from", "effective_to", "law_in_force_from", "change", "review", "approval",
)  # fmt: skip
FLOOR_PARTS = (
    "question_set", "report_types", "precedence", "defs", "rules", "type_rows", "notes", "folding", "prefill",
    "counting", "provisional",
)  # fmt: skip
FLOOR_RULES = {"US": "US-floor", "EU_NI": "EU-floor", "GB": "GB-floor", "IN": "IN-floor", "CA": "CA-floor"}


class RegisterError(ValueError):
    """The register's files are wrong: every problem, each naming its file."""


def content_hash(content) -> str:
    """sha256 of the canonical JSON of a version's content (sorted keys, no spaces)."""
    text = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _day(value) -> date | None:
    return None if value is None else date.fromisoformat(value)


def _contains(entry: dict, day: date) -> bool:
    start, end = _day(entry["effective_from"]), _day(entry["effective_to"])
    return (start is None or start <= day) and (end is None or day < end)


def _problems(entries: list[tuple[str, dict]]) -> list[str]:
    problems: list[str] = []
    codes: dict[str, str] = {}
    versions: dict[tuple, str] = {}
    for name, entry in entries:
        missing = [key for key in REQUIRED if key not in entry]
        if missing:
            problems.append(f"{name}: missing {', '.join(missing)}")
            continue
        if entry["code"] in codes:
            problems.append(f"{name}: code {entry['code']} also in {codes[entry['code']]}")
        codes[entry["code"]] = name
        key = (entry["rule"], entry["version"])
        if key in versions:
            problems.append(f"{name}: {entry['rule']} version {entry['version']} also in {versions[key]}")
        versions[key] = name
        if entry["kind"] not in KINDS:
            problems.append(f"{name}: unknown kind {entry['kind']}")
        if entry["change"].get("kind") not in CHANGE_KINDS:
            problems.append(f"{name}: change.kind is one of {', '.join(CHANGE_KINDS)}")
        if standards.STARTER_MARK not in str(entry["review"].get("note")):
            problems.append(f"{name}: review.note keeps the starter mark")
        for source in entry["source"]:
            if source.get("catalog") not in standards.BY_ID:
                problems.append(f"{name}: unknown catalog id {source.get('catalog')}")
        try:
            start, end = _day(entry["effective_from"]), _day(entry["effective_to"])
        except (TypeError, ValueError):
            problems.append(f"{name}: effective_from and effective_to are days (YYYY-MM-DD) or null")
            continue
        if start and end and end <= start:
            problems.append(f"{name}: effective_to {end} is not after effective_from {start}")
        if entry["held_as"] == DATA_HELD:
            if entry.get("content_hash") != content_hash(entry.get("content")):
                problems.append(f"{name}: content changed without a new version (content_hash does not match)")
            if entry["kind"] == "REPORTABILITY_FLOOR":
                content = entry["content"]
                lacking = [part for part in FLOOR_PARTS if part not in content]
                if lacking:
                    problems.append(f"{name}: floor lacks {', '.join(lacking)}")
                else:
                    problems += [f"{name}: {problem}" for problem in engine.check(content)]
        elif entry["held_as"] != CODE_HELD:
            problems.append(f"{name}: held_as is DATA or CODE")
    by_rule: dict[str, list[tuple[str, dict]]] = {}
    for name, entry in entries:
        if all(key in entry for key in REQUIRED):
            by_rule.setdefault(entry["rule"], []).append((name, entry))
    for rule, items in by_rule.items():
        problems += _period_problems(rule, sorted(items, key=lambda item: item[1]["version"]))
    return problems


def _period_problems(rule: str, items: list[tuple[str, dict]]) -> list[str]:
    """Versions other than corrections follow one another without overlap or gap, from the start to open; a correction
    has exactly the period of the lower version it corrects."""
    problems: list[str] = []
    periods = {entry["code"]: (entry["effective_from"], entry["effective_to"]) for _, entry in items}
    chain = []
    for name, entry in items:
        if entry["change"]["kind"] == "CORRECTION":
            corrected = entry["change"].get("corrects")
            if corrected not in periods or corrected == entry["code"]:
                problems.append(f"{name}: a correction names the version it corrects (change.corrects)")
            elif periods[corrected] != periods[entry["code"]]:
                problems.append(f"{name}: a correction has the period of {corrected}")
            continue
        chain.append((name, entry))
    chain.sort(key=lambda item: item[1]["effective_from"] or "")
    if chain and chain[0][1]["effective_from"] is not None:
        problems.append(f"{chain[0][0]}: {rule} has a gap before {chain[0][1]['effective_from']}")
    if chain and chain[-1][1]["effective_to"] is not None:
        problems.append(f"{chain[-1][0]}: {rule} has a gap after {chain[-1][1]['effective_to']}")
    for (name, before), (later, after) in zip(chain, chain[1:]):
        end, start = before["effective_to"], after["effective_from"]
        if end is None or (start is not None and start < end):
            problems.append(f"{later}: overlaps {name}")
        elif start != end:
            problems.append(f"{later}: {rule} has a gap from {end} to {start}")
    return problems


@functools.cache
def _load(directory: str) -> dict[str, dict]:
    entries = []
    for path in sorted(Path(directory).glob("*.json")):
        try:
            entries.append((path.name, json.loads(path.read_text(encoding="utf-8"))))
        except ValueError as error:
            raise RegisterError(f"{path.name}: not JSON ({error})") from error
    problems = _problems(entries)
    if problems:
        raise RegisterError("; ".join(problems))
    return {entry["code"]: entry for _, entry in entries}


def load() -> dict[str, dict]:
    """Every version, by code: read and checked once per process (per directory)."""
    return _load(str(_DIRECTORY))


def get(code: str) -> dict | None:
    return load().get(code)


def versions(rule: str) -> list[dict]:
    """A rule's versions, lowest first."""
    return sorted((entry for entry in load().values() if entry["rule"] == rule), key=lambda entry: entry["version"])


def today() -> date:
    return datetime.now(timezone.utc).date()


def pick(rule: str, day: date | None = None) -> dict | None:
    """The version of ``rule`` in force on ``day`` (today when None): the highest version whose period contains it."""
    day = day or today()
    found = [entry for entry in versions(rule) if _contains(entry, day)]
    return found[-1] if found else None


def state(entry: dict, day: date | None = None) -> str:
    """In force, Scheduled (starts after the day), Retired (ended) or Replaced (a correction or a higher version for
    the same day is in force)."""
    day = day or today()
    if not _contains(entry, day):
        start = _day(entry["effective_from"])
        return "SCHEDULED" if start and day < start else "RETIRED"
    return "IN_FORCE" if pick(entry["rule"], day)["code"] == entry["code"] else "REPLACED"


def floor(market: str, day: date | None = None) -> dict | None:
    """The market's reportability floor in force on ``day`` (today when None); None for a market without one."""
    rule = FLOOR_RULES.get(market or "")
    return pick(rule, day) if rule else None


def floor_day(market: str, aware, org_zone: str | None = None) -> date | None:
    """The day that picks a market's floor (R-D3): the awareness day in the authority's time zone of the floor in force
    today (the organization's where it names none, Canada); a day-only awareness is that day; None without
    awareness."""
    from backend.app.oversight.rules import zone_info
    from backend.app.reportability import deadlines

    if aware is None:
        return None
    if not isinstance(aware, datetime):
        return aware
    if deadlines.day_only(aware):
        return deadlines._utc(aware).astimezone(timezone.utc).date()
    current = floor(market)
    zone = (current and current["content"]["counting"]["authority_zone"]) or org_zone or "UTC"
    return deadlines._utc(aware).astimezone(zone_info(zone) or timezone.utc).date()


def floor_at(market: str, aware, org_zone: str | None = None) -> dict | None:
    """The market's floor in force at an awareness moment (a datetime or a day); today's floor without awareness."""
    return floor(market, floor_day(market, aware, org_zone))


def code_hash(implementation: str) -> str:  # shortcut: ast.dump can differ across Python minor versions; re-pin on an upgrade
    """sha256 of a code-held rule's syntax tree (``module:function``), without comments and docstrings: a pinned
    regulatory function's code may not change without a new register version (B4 step 7, DT-33)."""
    import ast
    import importlib
    import inspect
    import textwrap

    module, _, name = implementation.partition(":")
    tree = ast.parse(textwrap.dedent(inspect.getsource(getattr(importlib.import_module(module), name))))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(body, list)
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
        ):
            if isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return "sha256:" + hashlib.sha256(ast.dump(tree).encode("utf-8")).hexdigest()


def pin_problems() -> list[str]:
    """Pinned rules whose code, or the registered rule book whose file, changed without a new version (step 7)."""
    problems = []
    for entry in load().values():
        if entry.get("pinned") and entry.get("code_hash") != code_hash(entry["implementation"]):
            problems.append(f"{entry['code']}.json: {entry['implementation']} changed without a new version")
        if entry["held_as"] == DATA_HELD and "file" in entry.get("content", {}):
            path = Path(__file__).resolve().parents[3] / entry["content"]["file"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry["content"]["sha256"]:
                problems.append(f"{entry['code']}.json: {entry['content']['file']} changed without a new version")
    return problems
