"""The validation evidence screen (E2): each requirement, the tests that cover it and their last recorded result.

The requirement and test mapping is read from the repository (``docs/validation/requirements.csv`` with its named
test files, and the ``requirement(<scenario>)`` markers a JUnit run carries, B6b B4). Results come only from a
stored test run (a JUnit XML a platform administrator uploaded); without one every requirement says "No run
recorded". The release validation pack is the B6b generator's dry run (``validation/pack.py``), so every document in
it carries the "development results, not validation evidence" watermark: it supports a customer's own validation, it
never states that a release is validated.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from validation import pack

ROOT = Path(__file__).resolve().parents[1]
NO_RUN = "No run recorded"
MAX_JUNIT_BYTES = 20 * 1024 * 1024
# The regulatory framing of the screen and the pack, in the words and dates of docs/validation (MDX-B10-002 rows 2 and 3,
# MDX-VAL-001 R11): the QMSR date is stated there; the CSA guidance's title, date and status are marked "to confirm".
FRAMING = (
    "Risk-based: this evidence supports your Computer Software Assurance and validation of MDARIX for your intended "
    "use. In the US the QMSR (21 CFR Part 820 as amended, incorporating ISO 13485:2016 by reference) is effective "
    "2 Feb 2026. Aligned with a risk-based assurance approach (FDA Computer Software Assurance guidance); confirm "
    "against current FDA guidance. MDARIX functionality alone does not establish compliance: your risk assessment, "
    "procedures and validation decide it."
)


def current_release(root: Path = ROOT) -> str:
    """The release this code is (the VERSION file), "" when there is none."""
    return (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").exists() else ""


def repo_sources(root: Path = ROOT) -> pack.Sources:
    """The B6b sources under version control, as ``scripts/validation_pack.py`` reads them, without a test run."""
    docs = root / "docs" / "validation"
    return pack.Sources(
        requirements=pack.read_requirements(docs / "requirements.csv"),
        scenarios=pack.read_register(docs / "scenario-register.md"),
        deviations=pack.read_deviations(docs / "deviation-log.csv"),
        oq_expected=pack.read_oq_expected(docs / "oq-expected-results.csv"),
        pq_steps=pack.read_pq_steps(docs / "MDX-VAL-008_PQ_PROTOCOL.md"),
        rule_versions=pack.read_rule_register(root / "backend" / "app" / "rule_register" / "data"),
        signatures=pack.read_signatures(docs / "signatures.csv"),
        registers=pack.read_registers(docs / "registers"),
    )


def parse_junit(raw: bytes) -> dict:
    """A pytest JUnit XML as a run record: the commit and tree it ran on, when, the totals and every test case.

    Raises ``ValueError`` for anything that is not a JUnit report. A DOCTYPE is refused outright, so no entity in an
    uploaded file is ever expanded."""
    if len(raw) > MAX_JUNIT_BYTES:
        raise ValueError("The file is larger than 20 MB.")
    if b"<!DOCTYPE" in raw.upper():
        raise ValueError("The file declares a DOCTYPE; a pytest JUnit report has none.")
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as error:
        raise ValueError(f"The file is not readable XML ({error}).") from error
    if root.tag not in ("testsuites", "testsuite"):
        raise ValueError("The file is not a JUnit test report (no testsuites element).")
    tests = pack.read_junit(io.BytesIO(raw))
    if not tests:
        raise ValueError("The report holds no test case.")
    meta = pack.read_junit_meta(io.BytesIO(raw))
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    ran_at = None
    if suite is not None and suite.get("timestamp"):
        try:
            ran_at = datetime.fromisoformat(suite.get("timestamp"))
        except ValueError:
            ran_at = None
    return {
        "commit": (meta.get("commit") or "")[:40],
        "meta": meta,
        "ran_at": ran_at,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "tests": tests,
        "passed": sum(t["result"] == "pass" for t in tests),
        "failed": sum(t["result"] == "fail" for t in tests),
        "skipped": sum(t["result"] == "skipped" for t in tests),
    }


def _test_file(test_id: str) -> str:
    """``tests.test_x::test_y`` (JUnit classname) -> ``tests/test_x.py``; a class in the classname is dropped."""
    classname = test_id.split("::", 1)[0]
    parts = classname.split(".")
    while parts and not parts[-1].startswith("test_"):
        parts.pop()
    return "/".join(parts) + ".py" if parts else ""


def _result(results: list[str]) -> str:
    ran = [r for r in results if r != "skipped"]
    if not ran:
        return "Not in this run"
    return "Failed" if "fail" in ran else "Passed"


def evidence(sources: pack.Sources, run: dict | None) -> dict:
    """The screen: one row per requirement, the coverage counts and the run the results come from."""
    tests = run["tests"] if run else []
    sources.tests = tests
    by_file: dict[str, list[str]] = {}
    for test in tests:
        by_file.setdefault(_test_file(test["id"]), []).append(test["result"])
    rtm = {row["req_id"]: row for row in pack.rtm(sources)} if run else {}
    rows = []
    for req in sources.requirements:
        scenarios = req["scenario_ids"]
        linked = [t for t in pack._ran(sources) if any(pack._proves(sources, t, s) for s in scenarios)]
        named = [
            {
                "file": name,
                "result": _result(by_file.get(name, [])) if run else NO_RUN,
                "tests": len(by_file.get(name, [])),
            }
            for name in req["tests"]
        ]
        results = [t["result"] for t in linked] + [r for n in req["tests"] for r in by_file.get(n, [])]
        gap = not named and not linked
        rows.append({
            "req_id": req["req_id"], "class": req["class"], "text": req["text"],
            "named_tests": named,
            "linked_tests": [{"id": t["id"], "result": t["result"]} for t in linked],
            "scenarios_passed": rtm.get(req["req_id"], {}).get("scenarios_passed", f"0/{len(scenarios)}"),
            "result": "No test" if gap else _result(results) if run else NO_RUN,
            "gap": gap,
        })  # fmt: skip
    release = current_release()
    scripted, _ = pack.oq_tables(sources)
    approval = pack.protocol_approval(sources.signatures, release, pack.protocol_sha256(scripted), ROOT)
    expected = list(sources.oq_expected.values())
    return {
        "requirements": rows,
        "counts": {
            "requirements": len(rows),
            "with_tests": sum(not r["gap"] for r in rows),
            "gaps": sum(r["gap"] for r in rows),
            "passed": sum(r["result"] == "Passed" for r in rows),
            "failed": sum(r["result"] == "Failed" for r in rows),
            "not_run": sum(r["result"] in (NO_RUN, "Not in this run") for r in rows),
        },
        "protocol": {
            "id": pack.PROTOCOL_ID,
            "signed": approval.approved,
            "expected_results": len(expected),
            "expected_confirmed": sum(bool(r.get("confirmed_by", "").strip()) for r in expected),
        },
        "release": release,
        "framing": FRAMING,
    }


def release_pack(sources: pack.Sources, run: dict | None, release: str, date: str) -> bytes:
    """The B6b release validation pack as a ZIP, always a dry run (watermarked "development results, not validation
    evidence"), with every failing check listed in ``checks.txt``. Results come from the stored run only."""
    sources.tests = run["tests"] if run else []
    sources.junit_meta = run["meta"] if run else None
    commit = (run or {}).get("commit", "")[:8] or "no-run"
    scripted, _ = pack.oq_tables(sources)
    sources.oq_approval = pack.protocol_approval(sources.signatures, release, pack.protocol_sha256(scripted), ROOT)
    ctx = pack.Context(
        release=release, version_file=release, commit=commit, tag="", date=date, dry_run=True,
        head=pack.migration_head(ROOT / "infrastructure" / "database" / "migrations" / "versions"),
        problems=pack.check(sources, release)
        + pack.release_check_problems(None, commit, bool(sources.tests))
        + pack.junit_binding_problems(sources.junit_meta, commit)
        + sources.oq_approval.problems
        + ([] if sources.oq_approval.approved else [f"OQ protocol {pack.PROTOCOL_ID} {release} is not signed"]),
        oq_approved=sources.oq_approval.approved,
    )  # fmt: skip
    files = pack.build(ctx, sources)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            archive.writestr(f"validation-pack-{release}/{name}", raw)
        archive.writestr(f"validation-pack-{release}/READ-ME-FIRST.txt", (FRAMING + "\n").encode("utf-8"))
    return buffer.getvalue()
