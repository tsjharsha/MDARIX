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


# --------------------------------------------------------------------------------------------- A5: the eSubmitter PDF


def _typical_pdf(**view) -> tuple[bytes, bytes]:
    from backend.app.authority_reports import emdr_pdf
    from tests.test_fda_3500a_emdr import NOW, TYPICAL, TYPICAL_PARTY, _view

    sections = _sections(TYPICAL)
    xml = emdr.build(sections, [TYPICAL_PARTY], sender="USA Device Manufacturer", now=NOW, practice=False)
    left = emdr.check(sections, [TYPICAL_PARTY])[1]
    return xml, emdr_pdf.render(xml, {**_view(TYPICAL, practice=False), **view}, "USA Device Manufacturer", left)


def _sections_of(text: str) -> list[str]:
    import re

    return [line for line in text.splitlines() if re.match(r"^[A-H]\. [A-Z]{2}", line)]


def test_b3_the_pdf_has_fdas_blocks_in_fdas_order():
    import re

    from pypdf import PdfReader

    from reports.pdf import text_of
    from tests.test_fda_3500a_emdr import EXAMPLES

    fda = "\n".join(page.extract_text() for page in PdfReader(EXAMPLES / "Manufacturer Initial - Typical.pdf").pages)
    ours = text_of(_typical_pdf()[1])
    # Sections A to H, in FDA's order and words.
    assert _sections_of(ours) == _sections_of(fda) and len(_sections_of(fda)) == 8

    # Every numbered block FDA prints in a section MDARIX fills, MDARIX prints under the same section.
    def numbered(text: str) -> dict[str, set[str]]:
        found, section = {}, None
        for line in text.splitlines():
            if line in _sections_of(text):
                section = line[0]
            elif section and (match := re.match(r"^(\d+[ab]?)\. ", line)):
                found.setdefault(section, set()).add(match.group(1))
        return found

    theirs, mine = numbered(fda), numbered(ours)
    for section in "ABDEGH":
        assert theirs[section] <= mine[section], (section, theirs[section] - mine[section])
    assert "File Attachments: none" in ours


def test_b3_every_value_in_the_xml_is_in_the_pdf():
    from backend.app.authority_reports import emdr_pdf
    from reports.pdf import text_of

    xml, pdf = _typical_pdf()
    text = " ".join(text_of(pdf).split())
    values = {block: held for block, held in emdr_pdf.read(xml).items() if block in emdr.POINTERS}  # FDA's blocks
    ticked = 0
    for block, held in values.items():
        for value in held:
            if block in ("version", "E3"):  # E3 reads as its occupation, checked below
                continue
            if len(value) == 8 and value.isdigit():
                assert emdr_pdf.day(value) in text, (block, value)
            elif block in (*emdr_pdf.OPTIONS, "B1"):
                ticked += 1  # a choice: counted against the ticks below
            else:
                assert value.removeprefix("mailto:").removeprefix("tel:") in text, (block, value)
    # Each coded value in the file is one tick in the PDF, and the ticks read FDA's words.
    assert text.count("[X]") + text.count("(X)") == ticked
    for shown in (
        "[X] Adverse Event and/or [X] Product Problem",
        "[X] Death",
        "[X] Other Serious or Important Medical Events",
        "(X) Male",
        "[X] Health Professional [X] User Facility",
        "[X] 30-day",
        "[X] Initial",
        "(X) Death ( ) Serious Injury",
        "[X] Recall [X] Repair",
        "(X) Initial Use of Device",
        "Occupation Physician",
        "Initial Reporter Also Sent Report to FDA? (X) Yes",
        "Health Effect - Clinical Code: 1884 - 1708",
        "VENTRICULAR (ASSIST) BYPASS, Product Code: DSQ",
        "Premarket Identification PMA/510(k) P012345",
        "Mfr Report #: 1234567-2023-00001",
        "50 Year(s)",
        "180 Pound(s)",
    ):
        assert shown in text, shown


def test_b3_the_pdf_never_says_fda_generated_it():
    from reports.pdf import text_of

    text = text_of(_typical_pdf()[1])
    assert "Form FDA 3500A – eMDR content, prepared by MDARIX" in text
    assert "MDARIX never submits" in text
    lowered = text.lower()
    assert "esubmitter generated" not in lowered and "generated by fda" not in lowered
    assert "fda generated" not in lowered and "generated" not in lowered


def test_b3_the_same_snapshot_renders_the_same_bytes():
    import hashlib

    from reports.pdf import text_of

    xml, first = _typical_pdf()
    assert _typical_pdf()[1] == first
    # The record page names the file it was read from.
    assert f"SHA-256 of the eMDR file: {hashlib.sha256(xml).hexdigest()}" in text_of(first)


def test_b3_a_draft_pdf_is_marked_draft():
    from reports.pdf import text_of

    draft = text_of(_typical_pdf(signature=None)[1])
    assert "DRAFT - NOT APPROVED" in draft and "DRAFT PREVIEW - NOT APPROVED" in draft
    approved = text_of(_typical_pdf()[1])
    assert "NOT APPROVED" not in approved and "Approved by Rahul Colleague" in approved


# --------------------------------------------------------------------------------------------- B1 (follow-ups)


def test_b3_a_follow_up_is_due_30_days_after_the_information_arrived():
    from datetime import date

    from backend.app.authority_reports.router import follow_up_due

    assert follow_up_due(date(2026, 1, 31)) == date(2026, 3, 2)  # 30 calendar days (21 CFR 803.56)
    assert follow_up_due(date(2026, 12, 15)) == date(2027, 1, 14)


def test_b3_follow_up_numbers_count_only_the_follow_ups_submitted_before():
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from backend.app.authority_reports.router import follow_up_number

    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    chain = [
        SimpleNamespace(id=str(n), created_at=start + timedelta(days=n), state=state)
        for n, state in enumerate(("ACCEPTED", "CANCELLED", "SUBMITTED_PENDING", "DRAFT"))
    ]
    # Submitted, then cancelled before it was sent (never numbered), then submitted, then the open one: 1, 2, 2, 3.
    assert [follow_up_number(chain, row) for row in chain] == [1, 2, 2, 3]


# --------------------------------------------------------------------------------------------- B2 (follow-up file)


def _follow_up(values: dict, typed=("B5", "H11")) -> list[dict]:
    """A follow-up's sections: the narratives typed on it (ENTERED), the rest from the record."""
    sections = _sections(values)
    for item in sections[0]["fields"]:
        item["status"] = "ENTERED" if item["id"] in typed else "FROM_RECORD"
    return sections


def test_fdas_manufacturer_follow_up_example_is_reproduced_block_by_block():
    from tests.test_fda_3500a_emdr import EXAMPLES, NOW, POINTERS, TYPICAL, _example, _plain

    held = dict(TYPICAL)  # the initial report as FDA holds it; the follow-up holds the same, plus what is new
    values = {
        **held,
        "B5": "Additional event narrative.",
        "H11": "Additional follow-up manufacturer narrative.",
        "G6": "30-day; Follow-up #1",
        "H2": "Correction; Additional information",
    }
    found = emdr.prepare(
        _follow_up(values), [], kind="M-F", sender="USA Device Manufacturer", now=NOW, practice=False, previous=held
    )
    assert found["missing"] == [] and found["errors"] == [], (found["missing"], found["errors"])
    ours, theirs = _plain(found["xml"]), _example("Manufacturer Follow-up.xml")
    assert emdr.validate((EXAMPLES / "Manufacturer Follow-up.xml").read_bytes()) == []
    for block, path in POINTERS.items():
        if block not in ("B4", "version"):  # FDA's example leaves B4 out; MDARIX dates every report it sends
            assert sorted(ours.xpath(path)) == sorted(theirs.xpath(path)), block
    number = "//reasonOf/detectedIssueEvent/value[@code='C53579']/../text/text()"
    assert ours.xpath(number) == theirs.xpath(number) == ["1"]


def test_b3_unchanged_values_are_left_out_and_narratives_never_repeat():
    from tests.test_fda_3500a_emdr import NOW, TYPICAL, _plain

    held = dict(TYPICAL)
    values = {**held, "D1": "New brand name", "G6": "30-day; Follow-up #2", "H2": "Correction"}
    values["H6_PROBLEM"] = held["H6_PROBLEM"] + "; A0102 Extra (FDA 9999)"
    values["D4_LOT"] = ""  # cleared on the follow-up
    found = emdr.prepare(
        _follow_up(values, typed=()), [], kind="M-F", sender="X", now=NOW, practice=False, previous=held
    )
    assert found["errors"] == [] and found["missing"] == []
    ours = _plain(found["xml"])
    assert ours.xpath(emdr.POINTERS["D1"]) == ["New brand name"]  # changed: sent
    assert ours.xpath(emdr.POINTERS["H6 problem"]) == ["9999"]  # only the new code
    assert ours.xpath(emdr.POINTERS["B5"]) == [] and ours.xpath(emdr.POINTERS["H11"]) == []  # never repeated
    for block in ("D4 model", "D2 procode", "B1", "H1", "H6 clinical"):
        assert ours.xpath(emdr.POINTERS[block]) == [], block  # unchanged: left out
    assert any("FDA keeps the earlier value" in line and "D4_LOT" in line for line in found["left_out"])


def test_b3_g6_says_follow_up_with_its_number_and_h2_ticks_are_sent_as_fdas_codes():
    from tests.test_fda_3500a_emdr import NOW, TYPICAL, _plain

    values = {**TYPICAL, "G6": "30-day; Follow-up #3", "H2": "Response to FDA request; Device evaluation"}
    found = emdr.prepare(_follow_up(values), [], kind="M-F", sender="X", now=NOW, practice=False, previous=TYPICAL)
    ours = _plain(found["xml"])
    assert sorted(ours.xpath(emdr.POINTERS["G6"])) == ["C53577", "C53579"]
    assert ours.xpath("//reasonOf/detectedIssueEvent/value[@code='C53579']/../text/text()") == ["3"]
    h2 = "//reasonOf/detectedIssueEvent/code[@code='C53584']/../value/@code"
    assert sorted(ours.xpath(h2)) == ["C53587", "C53588"]
    assert not [line for line in found["left_out"] if line.startswith("G6")]  # "Follow-up #3" is FDA's choice


def test_b3_the_official_form_ticks_follow_up_and_h2():
    from backend.app.authority_reports import fda_3500a

    pages, left = fda_3500a.placements(
        _sections({"G6": "30-day; Follow-up #2", "H2": "Correction; Device evaluation"}), None
    )
    assert pages[8]["repFollow[0]"] == fda_3500a.ON and pages[8]["repFollowNum[0]"] == "2" and pages[8]["rep30[0]"]
    assert pages[9]["correction[0]"] == fda_3500a.ON and pages[9]["devEval[0]"] == fda_3500a.ON
    assert not left
