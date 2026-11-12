"""B6b B5: the per-release validation pack (MDX-VAL-004 to -012) built from text sources under version control.

Inputs: ``docs/validation/requirements.csv`` (URS source), ``scenario-register.md``, the release's pytest JUnit XML
(with ``requirement`` properties, B4), ``artifacts/release-checks-<version>.json``, ``deviation-log.csv`` and, when
given, a clock-check JSON. Outputs: URS, FS/DS, IQ record, OQ protocol and results log, RTM, deviations, G13 figures,
draft VSR and the release approval record (Markdown source, DOCX, PDF; tables also CSV and XLSX; a SHA-256 manifest).

The MDX-B10-005 section 6 checks and the deviation rules (B6-57, B6-58) are all collected and listed together; a
release pack is written only when none fails. A dry run writes the pack anyway, marked "development results, not
validation evidence", with the failures listed in it."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

from validation import docx_render, xlsx_write

FIVE = ("NOT RUN", "PASS", "FAIL", "BLOCKED", "REQUIRES HUMAN DECISION")
DEV_BANNER = "DEVELOPMENT RESULTS, NOT VALIDATION EVIDENCE"
SYSTEM_OWNER = "Sriharsha Telikicherla, Product & Engineering, system owner"
QUALITY_APPROVER = "Srinivas Telikicherla, QA/RA, quality approver"
DEVIATION_COLUMNS = [
    "dev_id", "raised_utc", "raised_by", "found_in", "test_or_scenario", "req_id", "expected", "seen",
    "documented_first_utc", "impact", "gxp_risk", "classification", "root_cause", "correction", "retest_id",
    "retest_result", "change_control", "capa_ref", "approved_by", "closed_utc", "status",
]  # fmt: skip


# MDX-VAL-012 interim template (owner decision O13, B6b-D7, MDX-VAL-001 VMP-R41): the release approval record used
# from the big-bang deploy until MDX-VAL-001 is approved as 1.0; docs/validation/MDX-VAL-012_RELEASE_APPROVAL_TEMPLATE.md
# holds the same lines. The quality approver initials each criterion.
INTERIM_BASIS = (
    "Interim release approval (MDX-VAL-001 VMP-R41, owner decision B6b-D7): the Validation Master Plan is a draft; "
    "this record approves the deploy, it does not state that the release is validated under the plan."
)
INTERIM_CRITERIA = (
    "Release identity: the release equals VERSION, the commit is the tagged commit, one migration head",
    "Release checks: full suite on this commit, every step passed (release-checks JSON and its SHA-256)",
    "Every class-A scenario named by the change-impact assessment is PASS with evidence, or NOT RUN and listed in a "
    "risk acceptance under criterion 4; none is FAIL (VMP-R49, VMP-R49a, VMP-R50)",
    "Every Open MDX-VAL-002 row this release relies on, and every class-A scenario still NOT RUN, has a signed risk "
    "acceptance listed in this record (RA-R07, RA-R08, VMP-R49b)",
    "No failed class-A test, no open critical deviation, no open deviation that affects patient safety or data "
    "integrity; every other open deviation has its acceptance rationale (VMP-R50, VMP-R50a, VMP-R51)",
    "No critical failure of VMP-R60 (a risk acceptance never covers one)",
    "Change-impact assessment reviewed; customer change notice given where VMP-R37 needs one",
    "Restore point taken before the deploy and the rollback plan written",
    "After the deploy: deploy_gate.py passed on production, result recorded",
)


def record_id(release: str) -> str:
    """The per-release release approval record; the interim template itself is MDX-VAL-012."""
    return f"MDX-VAL-012-{release}"


class PackRefused(Exception):
    """The pack may not be written (a signed release folder)."""


@dataclass
class Sources:
    requirements: list[dict]
    scenarios: dict[str, dict]  # id -> {"title", "expected", "status", "notes"}
    tests: list[dict] = field(default_factory=list)  # {"id", "result", "seconds", "scenarios"}
    release_checks: dict | None = None
    release_checks_raw: bytes | None = None  # hashed as written, never re-serialised
    junit_raw: bytes | None = None  # copied into the release folder as junit.xml
    deviations: list[dict] = field(default_factory=list)
    clock_check: dict | None = None
    oq_expected: dict[str, dict] = field(default_factory=dict)  # scenario -> concrete OQ expected result (O20)


# ---- reading -------------------------------------------------------------------------------------------------------


def read_requirements(path: Path) -> list[dict]:
    rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
    for row in rows:
        for key in ("risk_ids", "scenario_ids", "negative_scenarios", "tests"):
            row[key] = (row.get(key) or "").split()
    return rows


def read_register(path: Path) -> dict[str, dict]:
    """shortcut: reads the register's Markdown tables as they are (ID first, then Status and Notes last); a table
    without a Notes column is not read. Upgrade if the register moves to CSV."""
    scenarios: dict[str, dict] = {}
    with_notes = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("| ID |"):
            with_notes = line.rstrip().endswith("| Status | Notes |")
            continue
        match = re.match(r"^\| ([A-Z0-9]+-[0-9]+[a-z]?) \|", line)
        if match and with_notes:
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            scenarios[match.group(1)] = {
                "title": cells[1], "expected": cells[2], "status": cells[-2], "notes": cells[-1],
            }  # fmt: skip
    return scenarios


def read_oq_expected(path: Path) -> dict[str, dict]:
    """``oq-expected-results.csv``: per class-A scenario the input and the concrete expected result (owner decision O20),
    its ``source`` (``requirement``: derived from the requirement; ``code``: drafted from the code) and who confirmed it
    (``confirmed_by``). Only a row derived from its requirement and confirmed counts as approved (owner, 12 Nov 2026)."""
    if not path.exists():
        return {}
    return {row["scenario_id"]: row for row in csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines())}


def read_junit(path: Path) -> list[dict]:
    tests = []
    for case in ElementTree.parse(path).getroot().iter("testcase"):
        outcome = "pass"
        if case.find("failure") is not None or case.find("error") is not None:
            outcome = "fail"
        elif case.find("skipped") is not None:
            outcome = "skipped"
        props = [(p.get("name"), p.get("value", "")) for p in case.iter("property")]
        scenarios = sorted({v for n, v in props if n == "requirement"} - {""})
        file_scenarios = sorted({v for n, v in props if n == "requirement_file"} - {""} - set(scenarios))
        tests.append({
            "id": f"{case.get('classname', '')}::{case.get('name', '')}", "result": outcome,
            "seconds": float(case.get("time") or 0), "scenarios": scenarios, "file_scenarios": file_scenarios,
        })  # fmt: skip
    return sorted(tests, key=lambda t: t["id"])


def read_deviations(path: Path) -> list[dict]:
    """The deviation log; its header must be exactly DEVIATION_COLUMNS (a file saved by Excel with a byte-order mark
    still reads; any other header is refused, so no row is silently dropped)."""
    if not path.exists():
        return []
    reader = csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines())
    if reader.fieldnames != DEVIATION_COLUMNS:
        raise ValueError(f"{path.name}: the header is not the MDX-VAL-010 column list")
    return list(reader)


def migration_head(versions: Path) -> str:
    """The Alembic head(s) from the migration files: revisions no other revision names as its down_revision."""
    revisions, parents = set(), set()
    for file in versions.glob("*.py"):
        text = file.read_text(encoding="utf-8")
        revision = re.search(r"^revision\b[^=]*=\s*['\"]([^'\"]+)['\"]", text, re.M)
        down = re.search(r"^down_revision\b[^=]*=\s*(.+)$", text, re.M)
        if revision:
            revisions.add(revision.group(1))
        if down:
            parents.update(re.findall(r"['\"]([^'\"]+)['\"]", down.group(1)))
    return ", ".join(sorted(revisions - parents)) or "unknown"


# ---- checks and computation ----------------------------------------------------------------------------------------

DEV_STATUSES = ("open", "corrected", "retested", "closed")
DEV_CLASSES = ("critical", "major", "minor")


def _utc(text: str) -> datetime:
    moment = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _ran(sources: Sources) -> list[dict]:
    return [t for t in sources.tests if t["result"] != "skipped"]


def _proves(sources: Sources, test: dict, sid: str) -> bool:
    """A test proves a scenario by its own (test-level) marker; a file-level marker counts only for a scenario that no
    class-A requirement cites (owner decision O24)."""
    if sid in test["scenarios"]:
        return True
    return sid in test.get("file_scenarios", ()) and sid not in class_a_scenarios(sources)


def is_future(sources: Sources, sid: str) -> bool:
    """A register row whose Notes start with "future:" describes a feature not built yet: never a scripted OQ step,
    never verification (owner, 12 Nov 2026)."""
    return sources.scenarios.get(sid, {}).get("notes", "").startswith("future:")


def scenario_outcome(sources: Sources, sid: str) -> str:
    """This release's outcome of one scenario: FAIL (a tagged test failed, or the register says FAIL), BLOCKED,
    PASS (a tagged test ran and passed), else NOT RUN. A register PASS alone is a development result (VMP-R31)."""
    results = {t["result"] for t in _ran(sources) if _proves(sources, t, sid)}
    status = sources.scenarios.get(sid, {}).get("status", "")
    if "fail" in results or status == "FAIL":
        return "FAIL"
    if status == "BLOCKED":
        return "BLOCKED"
    return "PASS" if "pass" in results else "NOT RUN"


def check(sources: Sources, release: str) -> list[str]:
    """Every failing case, listed (B6-49, B6-57, B6-58): never stops at the first."""
    problems = []
    for req in sources.requirements:
        rid = req["req_id"]
        if not req["scenario_ids"]:
            problems.append(f"{rid}: no scenario")
        if req["class"] == "A" and not req["negative_scenarios"]:
            problems.append(f"{rid}: class A without a negative scenario")
        elif req["class"] == "A" and all(is_future(sources, s) for s in req["negative_scenarios"]):
            problems.append(f"{rid}: class A whose negative scenarios are all future (not built)")
        for sid in sorted(set(req["scenario_ids"]) | set(req["negative_scenarios"])):
            if sid not in sources.scenarios:
                problems.append(f"{rid}: scenario {sid} is not in the register")
        if req["class"] == "A":
            for sid in req["scenario_ids"]:
                if scenario_outcome(sources, sid) == "FAIL":  # owner decision O18: never covered by an acceptance
                    problems.append(
                        f"{rid}: class-A scenario {sid} FAIL; a failed class-A test blocks the release (VMP-R50)"
                    )
    for sid in [s for s in class_a_scenarios(sources) if not is_future(sources, s)]:
        expected = sources.oq_expected.get(sid)
        if not expected or not expected.get("expected_result", "").strip():
            problems.append(f"{sid}: class-A scenario without a concrete OQ expected result (oq-expected-results.csv)")
        else:
            source, confirmed = expected.get("source", "").strip(), expected.get("confirmed_by", "").strip()
            why = (
                [] if source == "requirement" else [f"source '{source or 'blank'}', re-derive it from its requirement"]
            )
            why += [] if confirmed else ["not confirmed by the owner"]
            if why:  # owner, 12 Nov 2026: a result drafted from the code checks the code against itself
                problems.append(f"{sid}: OQ expected result not yet approved ({'; '.join(why)})")
    cited = {s for req in sources.requirements for s in req["scenario_ids"]}
    for sid in sorted(cited & set(sources.scenarios)):
        row = sources.scenarios[sid]
        if row["status"] not in FIVE:
            problems.append(f"{sid}: status '{row['status']}' is not one of the five values")
        # Evidence for a PASS: a passing tagged test in this release's JUnit, or an evidence ID (EVD-...) in Notes.
        if row["status"] == "PASS" and scenario_outcome(sources, sid) != "PASS" and "EVD-" not in row["notes"]:
            problems.append(f"{sid}: PASS without evidence (no passing tagged test in this JUnit, no EVD- record)")
    for test in sources.tests:
        for sid in test["scenarios"] + test.get("file_scenarios", []):
            if sid not in sources.scenarios:
                problems.append(f"{test['id']}: marker names unknown scenario {sid}")
    for dev in release_deviations(sources, release):
        dev_id, status = dev["dev_id"], dev.get("status", "").strip().lower()
        if status not in DEV_STATUSES:
            problems.append(f"{dev_id}: status '{dev.get('status')}' is not one of {', '.join(DEV_STATUSES)}")
        if dev.get("classification", "").strip().lower() not in DEV_CLASSES:
            problems.append(f"{dev_id}: classification '{dev.get('classification')}' is not critical, major or minor")
        for key in ("raised_utc", "documented_first_utc", "closed_utc"):
            if dev.get(key, "").strip():
                try:
                    _utc(dev[key])
                except ValueError:
                    problems.append(f"{dev_id}: {key} '{dev[key]}' is not a date and time")
        if status == "closed":
            if not dev.get("retest_result", "").strip():
                problems.append(f"{dev_id}: closed without a retest result")
            if not dev.get("approved_by", "").strip():
                problems.append(f"{dev_id}: closed without an approver")
    for dev in open_critical(sources, release):
        problems.append(f"{dev['dev_id']}: critical deviation open; no release approval record can be produced")
    return problems


def class_a_scenarios(sources: Sources) -> list[str]:
    seen: list[str] = []
    for req in sources.requirements:
        if req["class"] == "A":
            seen += [s for s in req["scenario_ids"] if s not in seen and s in sources.scenarios]
    return seen


def release_deviations(sources: Sources, release: str) -> list[dict]:
    return [d for d in sources.deviations if d.get("dev_id", "").startswith(f"DEV-{release}-")]


def open_critical(sources: Sources, release: str) -> list[dict]:
    """Not closed and classified critical, or with an unreadable class (it never lets a release through)."""
    return [
        d
        for d in release_deviations(sources, release)
        if d.get("classification", "").strip().lower() not in ("major", "minor")
        and d.get("status", "").strip().lower() != "closed"
    ]


def rtm(sources: Sources) -> list[dict]:
    rows = []
    for req in sources.requirements:
        scenarios = req["scenario_ids"]
        linked = [t for t in _ran(sources) if any(_proves(sources, t, s) for s in scenarios)]
        file_only = not linked and any(set(t.get("file_scenarios", ())) & set(scenarios) for t in _ran(sources))
        outcomes = {s: scenario_outcome(sources, s) for s in scenarios}
        statuses = {sources.scenarios.get(s, {}).get("status", "") for s in scenarios}
        if "FAIL" in outcomes.values():
            status = "Failed"
        elif "BLOCKED" in outcomes.values():
            status = "Blocked"
        elif "REQUIRES HUMAN DECISION" in statuses:
            status = "Requires human decision"
        elif scenarios and all(o == "PASS" for o in outcomes.values()):
            status = "Verified"
        else:
            status = "Not verified"
        rows.append({
            "req_id": req["req_id"], "class": req["class"], "risk_ids": " ".join(req["risk_ids"]),
            "scenarios": " ".join(scenarios) or "(none)",
            "negative_scenarios": " ".join(req["negative_scenarios"]) or "(none)",
            "tagged_tests": len(linked), "passed": sum(t["result"] == "pass" for t in linked),
            "failed": sum(t["result"] == "fail" for t in linked),
            "scenarios_passed": f"{sum(o == 'PASS' for o in outcomes.values())}/{len(scenarios)}",
            "coverage": "covered" if linked else "file-level only, not verification" if file_only else "NOT COVERED",
            "register_status": "; ".join(f"{s} {sources.scenarios.get(s, {}).get('status', 'NOT IN REGISTER')}" for s in scenarios),
            "named_tests": " ".join(req["tests"]), "status": status,
            "future": " ".join(s for s in scenarios if is_future(sources, s)),
        })  # fmt: skip
    return rows


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}% ({part}/{whole})" if whole else "no data (0/0)"


def g13(sources: Sources, release: str) -> dict:
    """The G13 figures (B6b-spec B.3), counted per scenario from this release's JUnit and the register."""
    figures: dict = {"coverage": {}}
    in_scope = sorted({s for r in sources.requirements for s in r["scenario_ids"]})
    outcome = {s: scenario_outcome(sources, s) for s in in_scope}
    executed = [s for s in in_scope if outcome[s] != "NOT RUN"]
    for cls in ("A", "B", "C"):
        in_class = [r for r in sources.requirements if r["class"] == cls]
        hit = sum(any(outcome.get(s) != "NOT RUN" for s in r["scenario_ids"]) for r in in_class)
        figures["coverage"][cls] = _pct(hit, len(in_class))
    class_a = [r for r in sources.requirements if r["class"] == "A"]
    figures["negative_coverage_class_a"] = _pct(sum(bool(r["negative_scenarios"]) for r in class_a), len(class_a))
    figures["execution_progress"] = _pct(len(executed), len(in_scope))
    figures["pass_rate"] = _pct(sum(outcome[s] == "PASS" for s in executed), len(executed))
    ran = _ran(sources)
    scope = "full suite" if (sources.release_checks or {}).get("full_suite") else "subset: not a full-suite run"
    figures["pass_rate_all_tests"] = (
        f"{_pct(sum(t['result'] == 'pass' for t in ran), len(ran))}, tests in this JUnit ({scope})"
    )
    devs = release_deviations(sources, release)
    deviated = {d.get("test_or_scenario", "").strip() for d in devs}
    figures["first_pass_yield"] = _pct(sum(outcome[s] == "PASS" and s not in deviated for s in executed), len(executed))
    figures["defect_leakage"] = (
        "no source yet: MDARIX's own complaint and CAPA registers do not exist until B6b Part D (D4)"
    )
    days = []
    for d in devs:
        if d.get("closed_utc", "").strip() and d.get("raised_utc", "").strip():
            try:
                days.append((_utc(d["closed_utc"]) - _utc(d["raised_utc"])).total_seconds() / 86400)
            except ValueError:
                pass  # listed by check()
    figures["deviation_closure_days"] = (
        {"median": round(statistics.median(days), 1), "max": round(max(days), 1), "closed": len(days)}
        if days
        else "no closed deviations in this release"
    )
    open_devs = [d for d in devs if d.get("status", "").strip().lower() != "closed"]
    by_class: dict[str, int] = {}
    for d in open_devs:
        key = d.get("classification") or "unclassified"
        by_class[key] = by_class.get(key, 0) + 1
    figures["open_deviations"] = {"count": len(open_devs), "by_classification": dict(sorted(by_class.items()))}
    figures["post_go_live_effectiveness"] = "no source yet: incident, complaint and CAPA registers come in B6b Part D"
    return figures


# ---- documents -----------------------------------------------------------------------------------------------------


@dataclass
class Context:
    release: str
    version_file: str
    commit: str
    tag: str
    date: str
    dry_run: bool
    head: str
    problems: list[str]
    oq_approved: bool = False  # signatures.csv holds this release's OQ protocol with the current SHA-256 (O20)


def _header(ctx: Context, doc_id: str, title: str, author: str, approver: str) -> str:
    status = f"DRAFT. {DEV_BANNER} (dry run)" if ctx.dry_run else "DRAFT (for review and signature)"
    return "\n".join([
        f"# {doc_id} {title}", "",
        f"**{DEV_BANNER}**" if ctx.dry_run else "", "",
        "| Field | Value |", "|---|---|",
        f"| Document ID | {doc_id} |", f"| Title | {title} |", f"| Version | release {ctx.release} |",
        f"| Status | {status} |", f"| Author (R) | {author} |",
        "| Reviewer | Independent CSV consultant (MDX-VAL-001 VMP-R09; not engaged yet) |", f"| Approver (A) | {approver} |",
        "| Drafting | Generated by `scripts/validation_pack.py` from the sources in section 1; reviewed by the author before signature |",
        f"| Date | {ctx.date} |", f"| Code baseline | commit `{ctx.commit}`, tag {ctx.tag or '(none yet)'}; `VERSION` {ctx.version_file} |",
        "", "Change history", "", "| Version | Date | Change | By |", "|---|---|---|---|",
        f"| release {ctx.release} | {ctx.date} | Generated from commit `{ctx.commit}`; a regeneration replaces this version "
        "until it is signed, after which a correction is a new version (VMP-R39) | Sriharsha Telikicherla (generator run) |",
        "",
    ])  # fmt: skip


def _table(header: list[str], rows: list[list]) -> str:
    def cell(v) -> str:
        return str(v).replace("|", "/").replace("\n", " ")

    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def _sources_section(ctx: Context) -> str:
    return (
        "## 1. Sources\n\n"
        "- `docs/validation/requirements.csv` (URS source), `docs/validation/scenario-register.md`, "
        "`docs/validation/deviation-log.csv`\n"
        "- the release's pytest JUnit XML and `artifacts/release-checks-<version>.json`\n"
        "- Register statuses recorded before the first release pack under MDX-VAL-001 are development results, not "
        "validation evidence (VMP-R31); this pack's evidence is the JUnit of this release and its scripted OQ records.\n\n"
    )


def urs(ctx: Context, s: Sources) -> str:
    rows = [
        [r["req_id"], r["revision"], r["class"], r["text"], r["spec_ref"], " ".join(r["risk_ids"])]
        for r in s.requirements
    ]
    return (
        _header(
            ctx,
            "MDX-VAL-004",
            "User requirements specification",
            QUALITY_APPROVER,
            SYSTEM_OWNER + " (after the quality approver's draft)",
        )
        + _sources_section(ctx)
        + "## 2. Introduction\n\n"
        "Intended use: MDARIX records and routes complaints about medical devices, supports the reportability decision "
        "per market and prepares the authority report files that trained employees of device manufacturers review, sign "
        "and submit (MDX-B10-001). Users: complaint handlers, triage and regulatory reviewers, quality approvers and "
        "administrators of device manufacturers. Modes: Connect (an add-on layer over the customer's QMS) and Complete "
        "(MDARIX is the system of record for complaints). AI helpers are off and out of scope.\n\n"
        'Each requirement is one testable "shall" statement. Class from MDX-VAL-002 (A: severity 4-5; B: 3; C: 1-2).\n\n'
        "## 3. Requirements\n\n" + _table(["REQ", "Rev", "Class", "Requirement", "Source", "Risks"], rows)
    )


def fsds(ctx: Context, s: Sources) -> str:
    rows = [
        [r["req_id"], r["spec_ref"], " ".join(r["scenario_ids"]) or "(none)", " ".join(r["tests"]) or "(none named)"]
        for r in s.requirements
    ]
    return (
        _header(
            ctx,
            "MDX-VAL-005",
            "Functional and design specification",
            SYSTEM_OWNER,
            QUALITY_APPROVER + " (independent review)",
        )
        + _sources_section(ctx)
        + "## 2. Functional specification (by reference)\n\n"
        "Per requirement, the approved spec section that defines the function, the scenarios that state its expected "
        "behaviour (scenario register) and the automated tests named for it. Screens and routes are those of the spec "
        "section named.\n\n"
        + _table(["REQ", "Specification", "Scenarios", "Named tests"], rows)
        + "\n## 3. Design specification (by reference)\n\n"
        "- System architecture: `docs/architecture/`; decisions: `docs/adr/`\n"
        "- Threat model and security design: MDX-B10-006 (`docs/validation/MDX-B10-006-Threat-Model.md`)\n"
        f"- Data model: Alembic migrations `infrastructure/database/migrations/` (head `{ctx.head}`); row-level security "
        "per tenant table (`mdarix_tenant_isolation`)\n"
        "- Overview: a FastAPI back end and a React front end over PostgreSQL; an outbox worker and a scheduler; "
        "every regulated change audited in a per-organisation hash chain.\n"
    )


def iq(ctx: Context, s: Sources) -> str:
    checks = s.release_checks or {}
    tools = checks.get("tools") or {}
    clock = s.clock_check or {}
    rows = [
        ["IQ-001", "Release identity", f"release {ctx.release}; `VERSION` {ctx.version_file}; commit `{ctx.commit}`; tag {ctx.tag or '(none)'}",
         "match" if ctx.release == ctx.version_file else "MISMATCH: set at the release join"],
        ["IQ-002", "Migration head (one head)", ctx.head, "one head" if "," not in ctx.head else "MORE THAN ONE HEAD"],
        ["IQ-003", "Python / Node", f"{tools.get('python') or 'not recorded'} / {tools.get('node') or 'not recorded'}", "recorded" if tools else "to record"],
        ["IQ-004", "PostgreSQL version", "to record at installation (`SELECT version()`)", "to record"],
        ["IQ-005", "Configuration check (`config_check`)", "to record at deploy", "to record"],
        ["IQ-006", "Deploy gate (`scripts/deploy_gate.py --release`)", "to record at deploy", "to record"],
        ["IQ-007", "Clock check (`scripts/clock_check.py`)", json.dumps(clock.get("status") or clock.get("result") or "not supplied"), "recorded" if clock else "to record"],
        ["IQ-008", "Release checks JSON", f"passed = {checks.get('passed')}, full suite = {checks.get('full_suite')}" if checks else "not supplied", "recorded" if checks else "to record"],
    ]  # fmt: skip
    return (
        _header(ctx, "MDX-VAL-006", "Installation qualification record", SYSTEM_OWNER, QUALITY_APPROVER)
        + _sources_section(ctx)
        + '## 2. Installation checks\n\nExecuted by: ________ Date: ________ (a check marked "to record" is filled in by hand at installation).\n\n'
        + _table(["Step", "Check", "Recorded", "Result"], rows)
    )


PROTOCOL_HEADER = [
    "Step",
    "REQ",
    "Scenario",
    "Scenario text",
    "Input",
    "Pre-approved expected result",
    "Checked by (automated)",
]
RESULT_HEADER = ["Executed by", "Date", "Result", "Evidence ID"]
PROTOCOL_ID, RESULTS_ID = "MDX-VAL-007-P", "MDX-VAL-007-R"


def oq_tables(s: Sources) -> tuple[list[list], list[list]]:
    """The scripted class-A OQ steps (protocol, without results) and the automated log of tagged tests."""
    scripted = [PROTOCOL_HEADER]
    n = 0
    for req in s.requirements:
        if req["class"] != "A":
            continue
        for sid in req["scenario_ids"]:
            row = s.scenarios.get(sid)
            if row and not is_future(s, sid):
                n += 1
                concrete = s.oq_expected.get(sid, {})
                scripted.append([f"OQ-{n:03d}", req["req_id"], sid, row["title"], concrete.get("input", ""),
                                 concrete.get("expected_result", "") or "(no concrete expected result)",
                                 concrete.get("checked_by", "")])  # fmt: skip
    req_of: dict[str, list[str]] = {}
    for req in s.requirements:
        for sid in req["scenario_ids"]:
            req_of.setdefault(sid, []).append(req["req_id"])
    log = [["Test", "Scenarios", "REQs", "Result", "Seconds"]]
    for t in s.tests:
        if t["scenarios"] or t.get("file_scenarios"):
            tagged = t["scenarios"] + [f"{sid} (file-level)" for sid in t.get("file_scenarios", [])]
            reqs = sorted({r for sid in t["scenarios"] + t.get("file_scenarios", []) for r in req_of.get(sid, [])})
            log.append([t["id"], " ".join(tagged), " ".join(reqs), t["result"].upper(), t["seconds"]])
    return scripted, log


def protocol_sha256(scripted: list[list]) -> str:
    """The SHA-256 of the OQ protocol's steps as CSV: what the quality approver signs before execution (O20)."""
    return hashlib.sha256(_csv(scripted)).hexdigest()


def protocol_approved(signatures: Path, release: str, sha256: str) -> bool:
    """``signatures.csv`` holds the signed OQ protocol of this release with exactly this SHA-256."""
    if not signatures.exists():
        return False
    return any(
        row.get("document_id") == PROTOCOL_ID and row.get("version") == release and row.get("sha256") == sha256
        for row in csv.DictReader(signatures.read_text(encoding="utf-8-sig").splitlines())
    )


def oq_protocol(ctx: Context, scripted: list[list], sha256: str) -> str:
    return (
        _header(
            ctx,
            PROTOCOL_ID,
            "Operational qualification protocol",
            SYSTEM_OWNER,
            QUALITY_APPROVER + " (approves the expected results before execution)",
        )  # fmt: skip
        + _sources_section(ctx)
        + "## 2. Approach\n\n"
        "Each class-A scenario is a scripted step with its input and a concrete expected result "
        "(`docs/validation/oq-expected-results.csv`). The quality approver approves this protocol before any step is "
        "executed; the approval is the signed PDF and its `signatures.csv` row (document "
        f"{PROTOCOL_ID}, version {ctx.release}, SHA-256 below). The generator writes no OQ results without that "
        "approval (owner decision O20). The automated tests named per step are supporting evidence (CSA).\n\n"
        f"Protocol SHA-256 (of the steps table as CSV): `{sha256}`\n\n"
        f"## 3. Scripted OQ steps (class A): {len(scripted) - 1}\n\n"
        + _table(scripted[0], scripted[1:])
        + "\n## 4. Approval before execution\n\nName: ____________ Role: quality approver Date (UTC): ____________\n\n"
        "Meaning: I approve these expected results before execution.\n"
    )


def oq(ctx: Context, s: Sources, scripted: list[list], log: list[list], sha256: str, approved: bool) -> str:
    untagged = sum(1 for t in s.tests if not t["scenarios"] and not t.get("file_scenarios"))
    state = (
        f"approved (`signatures.csv`, SHA-256 `{sha256}`)"
        if approved
        else f"NOT APPROVED (dry run only; SHA-256 `{sha256}`)"
    )
    steps = [scripted[0][:3] + scripted[0][5:6] + RESULT_HEADER] + [r[:3] + r[5:6] + [""] * 4 for r in scripted[1:]]
    return (
        _header(ctx, RESULTS_ID, "Operational qualification results", SYSTEM_OWNER, QUALITY_APPROVER)
        + _sources_section(ctx)
        + "## 2. Approach\n\n"
        f"Executed against OQ protocol {PROTOCOL_ID} for release {ctx.release}: {state}. Class-A steps are executed as "
        "scripted; the automated suite is supporting evidence (CSA): tagged tests are listed per scenario; class B "
        f"and C rows are covered by the automated suite, untagged (B6b-D17): {untagged} untagged test(s) ran in this "
        "JUnit.\n\n"
        f"## 3. Scripted OQ results (class A): {len(steps) - 1}\n\n"
        + _table(steps[0], steps[1:])
        + f"\n## 4. Automated results of tagged tests: {len(log) - 1}\n\n"
        + _table(log[0], log[1:])
    )


def rtm_markdown(ctx: Context, rows: list[dict]) -> str:
    keys = [
        "req_id",
        "class",
        "risk_ids",
        "scenarios",
        "negative_scenarios",
        "tagged_tests",
        "passed",
        "failed",
        "coverage",
        "status",
        "future",
    ]
    return (
        _header(ctx, "MDX-VAL-009", "Requirements traceability matrix", SYSTEM_OWNER, QUALITY_APPROVER)
        + _sources_section(ctx)
        + "## 2. Matrix\n\n"
        "Tests link to a requirement through their `requirement` markers naming one of its scenarios; for class A only a "
        'test\'s own marker counts (O24). "NOT COVERED" = '
        "no tagged test in this JUnit; the scripted OQ steps (MDX-VAL-007-R) then carry the evidence. Status: Verified / "
        "Not verified / Failed / Blocked / Requires human decision (MDX-B10-005 section 6). "
        '"future": scenarios of features not built yet, never verification. Full columns in `rtm.csv`.\n\n'
        + _table(keys, [[r[k] for k in keys] for r in rows])
    )


def _figures_rows(figures: dict) -> list[list]:
    return [[k, json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v] for k, v in figures.items()]


def vsr(ctx: Context, s: Sources, rows: list[dict], figures: dict, devs: list[dict]) -> str:
    by_class = [[c, sum(r["class"] == c for r in rows), sum(r["class"] == c and r["status"] == "Verified" for r in rows),
                 sum(r["class"] == c and r["coverage"] == "NOT COVERED" for r in rows), sum(r["class"] == c and r["status"] == "Failed" for r in rows)]
                for c in ("A", "B", "C")]  # fmt: skip
    conclusion = (
        "No conclusion: this is a dry run. " + DEV_BANNER + "."
        if ctx.dry_run
        else 'To be completed by the author after review: "MDARIX release '
        + ctx.release
        + ' is fit for MDARIX\'s intended use as validated" only if every class-A row is Verified or carries a signed risk acceptance; never "validated for every customer".'
    )
    return (
        _header(ctx, "MDX-VAL-011", "Validation summary report", SYSTEM_OWNER, QUALITY_APPROVER)
        + _sources_section(ctx)
        + f"## 2. Scope\n\nRelease {ctx.release}, commit `{ctx.commit}`. Requirements in scope: {len(rows)} (all; a change-impact "
        "assessment narrows later releases).\n\n"
        + "## 3. Environment\n\nAs recorded in the IQ record (MDX-VAL-006).\n\n"
        + "## 4. Results by class\n\n"
        + _table(["Class", "REQs", "Verified", "NOT COVERED", "Failed"], by_class)
        + "\n## 5. Validation figures (G13)\n\n"
        + _table(["Figure", "Value"], _figures_rows(figures))
        + f"\n## 6. Deviations\n\n{len(devs)} deviation(s) for this release (MDX-VAL-010).\n\n"
        + "## 7. Traceability check results\n\n"
        + ("\n".join(f"- {p}" for p in ctx.problems) if ctx.problems else "- none")
        + "\n\n"
        + "## 8. Known limitations\n\n- Requirements without a scenario or a negative scenario are listed in section 7.\n"
        "- Defect leakage has no source until MDARIX's own complaint and CAPA registers exist (B6b Part D).\n"
        "- Most test tags are at file level. For class-A requirements only a test's own marker counts as verification; "
        'a file-level marker shows as "file-level only, not verification" in the RTM (owner decision O24).\n\n'
        + _vsr_required(rows)
        + "## 9. Independence statement\n\nReviewed by the quality approver, who did not write the code or the tests: "
        "name ________ date ________\n\n" + "## 10. Audit-finding self-check\n\n"
        "- URS not written by engineering alone: ____\n- QA reviewed independently: ____\n- PQ executed by users: ____\n"
        "- Periodic-review owner named: ____\n- Security assessment (MDX-B10-006) linked into the risk assessment: ____\n"
        "- Every requirement traced to a test: ____\n\n" + f"## 11. Conclusion\n\n{conclusion}\n"
    )


def _vsr_required(rows: list[dict]) -> str:
    """The VSR content MDX-VAL-001 asks for: VMP-R96 counts, VMP-R46 label, VMP-R82/R84 people, VMP-R15 references."""
    class_a = [r for r in rows if r["class"] == "A"]
    tagged = sum(r["status"] == "Verified" for r in class_a)
    return (
        "## 8a. Class-A verification (VMP-R96)\n\n"
        + _table(
            [
                "Verified by tagged tests (this JUnit)",
                "Verified by executed scripted OQ steps (MDX-VAL-007-R)",
                "Not verified",
            ],
            [[tagged, "____ (counted from the signed OQ results)", f"{len(class_a) - tagged} less the scripted count"]],
        )  # fmt: skip
        + "\nUntil staging exists every result in this report is from the controlled local environment (VMP-R46).\n\n"
        "## 8b. People (VMP-R82, VMP-R84)\n\n"
        + _table(
            ["Role", "Name", "Read MDX-VAL-001 (date)", "Read the protocol (date)", "Qualification record"],
            [["Executor (IQ, OQ)", "", "", "", ""], ["Executor (PQ)", "", "", "", ""], ["Approver", "", "", "", ""]],
        )  # fmt: skip
        + "\n## 8c. References R9 to R12 (VMP-R15)\n\n"
        + _table(
            ["Reference", "Expectations met by this pack", "Expectations not met, with the reason"],
            [
                ["R9 ISO/TR 80002-2", "", ""],
                ["R10 GAMP 5 (2nd edition)", "", ""],
                ["R11 FDA CSA guidance", "", ""],
                ["R12 PIC/S PI 011-3", "", ""],
            ],
        )  # fmt: skip
        + "\n"
    )


def approval(ctx: Context, s: Sources, figures: dict, hashes: dict, devs: list[dict]) -> dict:
    checks = s.release_checks or {}
    summary = {
        "tests": len(s.tests), "passed": sum(t["result"] == "pass" for t in s.tests),
        "failed": sum(t["result"] == "fail" for t in s.tests), "skipped": sum(t["result"] == "skipped" for t in s.tests),
    }  # fmt: skip
    return {
        "document_id": record_id(ctx.release), "template": "MDX-VAL-012", "release": ctx.release, "commit": ctx.commit, "tag": ctx.tag, "migration_head": ctx.head,
        "release_checks": {"result": checks.get("passed"), "full_suite": checks.get("full_suite"), "sha256": hashes.get("release-checks.json")},
        "junit_summary": summary, "junit_sha256": hashes.get("junit.xml"), "rtm_sha256": hashes.get("rtm.csv"), "g13": figures,
        "open_deviations": [{"dev_id": d["dev_id"], "classification": d.get("classification"), "acceptance_rationale": ""}
                            for d in devs if d.get("status", "").strip().lower() != "closed"],
        "risk_acceptances": [],  # per Open row relied on: RSK ID, interim control, due date, signed acceptance ref
        "change_impact_reference": "", "customer_change_notice_date": "", "restore_point_and_rollback": "",
        "emergency_fix_written_ok": "", "deploy_gate_result": "", "basis": INTERIM_BASIS,
        "prepared_by": SYSTEM_OWNER, "prepared_date": "",
        "approver": QUALITY_APPROVER, "approval_date": "",
        "meaning": "I approve this release for production after the checks listed.",
        "status": DEV_BANNER if ctx.dry_run else "PREPARED, NOT SIGNED",
    }  # fmt: skip


CRITERIA_ROWS = [[n, text, "", ""] for n, text in enumerate(INTERIM_CRITERIA, 1)]


def approval_markdown(ctx: Context, record: dict) -> str:
    rows = [[k, v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)] for k, v in record.items()]
    return (
        _header(
            ctx,
            record_id(ctx.release),
            "Release approval record (template MDX-VAL-012)",
            SYSTEM_OWNER + " (prepares)",
            QUALITY_APPROVER + " (signs)",
        )
        + "## 1. Record\n\n"
        + _table(["Item", "Value"], rows)
        + "\n## 2. Criteria (the quality approver initials each)\n\n"
        + _table(["#", "Criterion", "Met (yes / no / accepted)", "Initials"], CRITERIA_ROWS)
        + "\n## 3. Signature\n\nName: ____________ Role: quality approver Date (UTC): ____________\n\n"
        "Meaning: I approve this release for production after the checks listed.\n"
    )


# ---- writing -------------------------------------------------------------------------------------------------------


def signed(out: Path, release: str, signatures: Path) -> bool:
    """A release folder is signed when it holds a signed PDF or ``signatures.csv`` names its approval record."""
    if out.exists() and any(out.glob("MDX-VAL-012*-signed.pdf")):  # a signed OQ protocol alone does not lock it
        return True
    if signatures.exists():
        for row in csv.DictReader(signatures.read_text(encoding="utf-8-sig").splitlines()):
            if row.get("document_id") == record_id(release):
                return True
    return False


def _csv(rows: list[list]) -> bytes:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    return buffer.getvalue().encode("utf-8")


def build(ctx: Context, s: Sources) -> dict[str, bytes]:
    """Every file of the pack, by name (deterministic: the same inputs give the same bytes)."""
    files: dict[str, bytes] = {}
    rows = rtm(s)
    figures = g13(s, ctx.release)
    devs = release_deviations(s, ctx.release)
    scripted, log = oq_tables(s)
    sha = protocol_sha256(scripted)
    rtm_rows = [list(rows[0].keys())] + [list(r.values()) for r in rows] if rows else [["req_id"]]
    files["rtm.csv"] = _csv(rtm_rows)
    files["rtm.xlsx"] = xlsx_write.write({"RTM": rtm_rows})
    files["oq-protocol.csv"] = _csv(scripted)
    with_results = ctx.oq_approved or ctx.dry_run  # O20: no OQ results without an approved protocol
    if with_results:
        steps = [scripted[0] + RESULT_HEADER] + [row + [""] * len(RESULT_HEADER) for row in scripted[1:]]
        files["oq-log.xlsx"] = xlsx_write.write({"Scripted OQ (class A)": steps, "Automated (tagged)": log})
    dev_rows = [DEVIATION_COLUMNS] + [[d.get(c, "") for c in DEVIATION_COLUMNS] for d in devs]
    files["deviations.csv"] = _csv(dev_rows)
    files["deviations.xlsx"] = xlsx_write.write({"Deviations": dev_rows})
    files["g13.json"] = (json.dumps(figures, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if s.release_checks is not None:
        files["release-checks.json"] = s.release_checks_raw or (json.dumps(s.release_checks, indent=2) + "\n").encode()
    if s.junit_raw is not None:
        files["junit.xml"] = s.junit_raw
    files["checks.txt"] = ("\n".join(ctx.problems) + "\n" if ctx.problems else "no failing check\n").encode("utf-8")
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    documents = {
        "MDX-VAL-004-URS": urs(ctx, s), "MDX-VAL-005-FS-DS": fsds(ctx, s), "MDX-VAL-006-IQ": iq(ctx, s),
        "MDX-VAL-007-P-OQ-protocol": oq_protocol(ctx, scripted, sha), "MDX-VAL-009-RTM": rtm_markdown(ctx, rows),
        "MDX-VAL-011-VSR": vsr(ctx, s, rows, figures, devs),
    }  # fmt: skip
    if with_results:
        documents["MDX-VAL-007-R-OQ-results"] = oq(ctx, s, scripted, log, sha, ctx.oq_approved)
    if not open_critical(s, ctx.release):
        record = approval(ctx, s, figures, hashes, devs)
        files["MDX-VAL-012-release-approval.json"] = (json.dumps(record, indent=2) + "\n").encode("utf-8")
        documents["MDX-VAL-012-release-approval"] = approval_markdown(ctx, record)
    _render(ctx, documents, files)
    manifest = {name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(files.items())}
    files["manifest.json"] = (
        json.dumps({"release": ctx.release, "commit": ctx.commit, "sha256": manifest}, indent=2) + "\n"
    ).encode("utf-8")
    return files


def _render(ctx: Context, documents: dict[str, str], files: dict[str, bytes]) -> None:
    from reports import pdf

    watermark = DEV_BANNER if ctx.dry_run else "DRAFT - NOT SIGNED"
    for name, markdown in documents.items():
        title = markdown.splitlines()[0].lstrip("# ")
        files[f"{name}.md"] = markdown.encode("utf-8")
        files[f"{name}.docx"] = docx_render.render_docx(markdown, title=title, document_date=ctx.date)
        files[f"{name}.pdf"] = pdf.render(title, [f"Release {ctx.release} - commit {ctx.commit} - {ctx.date}"],
                                          docx_render.pdf_lines(markdown), watermark=watermark,
                                          footer=f"MDARIX {name} - release {ctx.release}")  # fmt: skip


def build_protocol(ctx: Context, s: Sources) -> tuple[dict[str, bytes], str]:
    """Only the OQ protocol, for approval before execution (O20): its files and its SHA-256."""
    scripted, _ = oq_tables(s)
    sha = protocol_sha256(scripted)
    files = {"oq-protocol.csv": _csv(scripted)}
    _render(ctx, {"MDX-VAL-007-P-OQ-protocol": oq_protocol(ctx, scripted, sha)}, files)
    return files, sha


def release_check_problems(checks: dict | None, commit: str, has_junit: bool) -> list[str]:
    """A release pack needs this release's full-suite evidence: a real (not dry-run) release-checks run of the whole
    suite on the same commit, every step passed, and its JUnit."""
    problems = [] if has_junit else ["no JUnit XML given"]
    if checks is None:
        return problems + ["no release-checks JSON given"]
    if checks.get("dry_run"):
        problems.append("release-checks JSON is a dry run")
    if not checks.get("full_suite"):
        problems.append("release-checks JSON is not a full-suite run (-Full)")
    if checks.get("passed") is not True or any(s.get("result") != "pass" for s in checks.get("steps") or []):
        problems.append("release-checks JSON has a step that did not pass (skipped or failed)")
    theirs = str(checks.get("commit") or "")
    if not theirs or not (commit.startswith(theirs) or theirs.startswith(commit)):
        problems.append(f"release-checks JSON is for commit {theirs or '(none)'}, not {commit}")
    return problems


def write(out: Path, files: dict[str, bytes]) -> None:
    """Writes the pack. Files an earlier run generated (its manifest) that this run does not are removed; files a
    person added (change impact, PQ record) are kept."""
    out.mkdir(parents=True, exist_ok=True)
    old = out / "manifest.json"
    if old.exists():
        for name in json.loads(old.read_text(encoding="utf-8")).get("sha256", {}):
            if name not in files and (out / name).is_file():
                (out / name).unlink()
    for name, raw in files.items():
        (out / name).write_bytes(raw)
