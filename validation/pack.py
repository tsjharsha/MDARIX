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
from validation.pytest_requirements import HOOK_VERSION

FIVE = ("NOT RUN", "PASS", "FAIL", "BLOCKED", "REQUIRES HUMAN DECISION")
DEV_BANNER = "DEVELOPMENT RESULTS, NOT VALIDATION EVIDENCE"
SYSTEM_OWNER = "Sriharsha Telikicherla, Product & Engineering, system owner"
QUALITY_APPROVER = "Srinivas Telikicherla, QA/RA, quality approver"
# The people who sign, execute or run the generator (owner decision B6b-D1), by a distinct identifier: the two
# founders share the initials "S. T.", which never identify one person (rating-4 finding 6, 13 Nov 2026).
# ``writes_code``: the person writes the code under test, so never executes the PQ (MDX-VAL-008 PQ-R01).
PEOPLE = {
    "Srinivas T.": {"name": "Srinivas Telikicherla", "roles": ("quality approver",), "writes_code": False},
    "Sriharsha T.": {"name": "Sriharsha Telikicherla", "roles": ("system owner",), "writes_code": True},
}


def person(text: str) -> str | None:
    """The identifier of a named person, from the identifier or the full name; None for anything else."""
    text = (text or "").strip()
    for key, entry in PEOPLE.items():
        if text in (key, entry["name"]):
            return key
    return None


def _named(text: str) -> str:
    key = person(text)
    return f"{PEOPLE[key]['name']} ({key})" if key else text


DEVIATION_COLUMNS = [
    "dev_id", "raised_utc", "raised_by", "found_in", "test_or_scenario", "req_id", "expected", "seen",
    "documented_first_utc", "impact", "gxp_risk", "classification", "root_cause", "correction", "retest_id",
    "retest_result", "change_control", "capa_ref", "approved_by", "closed_utc", "status", "customer_scope",
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
    "Post-deploy check ready before signing: the deploy_gate.py command for this release is in section 4 of the record, "
    "and a failure starts the rollback of criterion 8",
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
    junit_meta: dict | None = None  # the suite's commit, tree and hook_version (read_junit_meta)
    deviations: list[dict] = field(default_factory=list)
    clock_check: dict | None = None
    oq_expected: dict[str, dict] = field(default_factory=dict)  # scenario -> concrete OQ expected result (O20)
    executed: list[dict] = field(default_factory=list)  # executed IQ / scripted OQ results (read_results)
    executed_raw: bytes | None = None  # copied into the release folder as executed-results.csv
    evidence: dict[str, list[dict]] = field(default_factory=dict)  # evidence ID -> stored files (read_evidence)
    oq_approval: Approval | None = None  # the verified OQ protocol approval (protocol_approval)
    pq_steps: dict[str, dict] = field(default_factory=dict)  # MDX-VAL-008 steps (read_pq_steps)
    pq_record: list[dict] | None = None  # pq-record.csv of the release, None when there is none
    pq_raw: bytes | None = None  # copied into the release folder as pq-record.csv
    rule_versions: list[dict] = field(default_factory=list)  # the rule register at this commit (read_rule_register)
    environment: dict = field(default_factory=dict)  # tool versions of the test run and the generator's own hashes
    signatures: list[dict] = field(default_factory=list)  # signatures.csv rows
    count_documents: dict[str, str] = field(default_factory=dict)  # documents holding a generated counts block


@dataclass
class Approval:
    """The OQ protocol approval of a release, checked against its signed PDF and the people register (O20, O31)."""

    approved: bool
    signer: str = ""  # PEOPLE identifier
    moment: datetime | None = None  # the approval; a date without a time counts as the end of that day
    problems: list[str] = field(default_factory=list)


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


RESULT_COLUMNS = ["step", "scenario_id", "executed_by", "date_utc", "result", "evidence_id"]


def read_results(path: Path) -> list[dict]:
    """``executed-results.csv``: one row per executed IQ step (``IQ-nnn``) or scripted OQ step (``OQ-nnn`` with its
    scenario), written by the executor; the generator feeds them into the IQ record, the OQ results, the RTM and the
    VSR, so no generated document is edited by hand (owner, 12 Nov 2026). Any other header is refused."""
    reader = csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines())
    if reader.fieldnames != RESULT_COLUMNS:
        raise ValueError(f"{path.name}: the header is not {','.join(RESULT_COLUMNS)}")
    return list(reader)


def _executed(sources: Sources, sid: str) -> set[str]:
    return {r["result"].strip() for r in sources.executed if r.get("scenario_id", "").strip() == sid}


def read_evidence(folder: Path) -> dict[str, list[dict]]:
    """The stored evidence of a release (VMP-R86): each file in ``<release folder>/evidence/`` is named after its
    evidence ID (``EVD-OQ-001.png``); an executed row's evidence ID resolves only to such a file."""
    found: dict[str, list[dict]] = {}
    if folder.is_dir():
        for file in sorted(p for p in folder.iterdir() if p.is_file()):
            found.setdefault(file.stem, []).append(
                {"file": f"evidence/{file.name}", "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}
            )
    return found


PQ_COLUMNS = ["step", "executed_by", "second_person", "date_utc", "result", "evidence_id", "deviation_id"]


def read_pq_steps(path: Path) -> dict[str, dict]:
    """The steps of the MDARIX PQ protocol (MDX-VAL-008 section 3): step -> persona, action, expected, scenarios."""
    steps: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.match(r"^\| PQ-\d{3} \|", line):
                cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
                steps[cells[0]] = {"persona": cells[1], "action": cells[2], "expected": cells[3], "scenarios": cells[4]}
    return steps


def read_pq_record(path: Path) -> list[dict]:
    """``pq-record.csv`` of a release (MDX-VAL-008 section 5), written by the PQ executor; any other header is refused."""
    reader = csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines())
    if reader.fieldnames != PQ_COLUMNS:
        raise ValueError(f"{path.name}: the header is not {','.join(PQ_COLUMNS)}")
    return list(reader)


def _canonical_hash(content) -> str:
    """The rule register's content hash (``backend/app/rule_register/register.py`` ``content_hash``), recomputed here
    so the IQ record states what the files hold without importing the application."""
    text = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_rule_register(folder: Path) -> list[dict]:
    """Every rule version at this commit (rating-4 finding 5): code, version, period, the file's SHA-256 (LF line
    endings, as git stores it) and its hash. A data-held version carries a content hash, recomputed here (``matches``);
    a code-held one names its implementation and, when pinned, a code hash, which ``tests/test_rule_pins_unit.py``
    recomputes from the code (``matches`` None here: the generator does not import the application)."""
    rows = []
    for file in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        raw = file.read_bytes()
        try:
            entry = json.loads(raw.decode("utf-8"))
        except ValueError:
            rows.append({"code": file.stem, "file": file.name, "unreadable": True})
            continue
        code_held = entry.get("held_as") == "CODE"
        rows.append({
            "code": entry.get("code", file.stem), "rule": entry.get("rule", ""), "version": entry.get("version", ""),
            "effective_from": entry.get("effective_from") or "start", "effective_to": entry.get("effective_to") or "open",
            "held_as": "CODE" if code_held else "DATA",
            "hash": (entry.get("code_hash") or f"implementation {entry.get('implementation') or 'not named'}")
            if code_held else entry.get("content_hash", ""),
            "matches": None if code_held else entry.get("content_hash") == _canonical_hash(entry.get("content")),
            "file_sha256": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest(), "file": file.name,
        })  # fmt: skip
    return rows


def read_signatures(path: Path) -> list[dict]:
    return list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines())) if path.exists() else []


def read_junit_meta(path: Path) -> dict:
    """The test-suite properties the requirement hook records: ``commit``, ``tree``, ``hook_version``."""
    meta: dict = {}
    for suite in ElementTree.parse(path).getroot().iter("testsuite"):
        props = suite.find("properties")
        if props is not None:
            meta.update({p.get("name"): p.get("value", "") for p in props.findall("property")})
    return meta


def junit_binding_problems(meta: dict | None, commit: str) -> list[str]:
    """A JUnit counts only for the commit it ran on, on a clean tree, with the current marker hook (owner, 12 Nov 2026):
    an older JUnit counted file-level markers as test-level ones."""
    if meta is None:
        return []  # no JUnit at all is listed by release_check_problems
    problems = []
    theirs = meta.get("commit", "")
    if len(theirs) != 40 or not theirs.startswith(commit):  # the full hash, never a short prefix
        problems.append(f"JUnit is for commit {theirs or '(not recorded)'}, not {commit}")
    if meta.get("tree") != "clean":
        problems.append(f"JUnit ran on a working tree '{meta.get('tree') or 'not recorded'}', not a clean one")
    if meta.get("hook_version") != HOOK_VERSION:
        problems.append(
            f"JUnit hook_version {meta.get('hook_version') or 'not recorded'}, not {HOOK_VERSION}: run the suite again"
        )
    return problems


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
DEV_FOUND_IN = ("IQ", "OQ", "PQ", "automated suite", "production")  # MDX-VAL-010 DL-R07
DEV_CUSTOMER_SCOPE = re.compile(r"all|CUS-\d{3}")  # MDX-VAL-010 DL-R08 (owner decision O36)


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
    if is_future(sources, sid):
        return "NOT RUN"  # O26: a feature not built is never verified, whatever a test says
    results = {t["result"] for t in _ran(sources) if _proves(sources, t, sid)}
    scripted = _executed(sources, sid)  # executed scripted OQ steps (results CSV)
    status = sources.scenarios.get(sid, {}).get("status", "")
    if "fail" in results or "FAIL" in scripted or status == "FAIL":
        return "FAIL"
    if status == "BLOCKED" or "BLOCKED" in scripted:
        return "BLOCKED"
    return "PASS" if "pass" in results or "PASS" in scripted else "NOT RUN"


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
    steps = {s for req in sources.requirements if req["class"] == "A" for s in req["scenario_ids"]}
    for row in sources.executed:
        step, result = row.get("step", "").strip(), row.get("result", "").strip()
        if result not in FIVE:
            problems.append(f"executed {step}: result '{result}' is not one of the five values")
        if not step.startswith(("IQ-", "OQ-")):
            problems.append(f"executed {step or '(blank)'}: step is not IQ-nnn or OQ-nnn")
        if step.startswith("OQ-") and row.get("scenario_id", "").strip() not in steps:
            problems.append(f"executed {step}: scenario '{row.get('scenario_id')}' is not a scripted class-A step")
        if result in ("PASS", "FAIL") and not all(
            row.get(k, "").strip() for k in ("executed_by", "date_utc", "evidence_id")
        ):
            problems.append(f"executed {step}: {result} without executor, date or evidence ID")
        problems += _executed_row_problems(sources, row, f"executed {step}")
    problems += _pq_problems(sources)
    if not sources.rule_versions:
        problems.append(
            "rule register: no rule version found (backend/app/rule_register/data); the IQ record lists none"
        )
    for rule in sources.rule_versions:
        if rule.get("unreadable"):
            problems.append(f"rule register {rule['file']}: not readable JSON")
        elif rule["matches"] is False:  # a code-held version is checked by its pin test
            problems.append(f"rule register {rule['code']}: content_hash does not match its content")
    for name, text in sorted(sources.count_documents.items()):
        problems += counts_problems(name, text, counts_block(sources))
    for dev in release_deviations(sources, release):
        dev_id, status = dev["dev_id"], dev.get("status", "").strip().lower()
        if status not in DEV_STATUSES:
            problems.append(f"{dev_id}: status '{dev.get('status')}' is not one of {', '.join(DEV_STATUSES)}")
        if dev.get("classification", "").strip().lower() not in DEV_CLASSES:
            problems.append(f"{dev_id}: classification '{dev.get('classification')}' is not critical, major or minor")
        if dev.get("found_in", "").strip() not in DEV_FOUND_IN:
            problems.append(f"{dev_id}: found_in '{dev.get('found_in')}' is not one of {', '.join(DEV_FOUND_IN)}")
        if not DEV_CUSTOMER_SCOPE.fullmatch(dev.get("customer_scope") or ""):
            problems.append(
                f"{dev_id}: customer_scope '{dev.get('customer_scope')}' is not 'all' or a customer code CUS-nnn"
            )
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
    for dev in release_deviations(sources, release):
        if dev.get("gxp_risk", "").strip().lower() == "high" and dev.get("status", "").strip().lower() != "closed":
            problems.append(f"{dev['dev_id']}: open deviation with GxP risk high; it blocks the release (VMP-R50a)")
    for dev in open_critical(sources, release):
        problems.append(f"{dev['dev_id']}: critical deviation open; no release approval record can be produced")
    return problems


def _moment(text: str, end_of_day: bool = False) -> datetime | None:
    """A UTC moment from ``YYYY-MM-DD[THH:MM[:SS]][Z]``; a bare date is the start of the day, or with ``end_of_day``
    its last second (an approval dated only by its day is never earlier than an execution on that day)."""
    try:
        moment = _utc(text)
    except ValueError:
        return None
    if end_of_day and re.fullmatch(r"\d{4}-\d{2}-\d{2}", text.strip()):
        moment = moment.replace(hour=23, minute=59, second=59)
    return moment


def _evidence_problems(sources: Sources, what: str, evidence_id: str) -> list[str]:
    files = sources.evidence.get(evidence_id.strip(), [])
    if not files:
        return [f"{what}: evidence {evidence_id} is not a stored file in the release folder's evidence/ (VMP-R86)"]
    if len(files) > 1:
        return [f"{what}: evidence {evidence_id} names {len(files)} files; one evidence ID is one file"]
    return []


def _executed_row_problems(sources: Sources, row: dict, what: str) -> list[str]:
    """Rating-4 finding 4: an executed row is checked, not trusted. The executor is a named person; the date is a date;
    the evidence ID resolves to a stored file; an OQ step is executed after the protocol approval and not by its
    approver; an IQ step is not executed by the IQ record's approver (VMP-R02, VMP-R86, VMP-R88)."""
    step, result = row.get("step", "").strip(), row.get("result", "").strip()
    executor, when = row.get("executed_by", "").strip(), row.get("date_utc", "").strip()
    who = person(executor)
    problems = []
    if executor and who is None:
        problems.append(f"{what}: executor '{executor}' is not a named person ({', '.join(PEOPLE)})")
    moment = _moment(when) if when else None
    if when and moment is None:
        problems.append(f"{what}: date_utc '{when}' is not a date and time")
    if result in ("PASS", "FAIL") and row.get("evidence_id", "").strip():
        problems += _evidence_problems(sources, what, row["evidence_id"])
    approval = sources.oq_approval
    if step.startswith("OQ-") and approval and approval.approved:
        if moment and approval.moment and moment <= approval.moment:
            problems.append(
                f"{what}: executed {when}, not after the OQ protocol approval of {approval.moment:%Y-%m-%d %H:%M} UTC; "
                "expected results are approved before execution (O20, VMP-R88)"
            )
        if who and who == approval.signer:
            problems.append(
                f"{what}: executed by {who}, who approved the OQ protocol; executor and approver are two people (VMP-R02)"
            )
    if step.startswith("IQ-") and who and "quality approver" in PEOPLE[who]["roles"]:
        problems.append(
            f"{what}: executed by {who}, the IQ record's approver; executor and approver are two people (VMP-R02)"
        )
    return problems


def _pq_problems(sources: Sources) -> list[str]:
    """The release's PQ record against MDX-VAL-008: known steps, the five results, an executor who does not write the
    code (PQ-R01), a second person who is someone else (PQ-R08), a deviation for a step not passed (PQ-R04), evidence
    that resolves (PQ-R03)."""
    if sources.pq_record is None:
        return []
    problems = []
    logged = {d.get("dev_id", "").strip() for d in sources.deviations}
    for row in sources.pq_record:
        step, result = row.get("step", "").strip(), row.get("result", "").strip()
        what = f"PQ {step or '(blank)'}"
        if step not in sources.pq_steps:
            problems.append(f"{what}: not a step of MDX-VAL-008")
        if result not in FIVE:
            problems.append(f"{what}: result '{result}' is not one of the five values")
        if result in ("PASS", "FAIL") and not all(
            row.get(k, "").strip() for k in ("executed_by", "date_utc", "evidence_id")
        ):
            problems.append(f"{what}: {result} without executor, date or evidence ID")
        executor, second = row.get("executed_by", "").strip(), row.get("second_person", "").strip()
        who = person(executor)
        if executor and who is None:
            problems.append(f"{what}: executor '{executor}' is not a named person ({', '.join(PEOPLE)})")
        elif who and PEOPLE[who]["writes_code"]:
            problems.append(f"{what}: executed by {who}, who writes the code under test (MDX-VAL-008 PQ-R01)")
        if second and person(second) is None:
            problems.append(f"{what}: second person '{second}' is not a named person ({', '.join(PEOPLE)})")
        elif second and person(second) == who:
            problems.append(f"{what}: the second person is the executor; four-eyes steps need two people (PQ-R08)")
        when = row.get("date_utc", "").strip()
        if when and _moment(when) is None:
            problems.append(f"{what}: date_utc '{when}' is not a date and time")
        if (
            result in ("FAIL", "BLOCKED", "REQUIRES HUMAN DECISION")
            and row.get("deviation_id", "").strip() not in logged
        ):
            problems.append(f"{what}: {result} without a deviation in deviation-log.csv (MDX-VAL-008 PQ-R04)")
        if result in ("PASS", "FAIL") and row.get("evidence_id", "").strip():
            problems += _evidence_problems(sources, what, row["evidence_id"])
    return problems


def pq_summary(sources: Sources) -> dict:
    """The PQ outcome for the VSR (MDX-VAL-008 section 4): a step passes on its latest PASS row."""
    if sources.pq_record is None:
        return {"record": "no pq-record.csv in this release folder: the MDARIX PQ was not executed for this release"}
    latest: dict[str, str] = {}
    for row in sorted(sources.pq_record, key=lambda r: r.get("date_utc", "")):
        latest[row.get("step", "").strip()] = row.get("result", "").strip()
    steps = sorted(sources.pq_steps)
    passed = [s for s in steps if latest.get(s) == "PASS"]
    missing = [s for s in steps if s not in latest]
    return {
        "record": "pq-record.csv", "steps": len(steps), "rows": len(sources.pq_record), "passed": len(passed),
        "not_passed": [s for s in steps if s in latest and latest[s] != "PASS"], "missing": missing,
        "accepted": bool(steps) and len(passed) == len(steps),
    }  # fmt: skip


def protocol_approval(signatures: list[dict], release: str, sha256: str, root: Path) -> Approval:
    """The OQ protocol approval of ``release`` for the protocol whose steps hash to ``sha256`` (``content_sha256``,
    O31), checked, not trusted (rating-4 finding 4): the signer is a named quality approver holding the role on the
    row, the date is a date, and the signed PDF exists with the row's SHA-256 (``sha256``)."""
    rows = [
        r for r in signatures
        if r.get("document_id") == PROTOCOL_ID and r.get("version") == release and r.get("content_sha256") == sha256
    ]  # fmt: skip
    if not rows:
        return Approval(False)
    row = rows[-1]
    what = f"OQ protocol approval ({PROTOCOL_ID} {release})"
    problems = []
    signer, role = person(row.get("signer", "")), row.get("role", "").strip()
    if signer is None:
        problems.append(f"{what}: signer '{row.get('signer')}' is not a named person ({', '.join(PEOPLE)})")
    elif role != "quality approver" or role not in PEOPLE[signer]["roles"]:
        problems.append(f"{what}: signer {signer} with role '{role}'; the quality approver approves the protocol (O20)")
    moment = _moment(row.get("date_utc", ""), end_of_day=True)
    if moment is None:
        problems.append(f"{what}: date_utc '{row.get('date_utc')}' is not a date")
    pdf = root / row.get("pdf_path", "").strip() if row.get("pdf_path", "").strip() else None
    if pdf is None or not pdf.is_file():
        problems.append(f"{what}: signed PDF '{row.get('pdf_path')}' is not stored")
    elif hashlib.sha256(pdf.read_bytes()).hexdigest() != row.get("sha256", "").strip().lower():
        problems.append(f"{what}: the SHA-256 of {row['pdf_path']} differs from its signatures.csv row")
    return Approval(not problems, signer or "", moment, problems)


COUNTS_BEGIN = (
    "<!-- generated counts: begin (python scripts/validation_pack.py --release <release> --update-counts) -->"
)
COUNTS_END = "<!-- generated counts: end -->"


def counts(s: Sources) -> list[list]:
    """The counts the documents state, computed from their sources (rating-4 finding 9): never typed."""
    reqs = s.requirements
    class_a = [r for r in reqs if r["class"] == "A"]
    oq = list(s.oq_expected.values())
    future = [sid for sid in s.scenarios if is_future(s, sid)]
    return [
        ["Requirements (`requirements.csv`)", len(reqs)],
        *[[f"Requirements, class {c}", sum(r["class"] == c for r in reqs)] for c in ("A", "B", "C")],
        ["Class-A requirements without a negative scenario", sum(not r["negative_scenarios"] for r in class_a)],
        ["Class-A requirements whose negative scenarios are all future",
         sum(bool(r["negative_scenarios"]) and all(is_future(s, x) for x in r["negative_scenarios"]) for r in class_a)],
        ["Scenarios in the register", len(s.scenarios)],
        ["Scenarios marked future (not built)", len(future)],
        ["Scripted class-A OQ steps", len(oq_tables(s)[0]) - 1],
        ["Class-A scenarios without an OQ expected result",
         sum(x not in s.oq_expected for x in class_a_scenarios(s) if not is_future(s, x))],
        ["OQ expected results (`oq-expected-results.csv`)", len(oq)],
        ["OQ expected results derived from the requirement", sum(r.get("source", "").strip() == "requirement" for r in oq)],
        ["OQ expected results drafted from the code", sum(r.get("source", "").strip() == "code" for r in oq)],
        ["OQ expected results confirmed by the owner", sum(bool(r.get("confirmed_by", "").strip()) for r in oq)],
        ["OQ expected results whose text says TO CONFIRM", sum("TO CONFIRM" in r.get("expected_result", "") for r in oq)],
        ["Deviations in `deviation-log.csv`", len(s.deviations)],
        ["Deviations not closed", sum(d.get("status", "").strip().lower() != "closed" for d in s.deviations)],
        ["Rows in `signatures.csv`", len(s.signatures)],
        ["MDARIX PQ steps (MDX-VAL-008)", len(s.pq_steps)],
    ]  # fmt: skip


def counts_block(s: Sources) -> str:
    return f"{COUNTS_BEGIN}\n\n{_table(['Count', 'Value'], counts(s))}\n{COUNTS_END}"


def counts_problems(name: str, text: str, block: str) -> list[str]:
    text = text.replace("\r\n", "\n")
    if COUNTS_BEGIN not in text or COUNTS_END not in text:
        return [f"{name}: no generated counts block"]
    if block not in text:
        return [f"{name}: the generated counts are stale; run scripts/validation_pack.py --update-counts"]
    return []


def with_counts(text: str, block: str) -> str:
    """``text`` (LF line endings) with its generated counts block replaced by ``block``."""
    start, end = text.index(COUNTS_BEGIN), text.index(COUNTS_END) + len(COUNTS_END)
    return text[:start] + block + text[end:]


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
        scripted = sum("PASS" in _executed(sources, s) for s in scenarios)
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
            "scripted_oq_passed": scripted,
            "coverage": "covered" if linked else "scripted OQ" if scripted
            else "file-level only, not verification" if file_only else "NOT COVERED",
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
    oq_approved: bool = (
        False  # signatures.csv holds this release's OQ protocol with the current content_sha256 (O20, O31)
    )
    author: str = ""  # who ran the generator: --author, else the git author (rating-4 finding 6)


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
        f"until it is signed, after which a correction is a new version (VMP-R39) | {_named(ctx.author) or 'not recorded'} "
        "(generator run) |",
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
    meta = s.junit_meta or {}
    env = s.environment
    rules = s.rule_versions
    wrong = [r["code"] for r in rules if r.get("unreadable") or r.get("matches") is False]
    data_held = sum(r.get("held_as") == "DATA" for r in rules)
    rows = [
        ["IQ-001", "Release identity", f"release {ctx.release}; `VERSION` {ctx.version_file}; commit `{ctx.commit}`; tag {ctx.tag or '(none)'}",
         "match" if ctx.release == ctx.version_file else "MISMATCH: set at the release join"],
        ["IQ-002", "Migration head (one head)", ctx.head, "one head" if "," not in ctx.head else "MORE THAN ONE HEAD"],
        ["IQ-003", "Python and key packages in the installed image", "to record at installation (`python --version`; `pip freeze` of the image)", "to record"],
        ["IQ-004", "PostgreSQL version", "to record at installation (`SELECT version()`)", "to record"],
        ["IQ-005", "Configuration check (`config_check`)", "to record at deploy", "to record"],
        ["IQ-006", "Deploy gate (`scripts/deploy_gate.py --release`)", "to record at deploy", "to record"],
        ["IQ-007", "Clock check (`scripts/clock_check.py`)", json.dumps(clock.get("status") or clock.get("result") or "not supplied"), "recorded" if clock else "to record"],
        ["IQ-008", "Release checks JSON", f"passed = {checks.get('passed')}, full suite = {checks.get('full_suite')}" if checks else "not supplied", "recorded" if checks else "to record"],
        ["IQ-009", "Node of the front-end build image", "to record at installation (`node --version`)", "to record"],
        ["IQ-010", "Rule register at this commit (section 3)", f"{len(rules)} versions: {data_held} data-held (content hash recomputed from the file), {len(rules) - data_held} code-held (code hash pinned, `tests/test_rule_pins_unit.py`)",
         "all match" if rules and not wrong else f"MISMATCH: {' '.join(wrong)}" if wrong else "NONE FOUND"],
    ]  # fmt: skip
    test_env = [
        ["IQ-T01", "Commit and tree of the test run (JUnit)", f"`{meta.get('commit') or 'not recorded'}`, tree {meta.get('tree') or 'not recorded'}",
         "recorded" if meta.get("commit") else "to record"],
        ["IQ-T02", "Migration head of the test database", ctx.head, "to record (`alembic current` on the test database)"],
        ["IQ-T03", "Python of the test run", meta.get("python") or "not recorded", "recorded" if meta.get("python") else "to record"],
        ["IQ-T04", "Key packages of the test run (pytest included)", meta.get("packages") or "not recorded", "recorded" if meta.get("packages") else "to record"],
        ["IQ-T05", "Node of the test run (release checks)", tools.get("node") or "not recorded", "recorded" if tools.get("node") else "to record"],
        ["IQ-T06", "PostgreSQL of the test database", "to record (`SELECT version()` on the test database)", "to record"],
        ["IQ-T07", "Test database built from the tagged commit", "to record (`scripts/prepare_test_environment.py --recreate`)", "to record"],
        ["IQ-T08", "Requirement marker hook (`validation/pytest_requirements.py`)", f"hook_version {meta.get('hook_version') or 'not recorded'}",
         "recorded" if meta.get("hook_version") else "to record"],
        ["IQ-T09", "Validation-pack generator", "; ".join(f"`{k}` SHA-256 {v}" for k, v in sorted((env.get("generator") or {}).items())) or "not recorded",
         "recorded" if env.get("generator") else "to record"],
    ]  # fmt: skip
    done = {r["step"].strip(): r for r in s.executed if r.get("step", "").startswith("IQ-")}
    keys = ("executed_by", "date_utc", "result", "evidence_id")
    rows = [row + [done.get(row[0], {}).get(k, "") for k in keys] for row in rows]
    test_env = [row + [done.get(row[0], {}).get(k, "") for k in keys] for row in test_env]
    header = ["Step", "Check", "Recorded", "Result", "Executed by", "Date (UTC)", "Executed result", "Evidence ID"]
    register = [[r.get("code"), r.get("version", ""), f"{r.get('effective_from', '')} to {r.get('effective_to', '')}",
                 r.get("held_as", ""), f"`{r.get('hash', '')}`",
                 "code-held: pin test" if r.get("matches") is None else "yes" if r.get("matches") else "NO",
                 f"`{r.get('file_sha256', '')}`"]
                for r in rules]  # fmt: skip
    return (
        _header(ctx, "MDX-VAL-006", "Installation qualification record", SYSTEM_OWNER, QUALITY_APPROVER)
        + _sources_section(ctx)
        + '## 2. Installation checks\n\nA check marked "to record" is executed at installation and written as a row of '
        "`executed-results.csv` (step IQ-nnn) with its evidence file; the next generation fills it in here, never by hand. "
        "The IQ record's approver does not execute it (VMP-R02).\n\n"
        + _table(header, rows)
        + "\n## 3. Rule register at this commit\n\nEvery rule version in `backend/app/rule_register/data/`, with its "
        "SHA-256 (LF line endings, as stored in git). A data-held version shows its content hash and whether it matches "
        "the content (recomputed by the generator); a code-held version shows its pinned code hash (or its "
        "implementation), which `tests/test_rule_pins_unit.py` recomputes from the code.\n\n"
        + _table(
            ["Code", "Version", "In force", "Held as", "Content or code hash", "Content hash matches", "File SHA-256"],
            register,
        )
        + "\n## 4. Test environment (VMP-R45, owner decision B6b-D16)\n\nUntil staging exists the controlled local "
        "environment is qualified here: the values come from the JUnit of this release (the marker hook records the "
        'commit, the tree, Python and the key packages) and the release-checks JSON; a row marked "to record" is '
        "executed as step IQ-Tnn of `executed-results.csv`.\n\n" + _table(header, test_env)
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


def author_problems(author: str) -> list[str]:
    """A generated document names the person who ran the generator (ALCOA: attributable), never a fixed name."""
    if person(author):
        return []
    return [
        f"the generator run is attributed to '{author or '(nobody)'}', not a named person: pass --author with one of "
        f"{', '.join(PEOPLE)}"
    ]


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
        f"approved (`signatures.csv`, content SHA-256 `{sha256}`)"
        if approved
        else f"NOT APPROVED (dry run only; SHA-256 `{sha256}`)"
    )
    done = {r.get("scenario_id", "").strip(): r for r in s.executed if r.get("step", "").startswith("OQ-")}
    keys = ("executed_by", "date_utc", "result", "evidence_id")
    steps = [scripted[0][:3] + scripted[0][5:6] + RESULT_HEADER] + [
        r[:3] + r[5:6] + [done.get(r[2], {}).get(k, "") for k in keys] for r in scripted[1:]
    ]
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
        + _pq_section(s)
        + "## 9. Independence statement\n\nReviewed by the quality approver, who did not write the code or the tests: "
        "name ________ date ________\n\n" + "## 10. Audit-finding self-check\n\n"
        "- URS not written by engineering alone: ____\n- QA reviewed independently: ____\n"
        f"- PQ executed by users: {_pq_self_check(s)}\n"
        "- Periodic-review owner named: ____\n- Security assessment (MDX-B10-006) linked into the risk assessment: ____\n"
        "- Every requirement traced to a test: ____\n\n" + f"## 11. Conclusion\n\n{conclusion}\n"
    )


def _pq_self_check(s: Sources) -> str:
    summary = pq_summary(s)
    if "steps" not in summary:
        return "no (no pq-record.csv for this release)"
    return f"{'yes' if summary['accepted'] else 'not complete'} ({summary['passed']} of {summary['steps']} steps PASS)"


def _pq_section(s: Sources) -> str:
    summary = pq_summary(s)
    if "steps" not in summary:
        return f"## 8d. MDARIX PQ (MDX-VAL-008)\n\n{summary['record']}.\n\n"
    rows = [
        ["Steps in MDX-VAL-008", summary["steps"]], ["Rows in pq-record.csv", summary["rows"]],
        ["Steps passed (latest row PASS)", summary["passed"]],
        ["Steps not passed", " ".join(summary["not_passed"]) or "none"], ["Steps without a row", " ".join(summary["missing"]) or "none"],
        ["Acceptance (MDX-VAL-008 section 4)", "every step PASS" if summary["accepted"] else "NOT MET"],
    ]  # fmt: skip
    return "## 8d. MDARIX PQ (MDX-VAL-008)\n\n" + _table(["PQ", "Value"], rows) + "\n"


def _vsr_required(rows: list[dict]) -> str:
    """The VSR content MDX-VAL-001 asks for: VMP-R96 counts, VMP-R46 label, VMP-R82/R84 people, VMP-R15 references."""
    class_a = [r for r in rows if r["class"] == "A"]
    tagged = sum(r["status"] == "Verified" and r["coverage"] == "covered" for r in class_a)
    scripted = sum(r["status"] == "Verified" and r["coverage"] == "scripted OQ" for r in class_a)
    return (
        "## 8a. Class-A verification (VMP-R96)\n\n"
        + _table(
            [
                "Verified by tagged tests (this JUnit)",
                "Verified by executed scripted OQ steps (MDX-VAL-007-R)",
                "Not verified",
            ],
            [[tagged, f"{scripted} (from executed-results.csv)", len(class_a) - tagged - scripted]],
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
        + _table(["#", "Criterion", "Met (yes / no / accepted)", "Initialled by (Srinivas T.)"], CRITERIA_ROWS)
        + "\n## 3. Signature\n\nName: ____________ Role: quality approver Date (UTC): ____________\n\n"
        "Meaning: I approve this release for production after the checks listed.\n"
        + f"\n## 4. Post-deploy record (after the signature; RA-T07)\n\nCommand: `python scripts/deploy_gate.py --release "
        f"v{ctx.release} --require worker,scheduler` on production. A failure starts the rollback (criterion 8).\n\n"
        "Result: ________ Time (UTC): ________ Run by (system owner): ________\n"
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
    if with_results:  # the result columns come from executed-results.csv, as in MDX-VAL-007-R (never blank by design)
        done = {r.get("scenario_id", "").strip(): r for r in s.executed if r.get("step", "").startswith("OQ-")}
        keys = ("executed_by", "date_utc", "result", "evidence_id")
        steps = [scripted[0] + RESULT_HEADER] + [
            row + [done.get(row[2], {}).get(k, "") or ("NOT RUN" if k == "result" else "") for k in keys]
            for row in scripted[1:]
        ]
        files["oq-log.xlsx"] = xlsx_write.write({"Scripted OQ (class A)": steps, "Automated (tagged)": log})
    if s.evidence:  # VMP-R86: each evidence file with its SHA-256, in the manifest of the release
        index = [["evidence_id", "file", "sha256"]]
        index += [[eid, f["file"], f["sha256"]] for eid, found in sorted(s.evidence.items()) for f in found]
        files["evidence-index.csv"] = _csv(index)
    if s.pq_raw is not None:
        files["pq-record.csv"] = s.pq_raw
    dev_rows = [DEVIATION_COLUMNS] + [[d.get(c, "") for c in DEVIATION_COLUMNS] for d in devs]
    files["deviations.csv"] = _csv(dev_rows)
    files["deviations.xlsx"] = xlsx_write.write({"Deviations": dev_rows})
    files["g13.json"] = (json.dumps(figures, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if s.release_checks is not None:
        files["release-checks.json"] = s.release_checks_raw or (json.dumps(s.release_checks, indent=2) + "\n").encode()
    if s.junit_raw is not None:
        files["junit.xml"] = s.junit_raw
    if s.executed_raw is not None:
        files["executed-results.csv"] = s.executed_raw
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
