"""The security-scan summary counts findings per severity, lists every High for a decision, and drops allow-listed
false positives only when the allow-list gives a reason."""

import json

import pytest

from scripts.security_scan_summary import build_summary, load_allowlist, main

pytestmark = pytest.mark.unit


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def reports(tmp_path):
    folder = tmp_path / "0.0.0-test"
    _write(
        folder / "bandit.json",
        {
            "results": [
                {
                    "issue_severity": "HIGH",
                    "issue_confidence": "HIGH",
                    "test_id": "B602",
                    "filename": "/src/backend/app/x.py",
                    "line_number": 7,
                    "issue_text": "shell=True",
                },
                {
                    "issue_severity": "LOW",
                    "issue_confidence": "HIGH",
                    "test_id": "B101",
                    "filename": "/src/backend/app/y.py",
                    "line_number": 3,
                    "issue_text": "assert used",
                },
            ]
        },
    )
    _write(
        folder / "zap" / "zap-baseline.json",
        {
            "site": [
                {
                    "@name": "http://scan-api:8000",
                    "alerts": [
                        {
                            "pluginid": "10038",
                            "riskcode": "2",
                            "name": "CSP header not set",
                            "instances": [{"uri": "/a"}],
                        },
                        {"pluginid": "40018", "riskcode": "3", "name": "SQL Injection", "instances": [{"uri": "/b"}]},
                    ],
                }
            ]
        },
    )
    (folder / "status.tsv").write_text("bandit\tran\t\nzap-baseline\tran\tpassive\n", encoding="utf-8")
    return folder


def test_counts_per_severity_and_every_high_gets_a_decision_line(reports):
    summary, record = build_summary(str(reports), [], "0.0.0-test")

    assert "| bandit | ran | 0 | 1 | 0 | 1 | 0 | 0 | 0 |" in summary
    assert "| zap-baseline | ran | 0 | 1 | 1 | 0 | 0 | 0 | 0 | passive |" in summary
    assert "| nuclei | not run | - |" in summary
    assert "`B602`" in summary and "backend/app/x.py:7" in summary
    assert "`40018`" in summary
    assert summary.count("Decision (fix now") == 2
    assert len(record) == 4


def test_allow_listed_finding_leaves_the_counts_and_the_decision_list(reports, tmp_path):
    allow = tmp_path / "allow.txt"
    allow.write_text(
        "# comment\nbandit | B602 | backend/app/x.py | command is a fixed list, reviewed 2026-11-14\n", encoding="utf-8"
    )

    summary, record = build_summary(str(reports), load_allowlist(str(allow)), "0.0.0-test")

    assert "| bandit | ran | 0 | 0 | 0 | 1 | 0 | 0 | 1 |" in summary
    assert "`B602`" not in summary
    assert [r["allow_listed"] for r in record if r["rule"] == "B602"] == [
        "command is a fixed list, reviewed 2026-11-14"
    ]


def test_allow_list_line_without_a_reason_is_refused(tmp_path):
    allow = tmp_path / "allow.txt"
    allow.write_text("bandit | B602 | * |\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="each filled in"):
        load_allowlist(str(allow))


def test_main_writes_summary_and_findings(reports):
    assert main([str(reports), "--allowlist", ""]) == 0

    assert (reports / "SUMMARY.md").read_text(encoding="utf-8").startswith("# Security scan summary: 0.0.0-test")
    assert len(json.loads((reports / "findings.json").read_text(encoding="utf-8"))) == 4


def test_schemathesis_server_errors_are_high_and_undocumented_status_codes_low(tmp_path):
    folder = tmp_path / "rel"
    (folder / "schemathesis").mkdir(parents=True)
    (folder / "schemathesis" / "junit.xml").write_text(
        """<testsuites><testsuite name="schemathesis">
<testcase name="POST /api/v1/things"><failure message="1. Test Case ID: aB1  - Server error  Received: 500
2. Test Case ID: cD2  - Undocumented HTTP status code      Received: 401"/></testcase>
<testcase name="GET /api/v1/other"><failure message="1. Test Case ID: eF3  - Response violates schema  x"/></testcase>
<testcase name="GET /api/v1/fine"/>
</testsuite></testsuites>""",
        encoding="utf-8",
    )
    (folder / "status.tsv").write_text("schemathesis\tran\t\n", encoding="utf-8")

    summary, record = build_summary(str(folder), [], "rel")

    assert sorted((r["severity"], r["rule"], r["location"]) for r in record) == [
        ("High", "Server error", "POST /api/v1/things"),
        ("Low", "Undocumented HTTP status code", "POST /api/v1/things"),
        ("Medium", "Response violates schema", "GET /api/v1/other"),
    ]
    assert "| schemathesis | ran | 0 | 1 | 1 | 1 | 0 | 0 | 0 |" in summary
