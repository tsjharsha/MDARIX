"""B6b Part E: write the customer templates (MDX-CUS-001 to -006) as Word files, and the UAT/PQ log of MDX-CUS-001 as
an Excel file, from their Markdown sources in docs/validation/ (MDX-VAL-000 DC-R02 to DC-R04).

    python scripts/customer_templates.py           # write docs/validation/customer-templates/
    python scripts/customer_templates.py --check   # exit 1 when a file there is missing, stale or not generated

Each file's date is the Date in its source's header, so the same commit gives byte-identical files. Word files come
from ``validation.docx_render`` (python-docx), the Excel file from ``validation.xlsx_write`` (owner decision B6b-D12).
A customer fills in a copy; filled copies never come back into this repository (DC-R06)."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from validation import docx_render, xlsx_write  # noqa: E402

DOCS = ROOT / "docs" / "validation"
OUT = DOCS / "customer-templates"
SOURCES = (
    "MDX-CUS-001_UAT_PQ_TEMPLATE.md",
    "MDX-CUS-002_DATA_MIGRATION_PLAN_TEMPLATE.md",
    "MDX-CUS-003_DATA_MIGRATION_REPORT_TEMPLATE.md",
    "MDX-CUS-004_PERIODIC_REVIEW_TEMPLATE.md",
    "MDX-CUS-005_GO_LIVE_CHECKLIST_AND_SUPPORT_PLAN.md",
    "MDX-CUS-006_CUSTOMER_VALIDATION_INSTRUCTIONS.md",
)
UAT_SOURCE = SOURCES[0]
UAT_CASES_HEADING = "## 7. Starting test cases"
# The columns the customer's business users fill in for each test case (MDX-CUS-001 section 8).
EXECUTION_COLUMNS = ["Executed by", "Date (UTC)", "Actual result", "Result", "Evidence ID", "Deviation ID"]
DEVIATION_COLUMNS = [
    "Deviation ID",
    "Test case",
    "What happened",
    "Classification (your procedure)",
    "Cause",
    "Action",
    "Retest result",
    "Raised to MDARIX (yes/no, reference)",
    "Closed by (your QA)",
    "Date closed (UTC)",
]
SIGN_OFF_COLUMNS = ["Role", "Name", "Meaning of signature", "Signature", "Date"]
SIGN_OFF_ROWS = [
    ["Business user (executes)", "", "I executed the test cases recorded against my name and recorded what I saw."],
    ["System owner (customer)", "", "I confirm the configuration under test is the signed snapshot named in the plan."],
    ["QA reviewer and approver (customer)", "", "I reviewed the results and deviations and approve this UAT/PQ."],
]


def header(markdown: str) -> dict[str, str]:
    """The DC-R19 header table at the top of a source: field -> value."""
    fields: dict[str, str] = {}
    for line in markdown.splitlines()[1:]:
        if not line.startswith("|"):
            if fields:
                break
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 2 and cells[0] not in ("Field", "---"):
            fields[cells[0]] = cells[1]
    return fields


def document_date(fields: dict[str, str]) -> str:
    """The header's Date ("14 Nov 2026") as YYYY-MM-DD; a source without a readable date is refused."""
    try:
        return datetime.strptime(fields.get("Date", ""), "%d %b %Y").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"{fields.get('Document ID', '?')}: the header Date must read like '14 Nov 2026'") from exc


def table_after(markdown: str, heading: str) -> list[list[str]]:
    """The first pipe table after ``heading`` (header row first, the separator row left out)."""
    if heading not in markdown:
        raise ValueError(f"No section {heading!r}")
    rows: list[list[str]] = []
    for line in markdown.split(heading, 1)[1].splitlines():
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-+:?", cell) for cell in cells):
                rows.append(cells)
        elif rows:
            break
    if not rows:
        raise ValueError(f"No table after {heading!r}")
    return rows


def _plain(text: str) -> str:
    return text.replace("**", "").replace("`", "")


def uat_workbook(markdown: str) -> bytes:
    """The UAT/PQ log: the starting test cases with empty execution columns, a deviation log and the sign-off."""
    cases = table_after(markdown, UAT_CASES_HEADING)
    fields = header(markdown)
    rows = [cases[0] + EXECUTION_COLUMNS] + [[_plain(cell) for cell in row] + [""] * 6 for row in cases[1:]]
    about = [
        ["Field", "Value"],
        ["Template", f"{fields['Document ID']} {fields['Title']}, version {fields['Version']} ({fields['Status']})"],
        ["Generated from", f"docs/validation/{UAT_SOURCE}"],
        ["Your organisation", ""],
        ["Release under test (MDARIX version)", ""],
        ["Configuration under test: signed snapshot review ID", ""],
        ["Configuration under test: snapshot SHA-256 (fingerprint)", ""],
        ["Your plan reference and version", ""],
        ["Result values", "PASS, FAIL, BLOCKED, NOT RUN (a BLOCKED or NOT RUN case is never a pass)"],
    ]
    return xlsx_write.write(
        {
            "About": about,
            "Test cases": rows,
            "Deviations": [DEVIATION_COLUMNS],
            "Sign-off": [SIGN_OFF_COLUMNS] + [row + ["", ""] for row in SIGN_OFF_ROWS],
        }
    )


def build(docs: Path = DOCS) -> dict[str, bytes]:
    """Every generated file name -> its bytes."""
    files: dict[str, bytes] = {}
    for source in SOURCES:
        markdown = (docs / source).read_text(encoding="utf-8")
        fields = header(markdown)
        stem = f"{fields['Document ID']}_v{fields['Version']}"
        title = f"{fields['Document ID']} {fields['Title']}"
        files[f"{stem}.docx"] = docx_render.render_docx(markdown, title=title, document_date=document_date(fields))
        if source == UAT_SOURCE:
            files[f"{stem}_uat-pq-log.xlsx"] = uat_workbook(markdown)
    return files


def check(files: dict[str, bytes], out: Path = OUT) -> list[str]:
    """What differs between ``out`` and ``files``: missing, stale and extra files."""
    problems = [f"missing: {name}" for name in files if not (out / name).exists()]
    problems += [
        f"stale: {name}" for name in files if (out / name).exists() and (out / name).read_bytes() != files[name]
    ]
    if out.exists():
        problems += [f"not generated from a source: {p.name}" for p in sorted(out.iterdir()) if p.name not in files]
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare, write nothing")
    args = parser.parse_args(argv)
    files = build()
    if args.check:
        problems = check(files)
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    OUT.mkdir(exist_ok=True)
    for name, data in files.items():
        (OUT / name).write_bytes(data)
        print(f"written {OUT / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
