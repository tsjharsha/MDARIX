"""Regression corpus for personal-data masking (genai/pii.py): what must be masked, and what must be kept.

Each MASKED case lists the fragments that may not survive masking (and, where useful, the placeholder expected).
Each KEPT case is text that must come back unchanged: investigation facts, standards, lot numbers, product names.
"""

import pytest

from genai.pii import is_personal_key, mask, mask_text

# (text, fragments that must disappear, placeholders that must appear)
MASKED = [
    # --- previously covered: labels, titles, contact details, numbers
    ("Patient: John Smith was admitted.", ["John Smith"], ["[PERSON]"]),
    ("Reporter name = J. Smith", ["J. Smith"], ["[PERSON]"]),
    ("DOB: 1961-04-02", ["1961-04-02"], ["[DATE_OF_BIRTH]"]),
    ("Address: 1 High Street, Leeds LS1 4AP", ["High Street", "LS1 4AP"], ["[ADDRESS]"]),
    ("Contact jane.doe@hospital.org for details.", ["jane.doe@hospital.org"], ["[EMAIL]"]),
    ("Call +1 617 555 0100 or (617) 555-0100.", ["617 555 0100", "555-0100"], ["[PHONE]"]),
    ("Call +44 20 7946 0958 tomorrow.", ["7946 0958"], ["[PHONE]"]),
    ("MRN 004512 on file.", ["004512"], ["[ID_NUMBER]"]),
    ("NHS number 943 476 5919 recorded.", ["943 476 5919"], ["[ID_NUMBER]"]),
    ("Dr. Alan Grant reviewed the device.", ["Alan Grant"], ["[PERSON]"]),
    ("Mrs Patel-Jones called back.", ["Patel-Jones"], ["[PERSON]"]),
    ("Reported by Jane Doe on Monday.", ["Jane Doe"], ["[PERSON]"]),
    ("Card 4111 1111 1111 1111 was charged.", ["4111 1111 1111 1111"], ["[CARD_NUMBER]"]),
    ("SSN 123-45-6789 appears in the file.", ["123-45-6789"], ["[ID_NUMBER]"]),
    ("client IP: 192.168.1.20 connected", ["192.168.1.20"], ["[IP_ADDRESS]"]),
    ("Phone: 0161 496 0000", ["0161 496 0000"], ["[PHONE]"]),
    ("E-mail: nurse.a@clinic.example", ["nurse.a@clinic.example"], ["[EMAIL]"]),
    # --- bare names in free text
    ("Jane Doe called the hotline about the pump.", ["Jane Doe"], ["[PERSON]"]),
    ("The device was returned by Priya Patel last week.", ["Priya Patel"], ["[PERSON]"]),
    ("John Smith and Mary Jones both reported alarms.", ["John Smith", "Mary Jones"], ["[PERSON]"]),
    ("Alan Grant reviewed lot L24-0815.", ["Alan Grant"], ["[PERSON]"]),
    ("Mohammed Al-Rashid described the fault.", ["Mohammed Al-Rashid"], ["[PERSON]"]),
    ("Follow up with Sarah O'Neill.", ["Sarah O'Neill"], ["[PERSON]"]),
    ("Spoke with Wei Zhang about the return.", ["Wei Zhang"], ["[PERSON]"]),
    # --- names after role words
    ("Nurse Priya Patel noticed the alarm.", ["Priya Patel"], ["[PERSON]"]),
    ("Dr Okonkwo-Baines examined the patient.", ["Okonkwo-Baines"], ["[PERSON]"]),
    ("Patient Xiomara Quintero-Vela was discharged.", ["Xiomara Quintero-Vela"], ["[PERSON]"]),
    ("Complainant Thaddeus Wrexham sent photos.", ["Thaddeus Wrexham"], ["[PERSON]"]),
    ("Reporter Ingrid Solvang confirmed the serial.", ["Ingrid Solvang"], ["[PERSON]"]),
    ("Caller Bartholomew Quist asked for a replacement.", ["Bartholomew Quist"], ["[PERSON]"]),
    ("Clinician Zephyrine Adebayo-Okafor approved.", ["Zephyrine Adebayo-Okafor"], ["[PERSON]"]),
    # --- reported by, lower case
    ("reported by jane doe via the portal", ["jane doe"], ["[PERSON]"]),
    ("Complaint reported by nurse okoro ikenna at night.", ["okoro ikenna"], ["[PERSON]"]),
    ("Event submitted by m. fernandez this morning.", ["m. fernandez"], ["[PERSON]"]),
    ("Issue called by Thaddeus via phone.", ["Thaddeus"], ["[PERSON]"]),
    # --- record numbers without a colon
    ("Patient ID 88213 affected.", ["88213"], ["[ID_NUMBER]"]),
    ("Medical record no. 004512 reviewed.", ["004512"], ["[ID_NUMBER]"]),
    ("Medical record number 7781-A attached.", ["7781-A"], ["[ID_NUMBER]"]),
    ("Hospital number H00912 noted.", ["H00912"], ["[ID_NUMBER]"]),
    ("Insurance member ID: XJ-5512-339", ["XJ-5512-339"], ["[ID_NUMBER]"]),
    ("Insurance member ID XJ-5512-339 confirmed.", ["XJ-5512-339"], ["[ID_NUMBER]"]),
    ("Policy number PN-2201-88 covers the device.", ["PN-2201-88"], ["[ID_NUMBER]"]),
    # --- dates of birth without a colon
    ("Date of birth 1961-04-02 confirmed.", ["1961-04-02"], ["[DATE_OF_BIRTH]"]),
    ("born 02/04/1961, treated in March", ["02/04/1961"], ["[DATE_OF_BIRTH]"]),
    ("DOB 2 April 1961", ["2 April 1961"], ["[DATE_OF_BIRTH]"]),
    ("Birthdate 04.02.1961 given by the caller.", ["04.02.1961"], ["[DATE_OF_BIRTH]"]),
    # --- unseparated phone numbers
    ("Contact 6175550100 after 5pm.", ["6175550100"], ["[PHONE]"]),
    ("Mobile +16175550100 is best.", ["16175550100"], ["[PHONE]"]),
    ("Ring 07700900123 to arrange collection.", ["07700900123"], ["[PHONE]"]),
    # --- postcodes outside labels
    ("The clinic in Leeds LS1 4AP returned the unit.", ["LS1 4AP"], ["[POSTCODE]"]),
    ("Shipped to London SW1A 1AA.", ["SW1A 1AA"], ["[POSTCODE]"]),
    ("Sent from Boston, MA 02114 by courier.", ["02114"], ["[POSTCODE]"]),
    ("Returned from Springfield, IL 62704-1234.", ["62704-1234"], ["[POSTCODE]"]),
    ("Clinic in D-80331 reported two events.", ["D-80331"], ["[POSTCODE]"]),
    ("Dispatched to NL-1012 AB.", ["NL-1012 AB"], ["[POSTCODE]"]),
    # --- age and sex
    ("A 67-year-old male collapsed during infusion.", ["67-year-old male"], ["[AGE_SEX]"]),
    ("The 72 year old woman noticed the alarm.", ["72 year old woman"], ["[AGE_SEX]"]),
    ("Pt is 54 y/o F with pump in situ.", ["54 y/o F"], ["[AGE_SEX]"]),
    ("Case: 81yo female, home use.", ["81yo female"], ["[AGE_SEX]"]),
    ("Male aged 45 reported dizziness.", ["aged 45"], ["[AGE_SEX]"]),
    # --- facilities
    ("Treated at Riverside General Hospital on 2026-03-01.", ["Riverside General Hospital"], ["[FACILITY]"]),
    ("Seen at St Mary's Clinic, then home.", ["St Mary's Clinic"], ["[FACILITY]"]),
    ("Transferred to the Summit Medical Centre.", ["Summit Medical Centre"], ["[FACILITY]"]),
    # --- initials
    ("Signed off by J. Smith.", ["J. Smith"], ["[PERSON]"]),
    ("Reviewed with A. B. Jones.", ["A. B. Jones"], ["[PERSON]"]),
    ("Note by J.D. Okafor.", ["J.D. Okafor"], ["[PERSON]"]),
    ("Initials: JD", ["JD"], ["[PERSON]"]),
    ("Witnessed by R. Nkemelu.", ["R. Nkemelu"], ["[PERSON]"]),
    # --- several kinds in one record
    (
        "Reported by Jane Doe (jane.doe@hospital.org, +1 617 555 0100). Patient: John Smith, DOB: 1961-04-02, "
        "MRN 004512. Address: 1 High Street, Leeds LS1 4AP; Card 4111 1111 1111 1111, SSN 123-45-6789.",
        ["Jane Doe", "jane.doe@hospital.org", "617 555 0100", "John Smith", "1961-04-02", "004512", "High Street"],
        ["[PERSON]", "[EMAIL]", "[PHONE]", "[DATE_OF_BIRTH]", "[ID_NUMBER]", "[ADDRESS]", "[CARD_NUMBER]"],
    ),
]

# Text that must come back unchanged: product, lot, change, standard and clinical wording is not personal data.
KEPT = [
    "Lot L24-0815 was built on 2026-10-03 at Riverbend Assembly.",
    "Lot AFD-26-010 and LOT-013 have incomplete traceability.",
    "Firmware 2.10.3.4 showed error E-104 after ECN-4471.",
    "ISO 14971 and IEC 60601-1 apply to the risk file.",
    "EN 60601-1-2 edition 4.1 was referenced; UL 60601 testing passed.",
    "Power Regulation Module Rev B replaced Rev A in Product Rev D.",
    "OrbitCare 300 Rev B, lot SAMPLE-ORBIT-300-LOT-003, mobile app build 4.2.",
    "The patient experienced a delayed alarm; the mobile app showed E-104 and we will address the issue.",
    "Patient Safety Officer reviewed the complaint trend.",
    "Complaint QMS-00044 and QMS-00045 are duplicate candidates for investigation INV-001.",
    "Evidence EV-VS001-003 arrived on 2026-04-08, after the first closure decision.",
    "Serial 1234567890 was returned; S/N 98765432109 was not.",
    "UDI 01234567890 matched GTIN 00812345678905.",
    "Max pressure 300 mmHg; Amber warning shown at 80% load.",
    "A 5-year-old device was serviced twice.",
    "Appendix A. Summary of results; Section B. Results table.",
    "U.S. Food and Drug Administration guidance and the I.V. pump specification were cited.",
    "Supplier NovaCap Components (alias Nova Cap) changed its curing profile in CHG-SUP-PROC-001.",
    "Component C-001 is the Harness Connector from OrbitFlex Electronics.",
    "Shutdown complaints increased after Rev D field deployment (2 of 13 read 4-6% high).",
    "Summit Final Test site MFG-02 released 18 lots in Q1 2026.",
    "Validation test VT-204 PASSED after 1000 h of testing.",
    "Risk RISK-003 is controlled by CTRL-007 (process control).",
    "Daisy chain the two monitors and check the Crystal oscillator drift.",
    "Mark II housing; Grace period of 30 days; Li ion cell at 3.7 V.",
    "Order 2026100300 shipped; ticket 1122334455 closed.",
]


@pytest.mark.parametrize("text, hidden, placeholders", MASKED, ids=[case[0][:40] for case in MASKED])
def test_personal_data_is_masked(text, hidden, placeholders):
    masked = mask_text(text)
    for fragment in hidden:
        assert fragment not in masked, f"{fragment!r} survived: {masked!r}"
    for placeholder in placeholders:
        assert placeholder in masked, f"{placeholder} missing: {masked!r}"


@pytest.mark.parametrize("text", KEPT, ids=[case[:40] for case in KEPT])
def test_investigation_facts_are_kept(text):
    assert mask_text(text) == text


def test_serials_and_lots_are_masked_only_beside_a_patient(monkeypatch):
    sentence = (
        "Complainant Thaddeus Wrexham returned lot L24-0815 and serial SN-4471-X on 2026-10-03. Lot L24-0816 was fine."
    )
    masked = mask_text(sentence)
    assert "Thaddeus Wrexham" not in masked and "L24-0815" not in masked and "SN-4471-X" not in masked
    assert "[LOT]" in masked and "[SERIAL]" in masked
    assert "L24-0816" in masked and "2026-10-03" in masked  # a sentence without a patient keeps its lot
    for patient_side in ("A 67-year-old male used lot L24-0815.", "MRN 004512: device lot L24-0815."):
        assert "L24-0815" not in mask_text(patient_side), patient_side
    monkeypatch.setenv("MDARIX_GENAI_MASK_SERIALS_NEAR_PII", "false")
    assert "L24-0815" in mask_text(sentence) and "Thaddeus Wrexham" not in mask_text(sentence)


# Precision: a staff member's name is masked, but the lot, standard, product and event date beside it are facts of
# the investigation and stay exactly as written.
STAFF_BESIDE_FACTS = [
    ("Dr. Alan Grant reviewed lot L24-0815 on 2026-10-03.", "Alan Grant", ["L24-0815", "2026-10-03"]),
    (
        "Dr. Alan Grant reviewed lot L24-0815 and serial SN-4471-X on 2026-10-03.",
        "Alan Grant",
        ["L24-0815", "SN-4471-X", "2026-10-03"],
    ),
    ("Alan Grant reviewed lot L24-0815.", "Alan Grant", ["L24-0815"]),
    (
        "Engineer Priya Patel tested lot L24-0815 against ISO 14971 on 2026-10-03.",
        "Priya Patel",
        ["L24-0815", "ISO 14971", "2026-10-03"],
    ),
    (
        "Signed off by J. Smith for OrbitCare 300 Rev B lot SAMPLE-ORBIT-300-LOT-003 on 2026-10-03 per IEC 60601-1.",
        "J. Smith",
        ["OrbitCare 300 Rev B", "SAMPLE-ORBIT-300-LOT-003", "2026-10-03", "IEC 60601-1"],
    ),
]


@pytest.mark.parametrize("text, person, facts", STAFF_BESIDE_FACTS, ids=[case[0][:40] for case in STAFF_BESIDE_FACTS])
def test_a_staff_name_beside_investigation_facts_keeps_the_facts(text, person, facts):
    masked = mask_text(text)
    assert person not in masked and "[PERSON]" in masked, masked
    for fact in facts:
        assert fact in masked, f"{fact!r} was masked: {masked!r}"


def test_dictionary_keys_in_any_casing_style_are_recognised():
    for key in ("patientName", "reporterEmail", "reporter-email", "name", "assigned_to", "assignee", "user"):
        assert is_personal_key(key), key
    for key in ("created_by", "reviewed_by", "approvedBy", "reported_by", "signed_by"):
        assert is_personal_key(key), key
    for key in ("patient_harm", "patient_impact", "product", "lot_identifier", "title", "evidence_identifier"):
        assert not is_personal_key(key), key
    assert mask({"patientName": "Jane Doe", "createdBy": "jsmith", "lot": "L-7", "patient_harm": "none"}) == {
        "patientName": "[PERSONAL_DATA]",
        "createdBy": "[PERSONAL_DATA]",
        "lot": "L-7",
        "patient_harm": "none",
    }


def test_nested_values_are_masked_everywhere():
    value = {"notes": ["Reported by Jane Doe", {"text": "Patient ID 88213", "lot": "L24-0815"}], "n": 3}
    assert mask(value) == {
        "notes": ["Reported by [PERSON]", {"text": "Patient ID [ID_NUMBER]", "lot": "L24-0815"}],
        "n": 3,
    }
