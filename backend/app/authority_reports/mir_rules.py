"""The EU and GB MIR rule books (B8 step 2): one row per MIR block of the mapping workbook, with the MDARIX fields
that hold it, its XML path and whether it is mandatory (M), conditional (C) or optional (O) in each report type.

Where the help text and the XSD disagree, the stricter of the two is kept (B8-D6). The rule book is register data
(``eu-mir-rule-book-1``, ``gb-mir-rule-book-1``, pinned by SHA-256); ``forms.py``'s ``must_in`` must agree with it (tested). Starter, for your
consultant to confirm.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from backend.app.authority_reports import forms

RULES = Path(__file__).with_name("rules")
BOOKS = {forms.EU_MIR.code: RULES / "eu_mir.csv", forms.GB_MIR.code: RULES / "gb_mir.csv"}
# The rule book's columns per report type, in the form's order of types.
TYPE_COLUMNS = {
    forms.MIR_INITIAL: "i",
    forms.MIR_FOLLOW_UP: "fu",
    forms.MIR_COMBINED: "c",
    forms.MIR_FINAL: "fr",
    forms.MIR_FINAL_NON: "fnr",
}


@lru_cache
def rows(form_code: str) -> tuple[dict, ...]:
    with BOOKS[form_code].open(encoding="utf-8", newline="") as handle:
        return tuple(csv.DictReader(handle))


def need(row: dict, report_type: str) -> str:
    """M, C or O: what the rule book says of ``row`` in ``report_type``."""
    return row[TYPE_COLUMNS[report_type]]


def mandatory_fields(form_code: str, report_type: str) -> dict[str, str]:
    """The MDARIX fields a report of this type must hold, each with the block that requires it (first one wins)."""
    found: dict[str, str] = {}
    for row in rows(form_code):
        if need(row, report_type) == "M":
            for field in filter(None, row["fields"].split(";")):
                found.setdefault(field, row["block"])
    return found
