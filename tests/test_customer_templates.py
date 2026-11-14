"""B6b Part E: the customer templates MDX-CUS-001 to -006 (sources in docs/validation/, Word and Excel copies in
docs/validation/customer-templates/, written by scripts/customer_templates.py); no database."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path

import pytest

from backend.app.trial.xlsx import read_rows
from scripts import customer_templates

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "validation"
HEADER_FIELDS = (
    "Document ID",
    "Title",
    "Version",
    "Status",
    "Author (R)",
    "Reviewer",
    "Approver (A)",
    "Drafting",
    "Date",
    "Code baseline",
)


def _source(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", customer_templates.SOURCES)
def test_each_template_has_the_document_control_header(name):
    """MDX-VAL-000 DC-R19 to DC-R22, DC-R40: the header fields, a DRAFT 0.x status, a person as author and a different
    person as approver."""
    fields = customer_templates.header(_source(name))
    assert set(HEADER_FIELDS) <= set(fields)
    assert fields["Document ID"] == name.split("_")[0]
    assert fields["Status"] == "DRAFT" and fields["Version"].startswith("0.")
    assert fields["Author (R)"].split(",")[0] != fields["Approver (A)"].split(",")[0]
    customer_templates.document_date(fields)


@pytest.mark.parametrize("name", customer_templates.SOURCES)
def test_no_template_makes_a_claim_the_rules_forbid(name):
    """MDX-VAL-000 DC-R29 and DC-R30, and the company is not registered: no price, no compliance, certification or
    alignment claim, no "validated" except "validated state", and the legal entity left as a placeholder."""
    text = " ".join(_source(name).split())
    for allowed in ("does not say it is validated for your use", "no certification claim", "certification letter"):
        text = text.replace(allowed, "")
    assert not re.search(r"\b(compliant|certified|certification|aligned|price|pricing)\b", text, re.I)
    assert not re.search(r"\bvalidated\b(?! state)", text, re.I)
    assert not re.search(r"[₹$€£]\s?\d|\b(INR|USD|EUR|GBP)\b", text)
    for line in _source(name).splitlines():
        if "legal entity" in line.lower():
            assert "[legal entity: to be added on registration]" in line


def test_the_starting_test_cases_trace_to_class_a_requirements_and_their_scenarios():
    """E1: each starting UAT/PQ case names a class-A requirement in requirements.csv and only scenarios that
    requirement lists, so a customer can find MDARIX's own test of it."""
    requirements = {row["req_id"]: row for row in csv.DictReader(io.StringIO(_source("requirements.csv")))}
    cases = customer_templates.table_after(_source(customer_templates.UAT_SOURCE), customer_templates.UAT_CASES_HEADING)
    header, rows = cases[0], cases[1:]
    assert len(rows) >= 30
    ids = [row[header.index("Case")] for row in rows]
    assert len(ids) == len(set(ids))
    for row in rows:
        req = requirements[row[header.index("MDARIX requirement")]]
        assert req["class"] == "A", row
        listed = set(req["scenario_ids"].split())
        assert set(row[header.index("MDARIX scenarios")].split()) <= listed, row
        assert row[header.index("Type")] in {"positive", "negative"}
        assert row[header.index("Mode")] in {"Both", "Connect", "Complete"}


def test_the_uat_log_reads_back_with_every_case_and_empty_execution_columns():
    """The Excel log is written by the standard-library writer and read back by the product's own reader."""
    markdown = _source(customer_templates.UAT_SOURCE)
    raw = customer_templates.uat_workbook(markdown)
    rows = read_rows(raw, sheet="Test cases")
    cases = customer_templates.table_after(markdown, customer_templates.UAT_CASES_HEADING)
    assert rows[0] == cases[0] + customer_templates.EXECUTION_COLUMNS
    assert [row[0] for row in rows[1:]] == [row[0] for row in cases[1:]]
    assert all(not any(row[len(cases[0]) :]) for row in rows[1:])
    assert read_rows(raw, sheet="Deviations")[0] == customer_templates.DEVIATION_COLUMNS


def test_the_same_sources_give_byte_identical_files_dated_from_the_header():
    first, second = customer_templates.build(), customer_templates.build()
    assert first == second
    versions = {
        name.split("_")[0]: customer_templates.header(_source(name))["Version"] for name in customer_templates.SOURCES
    }
    assert set(first) == {
        *(f"{doc_id}_v{version}.docx" for doc_id, version in versions.items()),
        f"MDX-CUS-001_v{versions['MDX-CUS-001']}_uat-pq-log.xlsx",
    }
    core = (
        zipfile.ZipFile(io.BytesIO(first[f"MDX-CUS-006_v{versions['MDX-CUS-006']}.docx"]))
        .read("docProps/core.xml")
        .decode()
    )
    assert "2026-11-14" in core


def test_the_committed_files_are_the_ones_the_sources_give():
    """The Word and Excel copies in docs/validation/customer-templates/ are never edited by hand (DC-R04)."""
    assert customer_templates.check(customer_templates.build()) == []


def test_a_stale_missing_or_stray_file_is_reported(tmp_path):
    files = {"a.docx": b"new", "b.docx": b"same"}
    (tmp_path / "b.docx").write_bytes(b"same")
    (tmp_path / "c.docx").write_bytes(b"stray")
    assert customer_templates.check(files, tmp_path) == ["missing: a.docx", "not generated from a source: c.docx"]
    (tmp_path / "a.docx").write_bytes(b"old")
    assert customer_templates.check(files, tmp_path) == ["stale: a.docx", "not generated from a source: c.docx"]


def test_a_header_date_that_cannot_be_read_is_refused():
    with pytest.raises(ValueError):
        customer_templates.document_date({"Document ID": "MDX-CUS-009", "Date": "2026-11-14"})


def test_the_superseded_instructions_name_their_successor():
    """E5: the old MVP instructions stay, marked SUPERSEDED, and point to MDX-CUS-006 (DC-R44, DC-R45)."""
    old = (ROOT / "docs" / "compliance" / "CSA_CUSTOMER_IMPLEMENTATION_INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "**SUPERSEDED" in old.splitlines()[2]
    assert "MDX-CUS-006_CUSTOMER_VALIDATION_INSTRUCTIONS.md" in old
