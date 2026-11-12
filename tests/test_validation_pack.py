"""B6b B4/B5: the requirement markers in JUnit and the validation-pack generator (scenarios B6-47 to B6-52, B6-57,
B6-58), on a small golden example; no database."""

from __future__ import annotations

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
JUNIT = """<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">
<testcase classname="tests.test_a" name="test_refused" time="0.10"><properties>
<property name="requirement" value="AA-02"/></properties></testcase>
<testcase classname="tests.test_a" name="test_saved" time="0.20"><properties>
<property name="requirement" value="AA-01"/></properties></testcase>
<testcase classname="tests.test_b" name="test_untagged" time="0.05"/>
</testsuite></testsuites>"""


def _root(tmp_path: Path, *, requirements=REQUIREMENTS, register=REGISTER, junit=JUNIT, deviations="") -> Path:
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
    return tmp_path


def _run(root: Path, *extra: str) -> int:
    args = ["--root", str(root), "--release", "9.9.9", "--junit", str(root / "junit.xml")]
    return validation_pack.main(args + ["--commit", "abc12345", "--date", "2026-11-12", *extra])


@pytest.mark.requirement("B6-47")
def test_requirement_marker_reaches_the_junit_xml(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers =\n    requirement(id): scenario\n")
    (tmp_path / "test_tagged.py").write_text(
        'import pytest\n\n@pytest.mark.requirement("IN-01", "IN-02")\ndef test_one():\n    pass\n'
    )
    junit = tmp_path / "junit.xml"
    done = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path / "test_tagged.py"), "-c", str(tmp_path / "pytest.ini"),
         "-p", "validation.pytest_requirements", "-p", "no:cacheprovider", "-q", f"--junitxml={junit}"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    assert done.returncode == 0, done.stdout + done.stderr
    assert [t["scenarios"] for t in pack.read_junit(junit)] == [["IN-01", "IN-02"]]


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
        signatures.write("MDX-VAL-012,9.9.9,S. T.,quality approver,approval,2026-11-12,x.pdf,00\n")
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
    assert class_a and all(real_rows[r]["coverage"] in ("covered", "NOT COVERED") for r in class_a)


def test_golden_figures_and_documents(tmp_path, capsys):
    root = _root(tmp_path)
    assert _run(root, "--out", str(tmp_path / "out")) == 0
    out = tmp_path / "out"
    figures = __import__("json").loads((out / "g13.json").read_text())
    assert figures["coverage"] == {"A": "100.0% (1/1)", "B": "0.0% (0/1)", "C": "no data (0/0)"}
    assert figures["negative_coverage_class_a"] == "100.0% (1/1)"
    assert figures["execution_progress"] == "66.7% (2/3)"
    assert figures["pass_rate_tagged_tests"] == "100.0% (2/2)" and figures["pass_rate_all_tests"] == "100.0% (3/3)"
    assert figures["defect_leakage"].startswith("no source yet")
    assert "WARNING: release 9.9.9" not in capsys.readouterr().err  # same as VERSION
    vsr = (out / "MDX-VAL-011-VSR.md").read_text(encoding="utf-8")
    assert "fit for MDARIX's intended use as validated" in vsr and "DEVELOPMENT RESULTS" not in vsr
    assert "| IQ-002 | Migration head (one head) | r2 | one head |" in (out / "MDX-VAL-006-IQ.md").read_text("utf-8")
    assert "OQ-001" in (out / "MDX-VAL-007-OQ.md").read_text("utf-8")


def test_release_identity_warning_and_dry_run_banner(tmp_path, capsys):
    root = _root(tmp_path, requirements=REQUIREMENTS + "REQ-T-009,A,Shall fail.,A,spec,RSK-9,,,\n")
    args = ["--root", str(root), "--release", "1.0.0", "--junit", str(root / "junit.xml"), "--date", "2026-11-12"]
    assert validation_pack.main(args + ["--dry-run", "--out", str(tmp_path / "dry")]) == 1
    err = capsys.readouterr().err
    assert "WARNING: release 1.0.0 differs from VERSION 9.9.9" in err and "REQ-T-009: no scenario" in err
    for name in ("MDX-VAL-004-URS.md", "MDX-VAL-011-VSR.md", "MDX-VAL-012-release-approval.md"):
        assert "DEVELOPMENT RESULTS, NOT VALIDATION EVIDENCE" in (tmp_path / "dry" / name).read_text("utf-8")
    assert "REQ-T-009: no scenario" in (tmp_path / "dry" / "checks.txt").read_text("utf-8")


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
