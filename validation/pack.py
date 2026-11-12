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
from datetime import datetime
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


class PackRefused(Exception):
    """The pack may not be written (a signed release folder)."""


@dataclass
class Sources:
    requirements: list[dict]
    scenarios: dict[str, dict]  # id -> {"title", "expected", "status", "notes"}
    tests: list[dict] = field(default_factory=list)  # {"id", "result", "seconds", "scenarios"}
    release_checks: dict | None = None
    deviations: list[dict] = field(default_factory=list)
    clock_check: dict | None = None


# ---- reading -------------------------------------------------------------------------------------------------------


def read_requirements(path: Path) -> list[dict]:
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
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


def read_junit(path: Path) -> list[dict]:
    tests = []
    for case in ElementTree.parse(path).getroot().iter("testcase"):
        outcome = "pass"
        if case.find("failure") is not None or case.find("error") is not None:
            outcome = "fail"
        elif case.find("skipped") is not None:
            outcome = "skipped"
        scenarios = sorted({p.get("value", "") for p in case.iter("property") if p.get("name") == "requirement"} - {""})
        tests.append({
            "id": f"{case.get('classname', '')}::{case.get('name', '')}", "result": outcome,
            "seconds": float(case.get("time") or 0), "scenarios": scenarios,
        })  # fmt: skip
    return sorted(tests, key=lambda t: t["id"])


def read_deviations(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))


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


def check(sources: Sources, release: str) -> list[str]:
    """Every failing case, listed (B6-49, B6-57, B6-58): never stops at the first."""
    problems = []
    tagged_pass = {s for t in sources.tests if t["result"] == "pass" for s in t["scenarios"]}
    for req in sources.requirements:
        rid = req["req_id"]
        if not req["scenario_ids"]:
            problems.append(f"{rid}: no scenario")
        if req["class"] == "A" and not req["negative_scenarios"]:
            problems.append(f"{rid}: class A without a negative scenario")
        for sid in sorted(set(req["scenario_ids"]) | set(req["negative_scenarios"])):
            if sid not in sources.scenarios:
                problems.append(f"{rid}: scenario {sid} is not in the register")
    cited = {s for req in sources.requirements for s in req["scenario_ids"]}
    for sid in sorted(cited & set(sources.scenarios)):
        row = sources.scenarios[sid]
        if row["status"] not in FIVE:
            problems.append(f"{sid}: status '{row['status']}' is not one of the five values")
        if row["status"] == "PASS" and not row["notes"] and sid not in tagged_pass:
            problems.append(f"{sid}: PASS without evidence (no passing tagged test, no evidence note)")
    for test in sources.tests:
        for sid in test["scenarios"]:
            if sid not in sources.scenarios:
                problems.append(f"{test['id']}: marker names unknown scenario {sid}")
    for dev in release_deviations(sources, release):
        if dev.get("status", "").strip().lower() == "closed":
            if not dev.get("retest_result", "").strip():
                problems.append(f"{dev['dev_id']}: closed without a retest result")
            if not dev.get("approved_by", "").strip():
                problems.append(f"{dev['dev_id']}: closed without an approver")
    for dev in open_critical(sources, release):
        problems.append(f"{dev['dev_id']}: critical deviation open; no release approval record can be produced")
    return problems


def release_deviations(sources: Sources, release: str) -> list[dict]:
    return [d for d in sources.deviations if d.get("dev_id", "").startswith(f"DEV-{release}-")]


def open_critical(sources: Sources, release: str) -> list[dict]:
    return [
        d
        for d in release_deviations(sources, release)
        if d.get("classification", "").strip().lower() == "critical" and d.get("status", "").strip().lower() != "closed"
    ]


def rtm(sources: Sources) -> list[dict]:
    rows = []
    for req in sources.requirements:
        scenarios = req["scenario_ids"]
        linked = [t for t in sources.tests if set(t["scenarios"]) & set(scenarios)]
        statuses = {sources.scenarios.get(s, {}).get("status", "") for s in scenarios}
        results = {t["result"] for t in linked}
        if "fail" in results:
            status = "Failed"
        elif "BLOCKED" in statuses:
            status = "Blocked"
        elif "REQUIRES HUMAN DECISION" in statuses:
            status = "Requires human decision"
        elif "pass" in results:
            status = "Verified"
        else:
            status = "Not verified"
        rows.append({
            "req_id": req["req_id"], "class": req["class"], "risk_ids": " ".join(req["risk_ids"]),
            "scenarios": " ".join(scenarios) or "(none)",
            "negative_scenarios": " ".join(req["negative_scenarios"]) or "(none)",
            "tagged_tests": len(linked), "passed": sum(t["result"] == "pass" for t in linked),
            "failed": sum(t["result"] == "fail" for t in linked),
            "coverage": "covered" if linked else "NOT COVERED",
            "register_status": "; ".join(f"{s} {sources.scenarios.get(s, {}).get('status', 'NOT IN REGISTER')}" for s in scenarios),
            "named_tests": " ".join(req["tests"]), "status": status,
        })  # fmt: skip
    return rows


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}% ({part}/{whole})" if whole else "no data (0/0)"


def g13(sources: Sources, release: str, rows: list[dict]) -> dict:
    figures: dict = {"coverage": {}}
    for cls in ("A", "B", "C"):
        in_class = [r for r in rows if r["class"] == cls]
        figures["coverage"][cls] = _pct(sum(r["coverage"] == "covered" for r in in_class), len(in_class))
    class_a = [r for r in sources.requirements if r["class"] == "A"]
    figures["negative_coverage_class_a"] = _pct(sum(bool(r["negative_scenarios"]) for r in class_a), len(class_a))
    in_scope = sorted({s for r in sources.requirements for s in r["scenario_ids"]})
    ran = [t for t in sources.tests if t["result"] != "skipped"]
    executed = sorted({s for t in ran for s in t["scenarios"]} & set(in_scope))
    figures["execution_progress"] = _pct(len(executed), len(in_scope))
    tagged = [t for t in ran if t["scenarios"]]
    figures["pass_rate_tagged_tests"] = _pct(sum(t["result"] == "pass" for t in tagged), len(tagged))
    figures["pass_rate_all_tests"] = _pct(sum(t["result"] == "pass" for t in ran), len(ran))
    devs = release_deviations(sources, release)
    deviated = {d.get("test_or_scenario", "").strip() for d in devs}
    failed = {s for t in ran if t["result"] == "fail" for s in t["scenarios"]}
    figures["first_pass_yield"] = _pct(sum(s not in deviated and s not in failed for s in executed), len(executed))
    figures["defect_leakage"] = (
        "no source yet: MDARIX's own complaint and CAPA registers do not exist until B6b Part D (D4)"
    )
    days = []
    for d in devs:
        if d.get("closed_utc") and d.get("raised_utc"):
            opened, closed = (datetime.fromisoformat(d[k].replace("Z", "+00:00")) for k in ("raised_utc", "closed_utc"))
            days.append((closed - opened).total_seconds() / 86400)
    figures["deviation_closure_days"] = (
        {"median": round(statistics.median(days), 1), "max": round(max(days), 1), "closed": len(days)}
        if days
        else "no closed deviations in this release"
    )
    open_devs = [d for d in devs if d.get("status", "").strip().lower() != "closed"]
    by_class: dict[str, int] = {}
    for d in open_devs:
        by_class[d.get("classification") or "unclassified"] = (
            by_class.get(d.get("classification") or "unclassified", 0) + 1
        )
    figures["open_deviations"] = {"count": len(open_devs), "by_classification": dict(sorted(by_class.items()))}
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


def _header(ctx: Context, doc_id: str, title: str, author: str, approver: str) -> str:
    status = f"DRAFT. {DEV_BANNER} (dry run)" if ctx.dry_run else "DRAFT (for review and signature)"
    return "\n".join([
        f"# {doc_id} {title}", "",
        f"**{DEV_BANNER}**" if ctx.dry_run else "", "",
        "| Field | Value |", "|---|---|",
        f"| Document ID | {doc_id} |", f"| Title | {title} |", f"| Version | release {ctx.release} |",
        f"| Status | {status} |", f"| Author (R) | {author} |", f"| Approver (A) | {approver} |",
        "| Drafting | Generated by `scripts/validation_pack.py` from the sources in section 1; reviewed by the author before signature |",
        f"| Date | {ctx.date} |", f"| Code baseline | commit `{ctx.commit}`, tag {ctx.tag or '(none yet)'}; `VERSION` {ctx.version_file} |",
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


def oq_tables(s: Sources) -> tuple[list[list], list[list]]:
    scripted = [
        [
            "Step",
            "REQ",
            "Scenario",
            "Scenario text",
            "Pre-approved expected result",
            "Executed by",
            "Date",
            "Result",
            "Evidence ID",
        ]
    ]
    n = 0
    for req in s.requirements:
        if req["class"] != "A":
            continue
        for sid in req["scenario_ids"]:
            row = s.scenarios.get(sid)
            if row:
                n += 1
                scripted.append([f"OQ-{n:03d}", req["req_id"], sid, row["title"], row["expected"], "", "", "", ""])
    req_of: dict[str, list[str]] = {}
    for req in s.requirements:
        for sid in req["scenario_ids"]:
            req_of.setdefault(sid, []).append(req["req_id"])
    log = [["Test", "Scenarios", "REQs", "Result", "Seconds"]]
    for t in s.tests:
        if t["scenarios"]:
            reqs = sorted({r for sid in t["scenarios"] for r in req_of.get(sid, [])})
            log.append([t["id"], " ".join(t["scenarios"]), " ".join(reqs), t["result"].upper(), t["seconds"]])
    return scripted, log


def oq(ctx: Context, s: Sources, scripted: list[list], log: list[list]) -> str:
    untagged = sum(1 for t in s.tests if not t["scenarios"])
    return (
        _header(
            ctx,
            "MDX-VAL-007",
            "Operational qualification protocol and results",
            SYSTEM_OWNER,
            QUALITY_APPROVER + " (pre-approves expected results)",
        )
        + _sources_section(ctx)
        + "## 2. Approach\n\n"
        "Class-A scenarios are executed as scripted steps with the expected results below, pre-approved by the quality "
        "approver before execution (format of the free-trial test scripts). The automated suite is supporting evidence "
        "(CSA): tagged tests are listed per scenario; class B and C rows are covered by the automated suite, untagged "
        f"(B6b-D17): {untagged} untagged test(s) ran in this JUnit.\n\n"
        f"## 3. Scripted OQ steps (class A): {len(scripted) - 1}\n\n"
        + _table(scripted[0], scripted[1:])
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
    ]
    return (
        _header(ctx, "MDX-VAL-009", "Requirements traceability matrix", SYSTEM_OWNER, QUALITY_APPROVER)
        + _sources_section(ctx)
        + "## 2. Matrix\n\n"
        'Tests link to a requirement through their `requirement` markers naming one of its scenarios. "NOT COVERED" = '
        "no tagged test in this JUnit; the scripted OQ steps (MDX-VAL-007) then carry the evidence. Status: Verified / "
        "Not verified / Failed / Blocked / Requires human decision (MDX-B10-005 section 6). Full columns in `rtm.csv`.\n\n"
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
        "- Defect leakage has no source until MDARIX's own complaint and CAPA registers exist (B6b Part D).\n\n"
        + "## 9. Independence statement\n\nThe quality approver, who did not write the code or the tests, reviewed the results.\n\n"
        + "## 10. Audit-finding self-check\n\n"
        "- URS not written by engineering alone: ____\n- QA reviewed independently: ____\n- PQ executed by users: ____\n"
        "- Periodic-review owner named: ____\n- Security assessment (MDX-B10-006) linked into the risk assessment: ____\n"
        "- Every requirement traced to a test: ____\n\n" + f"## 11. Conclusion\n\n{conclusion}\n"
    )


def approval(ctx: Context, s: Sources, figures: dict, hashes: dict, devs: list[dict]) -> dict:
    checks = s.release_checks or {}
    summary = {
        "tests": len(s.tests), "passed": sum(t["result"] == "pass" for t in s.tests),
        "failed": sum(t["result"] == "fail" for t in s.tests), "skipped": sum(t["result"] == "skipped" for t in s.tests),
    }  # fmt: skip
    return {
        "document_id": "MDX-VAL-012", "release": ctx.release, "commit": ctx.commit, "tag": ctx.tag, "migration_head": ctx.head,
        "release_checks": {"result": checks.get("passed"), "sha256": hashes.get("release-checks.json")},
        "junit_summary": summary, "rtm_sha256": hashes.get("rtm.csv"), "g13": figures,
        "open_deviations": [{"dev_id": d["dev_id"], "classification": d.get("classification"), "rationale": d.get("impact")}
                            for d in devs if d.get("status", "").strip().lower() != "closed"],
        "change_impact_reference": "", "customer_change_notice_date": "", "restore_point_and_rollback": "",
        "approver": QUALITY_APPROVER, "approval_date": "",
        "meaning": "I approve this release for production after the checks listed.",
        "status": DEV_BANNER if ctx.dry_run else "PREPARED, NOT SIGNED",
    }  # fmt: skip


def approval_markdown(ctx: Context, record: dict) -> str:
    rows = [[k, v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)] for k, v in record.items()]
    return (
        _header(
            ctx, "MDX-VAL-012", "Release approval record", SYSTEM_OWNER + " (prepares)", QUALITY_APPROVER + " (signs)"
        )
        + "## 1. Record\n\n"
        + _table(["Item", "Value"], rows)
        + "\n## 2. Signature\n\nName: ____________ Role: quality approver Date (UTC): ____________\n\n"
        "Meaning: I approve this release for production after the checks listed.\n"
    )


# ---- writing -------------------------------------------------------------------------------------------------------


def signed(out: Path, release: str, signatures: Path) -> bool:
    """A release folder is signed when it holds a signed PDF or ``signatures.csv`` names its approval record."""
    if out.exists() and any(out.glob("*-signed.pdf")):
        return True
    if signatures.exists():
        for row in csv.DictReader(signatures.read_text(encoding="utf-8").splitlines()):
            if row.get("document_id") == "MDX-VAL-012" and row.get("version") == release:
                return True
    return False


def _csv(rows: list[list]) -> bytes:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    return buffer.getvalue().encode("utf-8")


def build(ctx: Context, s: Sources) -> dict[str, bytes]:
    """Every file of the pack, by name (deterministic: the same inputs give the same bytes)."""
    from reports import pdf

    files: dict[str, bytes] = {}
    rows = rtm(s)
    figures = g13(s, ctx.release, rows)
    devs = release_deviations(s, ctx.release)
    scripted, log = oq_tables(s)
    rtm_rows = [list(rows[0].keys())] + [list(r.values()) for r in rows] if rows else [["req_id"]]
    files["rtm.csv"] = _csv(rtm_rows)
    files["rtm.xlsx"] = xlsx_write.write({"RTM": rtm_rows})
    files["oq-log.xlsx"] = xlsx_write.write({"Scripted OQ (class A)": scripted, "Automated (tagged)": log})
    dev_rows = [DEVIATION_COLUMNS] + [[d.get(c, "") for c in DEVIATION_COLUMNS] for d in devs]
    files["deviations.csv"] = _csv(dev_rows)
    files["deviations.xlsx"] = xlsx_write.write({"Deviations": dev_rows})
    files["g13.json"] = (json.dumps(figures, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if s.release_checks is not None:
        files["release-checks.json"] = (json.dumps(s.release_checks, indent=2, sort_keys=True) + "\n").encode("utf-8")
    files["checks.txt"] = ("\n".join(ctx.problems) + "\n" if ctx.problems else "no failing check\n").encode("utf-8")
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    documents = {
        "MDX-VAL-004-URS": urs(ctx, s), "MDX-VAL-005-FS-DS": fsds(ctx, s), "MDX-VAL-006-IQ": iq(ctx, s),
        "MDX-VAL-007-OQ": oq(ctx, s, scripted, log), "MDX-VAL-009-RTM": rtm_markdown(ctx, rows),
        "MDX-VAL-011-VSR": vsr(ctx, s, rows, figures, devs),
    }  # fmt: skip
    if not open_critical(s, ctx.release):
        record = approval(ctx, s, figures, hashes, devs)
        files["MDX-VAL-012-release-approval.json"] = (json.dumps(record, indent=2) + "\n").encode("utf-8")
        documents["MDX-VAL-012-release-approval"] = approval_markdown(ctx, record)
    watermark = DEV_BANNER if ctx.dry_run else "DRAFT - NOT SIGNED"
    for name, markdown in documents.items():
        title = markdown.splitlines()[0].lstrip("# ")
        files[f"{name}.md"] = markdown.encode("utf-8")
        files[f"{name}.docx"] = docx_render.render_docx(markdown, title=title, document_date=ctx.date)
        files[f"{name}.pdf"] = pdf.render(title, [f"Release {ctx.release} - commit {ctx.commit} - {ctx.date}"],
                                          docx_render.pdf_lines(markdown), watermark=watermark,
                                          footer=f"MDARIX {name} - release {ctx.release}")  # fmt: skip
    manifest = {name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(files.items())}
    files["manifest.json"] = (
        json.dumps({"release": ctx.release, "commit": ctx.commit, "sha256": manifest}, indent=2) + "\n"
    ).encode("utf-8")
    return files


def write(out: Path, files: dict[str, bytes]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, raw in files.items():
        (out / name).write_bytes(raw)
