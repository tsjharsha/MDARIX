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


# --------------------------------------------------------------------------------------------- A3: the report number


def test_b3_the_next_number_follows_the_last_and_restarts_each_year():
    used = ["1234567-2026-00041", "not a number", "1234567-2026-00042"]
    assert emdr.next_number(used, 2026, practice=False) == "1234567-2026-00043"
    assert emdr.next_number(used, 2027, practice=False) == "1234567-2027-00001"  # a new year starts at 00001
    # The registration number is the organization's last one (a 10-digit FEI here).
    assert emdr.next_number([*used, "3001234567-2026-00007"], 2026, practice=False) == "3001234567-2026-00008"
    assert emdr.next_number([], 2026, practice=False) is None  # the first number is typed once
    assert emdr.REPORT_NUMBER.match(emdr.next_number(used, 2026, practice=False))


def test_b3_a_practice_number_starts_with_7():
    first = ["1234567-2026-00001"]
    assert emdr.next_number(first, 2026, practice=True) == "1234567-2026-70001"
    assert emdr.next_number([*first, "1234567-2026-70001"], 2026, practice=True) == "1234567-2026-70002"
    # A real report's sequence never counts FDA's test numbers.
    assert emdr.next_number([*first, "1234567-2026-70001"], 2026, practice=False) == "1234567-2026-00002"


# --------------------------------------------------------------------------------------------- A4: the frozen file


def test_b3_the_approval_fingerprint_covers_the_xml():
    import hashlib
    from datetime import timedelta
    from types import SimpleNamespace

    from backend.app.authority_reports import router
    from backend.app.human_decision.rules import fingerprint
    from tests.test_fda_3500a_emdr import NOW

    obligation = SimpleNamespace(id="r1", form_code="FDA_3500A", form_version="Form FDA 3500A (09/2025)", market="US")
    sections, parties = _sections(REPORT), [_party()]
    xml = emdr.build(sections, parties, sender="Org", now=NOW, practice=False)
    frozen = router.frozen_emdr(xml, parties, sections)
    assert frozen["emdr_xml"].encode("utf-8") == xml and frozen["emdr_sha256"] == hashlib.sha256(xml).hexdigest()
    assert frozen["emdr_parties"]["G1"]["email"] == "mdr@example.invalid"  # the parties as built, in parts
    material = lambda found: router.snapshot_material(obligation, "C-1", "a1", sections, found)  # noqa: E731
    signed = fingerprint(material(frozen))
    # Another file (made a second later), or the same file from other party details, is another approval.
    later = emdr.build(sections, parties, sender="Org", now=NOW + timedelta(seconds=1), practice=False)
    assert fingerprint(material(router.frozen_emdr(later, parties, sections))) != signed
    moved = [_party(contact_phone="+1(240)276-0002")]
    assert fingerprint(material(router.frozen_emdr(xml, moved, sections))) != signed
    # A report without a file (another market) is fingerprinted as before 0.10.96.
    assert "emdr_sha256" not in material({}) and fingerprint(material({})) != signed
