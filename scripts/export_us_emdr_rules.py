"""Export the mapping workbook's US sheet to the rule book the eMDR check reads.

The workbook (authority-forms-mapping.xlsx, sheet "US eMDR 3500A") is the rule book (decision D17): a rule changes in
the sheet first, then this script writes backend/app/authority_reports/rules/us_emdr_v2.csv (register entry
emdr-rule-book-2, B9 step 5). Version 1 (us_emdr.csv, manufacturer rows only) stays as it was: its rows are the
manufacturer rows of version 2, byte for byte (tests/test_b9_rule_book.py). Standard library only.

    python scripts/export_us_emdr_rules.py path/to/authority-forms-mapping.xlsx

Each row's need per report type (``m_i`` manufacturer initial, ``m_f`` manufacturer follow-up; B9: ``i_i``/``i_f``
importer initial/follow-up, ``u_i``/``u_f`` user facility initial/follow-up) is read from its rule:
``required`` (FDA's "Required 3500A fields": eMDR rejects a report without it), ``schema`` (MDARIX always writes it),
``conditional``, ``optional``, or blank when the row is not on that report type.
"""

from __future__ import annotations

import csv
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

SHEET = "US eMDR 3500A"
OUT = Path(__file__).resolve().parents[1] / "backend" / "app" / "authority_reports" / "rules" / "us_emdr_v2.csv"
COLUMNS = ("row", "block", "label", "report_types", "rule", "m_i", "m_f", "i_i", "i_f", "u_i", "u_f", "xpath", "source")
V1_COLUMNS = ("row", "block", "label", "report_types", "rule", "m_i", "m_f", "xpath", "source")
ROLE_KINDS = ("I-I", "I-F", "U-I", "U-F")
M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def sheet_rows(path: str, name: str) -> dict[int, dict[str, str]]:
    with zipfile.ZipFile(path) as book:
        shared = (
            [
                "".join(t.text or "" for t in item.iter(M + "t"))
                for item in ET.fromstring(book.read("xl/sharedStrings.xml")).findall(M + "si")
            ]
            if "xl/sharedStrings.xml" in book.namelist()
            else []
        )
        rels = {rel.get("Id"): rel.get("Target") for rel in ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))}
        sheet = next(s for s in ET.fromstring(book.read("xl/workbook.xml")).find(M + "sheets") if s.get("name") == name)
        target = rels[sheet.get(R + "id")].lstrip("/")
        part = ET.fromstring(book.read(target if target.startswith("xl/") else "xl/" + target))
    rows = {}
    for row in part.iter(M + "row"):
        cells = {}
        for cell in row.findall(M + "c"):
            value = cell.find(M + "v")
            if cell.get("t") == "s" and value is not None:
                text = shared[int(value.text)]
            elif cell.get("t") == "inlineStr":
                text = "".join(t.text or "" for t in cell.iter(M + "t"))
            else:
                text = value.text if value is not None else ""
            cells[re.match(r"[A-Z]+", cell.get("r")).group()] = (text or "").strip()
        rows[int(row.get("r"))] = cells
    return rows


def need(kind: str, types: str, rule: str) -> str:
    if kind not in types:
        return ""
    text = rule.lower()
    if text.startswith("mandatory (schema"):
        return "schema"
    if "fda required" in text:
        scope = text.split(";")[0]  # G6: "Mandatory on manufacturer follow-ups (FDA required); initial: check all"
        if "all manufacturer reports" in scope or ("initial" if kind == "M-I" else "follow-up") in scope:
            return "required"
        return "optional"
    return "conditional" if text.startswith("conditional") else "optional"


def role_need(kind: str, types: str, rule: str) -> str:
    """An importer (I-) or user facility (U-) report's need of a row (B9 step 5): FDA's lists, as the rule's own words
    scope them ("importer and user facility initial reports", "all initial reports", "on follow-ups"); a type marked
    "(U-I optional)" is optional."""
    if kind not in types:
        return ""
    if f"({kind} optional)" in types:
        return "optional"
    text = rule.lower()
    if text.startswith("mandatory (schema"):
        return "schema"
    if text.startswith("mandatory"):
        scope = text.split(";")[0].split(". ")[0]
        who, initial = ("importer" if kind[0] == "I" else "user facility"), kind.endswith("-I")
        if ("importer" in scope or "user facility" in scope) and who not in scope:
            return "optional"
        if ("initial" in scope and not initial) or ("follow-up" in scope and initial):
            return "optional"
        return "required"
    return "conditional" if text.startswith("conditional") else "optional"


def export(workbook: str) -> list[dict[str, str]]:
    rows = sheet_rows(workbook, SHEET)
    out = []
    for number, cells in sorted(rows.items()):
        types = cells.get("C", "")
        if number == 1 or not any(kind in types for kind in ("M-I", "M-F", *ROLE_KINDS)):
            continue
        rule = cells.get("D", "")
        out.append(
            {
                "row": str(number),
                "block": cells.get("A", ""),
                "label": cells.get("B", ""),
                "report_types": types,
                "rule": rule,
                "m_i": need("M-I", types, rule),
                "m_f": need("M-F", types, rule),
                **{kind.lower().replace("-", "_"): role_need(kind, types, rule) for kind in ROLE_KINDS},
                "xpath": cells.get("E", ""),
                "source": cells.get("G", ""),
            }
        )
    return out


if __name__ == "__main__":
    found = export(sys.argv[1])
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(found)
    print(f"{len(found)} rows -> {OUT}")
