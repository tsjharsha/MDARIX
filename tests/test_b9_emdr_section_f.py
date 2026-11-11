"""B9 step 6: an importer's or user facility's eMDR file. Section F (F1 to F14) as FDA's own examples place it, the
report number F2 (never with G8), F7 with its follow-up number, sections G and H left out, and FDA's schema. FDA's
"Importer Initial", "Importer Follow-up", "User Facility Initial" and "User Facility Follow-up" examples are rebuilt
block by block from their data. No database."""

from __future__ import annotations

import pytest

from backend.app.authority_reports import emdr
from tests.test_fda_3500a_emdr import EXAMPLES, NOW, TYPICAL, _paths, _party, _plain, _sections

IMPORTER = _party(
    role="IMPORTER",
    organisation="Device Importer",
    address="400 Peace Ave, Unit 501, Buffalo, NY 14201-0001",
    contact_name="Jane Flowers",
    contact_phone="+1(716)343-6001x12345",
    contact_email="jaflowers@importer.com",
)
FACILITY = _party(
    role="USER_FACILITY",
    organisation="John's Healthcare System",
    address=None,
    contact_name=None,
    contact_phone="+1(410)737-2001x12345",
    contact_email="trbrooks@johnshospital.com",
)
MAKER = _party(
    organisation="BYPASS Mfr",
    address=None,
    contact_name=None,
    contact_phone=None,
    contact_email="support@bypassmfr.com",
)
SHARED = ("A1", "A3", "B1", "B3", "B4", "B5", "B6", "B7", "D1", "D2A", "D2B", "D4_MODEL", "D4_LOT", "D4_CATALOG")
SHARED += ("D4_EXPIRY", "D4_SERIAL", "D4_UDI", "D6A", "D6B", "D7A", "D8", "E3", "E4")


def _text(party) -> str:
    """The text the worksheet writes from a party (worksheet._party), so ``office`` finds it."""
    text = ", ".join(part for part in (party.organisation, party.address) if part)
    contact = ", ".join(part for part in (party.contact_name, party.contact_phone, party.contact_email) if part)
    return f"{text}; contact: {contact}" if contact else text


def _initial(party, number: str, kind: str) -> dict:
    return {key: TYPICAL[key] for key in SHARED} | {
        "D9": "No",
        "F1": "Importer" if kind == "I" else "User facility",
        "F2": number,
        "F4": _text(party),
        "F6": "2023-07-02",
        "F7": "Initial",
        "F9": "2 years",
        "F10_CLINICAL": "E1 (FDA 1708); E2 (FDA 1884)",
        "F10_IMPACT": "F1 (FDA 1802); F2 (FDA 4634)",
        "F10_PROBLEM": "A1 (FDA 2896); A2 (FDA 1384)",
        "F10_COMPONENT": "G1 (FDA 765); G2 (FDA 527)",
        "F11": "Yes, 2023-08-01",
        "F12": "Other: Other location description",
        "F13": "Yes, 2023-08-01",
        "F14": _text(MAKER),
    }


BLOCKS = ("B1", "B3", "B4", "B5", "B6", "B7", "A3", "D1", "D2 procode", "D2 common name", "D4 model", "D4 lot")
BLOCKS += ("D4 catalog", "D4 expiry", "D4 serial", "D4 UDI", "D6A", "D6B", "D7A", "D8", "D9", "E3", "E4")
BLOCKS += ("H6 clinical", "H6 impact", "H6 problem", "H6 component", "G8")
SECTION_F = ("F1", "F2", "F4 email", "F6", "F7", "F7 number", "F9", "F11", "F12", "F13", "F14")


@pytest.mark.parametrize(
    "example, party, number, kind",
    [
        ("Importer Initial.xml", IMPORTER, "1234567890-2023-09001", "I"),
        ("User Facility Initial.xml", FACILITY, "1234567890-2023-0001", "U"),
    ],
)
def test_fdas_importer_and_user_facility_initial_examples_are_rebuilt_block_by_block(example, party, number, kind):
    values = _initial(party, number, kind)
    missing, left = emdr.check(_sections(values), [party, MAKER], kind=f"{kind}-I")
    assert missing == [], missing
    xml = emdr.build(_sections(values), [party, MAKER], sender="Importer", now=NOW, practice=False, kind=f"{kind}-I")
    assert emdr.validate(xml) == [] and emdr.validate((EXAMPLES / example).read_bytes()) == []
    ours, theirs = _plain(xml), _plain((EXAMPLES / example).read_bytes())
    for block in (*BLOCKS, *SECTION_F):
        assert sorted(ours.xpath(emdr.POINTERS[block])) == sorted(theirs.xpath(emdr.POINTERS[block])), block
    # FDA's structure, fewer blocks filled; no G or H reason, no G1 contact office.
    assert _paths(ours) <= _paths(theirs), sorted(_paths(ours) - _paths(theirs))
    assert not ours.xpath("//reasonOf") and not ours.xpath("//manufacturerOrReprocessor/contactParty")
    assert ours.xpath(emdr.POINTERS["F12"] + "/../originalText/text()") == ["Other location description"]


@pytest.mark.parametrize(
    "example, party, number, kind",
    [
        ("Importer Follow-up.xml", IMPORTER, "1234567890-2023-00001", "I"),
        ("User Facility Follow-up.xml", FACILITY, "1234567890-2023-0001", "U"),
    ],
)
def test_fdas_follow_up_examples_are_rebuilt_in_section_f(example, party, number, kind):
    values = {"F1": "Importer" if kind == "I" else "User facility", "F2": number, "F7": "Follow-up #1"}
    assert emdr.check(_sections(values), [party], kind=f"{kind}-F")[0] == []
    xml = emdr.build(_sections(values), [party], sender="Importer", now=NOW, practice=False, kind=f"{kind}-F")
    assert emdr.validate(xml) == []
    ours, theirs = _plain(xml), _plain((EXAMPLES / example).read_bytes())
    for block in ("F1", "F2", "F7", "F7 number", "F11", "F13", "G8"):
        assert sorted(ours.xpath(emdr.POINTERS[block])) == sorted(theirs.xpath(emdr.POINTERS[block])), block
    assert _paths(ours) <= _paths(theirs), sorted(_paths(ours) - _paths(theirs))
    # F7 on a follow-up needs its number.
    assert emdr.check(_sections({**values, "F7": "Follow-up"}), [party], kind=f"{kind}-F")[0] == [
        "F7: Follow-up with its number (Follow-up #1)"
    ]


def test_f2_formats_and_never_with_g8():
    base = _initial(IMPORTER, "1234567-2026-00001", "I")
    assert emdr.check(_sections(base), [IMPORTER], kind="I-I")[0] == []
    assert emdr.check(_sections({**base, "F2": "1234567890-2026-0001"}), [IMPORTER], kind="I-I")[0] == [
        "F2: FDA's format is your 7-digit CFN or 10-digit FEI, the year and a 5-digit number (1234567-2026-00001)"
    ]
    facility = _initial(FACILITY, "1234567890-2026-0001", "U")
    assert emdr.check(_sections(facility), [FACILITY], kind="U-I")[0] == []
    assert emdr.check(_sections({**facility, "F2": "1234567-2026-0001"}), [FACILITY], kind="U-I")[0] == [
        "F2: FDA's format is your 10-digit HCFA number, the year and a 4-digit number (1234567890-2026-0001)"
    ]
    both = emdr.check(_sections({**facility, "G8": "1234567-2026-00001"}), [FACILITY], kind="U-I")[0]
    assert both == ["G8: an importer's or user facility's report has no manufacturer report number"]
    # A role report ignores sections G and H: they are never sent, never asked for.
    assert "H1" not in " ".join(emdr.check(_sections(facility), [FACILITY], kind="U-I")[0])


def test_what_each_role_requires_and_f4_reads_the_roles_own_party():
    importer = _initial(IMPORTER, "1234567-2026-00001", "I")
    for key in ("B5", "D2A", "F10_PROBLEM"):
        missing = emdr.check(_sections({k: v for k, v in importer.items() if k != key}), [IMPORTER], kind="I-I")[0]
        assert [line for line in missing if line.startswith(f"{key}:")], (key, missing)
    facility = _initial(FACILITY, "1234567890-2026-0001", "U")
    for key in ("D2A", "F10_PROBLEM", "F10_COMPONENT"):  # optional on a user facility's report
        assert emdr.check(_sections({k: v for k, v in facility.items() if k != key}), [FACILITY], kind="U-I")[0] == []
    # F4 needs the role's own party (the importer's for an importer), reading as the report does.
    assert emdr.check(_sections(importer), [FACILITY], kind="I-I")[0][0].startswith("F4: set your organization's US")


def test_report_numbers_per_role_never_reused_practice_from_7():
    used = ["1234567890-2026-0001", "1234567890-2026-0002", "1234567-2026-00004"]
    assert emdr.next_number(used, 2026, False, "U") == "1234567890-2026-0003"
    assert emdr.next_number(used, 2026, True, "U") == "1234567890-2026-7001"
    assert emdr.next_number(used, 2027, False, "U") == "1234567890-2027-0001"
    assert emdr.next_number(used, 2026, False, "I") == "1234567-2026-00005"
    assert emdr.next_number(["1234567890-2026-0002"], 2026, False, "I") is None  # an HCFA number is not an F2 of I
    assert emdr.role_kind("IMPORTER", False) == "I-I" and emdr.role_kind(None, True) == "M-F"
    assert emdr.role_kind("USER_FACILITY", True) == "U-F"
