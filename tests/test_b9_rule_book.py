"""B9 step 5: the eMDR rule book version 2 (register emdr-rule-book-2) adds the importer (I-I, I-F) and user facility
(U-I, U-F) rows of the mapping workbook's US sheet. The manufacturer rows stay version 1's byte for byte, and FDA's
lists hold: importer initial 9 blocks, user facility initial 4, follow-ups F1, F2 and F7. No database."""

from __future__ import annotations

import csv
import io

from backend.app.authority_reports import emdr
from backend.app.rule_register import register
import pytest

V1 = emdr.RULES.with_name("us_emdr.csv")
V1_COLUMNS = ("row", "block", "label", "report_types", "rule", "m_i", "m_f", "xpath", "source")


# B6b B3: scenarios this file verifies (its register row names it, or it is the group's own test file).
pytestmark = pytest.mark.requirement("B9-13", "B9-17", "B9-18", "B9-19", "B9-20", "B9-23", "B9-33")


def _rows() -> list[dict]:
    with emdr.RULES.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_the_manufacturer_rows_are_version_1_byte_for_byte():
    out = io.StringIO()
    writer = csv.DictWriter(out, V1_COLUMNS, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(row for row in _rows() if "M-I" in row["report_types"] or "M-F" in row["report_types"])
    # Version 1's file is compared as text: its checkout's line endings are the platform's.
    assert out.getvalue() == V1.read_text(encoding="utf-8")
    assert emdr.RULES.read_bytes().count(b"\r") == 0  # version 2 is LF everywhere (.gitattributes): its pin holds


def test_fdas_lists_per_report_type():
    assert emdr.required("I-I") == {
        "B5",
        "D2A",
        "F1",
        "F2",
        "F4",
        "F10_CLINICAL",
        "F10_IMPACT",
        "F10_PROBLEM",
        "F10_COMPONENT",
    }
    assert emdr.required("U-I") == {"B5", "F1", "F2", "F4"}
    assert emdr.required("I-F") == emdr.required("U-F") == {"F1", "F2", "F7"}
    # The manufacturer's lists are unchanged (12 blocks on an initial report, G6 and G8 on a follow-up).
    assert len(emdr.required("M-I")) == 12 and emdr.required("M-F") == {"G6", "G8"}
    rows = {(row["block"], row["label"]): row for row in _rows()}
    assert rows["F7", "Type of Report\\Follow-up Number"]["i_f"] == "conditional"
    assert rows["F10", "Component Code"]["u_i"] == "optional"  # "(U-I optional)"
    assert rows["D2B", "Procode"]["u_i"] == "optional" and rows["D2B", "Procode"]["i_i"] == "required"
    # Section F is never on a manufacturer's report.
    assert all(not row["m_i"] and not row["m_f"] for row in _rows() if row["block"].startswith("F"))


def test_the_register_holds_version_2_as_a_correction_and_both_pins_hold():
    entry = register.pick("emdr-rule-book")
    assert entry["code"] == "emdr-rule-book-2" and entry["change"]["corrects"] == "emdr-rule-book-1"
    assert entry["content"]["file"].endswith("us_emdr_v2.csv")
    assert {source["catalog"] for source in entry["source"]} >= {"CFR803_30", "CFR803_40"}
    assert register.pin_problems() == []
