"""0.10.96 (B3): the US eMDR complete for manufacturers, the parts that need no database.

The rule book (rules/us_emdr.csv, the mapping workbook's US manufacturer rows) decides which blocks stop the file;
the report number is the organization's next; the file is frozen with the approval; the eSubmitter-layout PDF is
rendered from the file's own values."""

from __future__ import annotations

import csv

from backend.app.authority_reports import emdr
from tests.test_fda_3500a_emdr import REPORT, _party, _sections

# FDA's "Required 3500A fields" (HL7Medwatch.xlsx, Instructions sheet), in the report's own field names.
FDA_REQUIRED = {
    "M-I": {"B5", "D2A", "G1", "G8", "H1", *emdr.REQUIRED_CODES},
    "M-F": {"G6", "G8"},
}


def _rule_rows() -> list[dict]:
    with emdr.RULES.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


# --------------------------------------------------------------------------------------------- A1: the rule book


def test_b3_every_mandatory_us_row_is_enforced():
    rows = _rule_rows()
    assert len(rows) == 161 and all(row["m_i"] or row["m_f"] for row in rows)  # the sheet's manufacturer rows
    mandatory = [row for row in rows if row["m_i"] == "required"]
    # The rule book agrees with FDA's own list: 12 blocks on an initial report, 2 on a follow-up.
    assert len(mandatory) == 12 and emdr.required("M-I") == FDA_REQUIRED["M-I"]
    assert emdr.required("M-F") == FDA_REQUIRED["M-F"]
    assert emdr.check(_sections(REPORT), [_party()])[0] == []
    for row in mandatory:
        field = emdr.RULE_FIELDS[row["block"], row["label"]]
        values = {key: value for key, value in REPORT.items() if key != field}
        if field == "G8":
            values.pop("MFR_REPORT")  # G8 follows the front page's number
        missing = emdr.check(_sections(values), [_party()])[0]
        assert [line for line in missing if line.startswith(f"{field}:")], (row["row"], row["label"], missing)
    # Spot-check fix 3 is in the sheet the rule book comes from: B4 is "required if known", never a blocker.
    (b4,) = [row for row in rows if row["block"] == "B4"]
    assert b4["rule"].startswith("Required if known") and b4["m_i"] == "optional"


def test_b3_a_follow_up_needs_only_g6_with_its_number_and_g8():
    follow_up = {"G6": "30-day; Follow-up #1", "G8": "1234567-2026-00001"}
    assert emdr.check(_sections(follow_up), [], kind="M-F")[0] == []
    assert emdr.check(_sections({**follow_up, "G6": "30-day"}), [], kind="M-F")[0] == [
        "G6: Follow-up with its number (Follow-up #1)"
    ]
    assert emdr.check(_sections({"G6": "Follow-up #2"}), [], kind="M-F")[0] == ["G8: missing"]
    # A value given on a follow-up is still checked for FDA's format.
    assert emdr.check(_sections({**follow_up, "D2A": "dqa"}), [], kind="M-F")[0] == [
        "D2A: three capital letters (FDA's product code)"
    ]
    # The same two blocks are far from an initial report.
    assert len(emdr.check(_sections(follow_up), [], kind="M-I")[0]) > 10
