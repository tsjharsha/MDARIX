"""Mask personal information before any text leaves for an AI model.

Investigations need product, lot, change, supplier and complaint identifiers, so those are kept. What identifies a
person is replaced with a typed placeholder (``[EMAIL]``, ``[PHONE]``, ``[PERSON]`` ...):

* email addresses, phone numbers (grouped, or 10-11 digits run together), national/insurance/card-style numbers,
  labelled IP addresses, postcodes (UK, US state + ZIP, country-prefixed European codes);
* values after labels such as "Patient:", "Reporter:", "DOB:", "Address:"; record numbers with or without a colon
  ("MRN 004512", "Patient ID 88213", "Medical record no. 004512", "Insurance member ID: XJ-5512-339"); dates of
  birth with or without a colon ("Date of birth 1961-04-02", "born 02/04/1961");
* names after a personal title (Mr, Mrs, Ms, Dr ...), after a role word (Nurse, Patient, Complainant, Reporter,
  Caller ...), after "reported by" in any case, initials with a surname ("J. Smith"), and bare two-token names
  whose first token is a common given name (a built-in list). An unusual given name in free text without a label,
  title or role word is NOT recognised: the documentation says so, and labelled fields stay the reliable path;
* age-and-sex phrases ("67-year-old male"), care facilities after "at" ("at Riverside Hospital");
* the values of dictionary keys that hold personal data (snake_case or camelCase: ``patient_name``,
  ``reporterEmail``, ``name``, ``assigned_to``, ``assignee``, ``user``, any ``*_by`` key).

Device serials, lot numbers, product names, standards and ordinary event dates are kept, because the investigation is
about them. The exception is a serial or lot in the same sentence as a *patient-side* identifier (a patient,
complainant, caller or reporter, a date of birth, a record number, an address, an age with a sex): there the pair
could lead back to the patient through device registries, so it is masked too. A staff member beside a lot ("Dr. Alan
Grant reviewed lot L24-0815") does not identify a patient, so that lot stays
(``MDARIX_GENAI_MASK_SERIALS_NEAR_PII=false`` keeps them all). Masking runs on every model request
(``genai/provider.py``); it can be switched off only for local work on synthetic data
(``MDARIX_GENAI_PII_MASKING=false``), never in staging or production.
"""

from __future__ import annotations

import os
import re

EMAIL = re.compile(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
# Grouped phone numbers: optional country code, then at least three groups (617 555 0100, (617) 555-0100, +44 20 7946
# 0958). Requiring separators keeps lot numbers, dates and serials such as L24-0815 or 2026-10-03 intact.
PHONE = re.compile(r"(?<![\w-])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,5}\)[\s.-]?|\d{2,5}[\s.-])\d{3,4}[\s.-]\d{3,5}(?![\w-])")
# A phone number written without separators: 10 or 11 digits, an optional country code before them. A 10-11 digit
# run right after a serial, lot or order label is a record identifier and is kept (see _plain_phone).
PLAIN_PHONE = re.compile(r"(?<![\w.-])(?:\+\d{1,3}\s?)?\d{10,11}(?![\w-])")
RECORD_LABEL_BEFORE_NUMBER = re.compile(
    r"(?i)\b(?:s/n|sn|serial(?:\s+(?:number|no\.?))?|lot(?:\s+(?:number|no\.?))?|batch|udi|gtin|ref|part(?:\s+number)?|"
    r"order|po|ticket|case|complaint|rma|device\s+id|model|catalog(?:ue)?|item|invoice|tracking|epoch|timestamp)"
    r"\s*[:#]?\s*$"
)
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
# IP addresses only when labelled: a bare dotted number is usually a firmware or software version (2.10.3.4).
IPV4 = re.compile(
    r"(?i)\b(ip(?:\s+address)?|client\s+ip|remote\s+addr(?:ess)?|source\s+ip)(\s*[:=]?\s*)"
    r"(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
)
# An address runs to the end of its clause, commas included ("Address: 1 High Street, Leeds LS1 4AP").
ADDRESS = re.compile(r"(?i)\b((?:home\s+|postal\s+|street\s+)?address)(\s*[:#=]\s*)([^\n;|]{1,160})")
# Postcodes outside a labelled address: UK (LS1 4AP, SW1A 1AA), a US state followed by its ZIP (MA 02114,
# MA 02114-1234) and country-prefixed European codes (D-80331, F-75001, NL-1012 AB). A bare five-digit number is not
# a postcode here: it is as often a count or a record number.
US_STATES = (
    "AL|AK|AZ|AR|CA|CO|CT|DC|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|"
    "OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY"
)
POSTCODE = re.compile(
    r"\b(?:[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}"
    r"|(?<=\b(?:" + US_STATES + r")\s)\d{5}(?:-\d{4})?"
    r"|(?:D|F|NL|CH|DK|PL|CZ|AT|BE|ES|IT|PT|SE|NO|FI|IE|LU)-\d{4,5}(?:\s[A-Z]{2})?)\b"
)
# A labelled value: "Patient: Jane Doe", "Reporter name = J. Smith", "DOB: 1961-04-02", "Address: 1 High St". The label
# needs a ':', '#' or '=' so ordinary sentences ("the patient experienced", "mobile app", "address the issue") stay.
LABELLED = re.compile(
    r"(?i)\b(patient(?:\s+name)?|reporter(?:\s+name)?|caller|complainant|user\s+name|full\s+name|contact(?:\s+name)?|"
    r"date\s+of\s+birth|d\.?o\.?b\.?|birth\s*date|mrn|medical\s+record(?:\s+(?:number|no\.?))?|nhs\s+number|"
    r"hospital\s+number|patient\s+(?:id|identifier|number|no\.?)|ssn|social\s+security(?:\s+number)?|"
    r"(?:health\s+)?insurance\s+(?:member\s+)?(?:id|number|no\.?)|member\s+id|policy\s+number|"
    r"national\s+insurance(?:\s+number)?|nino|passport(?:\s+number)?|driv(?:ing|er'?s?)\s+licen[cs]e(?:\s+number)?|"
    r"initials|home\s+address|address|phone|telephone|mobile|e-?mail)(\s*[:#=]\s*)([^\n;,|]{1,80})"
)
# Record numbers often follow their label with a space only: "MRN 004512", "Patient ID 88213", "Medical record no.
# 004512", "NHS number 943 476 5919", "Insurance member ID XJ-5512-339".
RECORD_NUMBER = re.compile(
    r"(?i)\b(mrn|nhs\s+number|hospital\s+number|medical\s+record(?:\s+(?:number|no\.?))?|"
    r"patient\s+(?:id|identifier|number|no\.?)|(?:health\s+)?insurance\s+(?:member\s+)?(?:id|number|no\.?)|"
    r"member\s+id|policy\s+number|national\s+insurance(?:\s+number)?|nino|passport(?:\s+number)?|ssn)"
    r"(\s+)((?=[\w-]*\d)[A-Z0-9][\w-]{2,}(?:\s\d{3,}){0,3})"
)
# A date of birth without a colon: "Date of birth 1961-04-02", "born 02/04/1961", "born on 2 April 1961".
DATE = (
    r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+,?\s+\d{4}|"
    r"[A-Z][a-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})"
)
BIRTH_DATE = re.compile(r"(?i)\b(date\s+of\s+birth|d\.?o\.?b\.?|birth\s*date|born(?:\s+on)?)(\s+)" + DATE)
# Words for a person's role; a name after one of them is a person ("Nurse Priya Patel", "reported by nurse j. doe").
ROLE_WORDS = (
    "nurse|patient|complainant|reporter|caller|clinician|physician|surgeon|consultant|doctor|technician|biomed|"
    "technologist|paramedic|midwife|pharmacist|therapist|carer|caregiver|relative|guardian|parent|mother|father|"
    "wife|husband|spouse|user|operator|customer|witness|contact|anaesthetist|anesthesiologist|radiographer|"
    "distributor|representative|rep|engineer|staff"
)
# A name: optional initials, a token, optional middle initial, optional second token (any case: the caller decides).
NAME_ANY_CASE = r"(?:[A-Za-z]\.\s*)*[A-Za-z][a-zA-Z'-]+(?:\s+[A-Za-z]\.)?(?:\s+[A-Za-z][a-zA-Z'-]+)?"
NAME_TITLE_CASE = r"(?:[A-Z]\.\s*)*[A-Z][a-zA-Z'-]+(?:\s+[A-Z]\.)?(?:\s+[A-Z][a-zA-Z'-]+)?"
REPORTED_BY = re.compile(
    r"(?i)\b(reported by|called by|submitted by|contacted by|spoke (?:with|to)|interviewed|signed by|witnessed by|"
    r"notified by|escalated by|complaint from|call from)(\s+)((?:the\s+|a\s+|an\s+)?(?:" + ROLE_WORDS + r")\s+)?"
    r"(" + NAME_ANY_CASE + r")"
)
# Lower-case words after "reported by" that are not a name ("reported by phone", "reported by the distributor").
NOT_A_NAME = frozenset(
    """the a an our their his her its phone email e-mail fax letter post mail telephone in on at via by to of for
    from with during after before field service sales support hospital clinic site customer end user staff team
    this that these those one two three several multiple another same""".split()
)
TITLE = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof|Sister)\.?\s+" + NAME_TITLE_CASE)
ROLE_NAME = re.compile(r"\b(" + ROLE_WORDS.title() + r"|" + ROLE_WORDS.upper() + r")\.?\s+(" + NAME_TITLE_CASE + r")")
# Title-case tokens that follow a role word or a given name without being a surname.
NOT_A_SURNAME = frozenset(
    """safety harm impact record records data information monitoring population outcome outcomes report reported
    reports id identifier number experience experiences history care centre center hospital clinic infirmary trust
    group street road avenue lane drive close court place square park module board sensor valve pump rev revision
    series model version station university medical health surgery ward unit department service services
    controller monitor device devices system systems platform instrument instruments inc ltd llc gmbh plc
    corporation company plastics electronics components packaging boardworks hotline support line team feedback
    complaint complaints investigation investigations review reviews note notes summary file ii iii iv complete
    pressure flow load alert warning chain period scanner shift jar filter stick oscillator""".split()
)
# An initial (or two) followed by a surname: "J. Smith", "J.D. Smith", "A. B. Jones". Abbreviations such as U.S. or
# I.V. have no surname after them; "Appendix A. Summary" is a heading, not a name (see _initials).
INITIALS_NAME = re.compile(r"\b((?:[A-Z]\.\s?)+)([A-Z][a-z]{2,})\b")
NOT_BEFORE_INITIALS = frozenset(
    "appendix section figure table annex part step item exhibit schedule clause note option phase grade class type "
    "plan rev revision chapter paragraph attachment form block group zone level stage".split()
)
ORGANISATION_INITIALS = frozenset({"US", "UK", "EU"})
ORGANISATION_INITIALS_FOLLOWERS = frozenset(
    {"agency", "administration", "department", "food", "government", "regulator", "regulation"}
)
# A care facility named after "at": "at Riverside Hospital", "at St Mary's Clinic", "at the Summit Medical Centre".
FACILITY = re.compile(
    r"\b(at|from|to|of)\s+(the\s+)?((?:St\.?\s+)?[A-Z][\w'-]*(?:\s+(?:of|the|and|[A-Z][\w'-]*)){0,4}\s+"
    r"(?:Hospital|Clinic|Infirmary|Medical\s+Cent(?:er|re)|Health\s+Cent(?:er|re)|Surgery|Hospice|Care\s+Home|"
    r"Nursing\s+Home))\b"
)
# Age and sex together identify a person in a small population: "67-year-old male", "a 67 year old woman",
# "67 y/o F", "67yo female", "female aged 67", "F/67". An age alone ("5-year-old device") stays.
AGE_SEX = re.compile(
    r"(?i)\b(?:\d{1,3}[-\s]?(?:years?|yrs?|y)[-\s]?(?:old|o)[-\s]?(?:male|female|man|woman|boy|girl|gentleman|"
    r"lady|patient|m|f)\b"
    r"|\d{1,3}\s?(?:yo|y/o)\s?(?:m|f|male|female)?\b"
    r"|(?:male|female|man|woman|boy|girl|patient)\s+(?:patient\s+)?aged\s+\d{1,3}\b"
    r"|(?<!\w)[MF]/\d{1,3}\b)"
)
# Dictionary keys whose values identify a person. Clinical keys such as patient_harm or patient_impact are kept.
# Keys are normalised to snake_case first (patientName -> patient_name, reporter-email -> reporter_email).
PERSONAL_KEYS = re.compile(
    r"(?i)^(?:[a-z0-9]+_)*(e_?mail|phone|phone_number|mobile|telephone|patient_name|patient_id|patient_identifier|"
    r"reporter|reporter_name|complainant|complainant_name|caller_name|contact_name|dob|date_of_birth|birth_?date|"
    r"address|street|street_address|home_address|postcode|postal_code|zip|zip_code|ssn|mrn|national_id|"
    r"first_name|last_name|full_name|person_name|name|assigned_to|assignee|user|username|user_name|initials|"
    r"member_id|policy_number|nhs_number|insurance_number|passport_number)$|^(?:[a-z0-9]+_)*[a-z0-9]+_by$"
)
CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
# A serial, lot, batch or device identifier, masked only in a sentence that also names a person (module doc).
SERIAL_NEAR_PERSON = re.compile(
    r"(?i)\b((?:s/n|sn|serial(?:\s+(?:number|no\.?))?|lot(?:\s+(?:number|no\.?))?|batch(?:\s+(?:number|no\.?))?|"
    r"udi(?:-di|-pi)?|gtin|device\s+(?:id|identifier|serial))\s*[:#=]?\s*)((?=[\w-]*\d)[A-Z0-9][\w-]{3,})"
    r"|\b((?:lot|batch|sn|udi)-)([\w-]{2,})"
)
# Placeholders that always point at the patient side of a record; a lot or serial beside one is masked.
PATIENT_PLACEHOLDERS = ("[DATE_OF_BIRTH]", "[ID_NUMBER]", "[ADDRESS]", "[AGE_SEX]", "[POSTCODE]")
# A masked name is patient-side when a patient-side label or role word (or "reported by", "complaint from") stands
# just before it: "Patient: [PERSON]", "Complainant [PERSON]", "reported by nurse [PERSON]". A name after a title or
# a staff role ("Dr. [PERSON] reviewed", "Engineer [PERSON]") is not.
PATIENT_PERSON = re.compile(
    r"(?i)\b(?:patient(?:\s+name)?|complainant|caller|reporter(?:\s+name)?|user|customer|carer|caregiver|relative|"
    r"guardian|parent|mother|father|wife|husband|spouse|witness|contact(?:\s+name)?|full\s+name|reported\s+by|"
    r"called\s+by|submitted\s+by|complaint\s+from|call\s+from)\b[^\[\n]{0,16}\[PERSON\]"
)
SENTENCE = re.compile(r"(?<=[.!?;])\s+|\n+")

_ID_LABELS = {"mrn", "medical record", "medical record number", "medical record no", "nhs number", "hospital number"}
_ID_LABELS |= {"ssn", "social security", "social security number", "member id", "policy number", "nino", "passport"}
_ID_LABELS |= {"passport number", "national insurance", "national insurance number"}

# Common given names (lower case). A Title-case token in this set followed by a Title-case surname is a person.
# Names that are also everyday technical words (Max, Amber, Crystal, Grace, Mark II ...) are left out on purpose.
GIVEN_NAMES = frozenset(
    """aaron abdul abigail adam adrian agnes ahmed aidan aisha alan albert alex alexander alexandra alfred ali alice
    alicia alison allan allison amanda amelia amir amy ana andrea andrew andy angela anil anita ann anna anne
    annette anthony antonio arjun arthur ashley audrey austin ava barbara barry beatrice becky ben benjamin bernard
    beth betty beverly billy bob bobby bonnie brad bradley brandon brenda brian bridget brittany bruce bryan
    caitlin cameron carl carla carlos carmen carol caroline carolyn carrie catherine cathy cecilia chad charles
    charlie charlotte cheryl chloe chris christian christina christine christopher cindy claire clara clare
    claudia clifford colin connor craig cynthia daniel daniela danielle danny darren dave david deborah debra denise
    dennis derek diana diane dmitri dominic donald donna doris dorothy douglas duncan dylan eddie edith edward edwin
    eileen elaine eleanor elena elizabeth ella ellen emily emma eric erica erik erin ernest esther ethan eugene eva
    evan evelyn fatima felix fiona florence frances francis frank fred frederick gabriel gail gary gavin gemma
    geoffrey george gerald gillian gina glen glenn gloria gordon graham greg gregory gwen hannah harold harriet
    harry hassan hazel heather heidi helen henry holly howard hugh hugo ian imran irene isaac isabel isabella ivan
    jack jackie jacob jacqueline jake james jamie jane janet janice jasmine jason javier jay jean jeff jeffrey
    jennifer jenny jeremy jerry jess jesse jessica jill jim jimmy joan joanna joanne joe joel john johnny jon
    jonathan jordan jorge jose joseph josephine josh joshua joyce juan judith judy julia julian julie justin kai
    karen karl kate katherine kathleen kathryn kathy katie kay keith kelly ken kenneth kevin kim kimberly kirsty
    kristen kristin kyle larry laura lauren laurence lawrence leah leo leon leonard leslie lewis liam lily linda
    lindsay lisa liz lloyd logan lois lorraine louis louise lucas lucy luis luke lydia lynn madison malcolm manuel
    marc marcus margaret maria marie marilyn marion mark martha martin martina mary matt matthew maureen maya megan
    melanie melissa michael michelle miguel mike mildred miriam mohamed mohammed molly monica morgan muhammad nancy
    naomi natalie nathan neil nicholas nick nicola nicole nigel nina noah nora norman olivia omar oscar owen pamela
    patricia patrick paul paula pauline pedro peggy peter phil philip phillip phyllis priya rachel rafael ralph
    randy raymond rebecca reginald rhonda richard rick ricky rita rob robert roberta robin rodney roger ronald rosa
    rose rosemary ross roy russell ruth ryan sally sam samantha samuel sandra sara sarah scott sean sebastian
    shannon sharon shaun shawn sheila shirley simon sofia sonia sophia sophie stacey stanley stella stephanie
    stephen steve steven stuart sue susan suzanne sylvia tanya tara ted teresa terry thelma theodore theresa
    thomas tim timothy tina todd tom tommy tony tracey tracy travis trevor tyler valerie vanessa vera veronica
    victor victoria vincent vivian wayne wendy wesley william willie yasmin yvonne zachary zoe
    aarav aditya ananya arun deepak divya kavya lakshmi meera neha nikhil pooja rahul raj rajesh ravi rohan sanjay
    shreya sunita suresh vijay vikram wei ming yuki hiroshi kenji sakura haruto mei ji-woo seo-yun
    ahmad amina ayesha bilal farah hamza khalid layla maryam mustafa nadia noor rania samir tariq yusuf zainab
    chiamaka chidi emeka ngozi adaeze kwame kofi akosua abebe tesfaye amara zuri sven lars anders bjorn
    ingrid astrid freya hans klaus jurgen matthias stefan ulrich wolfgang anja katrin sabine ute pierre jacques
    francois luc michel philippe sylvie nathalie chantal giovanni luca marco matteo paolo giulia chiara
    francesca alessandro diego mateo valentina camila mariana luisa pablo""".split()
)
GIVEN_NAME = re.compile(r"\b([A-Z][a-z]+(?:-[A-Z][a-z]+)?)\s+(?:([A-Z])\.\s+)?([A-Z](?:[a-zA-Z'-]+|\.))(?![\w'-])")


def enabled() -> bool:
    """Masking is on unless switched off for local work on synthetic data (staging and production ignore that)."""
    from backend.app.runtime_env import is_production_like

    if is_production_like():
        return True
    return os.getenv("MDARIX_GENAI_PII_MASKING", "true").strip().lower() not in {"0", "false", "no", "off"}


def mask_serials_near_pii() -> bool:
    """Serials and lots in a sentence that names a person are masked unless an operator switched that off."""
    return os.getenv("MDARIX_GENAI_MASK_SERIALS_NEAR_PII", "true").strip().lower() not in {"0", "false", "no", "off"}


def _luhn(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


def _card(match: re.Match) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return "[CARD_NUMBER]" if 13 <= len(digits) <= 19 and _luhn(digits) else match.group(0)


def _placeholder(label: str) -> str:
    label = re.sub(r"\s+", " ", label.lower()).replace(".", "").strip()
    if label in {"date of birth", "dob", "birthdate", "birth date", "born", "born on"}:
        return "[DATE_OF_BIRTH]"
    if label in _ID_LABELS or label.startswith(("patient id", "patient identifier", "patient number", "patient no")):
        return "[ID_NUMBER]"
    if "insurance" in label or "licen" in label or label.startswith("passport"):
        return "[ID_NUMBER]"
    if label.endswith("address"):
        return "[ADDRESS]"
    if label in {"phone", "telephone", "mobile"}:
        return "[PHONE]"
    if label in {"email", "e-mail"}:
        return "[EMAIL]"
    return "[PERSON]"


def _plain_phone(match: re.Match) -> str:
    """A 10-11 digit run is a phone number unless a serial, lot or order label stands right before it."""
    before = match.string[max(0, match.start() - 40) : match.start()]
    return match.group(0) if RECORD_LABEL_BEFORE_NUMBER.search(before) else "[PHONE]"


def _title_case(token: str) -> bool:
    return token[:1].isupper() and (token[1:].islower() or token.endswith("."))


def _reported_by(match: re.Match) -> str:
    """The name after "reported by": Title-case tokens, or two lower-case tokens that are not ordinary words."""
    lead, space, role, name = match.group(1), match.group(2), match.group(3) or "", match.group(4)
    tokens = name.split()
    if _title_case(tokens[0]):
        kept = []
        while tokens and _title_case(tokens[0]):
            kept.append(tokens.pop(0))
        return f"{lead}{space}{role}[PERSON]" + ("" if not tokens else " " + " ".join(tokens))
    if len(tokens) >= 2 and not any(token.lower().rstrip(".") in NOT_A_NAME for token in tokens[:2]):
        return f"{lead}{space}{role}[PERSON]" + ("" if len(tokens) == 2 else " " + " ".join(tokens[2:]))
    return match.group(0)


def _role_name(match: re.Match) -> str:
    first = match.group(2).split()[0].lower().rstrip(".")
    if first in NOT_A_SURNAME or first in {"id", "no"}:
        return match.group(0)
    return f"{match.group(1)} [PERSON]"


def _given_name(match: re.Match) -> str:
    first, surname = match.group(1), match.group(3)
    if first.lower() not in GIVEN_NAMES or surname.lower() in NOT_A_SURNAME:
        return match.group(0)
    return "[PERSON]"


def _initials(match: re.Match) -> str:
    before = match.string[: match.start()].rstrip()
    previous = before.split()[-1].lower().strip(":;,.") if before else ""
    initials = re.sub(r"[^A-Z]", "", match.group(1))
    surname = match.group(2).lower()
    if initials in ORGANISATION_INITIALS and surname in ORGANISATION_INITIALS_FOLLOWERS:
        return match.group(0)
    if previous in NOT_BEFORE_INITIALS or surname in NOT_A_SURNAME:
        return match.group(0)
    return "[PERSON]"


def _facility(match: re.Match) -> str:
    return f"{match.group(1)} {match.group(2) or ''}[FACILITY]"


def _serial(match: re.Match) -> str:
    label = (match.group(1) or match.group(3)).lower()
    placeholder = "[LOT]" if label.startswith(("lot", "batch")) else "[SERIAL]"
    return f"{match.group(1) or match.group(3)}{placeholder}"


def _names_a_patient(sentence: str) -> bool:
    """True when a masked sentence carries a patient-side identifier (module doc): only then is its lot masked."""
    return any(token in sentence for token in PATIENT_PLACEHOLDERS) or bool(PATIENT_PERSON.search(sentence))


def _serials_near_people(text: str) -> str:
    """Serial, lot and batch identifiers in sentences that also identify a patient."""
    parts = SENTENCE.split(text)
    separators = SENTENCE.findall(text)
    out = []
    for index, part in enumerate(parts):
        if _names_a_patient(part):
            part = SERIAL_NEAR_PERSON.sub(_serial, part)
        out.append(part)
        if index < len(separators):
            out.append(separators[index])
    return "".join(out)


def mask_text(text: str) -> str:
    """The text with personal information replaced by typed placeholders."""
    if not text:
        return text
    masked = EMAIL.sub("[EMAIL]", text)
    masked = ADDRESS.sub(lambda m: f"{m.group(1)}{m.group(2)}[ADDRESS]", masked)
    masked = LABELLED.sub(lambda m: f"{m.group(1)}{m.group(2)}{_placeholder(m.group(1))}", masked)
    masked = BIRTH_DATE.sub(lambda m: f"{m.group(1)}{m.group(2)}[DATE_OF_BIRTH]", masked)
    masked = RECORD_NUMBER.sub(lambda m: f"{m.group(1)}{m.group(2)}[ID_NUMBER]", masked)
    masked = REPORTED_BY.sub(_reported_by, masked)
    masked = TITLE.sub("[PERSON]", masked)
    masked = ROLE_NAME.sub(_role_name, masked)
    masked = FACILITY.sub(_facility, masked)
    masked = GIVEN_NAME.sub(_given_name, masked)
    masked = INITIALS_NAME.sub(_initials, masked)
    masked = AGE_SEX.sub("[AGE_SEX]", masked)
    masked = SSN.sub("[ID_NUMBER]", masked)
    masked = CARD.sub(_card, masked)
    masked = PHONE.sub("[PHONE]", masked)
    masked = PLAIN_PHONE.sub(_plain_phone, masked)
    masked = POSTCODE.sub("[POSTCODE]", masked)
    masked = IPV4.sub(lambda m: f"{m.group(1)}{m.group(2)}[IP_ADDRESS]", masked)
    if mask_serials_near_pii():
        masked = _serials_near_people(masked)
    return masked


def is_personal_key(key) -> bool:
    """True for a dictionary key that holds personal data, whatever its casing style."""
    normalised = CAMEL_BOUNDARY.sub("_", str(key)).replace("-", "_").replace(" ", "_").lower()
    return bool(PERSONAL_KEYS.match(normalised))


def mask(value):
    """Mask strings anywhere in a JSON-like value; values under personal-data keys are replaced entirely."""
    if isinstance(value, dict):
        return {
            key: ("[PERSONAL_DATA]" if is_personal_key(key) and item not in (None, "") else mask(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [mask(item) for item in value]
    if isinstance(value, tuple):
        return tuple(mask(item) for item in value)
    if isinstance(value, str):
        return mask_text(value)
    return value
