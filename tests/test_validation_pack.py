"""B6b B4/B5: the requirement markers in JUnit and the validation-pack generator (scenarios B6-47 to B6-52, B6-57,
B6-58), on a small golden example; no database."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.trial.xlsx import read_rows
from scripts import validation_pack
from validation import pack, xlsx_write

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]

REQUIREMENTS = """req_id,revision,text,class,spec_ref,risk_ids,scenario_ids,negative_scenarios,tests
REQ-T-001,A,The thing shall refuse a bad input.,A,spec 1,RSK-001,AA-01 AA-02,AA-02,tests/test_a.py
REQ-T-002,A,The other thing shall show counts.,B,spec 2,RSK-002,AA-03,,
"""
REGISTER = """# register

| ID | Scenario | Expected behaviour | Item | Status | Notes |
|---|---|---|---|---|---|
| AA-01 | Good input | Saved | X | PASS | run 1, tests/test_a.py |
| AA-02 | Bad input | Refused | X | NOT RUN | |
| AA-03 | Counts | Equal | X | NOT RUN | |
"""
OQ_EXPECTED = """scenario_id,revision,input,expected_result,checked_by,source,confirmed_by
AA-01,A,Submit a good input,200; saved,tests/test_a.py::test_saved,requirement,Srinivas 2026-11-13
AA-02,A,Submit a bad input,422 BAD_INPUT; nothing saved,tests/test_a.py::test_refused,requirement,Srinivas 2026-11-13
"""
JUNIT = """<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">
<testcase classname="tests.test_a" name="test_refused" time="0.10"><properties>
<property name="requirement" value="AA-02"/></properties></testcase>
<testcase classname="tests.test_a" name="test_saved" time="0.20"><properties>
<property name="requirement" value="AA-01"/></properties></testcase>
<testcase classname="tests.test_b" name="test_untagged" time="0.05"/>
</testsuite></testsuites>"""


RELEASE_CHECKS = (
    '{"release": "9.9.9", "commit": "abc12345", "dry_run": false, "full_suite": true, "passed": true,'
    ' "tools": {"python": "Python 3.x", "node": "v20"}, "steps": [{"step": "pytest", "result": "pass"}]}'
)


def _approve_protocol(root: Path, release: str = "9.9.9") -> str:
    """Signs the OQ protocol the way the quality approver does (O20): its signatures.csv row names its SHA-256."""
    docs = root / "docs" / "validation"
    sources = pack.Sources(pack.read_requirements(docs / "requirements.csv"), pack.read_register(docs / "scenario-register.md"),
                           oq_expected=pack.read_oq_expected(docs / "oq-expected-results.csv"))  # fmt: skip
    sha = pack.protocol_sha256(pack.oq_tables(sources)[0])
    with open(docs / "signatures.csv", "a", encoding="utf-8") as signatures:
        signatures.write(f"{pack.PROTOCOL_ID},{release},S. T.,quality approver,approval,2026-11-12,p.pdf,{sha}\n")
    return sha


def _root(
    tmp_path: Path, *, requirements=REQUIREMENTS, register=REGISTER, junit=JUNIT, deviations="", approve=True
) -> Path:
    docs = tmp_path / "docs" / "validation"
    docs.mkdir(parents=True)
    (docs / "requirements.csv").write_text(requirements, encoding="utf-8")
    (docs / "scenario-register.md").write_text(register, encoding="utf-8")
    (docs / "deviation-log.csv").write_text(",".join(pack.DEVIATION_COLUMNS) + "\n" + deviations, encoding="utf-8")
    (docs / "signatures.csv").write_text("document_id,version,signer,role,meaning,date_utc,pdf_path,sha256\n")
    (tmp_path / "VERSION").write_text("9.9.9\n")
    versions = tmp_path / "infrastructure" / "database" / "migrations" / "versions"
    versions.mkdir(parents=True)
    (versions / "a.py").write_text('revision = "r1"\ndown_revision = None\n')
    (versions / "b.py").write_text('revision = "r2"\ndown_revision = "r1"\n')
    (tmp_path / "junit.xml").write_text(junit, encoding="utf-8")
    (tmp_path / "release-checks.json").write_text(RELEASE_CHECKS, encoding="utf-8")
    (docs / "oq-expected-results.csv").write_text(OQ_EXPECTED, encoding="utf-8")
    if approve:
        _approve_protocol(tmp_path)
    return tmp_path


def _run(root: Path, *extra: str) -> int:
    args = ["--root", str(root), "--release", "9.9.9", "--junit", str(root / "junit.xml")]
    args += ["--release-checks", str(root / "release-checks.json")]
    return validation_pack.main(args + ["--commit", "abc12345", "--date", "2026-11-12", *extra])


@pytest.mark.requirement("B6-47")
def test_requirement_marker_reaches_the_junit_xml(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers =\n    requirement(id): scenario\n")
    (tmp_path / "test_tagged.py").write_text(
        'import pytest\n\npytestmark = pytest.mark.requirement("IN-09")\n\n'
        '@pytest.mark.requirement("IN-01", "IN-02")\ndef test_one():\n    pass\n'
    )
    junit = tmp_path / "junit.xml"
    done = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path / "test_tagged.py"), "-c", str(tmp_path / "pytest.ini"),
         "-p", "validation.pytest_requirements", "-p", "no:cacheprovider", "-q", f"--junitxml={junit}"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    assert done.returncode == 0, done.stdout + done.stderr
    read = pack.read_junit(junit)
    assert [t["scenarios"] for t in read] == [["IN-01", "IN-02"]] and [t["file_scenarios"] for t in read] == [["IN-09"]]
    # The wiring in tests/conftest.py: a test of this file, run through the real conftest, carries its marker.
    real = tmp_path / "real.xml"
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_validation_pack.py::test_xlsx_reads_back_equal_and_formula_stays_text",
         "-p", "no:cacheprovider", "-q", f"--junitxml={real}"],
        cwd=ROOT, capture_output=True, text=True, timeout=300, env={**os.environ, "MDARIX_TEST_NO_DATABASE": "1"},
    )  # fmt: skip
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    assert [t["scenarios"] for t in pack.read_junit(real)] == [["B6-48"]]


@pytest.mark.requirement("B6-48")
def test_xlsx_reads_back_equal_and_formula_stays_text():
    rows = [["ID", "Value"], ["=HYPERLINK(1)", 3], ["a<b & c", "x"]]
    raw = xlsx_write.write({"Sheet one": rows, "Two": [["only"]]})
    assert read_rows(raw) == [["ID", "Value"], ["=HYPERLINK(1)", "3"], ["a<b & c", "x"]]
    assert read_rows(raw, sheet="Two") == [["only"]]
    assert b"<f>" not in raw  # no formula part anywhere (the sheet XML is deflated; the reader proves text)


@pytest.mark.requirement("B6-49")
def test_every_traceability_check_fails_and_all_are_listed(tmp_path, capsys):
    requirements = REQUIREMENTS + (
        "REQ-T-003,A,Shall have no negative.,A,spec,RSK-003,AA-01,,\n"
        "REQ-T-004,A,Shall have no scenario.,A,spec,RSK-004,,,\n"
        "REQ-T-005,A,Shall cite a missing one.,A,spec,RSK-005,AA-99,AA-99,\n"
    )
    register = REGISTER.replace("| AA-03 | Counts | Equal | X | NOT RUN | |", "| AA-03 | Counts | Equal | X | PASS | |")
    junit = JUNIT.replace('value="AA-01"', 'value="ZZ-01"')
    root = _root(tmp_path, requirements=requirements, register=register, junit=junit)
    assert _run(root) == 1
    said = capsys.readouterr().err
    for expected in (
        "REQ-T-003: class A without a negative scenario",
        "REQ-T-004: no scenario",
        "REQ-T-005: scenario AA-99 is not in the register",
        "AA-03: PASS without evidence",
        "marker names unknown scenario ZZ-01",
    ):
        assert expected in said
    assert not (root / "docs" / "validation" / "releases").exists()  # nothing written outside a dry run


@pytest.mark.requirement("B6-50")
def test_signed_release_folder_is_never_overwritten(tmp_path, capsys):
    root = _root(tmp_path)
    folder = root / "docs" / "validation" / "releases" / "9.9.9"
    folder.mkdir(parents=True)
    (folder / "MDX-VAL-012-release-approval-signed.pdf").write_bytes(b"%PDF signed")
    assert _run(root) == 2
    assert "REFUSED" in capsys.readouterr().err
    assert [p.name for p in folder.iterdir()] == ["MDX-VAL-012-release-approval-signed.pdf"]
    (folder / "MDX-VAL-012-release-approval-signed.pdf").unlink()
    with open(root / "docs" / "validation" / "signatures.csv", "a") as signatures:
        signatures.write("MDX-VAL-012-9.9.9,9.9.9,S. T.,quality approver,approval,2026-11-12,x.pdf,00\n")
    assert _run(root) == 2


@pytest.mark.requirement("B6-51")
def test_same_inputs_give_byte_identical_files(tmp_path):
    root = _root(tmp_path)
    assert _run(root, "--out", str(tmp_path / "one")) == 0
    assert _run(root, "--out", str(tmp_path / "two")) == 0
    one = {p.name: p.read_bytes() for p in (tmp_path / "one").iterdir()}
    assert one == {p.name: p.read_bytes() for p in (tmp_path / "two").iterdir()}
    assert {"MDX-VAL-004-URS.docx", "rtm.xlsx", "oq-log.xlsx", "MDX-VAL-011-VSR.pdf", "manifest.json"} <= set(one)


@pytest.mark.requirement("B6-52")
def test_rtm_lists_every_class_a_requirement_as_covered_or_not_covered(tmp_path):
    root = _root(tmp_path)
    assert _run(root, "--out", str(tmp_path / "out")) == 0
    rows = read_rows((tmp_path / "out" / "rtm.xlsx").read_bytes())
    header, body = rows[0], {r[0]: dict(zip(rows[0], r)) for r in rows[1:]}
    assert header[0] == "req_id" and set(body) == {"REQ-T-001", "REQ-T-002"}
    assert body["REQ-T-001"]["coverage"] == "covered" and body["REQ-T-001"]["status"] == "Verified"
    assert body["REQ-T-001"]["tagged_tests"] == "2"
    assert body["REQ-T-002"]["coverage"] == "NOT COVERED" and body["REQ-T-002"]["status"] == "Not verified"
    # The real requirements: every class-A REQ has an RTM row, covered or NOT COVERED, never missing.
    real = pack.Sources(
        pack.read_requirements(ROOT / "docs/validation/requirements.csv"),
        pack.read_register(ROOT / "docs/validation/scenario-register.md"),
    )
    real_rows = {r["req_id"]: r for r in pack.rtm(real)}
    class_a = [r["req_id"] for r in real.requirements if r["class"] == "A"]
    assert class_a and set(real_rows) == {r["req_id"] for r in real.requirements}
    assert all(real_rows[r]["coverage"] == "NOT COVERED" and real_rows[r]["status"] != "Verified" for r in class_a)
    # A register FAIL makes the requirement Failed even when its tagged tests pass.
    failing = pack.Sources(pack.read_requirements(root / "docs/validation/requirements.csv"),
                           pack.read_register(root / "docs/validation/scenario-register.md"),
                           pack.read_junit(root / "junit.xml"))  # fmt: skip
    failing.scenarios["AA-01"]["status"] = "FAIL"
    assert {r["req_id"]: r["status"] for r in pack.rtm(failing)}["REQ-T-001"] == "Failed"


def test_golden_figures_and_documents(tmp_path, capsys):
    root = _root(tmp_path)
    assert _run(root, "--out", str(tmp_path / "out")) == 0
    out = tmp_path / "out"
    figures = __import__("json").loads((out / "g13.json").read_text())
    assert figures["coverage"] == {"A": "100.0% (1/1)", "B": "0.0% (0/1)", "C": "no data (0/0)"}
    assert figures["negative_coverage_class_a"] == "100.0% (1/1)"
    assert figures["execution_progress"] == "66.7% (2/3)"
    assert figures["pass_rate"] == "100.0% (2/2)"
    assert figures["pass_rate_all_tests"] == "100.0% (3/3), tests in this JUnit (full suite)"
    assert figures["defect_leakage"].startswith("no source yet")
    assert "WARNING: release 9.9.9" not in capsys.readouterr().err  # same as VERSION
    vsr = (out / "MDX-VAL-011-VSR.md").read_text(encoding="utf-8")
    assert "fit for MDARIX's intended use as validated" in vsr and "DEVELOPMENT RESULTS" not in vsr
    assert "| IQ-002 | Migration head (one head) | r2 | one head |" in (out / "MDX-VAL-006-IQ.md").read_text("utf-8")
    assert "OQ-001" in (out / "MDX-VAL-007-R-OQ-results.md").read_text("utf-8")
    assert "422 BAD_INPUT; nothing saved" in (out / "MDX-VAL-007-P-OQ-protocol.md").read_text("utf-8")
    record = __import__("json").loads((out / "MDX-VAL-012-release-approval.json").read_text())
    assert record["risk_acceptances"] == [] and record["basis"] == pack.INTERIM_BASIS  # O13 interim template
    assert record["document_id"] == "MDX-VAL-012-9.9.9" and record["template"] == "MDX-VAL-012"
    assert (out / "junit.xml").read_bytes() == (root / "junit.xml").read_bytes()
    assert record["junit_sha256"] == __import__("hashlib").sha256((root / "junit.xml").read_bytes()).hexdigest()
    assert "## 8a. Class-A verification (VMP-R96)" in vsr and "| 1 | ____" in vsr and "(VMP-R15)" in vsr
    assert "| Reviewer | Independent CSV consultant" in vsr and "Change history" in vsr
    assert "| 9 | After the deploy: deploy_gate.py passed" in (out / "MDX-VAL-012-release-approval.md").read_text(
        "utf-8"
    )


def test_a_failed_class_a_test_always_blocks_the_release(tmp_path, capsys):
    """O18: a failed class-A test is a check failure (no risk acceptance covers it); nothing is written."""
    junit = JUNIT.replace('time="0.10"><properties>', 'time="0.10"><failure message="x"/><properties>')
    root = _root(tmp_path, junit=junit)
    assert _run(root, "--out", str(tmp_path / "out")) == 1
    assert (
        "REQ-T-001: class-A scenario AA-02 FAIL; a failed class-A test blocks the release (VMP-R50)"
        in capsys.readouterr().err
    )
    assert not (tmp_path / "out").exists()


def test_no_oq_results_without_an_approved_protocol(tmp_path, capsys):
    """O20: the protocol is written for approval; without its signatures.csv row (same SHA-256) no OQ results, except a
    dry run; a changed expected result needs a new approval; a class-A scenario needs a confirmed concrete result."""
    root = _root(tmp_path, approve=False)
    assert _run(root, "--oq-protocol", "--out", str(tmp_path / "p")) == 0
    sha = capsys.readouterr().out.split("SHA-256 ")[1].split(".")[0]
    assert {p.name for p in (tmp_path / "p").iterdir()} >= {"MDX-VAL-007-P-OQ-protocol.pdf", "oq-protocol.csv"}
    assert not any("results" in p.name or p.name == "oq-log.xlsx" for p in (tmp_path / "p").iterdir())
    assert _run(root, "--out", str(tmp_path / "out")) == 1
    assert f"is not approved: no signatures.csv row with SHA-256 {sha}" in capsys.readouterr().err
    assert _run(root, "--dry-run", "--out", str(tmp_path / "dry")) == 1
    assert "NOT APPROVED (dry run only" in (tmp_path / "dry" / "MDX-VAL-007-R-OQ-results.md").read_text("utf-8")
    assert _approve_protocol(root) == sha
    assert _run(root, "--out", str(tmp_path / "out")) == 0
    assert f"approved (`signatures.csv`, SHA-256 `{sha}`)" in (
        tmp_path / "out" / "MDX-VAL-007-R-OQ-results.md"
    ).read_text("utf-8")
    expected = root / "docs" / "validation" / "oq-expected-results.csv"
    confirmed = ",requirement,Srinivas 2026-11-13\n"
    expected.write_text(
        OQ_EXPECTED.replace("422 BAD_INPUT", "409 BAD_INPUT")
        .replace(confirmed, ",code,Srinivas 2026-11-13\n", 1)
        .replace(confirmed, ",requirement,\n", 1)
    )
    assert _run(root, "--out", str(tmp_path / "out2")) == 1
    said = capsys.readouterr().err
    assert "is not approved" in said
    assert "AA-01: OQ expected result not yet approved (source 'code', re-derive it from its requirement)" in said
    assert "AA-02: OQ expected result not yet approved (not confirmed by the owner)" in said
    expected.write_text(OQ_EXPECTED.splitlines()[0] + "\n")
    assert _run(root, "--dry-run", "--out", str(tmp_path / "dry2")) == 1
    assert "AA-02: class-A scenario without a concrete OQ expected result" in capsys.readouterr().err


def test_file_level_markers_never_verify_a_class_a_requirement(tmp_path):
    """O24: for class A only a test's own marker counts; a file-level marker shows "file-level only, not
    verification". For class B a file-level marker still counts."""
    junit = JUNIT.replace('name="requirement" value="AA-02"', 'name="requirement_file" value="AA-02"')
    junit = junit.replace('<testcase classname="tests.test_b" name="test_untagged" time="0.05"/>',
                          '<testcase classname="tests.test_b" name="test_counts" time="0.05"><properties>'
                          '<property name="requirement_file" value="AA-03"/></properties></testcase>')  # fmt: skip
    root = _root(tmp_path, junit=junit)
    assert _run(root, "--dry-run", "--out", str(tmp_path / "out")) == 0  # AA-02 now NOT RUN (no check fails)
    rows = read_rows((tmp_path / "out" / "rtm.xlsx").read_bytes())
    body = {r[0]: dict(zip(rows[0], r)) for r in rows[1:]}
    assert body["REQ-T-001"]["status"] == "Not verified" and body["REQ-T-001"]["scenarios_passed"] == "1/2"
    assert body["REQ-T-002"]["coverage"] == "covered" and body["REQ-T-002"]["status"] == "Verified"
    only_file = junit.replace('name="requirement" value="AA-01"', 'name="requirement_file" value="AA-01"')
    (root / "junit.xml").write_text(only_file, encoding="utf-8")
    assert _run(root, "--dry-run", "--out", str(tmp_path / "out")) == 1
    rows = read_rows((tmp_path / "out" / "rtm.xlsx").read_bytes())
    body = {r[0]: dict(zip(rows[0], r)) for r in rows[1:]}
    assert body["REQ-T-001"]["coverage"] == "file-level only, not verification"


def test_interim_template_and_generator_list_the_same_criteria():
    """O13: MDX-VAL-012 template section 4 and the generated record print the same nine criteria."""
    text = (ROOT / "docs" / "validation" / "MDX-VAL-012_RELEASE_APPROVAL_TEMPLATE.md").read_text(encoding="utf-8")
    section = text.split("## 4. Criteria")[1].split("\n## ")[0]
    lines = [line for line in section.splitlines() if line[:2] == "| " and line[2].isdigit()]
    rows = [line.split(" | ", 1)[1].rstrip(" |").replace("`", "") for line in lines]
    assert rows == list(pack.INTERIM_CRITERIA)


def test_release_identity_warning_and_dry_run_banner(tmp_path, capsys):
    root = _root(tmp_path, requirements=REQUIREMENTS + "REQ-T-009,A,Shall fail.,A,spec,RSK-9,,,\n")
    args = ["--root", str(root), "--release", "1.0.0", "--junit", str(root / "junit.xml"), "--date", "2026-11-12"]
    assert validation_pack.main(args + ["--dry-run", "--out", str(tmp_path / "dry")]) == 1
    err = capsys.readouterr().err
    assert "WARNING: release 1.0.0 differs from VERSION 9.9.9" in err and "REQ-T-009: no scenario" in err
    for name in ("MDX-VAL-004-URS.md", "MDX-VAL-011-VSR.md", "MDX-VAL-012-release-approval.md"):
        assert "DEVELOPMENT RESULTS, NOT VALIDATION EVIDENCE" in (tmp_path / "dry" / name).read_text("utf-8")
    assert "REQ-T-009: no scenario" in (tmp_path / "dry" / "checks.txt").read_text("utf-8")


def test_release_identity_mismatch_is_refused_outside_a_dry_run(tmp_path, capsys):
    """O16: outside a dry run a release that differs from VERSION writes nothing; the same release as VERSION is allowed."""
    root = _root(tmp_path)
    args = ["--root", str(root), "--release", "1.0.0", "--junit", str(root / "junit.xml")]
    args += ["--release-checks", str(root / "release-checks.json"), "--commit", "abc12345", "--date", "2026-11-12"]
    assert validation_pack.main(args + ["--out", str(tmp_path / "out")]) == 1
    assert "REFUSED: release 1.0.0 differs from VERSION 9.9.9" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()
    (root / "VERSION").write_text("1.0.0\n")
    _approve_protocol(root, "1.0.0")
    assert validation_pack.main(args + ["--out", str(tmp_path / "out")]) == 0
    assert "differs from VERSION" not in capsys.readouterr().err


DEV = "DEV-9.9.9-{n},2026-11-10T09:00:00Z,SH,OQ,AA-02,REQ-T-001,refused,saved,2026-11-10T09:05:00Z,none,{risk},{cls},,,{retest},{result},no,,{approver},{closed},{status}\n"


@pytest.mark.requirement("B6-57")
def test_deviation_cannot_close_without_retest_and_approver(tmp_path, capsys):
    deviations = DEV.format(
        n="001",
        risk="low",
        cls="minor",
        retest="",
        result="",
        approver="",
        closed="2026-11-11T09:00:00Z",
        status="Closed",
    )
    deviations += DEV.format(n="002", risk="low", cls="minor", retest="OQ-1", result="PASS", approver="SR", closed="2026-11-12T09:00:00Z", status="Closed")  # fmt: skip
    assert _run(_root(tmp_path, deviations=deviations)) == 1
    err = capsys.readouterr().err
    assert "DEV-9.9.9-001: closed without a retest result" in err and "DEV-9.9.9-001: closed without an approver" in err
    assert "DEV-9.9.9-002" not in err
    wrong = DEV.format(n="003", risk="low", cls="minor", retest="", result="", approver="", closed="", status="open")
    assert _run(_root(tmp_path / "found", deviations=wrong.replace(",SH,OQ,", ",SH,document review,"))) == 1
    assert "DEV-9.9.9-003: found_in 'document review' is not one of IQ, OQ, PQ" in capsys.readouterr().err


@pytest.mark.requirement("B6-58")
def test_no_release_approval_record_while_a_critical_deviation_is_open(tmp_path, capsys):
    deviations = DEV.format(n="001", risk="high", cls="critical", retest="", result="", approver="", closed="", status="Open")  # fmt: skip
    root = _root(tmp_path, deviations=deviations)
    assert _run(root) == 1
    assert "critical deviation open; no release approval record" in capsys.readouterr().err
    assert _run(root, "--dry-run", "--out", str(tmp_path / "dry")) == 1
    names = {p.name for p in (tmp_path / "dry").iterdir()}
    assert "MDX-VAL-011-VSR.md" in names and not any(n.startswith("MDX-VAL-012") for n in names)
    figures = __import__("json").loads((tmp_path / "dry" / "g13.json").read_text())
    assert figures["open_deviations"] == {"by_classification": {"critical": 1}, "count": 1}


def test_stale_approval_record_is_removed_and_bom_log_still_read(tmp_path):
    root = _root(tmp_path)
    assert _run(root, "--out", str(tmp_path / "out")) == 0
    assert (tmp_path / "out" / "MDX-VAL-012-release-approval.json").exists()
    (tmp_path / "out" / "change-impact.md").write_text("kept")
    log = root / "docs" / "validation" / "deviation-log.csv"
    critical = DEV.format(n="001", risk="high", cls="critical", retest="", result="", approver="", closed="", status="open")  # fmt: skip
    log.write_bytes(b"\xef\xbb\xbf" + log.read_bytes() + critical.encode())  # saved by Excel: byte-order mark
    assert _run(root, "--dry-run", "--out", str(tmp_path / "out")) == 1
    names = {p.name for p in (tmp_path / "out").iterdir()}
    assert not any(n.startswith("MDX-VAL-012") for n in names) and "change-impact.md" in names
    log.write_text("dev_id,status\nDEV-9.9.9-001,open\n")
    with pytest.raises(ValueError):
        pack.read_deviations(log)


def test_release_pack_needs_full_suite_evidence_of_the_same_commit():
    good = {"commit": "abc12345", "dry_run": False, "full_suite": True, "passed": True, "steps": [{"result": "pass"}]}
    assert pack.release_check_problems(good, "abc12345", True) == []
    bad = {**good, "dry_run": True, "full_suite": False, "commit": "ffff0000", "steps": [{"result": "skipped"}]}
    said = " ".join(pack.release_check_problems(bad, "abc12345", False))
    for part in ("no JUnit", "dry run", "not a full-suite", "did not pass", "for commit ffff0000"):
        assert part in said
    assert pack.release_check_problems(None, "abc12345", True) == ["no release-checks JSON given"]


def test_signing_pdfs_hold_section_4_and_the_template_unsigned():
    """O19: MDX-VAL-000 section 4 and the MDX-VAL-012 template are produced for the owner's signature, unsigned."""
    from scripts import validation_signing_pdfs as signing

    text = signing.section_4((ROOT / "docs" / "validation" / "README.md").read_text(encoding="utf-8"))
    assert text.startswith("# MDX-VAL-000 section 4:") and "| O24 |" in text and "## 5. " not in text
    assert "I approve the owner decisions in this section as in force" in text
    assert signing.render(text, "MDX-VAL-000-section-4").startswith(b"%PDF")


def test_a_future_scenario_is_never_an_oq_step_or_verification(tmp_path):
    """Owner, 12 Nov 2026: a register row whose Notes start with "future:" (feature not built) stays out of the scripted
    OQ steps and the expected-result checks; the RTM lists it; a class-A REQ whose only negative is future is flagged."""
    register = REGISTER.replace("| AA-02 | Bad input | Refused | X | NOT RUN | |",
                                "| AA-02 | Bad input | Refused | X | NOT RUN | future: B4b (refusal); not verification |")  # fmt: skip
    root = _root(tmp_path, register=register, approve=False)
    docs = root / "docs" / "validation"
    (docs / "oq-expected-results.csv").write_text(
        OQ_EXPECTED.splitlines()[0] + "\n" + OQ_EXPECTED.splitlines()[1] + "\n"
    )
    sources = pack.Sources(pack.read_requirements(docs / "requirements.csv"), pack.read_register(docs / "scenario-register.md"),
                           oq_expected=pack.read_oq_expected(docs / "oq-expected-results.csv"))  # fmt: skip
    assert [row[2] for row in pack.oq_tables(sources)[0][1:]] == ["AA-01"]
    problems = pack.check(sources, "9.9.9")
    assert not any("AA-02" in p and "OQ expected" in p for p in problems)
    assert "REQ-T-001: class A whose negative scenarios are all future (not built)" in problems
    assert {r["req_id"]: r["future"] for r in pack.rtm(sources)} == {"REQ-T-001": "AA-02", "REQ-T-002": ""}
