"""Validated import of products, lots and complaints: CSV uploads (trials and workspaces) and mapped connector records.

Every batch is checked in full before anything is written: only template columns are accepted, references must
resolve inside the tenant, and text that holds personal data is rejected: anything masking would replace (names,
phone numbers, emails, dates of birth, patient or record numbers, addresses ... genai/pii.py), and labels such as
"MRN" or "date of birth" that masking leaves in place. By default a batch with any problem imports nothing. An
uploader may choose instead (``on_problems=skip``) to import the rows that pass and get the others back as a rejects file with each
row's problems (returned, never stored), and (``personal_data=mask``) to have personal data in free text replaced by
typed placeholders such as [PERSON] or [PHONE] (genai/pii.py) instead of refused; what masking cannot remove is still
refused. A problem of the file itself (columns, encoding, size, limits) always stops the whole file. An ImportPolicy
sets the source label recorded on each row and any row or file limits (free trials have both).

Files arrive as bytes (a raw ``text/csv`` body or a multipart upload, ``read_upload``) and are decoded as UTF-8, with
or without a byte-order mark, else as Windows text (Excel's plain CSV), said back as a note; bytes neither defines
refuse the file. The delimiter is detected from the header line (comma, semicolon or tab, as spreadsheets in
different countries save them). A workbook is read from its first visible sheet that holds the template's columns
(or the sheet the uploader names), and the column names are found below a title or blank rows (stage 4, J6).

Dates are YYYY-MM-DD, or DD/MM/YYYY or MM/DD/YYYY in the order the uploader declares (``date_format`` DMY or MDY) or
the file shows (``AUTO``: a day over 12, or a header such as "Event Date (DD/MM/YYYY)"; when nothing in the file
tells, the organization's usual order), because 03/04/2026 is a different day in each. "14-Mar-2026" and Excel day
numbers are read in any order. A date before 1970, or a past event dated in the future, is refused (J41). Whole
numbers read "1,25,000", "1,250" and "1250,00" alike; "1.250" is read by the chosen number format and refused, with
the choice named, when it would not be whole (``number_format``).
"""

from __future__ import annotations

import csv
import io
import itertools
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from backend.app import product_facts
from backend.app.csv_safe import FORMULA_TRIGGERS
from backend.app.db.models.foundation import (
    Complaint,
    Investigation,
    InvestigationComplaint,
    LotBatch,
    ManufacturingSite,
    Product,
    ProductVersion,
)
from backend.app.trial import business_imports, insight_questions
from backend.app.trial.columns import examples as column_examples
from backend.app.trial.columns import match as columns_match
from backend.app.trial.sample_data import SAMPLE_SOURCE
from backend.app.trial.service import TRIAL_FILE_LIMIT_BYTES, TRIAL_ROW_LIMIT
from backend.app.intake import case_import

UPLOAD_SOURCE = "TRIAL_UPLOAD"
WORKSPACE_UPLOAD_SOURCE = "CSV_IMPORT"
MAX_ISSUES = 50
# Rows one file (or one connector sync) may bring in at once; larger loads are split, so a request stays short.
MAX_ROWS_PER_FILE = 50_000


@dataclass(frozen=True)
class ImportPolicy:
    source: str
    row_limit: int | None = None
    file_limit_bytes: int = 10 * 1024 * 1024
    file_too_large: str = "Files can be up to 10 MB"
    limit_label: str = "your workspace"
    # An Excel workbook's total unpacked size (backend/app/trial/xlsx.py): a 2 MB trial file that unpacks to more is a
    # "zip bomb", not an export.
    xlsx_max_bytes: int = 60 * 1024 * 1024
    # A complaints file may name products, versions and lots not loaded yet: with this they are added from it (a free
    # trial starts from one complaints export); without it each must be loaded first (an organization's master data).
    create_references: bool = False
    # A governed import: rows set aside are stored for correction (R14), personal data masked, every written row keeps
    # its lineage (R16) and the run its data-quality report (R17). A free trial is governed too (0.10.56): the trial
    # and the MVP behave the same once the data is in.
    quarantine: bool = False


TRIAL_POLICY = ImportPolicy(
    source=UPLOAD_SOURCE,
    row_limit=TRIAL_ROW_LIMIT,
    file_limit_bytes=TRIAL_FILE_LIMIT_BYTES,
    file_too_large="Files can be up to 2 MB during the free trial",
    limit_label="your trial",
    xlsx_max_bytes=20 * 1024 * 1024,
    create_references=True,
    quarantine=True,
)
WORKSPACE_POLICY = ImportPolicy(source=WORKSPACE_UPLOAD_SOURCE, quarantine=True)

# What a column is for, in plain words, for the columns whose meaning changes what MDARIX finds (shown beside each
# template in the import panel; templates_for() keeps only the template's own columns).
COLUMN_HELP: dict[str, dict[str, str]] = {
    "products": {
        "version_release_date": "The day the version was released (YYYY-MM-DD). A version younger than 90 days is "
        "compared with the version it replaced, from this day.",
        "device_category": "Implant, single-use, reusable (or capital equipment), software, IVD or kit. It decides "
        "which report fields MDARIX fills (an implant, the software version) and is shown in Help › What MDARIX "
        "covers.",
        "single_use": "Y or N: labelled for single use. A single-use product's trend is counted by calendar day, or "
        "with a use period by the units still in use.",
        "use_period_days": "For a single-use product, how many days a unit stays in use after its lot's release (a "
        "whole number). The trend check then counts each lot's units as in use only for those days.",
    },
    "lots": {
        "version": "The product version the lot builds. Its complaints are counted against this version's lots.",
        "manufacture_date": "The day the lot was released to the field (YYYY-MM-DD). Its units count from this day.",
        "quantity": "How many devices the lot released, a whole number (1,250 is fine). With a quantity on every lot "
        "of a version, the trend check counts complaints per unit in the field instead of per calendar day, so a "
        "version shipped in growing numbers is not mistaken for a rising trend.",
        "expiry_date": "The lot's expiry (use-by) date, if it has one (YYYY-MM-DD): report worksheets fill their "
        "expiration date from it.",
    },
    "complaints": {
        "awareness_date": "When your organization first learned of the event (YYYY-MM-DD): reporting clocks start "
        "here.",
        "country": "Where the event happened: decides which market's reporting window applies.",
        "death": "Y or N. A death reported starts the reporting clocks.",
        "serious_injury": "Y or N. A serious injury reported starts the reporting clocks.",
        "malfunction": "Y or N. A malfunction starts the reporting clocks of markets that report malfunctions.",
        "status": "Your quality system's status as it is (Open, Closed, Cancelled, Void, Inquiry...): cancelled records "
        "and inquiries stay visible, and the second look checks them for complaint signs.",
        "product_name": "The product's name. During a free trial a product, version or lot the complaints name but you "
        "have not loaded is added from this file, under this name.",
        "problem_code": "Your problem code. Signals group by product version and problem code.",
        "triage_date": "The day your quality system triaged the complaint (YYYY-MM-DD). With the triage columns MDARIX "
        "keeps your QMS triage: a complaint with no harm flag is accepted as triaged, one with a death, an injury, a "
        "malfunction or harm words waits for a person to confirm it.",
        "triage_severity": "The severity your QMS triage gave (Negligible, Minor, Serious, Critical, Catastrophic or "
        "your own scale's words, mapped like 'severity').",
        "triage_owner": "Who owns the triage in your QMS: a role or a team (Complaint unit), not a person's name.",
        "immediate_action": "What was done at once (user told how to stay safe, device taken out of use), or blank.",
        "use_environment": "Where the device was used (hospital ward, intensive care unit, operating theatre, home, "
        "ambulance, clinic): proposed for a person to confirm. Any other value stays Unknown, shown as you gave it.",
        "user_type": "Who used it (healthcare professional, lay user, patient, service engineer): proposed for a person "
        "to confirm. Any other value stays Unknown, shown as you gave it.",
    },
    "lot_genealogy": {
        "component_lot_id": "The component's own lot that went into this lot (a sensor lot, for example). An investigation's lot "
        "impact lists every lot built with the same component lot.",
    },
    "distribution": {
        "lot_id": "The lot shipped. A row for a lot not loaded yet is set aside with its reason.",
        "consignee": "The organization the units went to: a hospital, a distributor or a clinic. Never a patient or "
        "another person: names of people are refused.",
        "country": "The two-letter ISO country code of the consignee (IN, US, DE...).",
        "quantity": "Units shipped, a whole number. Units shipped beyond the lot's units released are flagged in the "
        "data-quality report.",
        "ship_date": "The day the units left (YYYY-MM-DD).",
    },
}
# Templates a free trial offers and a pilot does not yet (owner decision, 1 Nov 2026: lot impact, T-G5, stays hidden
# on a pilot until the MVP plan schedules G5).
TRIAL_ONLY = frozenset({"distribution"})


def offered(entity: str, policy: "ImportPolicy") -> bool:
    from backend.app.feature_set import routine_path

    if entity == "cases" and not routine_path():  # B7a switched off: no Cases template
        return False
    return entity not in TRIAL_ONLY or policy.source == UPLOAD_SOURCE


def column_help(entity: str) -> dict[str, str]:
    """The help for the entity's own columns, in template order."""
    spec = TEMPLATES.get(entity) or {}
    columns = [*spec.get("required", []), *spec.get("optional", [])]
    known = COLUMN_HELP.get(entity, {})
    return {column: known[column] for column in columns if column in known}


TEMPLATES: dict[str, dict] = {
    "products": {
        "title": "Products and versions",
        "required": ["product_id", "product_name"],
        # A version is optional so sources that only list products (e.g. a PLM product list) can load them.
        "optional": [
            "version",
            "product_family",
            "version_release_date",
            "device_category",
            "single_use",
            "use_period_days",
        ],
        "example": [
            ["PUMP-200", "AquaFlow 200 Infusion Pump", "Rev C", "Infusion therapy", "2026-03-15", "Reusable", "N", ""],
            ["PUMP-200", "AquaFlow 200 Infusion Pump", "Rev D", "Infusion therapy", "2026-07-01", "Reusable", "N", ""],
        ],
    },
    "lots": {
        "title": "Lots and batches",
        "required": ["lot_id", "product_id", "version"],
        # quantity: devices the lot released; the trend check then counts complaints per unit in the field.
        "optional": ["manufacture_date", "site_id", "quantity", "expiry_date"],
        "example": [
            ["L24-0815", "PUMP-200", "Rev D", "2026-07-20", "", "250", ""],
            ["L24-0902", "PUMP-200", "Rev D", "2026-08-11", "", "300", ""],
        ],
    },
    "complaints": {
        "title": "Complaints",
        "required": ["complaint_id", "product_id", "description"],
        "optional": [
            "version",
            "lot_id",
            "event_date",
            "received_date",
            "status",
            # Regulatory details from the quality system (none identifies a person).
            "awareness_date",
            "severity",
            "country",
            "reporter_type",
            "complaint_type",
            "problem_code",
            "serial_number",
            "udi",
            "device_returned",
            "patient_involved",
            "serious_injury",
            "death",
            "malfunction",
            "product_name",
            "use_environment",
            "user_type",
            # T-D9 (0.10.93, B2): the triage done in the QMS (spec 3.4).
            "triage_date",
            "triage_severity",
            "triage_owner",
            "immediate_action",
            # B7 (spec 3.3, BK-12): the MDARIX ID of a complaint exported for QMS entry; the row merges into it.
            "mdarix_ref",
        ],
        "example": [
            [
                "CMP-10021",
                "PUMP-200",
                "Occlusion alarm sounded with no occlusion present. Device returned for evaluation.",
                "Rev D",
                "L24-0815",
                "2026-08-28",
                "2026-08-30",
                "open",
                "2026-08-30",
                "major",
                "IE",
                "Healthcare professional",
                "Device malfunction",
                "ALM-OCC-FALSE",
                "SN-200D-004471",
                "",
                "Y",
                "Y",
                "N",
                "N",
                "Y",
                "AquaFlow 200 Infusion Pump",
                "Intensive care unit",
                "Healthcare professional",
                "2026-08-31",
                "Minor",
                "Complaint unit",
                "Infusion moved to a backup pump; device taken out of use",
                "",
            ],
            # The investigations example links both complaints, so the templates load in the order they are offered
            # (FUN-10).
            [
                "CMP-10022",
                "PUMP-200",
                "Occlusion alarm during infusion; the line was clear when checked.",
                "Rev D",
                "L24-0902",
                "2026-09-01",
                "2026-09-02",
                "open",
                "2026-09-02",
                "major",
                "IE",
                "Healthcare professional",
                "Device malfunction",
                "ALM-OCC-FALSE",
                "SN-200D-004519",
                "",
                "N",
                "Y",
                "N",
                "N",
                "Y",
                "AquaFlow 200 Infusion Pump",
                "Intensive care unit",
                "Healthcare professional",
                "",
                "",
                "",
                "",
                "",
            ],
        ],
    },
    **business_imports.TEMPLATES,
    # B7 step 5: call logs from a call centre or CRM, each row a Case to check (backend/app/intake/case_import.py).
    "cases": case_import.TEMPLATE,
}
COLUMN_HELP["cases"] = case_import.HELP
# Yes/no columns, and columns that hold longer text than the 255-character default.
FLAG_COLUMNS = {"device_returned", "patient_involved", "serious_injury", "death", "malfunction"}
FLAG_VALUES = {"y": True, "yes": True, "true": True, "1": True, "n": False, "no": False, "false": False, "0": False}
# What registers write for "not known" in a yes/no column: read as blank (unknown), never as No.
FLAG_NOT_KNOWN = frozenset({"na", "n/a", "-", "--", "unknown", "not known", "not applicable"})
FLAG_HINT = "use Y, N, Yes, No, 1 or 0, or leave it blank (or NA) when it is not known."
LONG_TEXT = {"description": 4000, "immediate_action": 4000, "text": 4000, "question": 4000, "content": 20000}

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/#:-]{0,119}$")
# A version may carry build metadata, as software versions do ("1.4.2+build", J41).
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/#:+-]{0,119}$")
PERSONS_NAME = "a person's name"
# Personal data is found by masking (genai/pii.py), so refusing catches everything masking would replace. These
# patterns are a second net for what masking leaves in place: labels ("MRN", "date of birth", "Aadhaar") and a few
# looser layouts. (pattern, what it found, whether it matches only a label rather than the value).
_PERSONAL_DATA = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "an email address", False),
    (re.compile(r"(?<!\w)(\+\d{1,3}[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\w)"), "a phone number", False),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "a national ID number", False),
    (re.compile(r"\b(d\.?o\.?b\.?|date of birth|born on|birth ?date)\b", re.I), "a date of birth", True),
    (
        re.compile(
            r"\b(mrn|medical record|patient (id|no|number|name)|ssn|social security|nhs (no|number)|aadhaar)\b",
            re.I,
        ),
        "a patient or record identifier",
        True,
    ),
    # The title in any case ("mr. smith"), the name capitalised or not.
    (re.compile(r"\b(?i:mr|mrs|ms|miss|dr)\.?\s+[A-Za-z][a-z]+"), PERSONS_NAME, False),
]
# What each second-net finding becomes in a stored value (label-only findings keep their label: the value after it
# is masked).
_SECOND_NET_PLACEHOLDER = {
    "an email address": "[EMAIL]",
    "a phone number": "[PHONE]",
    "a national ID number": "[ID_NUMBER]",
    PERSONS_NAME: "[PERSON]",
}
# Device identifiers are checked as identifiers, not as text: a ten-digit serial is not a phone number and a GTIN-14
# not a card number (J8). A UDI is written as GS1 element strings ("(01)00884838000292(17)261120(10)L24-0815") or
# HIBC, which starts with "+" ("+H123PUMP2001/$$3261120L24-0815"); exports escape a leading "+" (csv_safe).
_UDI = re.compile(r"^[+A-Za-z0-9(][A-Za-z0-9 ._/#:()$%*+-]{0,119}$")
DEVICE_IDS = {"serial_number": _ID, "udi": _UDI}
# Columns that hold the name of a thing (a product, a part, a supplier, a site): a title or a given name there is a
# brand ("Dr Trust BP monitor", "Dr. Morepen"), never a person, so names are not looked for in them.
THING_NAMES = frozenset({"product_name", "product_family", "component_name", "supplier_name", "site_name"})
# What masking puts in place of personal data (genai/pii.py), e.g. [PERSON], [PHONE], [DATE_OF_BIRTH].
_MASK_PLACEHOLDER = re.compile(r"\[[A-Z_]+\]")
# Each placeholder in the words of the check report. A lot or serial is masked only beside a patient's details, so
# the report names those details, not the lot.
_MASK_FOUND = {
    "[PERSON]": "a person's name",
    "[PHONE]": "a phone number",
    "[EMAIL]": "an email address",
    "[DATE_OF_BIRTH]": "a date of birth",
    "[ID_NUMBER]": "a patient or record identifier",
    "[ADDRESS]": "an address",
    "[POSTCODE]": "a postcode",
    "[CARD_NUMBER]": "a card number",
    "[IP_ADDRESS]": "an IP address",
    "[AGE_SEX]": "a person's age and sex",
    "[FACILITY]": "the name of a hospital or care home",
    "[LOT]": None,
    "[SERIAL]": None,
}


def template_csv(entity: str) -> str:
    spec = TEMPLATES[entity]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(spec["required"] + spec["optional"])
    for example in spec["example"]:
        writer.writerow(example)
    return out.getvalue()


# A plain signed number ("-5", "+0.25"): it starts with a sign, but a spreadsheet reads it as the number it is.
_SIGNED_NUMBER = re.compile(r"^[+-]\d+(\.\d+)?$")


def _spreadsheet_formula(value: str) -> bool:
    """Text a spreadsheet would run as a formula when the data is exported and opened (CSV injection): anything that
    starts with a character csv_safe escapes on export, except a plain signed number. The check refused "-" only with
    a "(" in the first 40 characters, so "-2+3+cmd|..." went through (SEC-06)."""
    return value.startswith(FORMULA_TRIGGERS) and not _SIGNED_NUMBER.match(value)


def _personal_match(value: str, labels: bool = True, names: bool = True) -> tuple[str, str] | None:
    """What personal data the text seems to hold and the words that hold it. ``labels=False`` (after masking) ignores
    a label such as "MRN" or "date of birth" left in front of a placeholder; the values themselves are still looked
    for. ``names=False`` is for the name of a thing (THING_NAMES)."""
    if not labels:
        value = _MASK_PLACEHOLDER.sub(" ", value)
    for pattern, label, label_only in _PERSONAL_DATA:
        if (label_only and not labels) or (label == PERSONS_NAME and not names):
            continue
        found = pattern.search(value)
        if found:
            return label, found.group(0)
    return None


def _personal_data(value: str, labels: bool = True, names: bool = True) -> str | None:
    """What personal data the text seems to hold ("a phone number"), or None."""
    found = _personal_match(value, labels, names)
    return found[0] if found else None


# Template columns stored under another name (the rest are stored under their own name).
_STORED_AS = {
    "product_name": "name",
    "component_name": "name",
    "supplier_name": "name",
    "site_name": "name",
    "failure_mode_name": "name",
    "question": "investigation_question",
    "owner": "owner_ref",
}


def column_limit(entity: str, column: str) -> int:
    """How many characters the column's value may have: what its database column holds (complaints.status 40,
    complaints.country 80...), so a file the check calls ready never fails at writing (J10); text columns keep
    LONG_TEXT or 255. The quality system's own status words are kept (Cancelled, Void, Closed - no action...)."""
    from backend.app.db.models.lot_impact import LotDistribution

    models = {"products": Product, "lots": LotBatch, "complaints": Complaint, "distribution": LotDistribution}
    model = models.get(entity) or business_imports.KEYED.get(entity, (None,))[0]
    stored = getattr(getattr(model, "__table__", None), "c", {}).get(_STORED_AS.get(column, column))
    length = getattr(getattr(stored, "type", None), "length", None)
    return length or LONG_TEXT.get(column, 255)


def _free_text(column: str) -> bool:
    """A column of free text, checked (and stored) for personal data; identifiers, codes, dates and counts are not."""
    return not (
        column.endswith(("_id", "_ids", "_date", "_at"))
        or column in ("version", "received_zone", "mdarix_ref")
        or column in FLAG_COLUMNS
        or column in COUNT_COLUMNS
        or column in DEVICE_IDS
        or column in ("device_category", "single_use", "use_period_days")
    )


def stored_value(column: str, value):
    """A set-aside value as it may be stored (R14): free text with every personal detail masking finds replaced by a
    placeholder, and what only the second net finds ("mr smith") too, so the set-aside view's "kept only as
    placeholders" holds (J7). Identifiers are kept: a person needs them to find and fix the row."""
    if not value or not isinstance(value, str) or not _free_text(column):
        return value
    names = column not in THING_NAMES
    masked = _mask(value, names=names)
    for pattern, label, label_only in _PERSONAL_DATA:
        if not label_only and (names or label != PERSONS_NAME):
            masked = pattern.sub(_SECOND_NET_PLACEHOLDER[label], masked)
    return masked


def _quoted(words: str) -> str:
    """The words a check found, quoted in its message (each message quotes them in the same form, so a stored copy can
    leave them out: import_quarantine.store)."""
    return f" (“{' '.join(words.split())[:80]}”)"


def _masked_words(value: str, masked: str) -> str:
    """The words of the value that masking replaced, as the person wrote them ("Mr. John Smith, 98450 12345")."""
    import difflib

    before, after = re.findall(r"\S+|\s+", value), re.findall(r"\S+|\s+", masked)
    spans = [
        "".join(before[i1:i2]).strip(" ,.;:")
        for tag, i1, i2, _, _ in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes()
        if tag in ("replace", "delete")
    ]
    return ", ".join(span for span in spans if span)


def file_label(name: str | None) -> str | None:
    """The uploaded file's name as a run report shows it: the last part of the path, at most 120 characters, personal
    data masked (a name such as "complaints from jane.doe@example.com.csv"). None when none was sent."""
    name = (name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()[:120]
    if not name:
        return None
    return _mask(name) if _personal_data(name) else name


def _mask(value: str, names: bool = True) -> str:
    """Personal data replaced by typed placeholders, the masking every AI request gets (genai/pii.py)."""
    from genai.pii import mask_text

    return mask_text(value, names=names)


def _masking_found(value: str, masked: str) -> str | None:
    """What masking replaced, in plain words ("a person's name and a phone number"); None when it changed nothing.
    Placeholders already in the text (a file masked before) are not counted again."""
    if masked == value:
        return None
    already = {}
    for placeholder in _MASK_PLACEHOLDER.findall(value):
        already[placeholder] = already.get(placeholder, 0) + 1
    found: list[str] = []
    for placeholder in _MASK_PLACEHOLDER.findall(masked):
        if already.get(placeholder):
            already[placeholder] -= 1
            continue
        words = _MASK_FOUND.get(placeholder, "personal data")
        if words and words not in found:
            found.append(words)
    if not found:
        return "personal data"
    return found[0] if len(found) == 1 else ", ".join(found[:-1]) + " and " + found[-1]


# Whole-number columns (a lot's quantity): digits, with the separators a spreadsheet writes ("1,250", "1,25,000").
COUNT_COLUMNS = frozenset({"quantity"})
COUNT_MAX = 10_000_000
# How the file writes numbers: "1,250.00" and India's "1,25,000" (a comma groups digits), or "1.250,00" (a comma marks
# the decimals). Only "1,250" and "1.250" read differently in the two; every other form tells by itself (J41).
NUMBER_FORMATS = {"GROUP": "1,250.00 or 1,25,000", "DECIMAL_COMMA": "1.250,00"}
_NUMBER_NOISE = re.compile(r"[\s  '_]")


def _grouped(text: str, separator: str) -> bool:
    """Digits grouped by ``separator``: in threes (1,250,000) or the Indian way, the last three then twos (1,25,000)."""
    parts = text.split(separator)
    if len(parts) < 2 or not all(part.isdigit() for part in parts) or not 1 <= len(parts[0]) <= 3:
        return False
    if all(len(part) == 3 for part in parts[1:]):
        return True
    return len(parts[-1]) == 3 and len(parts[0]) <= 2 and all(len(part) == 2 for part in parts[1:-1])


def whole_number(value: str, numbers: str = "GROUP") -> int | None:
    """A whole number from 0 to COUNT_MAX as the file writes it in ``numbers`` (NUMBER_FORMATS), else None: "1,25,000"
    is 125000, "1250,00" and "1.250,00" are 1250 (never 125,000), "1,5" is not whole."""
    text = _NUMBER_NOISE.sub("", str(value or ""))
    if not text or not re.fullmatch(r"\d[\d.,]*\d|\d", text):
        return None
    if "," in text and "." in text:
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        whole, _, fraction = text.rpartition(decimal)
        if decimal in whole or not _grouped(whole, "." if decimal == "," else ","):
            return None
    elif "," in text or "." in text:
        separator = "," if "," in text else "."
        groups = (separator == ",") == (numbers == "GROUP")
        if _grouped(text, separator) and (groups or text.count(separator) > 1):
            whole, fraction = text, ""
        elif text.count(separator) == 1:
            whole, _, fraction = text.partition(separator)
        else:
            return None
    else:
        whole, fraction = text, ""
    if fraction.strip("0"):
        return None
    number = int(whole.replace(",", "").replace(".", ""))
    return number if number <= COUNT_MAX else None


def _count(value: str) -> int | None:
    """A whole number from 0 to COUNT_MAX, else None (``whole_number``; a file's values were read in its format)."""
    return whole_number(value)


def count_problem(value: str, numbers: str = "GROUP") -> str:
    """Why a whole-number value was refused, naming the number-format choice when the other one reads it whole."""
    other = "DECIMAL_COMMA" if numbers == "GROUP" else "GROUP"
    if whole_number(value, other) is not None:
        return (
            f"'{value}' is not a whole number as numbers are written {NUMBER_FORMATS[numbers]}. If it means "
            f"{whole_number(value, other):,}, choose 'Numbers in the file: {NUMBER_FORMATS[other]}' and check again."
        )
    return f"'{value}' is not a whole number from 0 to {COUNT_MAX:,}: write it as 1250, 1,250 or 1,25,000."


def _date(value: str) -> datetime | None:
    return datetime.combine(date.fromisoformat(value), time(12, 0), tzinfo=timezone.utc)


DATE_FORMATS = {"ISO": "YYYY-MM-DD", "DMY": "DD/MM/YYYY", "MDY": "MM/DD/YYYY", "AUTO": "found from the file"}
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DAY_MONTH_YEAR = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})$")
# "14-Mar-2026", "14 March 26", "Mar 14, 2026": the month's name cannot be misread.
_DAY_NAME_YEAR = re.compile(r"^(\d{1,2})[\s/.-]*([A-Za-z]{3,9})\.?[\s/.,-]*(\d{4}|\d{2})$")
_NAME_DAY_YEAR = re.compile(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})$")
_MONTHS = {name: number for number, name in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
# A time after the date ("14/03/2026 10:30", "2026-03-14T10:30:00Z"): the day is what is kept.
_TIME_AFTER = re.compile(
    r"^(.+?)(?:[ T]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?\s*(?:[AaPp]\.?[Mm]\.?)?(?:Z|[+-]\d{2}:?\d{2})?)$"
)
# An Excel day number left as a number in a date column (a cell not formatted as a date, or a CSV saved from one).
_EXCEL_DAY = re.compile(r"^\d{5}(\.\d+)?$")
EXCEL_EPOCH = date(1899, 12, 30)
# A date before this year is a typing slip for any device in use today (1926 for 2026); a past event (a complaint, a
# lot made, a shipment) dated after tomorrow is one too. Planned dates (an expiry, a due date) may lie ahead.
EARLIEST_YEAR = 1970
FUTURE_DATES = frozenset(
    {"expiry_date", "due_date", "effectiveness_check_date", "effective_date", "version_release_date"}
)
_DELIMITERS = ",;\t"
# A multipart upload carries a little framing around the file; allowed on top of the file limit.
MULTIPART_OVERHEAD_BYTES = 64 * 1024


def date_format_or_422(value: str | None) -> str:
    """The ``date_format`` query parameter: ISO (default), DMY, MDY or AUTO (found from the file); anything else is
    refused."""
    chosen = (value or "ISO").strip().upper()
    if chosen not in DATE_FORMATS:
        raise HTTPException(
            422,
            detail={
                "code": "DATE_FORMAT_INVALID",
                "message": "date_format must be ISO (YYYY-MM-DD), DMY (DD/MM/YYYY), MDY (MM/DD/YYYY) or AUTO",
            },
        )
    return chosen


def number_format_or_422(value: str | None) -> str:
    """The ``number_format`` query parameter: GROUP ("1,250.00", "1,25,000"; the default) or DECIMAL_COMMA."""
    chosen = (value or "GROUP").strip().upper()
    if chosen not in NUMBER_FORMATS:
        raise HTTPException(
            422,
            detail={"code": "NUMBER_FORMAT_INVALID", "message": "number_format must be GROUP or DECIMAL_COMMA"},
        )
    return chosen


def _year(text: str) -> int:
    """A year as written: "26" is 2026 (a two-digit year after 2000; a slip shows as a date still to come)."""
    return int(text) + 2000 if len(text) == 2 else int(text)


def iso_date(value: str, date_format: str = "ISO", epoch: date | None = None) -> str | None:
    """``value`` as YYYY-MM-DD, or None when it is not a real date in ``date_format``.

    YYYY-MM-DD and a month written by name are accepted in every format (they cannot be misread); day and month in
    another order only in the order declared (DMY or MDY). A time after the date is left out. With ``epoch`` (the
    file's Excel date system) an Excel day number such as 46095 is read too.
    """
    value = value.strip()
    timed = _TIME_AFTER.match(value)
    if timed:
        value = timed.group(1).strip()
    try:
        if _ISO_DATE.match(value):
            return date.fromisoformat(value).isoformat()
        named = _DAY_NAME_YEAR.match(value) or _NAME_DAY_YEAR.match(value)
        if named:
            parts = named.groups()
            day, name, year = (parts[0], parts[1], parts[2]) if parts[0].isdigit() else (parts[1], parts[0], parts[2])
            month = _MONTHS.get(name[:3].lower())
            return date(_year(year), month, int(day)).isoformat() if month else None
        match = _DAY_MONTH_YEAR.match(value)
        if match and date_format in ("DMY", "MDY"):
            first, second, year = match.groups()
            day, month = (int(first), int(second)) if date_format == "DMY" else (int(second), int(first))
            return date(_year(year), month, day).isoformat()
        if epoch is not None and _EXCEL_DAY.match(value):
            return (epoch + timedelta(days=int(float(value)))).isoformat()
    except (ValueError, OverflowError):
        return None
    return None


def _strict_iso(value: str) -> bool:
    """Whether ``value`` is a real YYYY-MM-DD date (what is stored)."""
    try:
        return bool(_ISO_DATE.match(value)) and bool(date.fromisoformat(value))
    except ValueError:
        return False


def _is_time(value: str) -> bool:
    """Whether ``value`` is an ISO date and time (what a Cases file's times are read into)."""
    try:
        datetime.fromisoformat(value)
        return True
    except ValueError:
        return False


def date_problem(column: str, value: str, typed: str | None = None, today: date | None = None) -> str | None:
    """Why a real date cannot be right (J41): before EARLIEST_YEAR, or a past event dated after tomorrow."""
    day = date.fromisoformat(value)
    shown = f"{day.day} {day:%b %Y}"
    typed = typed or value
    if day.year < EARLIEST_YEAR:
        return (
            f"'{typed}' reads as {shown}, before {EARLIEST_YEAR}: too early for a device in use today. Check the year."
        )
    today = today or datetime.now(timezone.utc).date()
    if column not in FUTURE_DATES and day > today + timedelta(days=1):
        return f"'{typed}' reads as {shown}, a day still to come. Check the year, and the order of day and month."
    return None


def resolve_date_order(headers: list[str], values: list[str], usual: str) -> tuple[str, str | None]:
    """The order of day and month in a file whose uploader chose "find it from the file" (AUTO), and what to say back:
    a header that names it ("Event Date (DD/MM/YYYY)"), else the dates (a first number over 12 is a day), else the
    organization's usual order (``usual``, DMY or MDY)."""
    from backend.app.trial.columns import date_order_hint

    hinted = {date_order_hint(header) for header in headers} - {None}
    if len(hinted) == 1:
        order = hinted.pop()
        return order, f"Dates read as {DATE_FORMATS[order]}, as the column names say."
    day_first = month_first = undecided = 0
    for value in values:
        timed = _TIME_AFTER.match(value.strip())
        match = _DAY_MONTH_YEAR.match(timed.group(1).strip() if timed else value.strip())
        if not match:
            continue
        first, second = int(match.group(1)), int(match.group(2))
        if first > 12 >= second:
            day_first += 1
        elif second > 12 >= first:
            month_first += 1
        else:
            undecided += 1
    if day_first and not month_first:
        return "DMY", "Dates read as DD/MM/YYYY: dates such as 14/03 can only be day first."
    if month_first and not day_first:
        return "MDY", "Dates read as MM/DD/YYYY: dates such as 03/14 can only be month first."
    if day_first and month_first:
        return usual, (
            f"Some dates can only be day first and others only month first: all were read as {DATE_FORMATS[usual]}, "
            "your organization's usual order. Check the dates refused below."
        )
    if undecided:
        return usual, (
            f"Dates read as {DATE_FORMATS[usual]}, your organization's usual order: no date in the file tells day from "
            "month. If they are the other way round, change 'Dates in the file' and check again."
        )
    return usual, None


# Time zones whose people write the month first (the United States); everyone else is read day first.
_MONTH_FIRST_ZONES = re.compile(
    r"^(America/(New_York|Chicago|Denver|Los_Angeles|Phoenix|Anchorage|Detroit|Boise|Juneau|Sitka|Nome|Adak|Indiana/.*|"
    r"Kentucky/.*|North_Dakota/.*|Menominee|Metlakatla|Yakutat)|Pacific/Honolulu|US/.*)$"
)
# Time zones whose people write "1.250,00" (a comma for the decimals).
_DECIMAL_COMMA_ZONES = re.compile(
    r"^(Europe/(?!London|Dublin|Zurich|Isle_of_Man|Jersey|Guernsey|Gibraltar|Malta).*|America/(Sao_Paulo|Argentina/.*))$"
)


def usual_formats(zone: str | None) -> dict:
    """The organization's usual date order and number format, from its time zone (Settings): what "find it from the
    file" falls back on and what the upload screen starts with. India reads DD/MM/YYYY and "1,25,000"."""
    zone = zone or ""
    return {
        "date_order": "MDY" if _MONTH_FIRST_ZONES.match(zone) else "DMY",
        "number_format": "DECIMAL_COMMA" if _DECIMAL_COMMA_ZONES.match(zone) else "GROUP",
    }


def _decode(raw: bytes, report: "_Report") -> str | None:
    """The file as text: UTF-8 (with or without a byte-order mark), UTF-16 with its byte-order mark (Excel's "Unicode
    text"), or else Windows-1252, the encoding Excel on Windows saves plain "CSV" in, said back to the uploader as a
    note. Nothing is ever silently replaced: bytes no encoding defines refuse the file."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            report.add(None, None, "The file could not be read as UTF-16 text. Save it as 'CSV UTF-8' and try again.")
            return None
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        try:
            text = raw.decode("cp1252")
        except UnicodeDecodeError:
            line = raw[: exc.start].count(b"\n") + 1
            report.add(
                line,
                None,
                "The file is not UTF-8 or Windows text. Save it as 'CSV UTF-8' and try again, so that accented letters "
                "and symbols are kept exactly.",
            )
            return None
        report.notes.append(
            "Read as Windows text (Excel's plain CSV). Check accented letters in the preview; saving as 'CSV UTF-8' "
            "avoids any doubt."
        )
        return text


@dataclass(frozen=True)
class FileReading:
    """How the uploader asked the file to be read, beside its date order: the workbook sheet (None: the first visible
    one that holds the template's columns), the number format (NUMBER_FORMATS), the column that holds a complaint's
    date when the file names none MDARIX knows (a header, or "none" for the import day), and the organization's usual
    date order, for "find it from the file" when nothing in the file tells."""

    sheet: str | None = None
    numbers: str = "GROUP"
    date_column: str | None = None
    usual_order: str = "DMY"


# Rows looked at for the column names (below a title, a date of export or blank rows), and sheets looked at for them.
HEADER_SEARCH_ROWS = 20
SHEETS_LOOKED_AT = 20


def _header_score(entity: str, cells: list[str], allowed: list[str]) -> tuple[bool, int]:
    """(holds every required column, how many cells name a template column) for a row read as the column names."""
    fields = columns_match(entity, [str(cell).strip() for cell in cells], allowed)["fields"]
    found = {field for field in fields if field}
    return all(column in found for column in TEMPLATES[entity]["required"]), len(found)


def header_index(entity: str, table: list[list[str]]) -> int:
    """The row of ``table`` that holds the column names: of its first rows, the one naming the most template columns
    (every required one first), the earliest on a tie; the first row with a value when none names any (J6)."""
    spec = TEMPLATES[entity]
    allowed = spec["required"] + spec["optional"]
    best, best_score = None, (False, 0)
    for index, cells in enumerate(table[:HEADER_SEARCH_ROWS]):
        if not any(str(cell).strip() for cell in cells):
            continue
        score = _header_score(entity, cells, allowed)
        if best is None or score > best_score:
            best, best_score = index, score
    if best is None or best_score[1] == 0:
        return next((index for index, cells in enumerate(table) if any(str(c).strip() for c in cells)), 0)
    return best


def detect(raw: bytes, policy: "ImportPolicy" = None) -> dict:
    """Which template a file is (0.10.82, D1.10: one drop zone for every object): of the templates offered, the one
    whose column names the file's header row fits best, every required column first, then the most columns named,
    then the largest share of the template's columns. ``entity`` is None when no template's column is named.
    shortcut: a workbook's sheet is chosen as for a complaints file; a workbook with one object per sheet is read on
    its best sheet for complaints, so the person picks the object when it is another."""
    policy = policy or TRIAL_POLICY
    report = _Report()
    table = _table(raw, report, policy, "complaints")
    if table is None:
        return {"entity": None, "message": report.issues[0]["message"] if report.issues else "The file cannot be read."}
    head = [cells for cells in table[:HEADER_SEARCH_ROWS] if any(str(cell).strip() for cell in cells)]
    scored = []
    for entity, spec in TEMPLATES.items():
        if not offered(entity, policy):
            continue
        allowed = spec["required"] + spec["optional"]
        complete, named = max((_header_score(entity, cells, allowed) for cells in head), default=(False, 0))
        scored.append(((complete, named, named / len(allowed)), entity))
    (complete, named, _), entity = max(scored, default=((False, 0, 0), None))
    if not named:
        return {
            "entity": None,
            "message": "No column of this file matches a template. Download a template to see the columns.",
        }
    return {
        "entity": entity,
        "title": TEMPLATES[entity]["title"],
        "complete": complete,
        "columns_matched": named,
    }


def _choose_sheet(book, entity: str, reading: FileReading, report: "_Report"):
    """The sheet to read: the one named, else of the visible sheets with a value the one whose column names fit the
    template best, the first on a tie (J6; a hidden sheet is never chosen unnamed). What was read, and what else is
    there, is said back."""
    visible = [sheet for sheet in book.sheets if not sheet.hidden]
    hidden = [sheet.name for sheet in book.sheets if sheet.hidden]
    if reading.sheet:
        chosen = book.sheet(reading.sheet)
    else:
        spec = TEMPLATES[entity]
        allowed = spec["required"] + spec["optional"]
        chosen, best = None, (False, 0)
        for sheet in visible[:SHEETS_LOOKED_AT]:
            head = book.rows(sheet, stop_after=HEADER_SEARCH_ROWS)
            if not any(any(cells) for cells in head):
                continue
            # The sheet whose column names fit the template best (every required column first): a complaints
            # register's "Batch/Lot No." fits a lots file less than the batch register beside it does.
            score = max(_header_score(entity, cells, allowed) for cells in head if any(cells))
            if chosen is None or score > best:
                chosen, best = sheet, score
        chosen = chosen or (visible or book.sheets)[0]
    report.sheet = chosen.name
    report.sheets = [sheet.name for sheet in visible]
    others = [f"'{sheet.name}'" for sheet in visible if sheet is not chosen]
    note = f"Read the sheet '{chosen.name}' of the Excel workbook"
    if others:
        note += f"; its other sheets: {', '.join(others)} (choose one below to read it instead)"
    if hidden:
        note += f". Hidden sheets are not read: {', '.join(repr(name) for name in hidden)}"
    report.notes.append(note + ".")
    return chosen


def _table(
    raw: bytes,
    report: "_Report",
    policy: ImportPolicy = TRIAL_POLICY,
    entity: str = "complaints",
    reading: FileReading | None = None,
) -> list[list[str]] | None:
    """The upload as rows of cells, ``table[n - 1]`` being the file's row n: an Excel workbook's sheet
    (backend/app/trial/xlsx.py, ``_choose_sheet``), else delimited text (comma, semicolon or tab). None when it cannot
    be read (the reason is in the report). A workbook is read no further than the rows the policy takes (plus a
    margin), within the policy's unpacked size."""
    from backend.app.trial import xlsx

    max_rows = min(policy.row_limit or MAX_ROWS_PER_FILE, MAX_ROWS_PER_FILE)
    if xlsx.is_xlsx(raw):
        try:
            with xlsx.Workbook(
                raw,
                max_rows=max_rows,
                max_bytes=policy.xlsx_max_bytes,
            ) as book:
                rows = book.rows(_choose_sheet(book, entity, reading or FileReading(), report))
                report.epoch = book.epoch
        except xlsx.XlsxError as exc:
            report.add(None, None, str(exc))
            return None
        return rows
    text = _decode(raw, report)
    if text is None:
        return None
    report.epoch = EXCEL_EPOCH
    report.delimited = True
    # Read no further than a workbook would (header + the rows taken + the margin), so an oversized file is refused
    # without building every row in memory.
    row_cap = 1 + max_rows + xlsx.ROW_MARGIN
    # strict: a stray quote mark is refused with its line, never read as one cell holding the rest of the file.
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=_delimiter(text), strict=True)
    rows, start = [], 1
    try:
        for row in itertools.islice(reader, row_cap + 1):
            rows.append(row)
            start = reader.line_num + 1
    except csv.Error:
        report.add(
            None,
            None,
            f'Line {start}: a quote mark (") there is not closed, or more text follows it in the same value. Remove '
            "the stray quote (or put the whole value in quotes, doubling any quote inside it) and upload again.",
        )
        return None
    if len(rows) > row_cap:
        report.add(None, None, xlsx.too_many_rows(max_rows))
        return None
    return rows


def _delimiter(text: str) -> str:
    """Comma, semicolon or tab, whichever the header line uses (comma when it cannot tell, e.g. one column). The header
    may sit below a title, so of the first lines the one with the most separators is read."""
    lines = text.split("\n", HEADER_SEARCH_ROWS)[:HEADER_SEARCH_ROWS]
    # The first line with the most of any one separator: a title line has few, a data line no more than the header.
    header = max(lines, key=lambda line: max(line.count(mark) for mark in _DELIMITERS)) if lines else ""
    try:
        return csv.Sniffer().sniff(header, delimiters=_DELIMITERS).delimiter
    except csv.Error:
        return ","


async def read_upload(request: Request, limit: int, message: str) -> bytes:
    """The uploaded file's bytes, from a raw body (``text/csv``) or a multipart form (its ``file`` field).

    The body is read with a hard limit before anything is parsed; a multipart file over ``limit`` is refused too.
    """
    from starlette.datastructures import UploadFile
    from starlette.formparsers import MultiPartParser

    from backend.app.request_body import read_limited

    multipart = request.headers.get("content-type", "").lower().startswith("multipart/form-data")
    raw = await read_limited(request, limit + (MULTIPART_OVERHEAD_BYTES if multipart else 0), message=message)
    if not multipart:
        return raw

    async def body():
        yield raw

    try:
        form = await MultiPartParser(request.headers, body(), max_files=1, max_fields=5).parse()
    except Exception as exc:  # starlette raises its own MultiPartException for a malformed form
        raise HTTPException(
            422, detail={"code": "UPLOAD_INVALID", "message": "The upload could not be read; send one CSV file"}
        ) from exc
    try:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise HTTPException(
                422, detail={"code": "UPLOAD_INVALID", "message": "Send the CSV file in a form field named 'file'"}
            )
        content = await upload.read()
    finally:
        await form.close()
    if len(content) > limit:
        raise HTTPException(413, detail={"code": "FILE_TOO_LARGE", "message": message})
    return content


class _Report:
    def __init__(self) -> None:
        self.issues: list[dict] = []
        self.error_count = 0
        # Problems of the whole file (encoding, header, size, limits: no row can be imported) and of single rows.
        self.file_problems = 0
        self.row_problems: dict[int, list[str]] = {}
        # Values whose personal data was masked, and what they were (for the rejects file only; never saved).
        self.masked_values = 0
        self.originals: dict[tuple[int, str], str] = {}
        # How the file was read, said back to the uploader: notes (an encoding read, a workbook sheet), the headers read
        # under another name, the columns not used, and the products, versions and lots a complaints file adds.
        self.notes: list[str] = []
        self.mapping: list[dict] = []
        self.ignored: list[str] = []
        self.duplicates: list[dict] = []
        self.creates: dict[str, int] = {}
        # Rows of the file that would add a record (not update one): what a free trial's row allowance counts.
        self.new_rows = 0
        # The file holds no data row at all: nothing in it, or a header alone (DEV-018).
        self.no_rows = False
        # Non-blank data lines in the file, counted as read: what the run report balances against (R17).
        self.data_lines = 0
        # Where the column names were (the file's row number), each template column's header in the file, the
        # workbook's sheet read and its visible sheets, its Excel date system, the date order and number format used,
        # and each value as typed where it was read into another form (a date, a number), for the messages.
        self.header_line = 1
        self.headers: dict[str, str] = {}
        self.sheet: str | None = None
        self.sheets: list[str] = []
        self.epoch: date | None = None
        self.date_order = "ISO"
        self.numbers = "GROUP"
        self.typed: dict[tuple[int, str], str] = {}
        # A complaints file without a date column: the columns the uploader may choose for it (J5).
        self.needs_date_column = False
        self.date_candidates: list[str] = []
        # Rows with fewer cells than the header has columns: (cells, columns), flagged, never refused (0.10.81, F9).
        self.short_rows: dict[int, tuple[int, int]] = {}
        # Delimited text (a workbook's rows may stop at their last filled cell, so only text rows are short).
        self.delimited = False

    def add(self, row: int | None, column: str | None, message: str) -> None:
        self.error_count += 1
        if len(self.issues) < MAX_ISSUES:
            self.issues.append({"row": row, "column": column, "header": self.headers.get(column), "message": message})
        if row is None or row == self.header_line:  # the column names' row
            self.file_problems += 1
        else:
            self.row_problems.setdefault(row, []).append(f"{column}: {message}" if column else message)


# The complaint fields that date a complaint: a file with neither is asked which column holds the date (J5).
COMPLAINT_DATE_FIELDS = ("event_date", "received_date")
NO_DATE_COLUMN = "none"


def _date_column(headers: list[str], fields: list, reading: FileReading, report: _Report) -> None:
    """A complaints file with no event or received date column: the column the uploader named is read as the received
    date; "none" dates each complaint the day it is imported, said back; with no choice the file is not ready and the
    uploader is asked, because otherwise every complaint gets the import day and reads as a sudden rise (J5)."""
    choice = (reading.date_column or "").strip()
    if choice.lower() == NO_DATE_COLUMN:
        report.notes.append(
            "The file has no date column: each complaint is dated the day it is imported, so the trend check reads "
            "every one as new."
        )
        return
    if choice:
        index = next(
            (i for i, header in enumerate(headers) if header.strip().lower() == choice.lower() and fields[i] is None),
            None,
        )
        if index is not None:
            fields[index] = "received_date"
            report.mapping.append({"header": headers[index].strip(), "column": "received_date"})
            report.ignored = [header for header in report.ignored if header != headers[index].strip()]
            return
    report.needs_date_column = True
    report.date_candidates = list(report.ignored)
    report.add(
        None,
        "received_date",
        f"The file has no column '{choice}'. Choose the column that holds the date each complaint was received."
        if choice
        else "No column gives each complaint's date (such as 'Date of Complaint', 'Event Date' or 'Date Received'). "
        "Choose above which column holds the date each complaint was received: without a date every "
        "complaint is dated today and reads as a sudden rise.",
    )


def _parse(
    entity: str,
    raw: bytes,
    report: _Report,
    policy: ImportPolicy = TRIAL_POLICY,
    date_format: str = "ISO",
    reading: FileReading | None = None,
) -> list[tuple[int, dict]]:
    """The file's data rows as ``(row number in the file, {template column: value})``: its sheet chosen, its column
    names found (below any title), matched to the template, dates read as YYYY-MM-DD and whole numbers as digits (a
    value that is neither is left as typed for ``_check_values`` to refuse). ``report.date_order`` is the order used
    (AUTO resolved)."""
    reading = reading or FileReading()
    report.numbers = reading.numbers
    if entity not in TEMPLATES or not offered(entity, policy):
        raise HTTPException(404, detail={"code": "TEMPLATE_NOT_FOUND", "message": "Unknown template"})
    if len(raw) > policy.file_limit_bytes:
        raise HTTPException(413, detail={"code": "FILE_TOO_LARGE", "message": policy.file_too_large})
    table = _table(raw, report, policy, entity, reading)
    if table is None:
        return []
    start = header_index(entity, table)
    header = table[start] if start < len(table) else None
    if not header or not any(cell.strip() for cell in header):
        report.no_rows = True
        report.add(None, None, "The file is empty.")
        return []
    report.header_line = start + 1
    if start:
        report.notes.append(
            f"The column names are on row {start + 1}: the rows above them (a title, blank rows) are not data."
        )
    report.no_rows = not any(any(cell.strip() for cell in cells) for cells in table[start + 1 :])
    spec = TEMPLATES[entity]
    allowed = spec["required"] + spec["optional"]
    # The export's headers matched to the template (backend/app/trial/columns.py): a header under another name is
    # read as its column, one the template does not know is not used (never stored) and listed back.
    headers = [cell.strip() for cell in header]
    matched = columns_match(entity, headers, allowed)
    fields = matched["fields"]
    report.mapping = matched["mapping"]
    report.ignored = matched["ignored"] + [item["header"] for item in matched["duplicates"]]
    report.duplicates = matched["duplicates"]
    if entity == "cases":
        for name in case_import.contact_headers(matched["ignored"]):
            report.notes.append(f"Column '{name}' is not read: {case_import.CONTACT_NOTE} (nothing from it is saved).")
    for column in spec["required"]:
        if column not in fields:
            names = column_examples(entity, column)
            hint = f" (for example {' or '.join(repr(name) for name in names)})" if names else ""
            report.add(report.header_line, column, f"Required column '{column}'{hint} is missing.")
    if (
        entity == "complaints"
        and not report.error_count
        and not report.no_rows
        and not set(COMPLAINT_DATE_FIELDS) & set(fields)
    ):
        _date_column(headers, fields, reading, report)
    report.headers = {field: name for name, field in zip(headers, fields) if field}
    if report.error_count:
        return []
    rows = []
    for line_number, cells in enumerate(table[start + 1 :], start + 2):
        if not any(cell.strip() for cell in cells):
            continue
        report.data_lines += 1
        if any(cell.strip() for cell in cells[len(fields) :]):
            # Kept with its problem, so it is set aside (and quarantined, counted) rather than lost.
            report.add(line_number, None, "This row has more values than the header has columns.")
        elif report.delimited and len(cells) < len(fields):
            report.short_rows[line_number] = (len(cells), len(fields))
        row = {
            column: (cells[i].strip() if i < len(cells) else "")
            for i, column in enumerate(fields)
            if column is not None
        }
        rows.append((line_number, row))
    order = date_format
    if date_format == "AUTO":
        dated = [column for column in report.headers if column.endswith("_date")]
        values = [row[column] for _, row in rows for column in dated if row.get(column)]
        order, note = resolve_date_order([report.headers[column] for column in dated], values, reading.usual_order)
        if note:
            report.notes.append(note)
    report.date_order = order
    day_numbers = 0
    for line_number, row in rows:
        for column, value in row.items():
            if not value:
                continue
            # Dates in the file's order become YYYY-MM-DD and whole numbers digits here; a value that is not one is
            # left as typed and refused by _check_values with what to do.
            if column.endswith("_date"):
                read = iso_date(value, order, report.epoch)
                day_numbers += bool(read and _EXCEL_DAY.match(value.strip()))
            elif column.endswith("_at"):
                read = case_import.iso_time(value, order)
            elif column in COUNT_COLUMNS:
                number = whole_number(value, reading.numbers)
                read = str(number) if number is not None else None
            else:
                continue
            if read and read != value:
                report.typed[(line_number, column)] = value
                row[column] = read
    if day_numbers:
        plural = "date" if day_numbers == 1 else "dates"
        system = " in the 1904 date system" if report.epoch == date(1904, 1, 1) else ""
        report.notes.append(
            f"{day_numbers:,} {plural} written as Excel day numbers (such as 46095) read as dates{system}."
        )
    if not rows:
        report.add(None, None, "The file has a header but no data rows.")
    return rows


def identity_columns(entity: str) -> list[str]:
    """The columns naming one record of ``entity``: a duplicate in a file, a set-aside row a later import closes."""
    spec = TEMPLATES[entity]
    key = spec["required"][0]
    return spec.get("identity") or ([key, "version"] if entity == "products" else [key])


def _check_values(
    entity: str,
    rows: list[tuple[int, dict]],
    report: _Report,
    date_format: str = "ISO",
    mask_personal_data: bool = False,
) -> None:
    """Check every value. With ``mask_personal_data`` free text has its personal data replaced (in the row, so the
    masked text is what is saved) instead of being refused; what masking does not remove is still refused."""
    spec = TEMPLATES[entity]
    key = spec["required"][0]
    columns = identity_columns(entity)
    seen: dict[tuple, int] = {}
    complaint_lots: dict[str, tuple[int, set]] = {}
    for line, row in rows:
        # A kit's later lot (the same complaint again, with another lot) gives only its lot: the complaint's first row
        # gave its description (J32).
        first = complaint_lots.get(row.get(key)) if entity == "complaints" else None
        later_lot = bool(first and row.get("lot_id") and "" not in first[1] and row["lot_id"] not in first[1])
        for column in spec["required"]:
            if not row.get(column) and not (later_lot and column == "description"):
                report.add(line, column, f"'{column}' is required.")
        for column, value in row.items():
            if not value:
                continue
            if column == "version":
                if not _VERSION.match(value):
                    report.add(
                        line,
                        column,
                        f"'{value[:40]}': use up to 120 letters, numbers, spaces or . _ / # : + - characters.",
                    )
            elif column.endswith("_id"):
                if not _ID.match(value):
                    report.add(
                        line,
                        column,
                        f"'{value[:40]}': use up to 120 letters, numbers, spaces or . _ / # : - characters.",
                    )
            elif column.endswith("_ids"):
                if any(not _ID.match(part) for part in business_imports.split_ids(value)):
                    report.add(line, column, "List identifiers separated by ; (letters, numbers, . _ / # : -).")
            elif column in FLAG_COLUMNS:
                if value.lower() in FLAG_NOT_KNOWN:
                    row[column] = ""  # "NA", "-", "Unknown": not known, never a No
                elif value.lower() not in FLAG_VALUES:
                    report.add(line, column, f"'{value[:40]}' is not a yes or no: {FLAG_HINT}")
            elif column in COUNT_COLUMNS:
                if _count(value) is None:
                    report.add(line, column, count_problem(value, report.numbers))
            elif column.endswith("_at"):
                if not _is_time(value):
                    report.add(line, column, f"'{value[:40]}' is not a date and time (YYYY-MM-DD HH:MM).")
            elif column.endswith("_date"):
                typed = report.typed.get((line, column))
                if not _strict_iso(value):
                    order = report.date_order if report.date_order in ("DMY", "MDY") else date_format
                    expected = "YYYY-MM-DD" + (f" or {DATE_FORMATS[order]}" if order in ("DMY", "MDY") else "")
                    report.add(line, column, f"'{value}' is not a date in {expected} format.")
                else:
                    problem = date_problem(column, value, typed)
                    if problem:
                        report.add(line, column, problem)
            elif column == "device_category":
                if product_facts.category_code(value) is None:
                    report.add(line, column, product_facts.CATEGORY_HINT)
            elif column == "use_period_days":
                if not value.isdigit() or not 1 <= int(value) <= product_facts.USE_PERIOD_MAX:
                    report.add(line, column, "Use a whole number of days from 1 to 36,500.")
            elif column == "single_use":
                if value.lower() not in FLAG_VALUES:
                    report.add(line, column, f"'{value[:40]}' is not a yes or no: {FLAG_HINT}")
            elif column in DEVICE_IDS:
                if not DEVICE_IDS[column].match(value):
                    extra = " ( ) $ % * +" if column == "udi" else ""
                    report.add(
                        line, column, f"Use up to 120 letters, numbers, spaces or . _ / # : -{extra} characters."
                    )
            else:
                # The same detection both ways: refusing flags whatever masking would replace.
                names = column not in THING_NAMES
                masked = _mask(value, names=names)
                if mask_personal_data:
                    if masked != value:
                        report.masked_values += 1
                        report.originals[(line, column)] = value
                        row[column] = value = masked
                    found = _personal_match(value, labels=False, names=names)
                else:
                    label = _masking_found(value, masked)
                    found = (label, _masked_words(value, masked)) if label else _personal_match(value, names=names)
                limit = column_limit(entity, column)
                # A shipment's country has its own check, which names the two-letter code.
                if len(value) > limit and (entity, column) != ("distribution", "country"):
                    report.add(line, column, f"Keep this to {limit} characters or fewer.")
                if found:
                    advice = (
                        "Masking could not remove it; remove it from the file."
                        if mask_personal_data
                        else "Remove personal data and retry, or choose to mask it."
                    )
                    words = _quoted(found[1]) if found[1] else ""
                    report.add(line, column, f"This looks like it contains {found[0]}{words}. {advice}")
                if _spreadsheet_formula(value):
                    report.add(
                        line, column, "Text cannot start with =, +, - or @: spreadsheets would run it as a formula."
                    )
        if entity == "complaints":
            # A kit's complaint names each of its lots on a row of its own (J32): a row of the same complaint with
            # another lot is that lot, not a duplicate. The same lot again, or a row without one, still is.
            first, lots = complaint_lots.setdefault(row.get(key), (line, set()))
            lot = row.get("lot_id") or ""
            if line != first and (not lot or "" in lots or lot in lots):
                report.add(line, key, f"Duplicate of row {first}.")
            lots.add(lot)
            continue
        identity = tuple(row.get(column) for column in columns)
        if identity in seen:
            report.add(line, key, f"Duplicate of row {seen[identity]}.")
        else:
            seen[identity] = line


class _Lookup:
    """Tenant-scoped product, version and lot lookups, including rows created earlier in the same file."""

    def __init__(self, db: Session, tenant_id) -> None:
        self.db, self.tenant_id = db, tenant_id
        self.products: dict[str, Product | None] = {}
        self.versions: dict[tuple[str, str], ProductVersion | None] = {}
        self.lots: dict[str, LotBatch | None] = {}
        self.versions_by_id: dict[uuid.UUID, ProductVersion | None] = {}

    def complaints(self, identifiers) -> dict[str, Complaint]:
        """The workspace's complaints among ``identifiers``, by identifier: one query per 1,000 identifiers, not one
        per row (NEW-4)."""
        wanted = list(dict.fromkeys(identifiers))
        found: dict[str, Complaint] = {}
        for start in range(0, len(wanted), 1000):
            for complaint in self.db.query(Complaint).filter(
                Complaint.tenant_id == self.tenant_id, Complaint.complaint_identifier.in_(wanted[start : start + 1000])
            ):
                found[complaint.complaint_identifier] = complaint
        return found

    def version_by_id(self, version_id) -> ProductVersion | None:
        """A lot's version, read once per version (NEW-4)."""
        if version_id not in self.versions_by_id:
            self.versions_by_id[version_id] = (
                self.db.query(ProductVersion).filter(ProductVersion.id == version_id).first()
            )
        return self.versions_by_id[version_id]

    def product(self, identifier: str) -> Product | None:
        if identifier not in self.products:
            self.products[identifier] = (
                self.db.query(Product)
                .filter(Product.tenant_id == self.tenant_id, Product.product_identifier == identifier)
                .first()
            )
        return self.products[identifier]

    def version(self, product: Product, identifier: str) -> ProductVersion | None:
        key = (product.product_identifier, identifier)
        if key not in self.versions:
            self.versions[key] = (
                self.db.query(ProductVersion)
                .filter(
                    ProductVersion.tenant_id == self.tenant_id,
                    ProductVersion.product_id == product.id,
                    ProductVersion.version_identifier == identifier,
                )
                .first()
            )
        return self.versions[key]

    def site(self, identifier: str) -> ManufacturingSite | None:
        return (
            self.db.query(ManufacturingSite)
            .filter(ManufacturingSite.tenant_id == self.tenant_id, ManufacturingSite.site_identifier == identifier)
            .first()
        )

    def lot(self, identifier: str) -> LotBatch | None:
        if identifier not in self.lots:
            self.lots[identifier] = (
                self.db.query(LotBatch)
                .filter(LotBatch.tenant_id == self.tenant_id, LotBatch.lot_identifier == identifier)
                .first()
            )
        return self.lots[identifier]


def _check_references(entity: str, rows, lookup: _Lookup, report: _Report, create: bool = False) -> int:
    """Validate references and count the records that would be new; ``report.new_rows`` counts the rows that add one
    (a row that only updates a record is not counted, nor are the products, versions and lots a complaints file names).
    With ``create`` (a free trial) a complaints file may name products, versions and lots not loaded yet: they are
    counted as records it adds (``report.creates``) instead of refused."""
    if entity in business_imports.TEMPLATES:
        new = business_imports.check(entity, rows, lookup, report)
        report.new_rows = new  # one record per row
        return new
    if entity == "cases":
        return case_import.check(rows, lookup, report)
    if create and entity == "complaints":
        return _check_complaints_creating(rows, lookup, report)
    new = 0
    new_products: set[str] = set()
    new_versions: set[tuple[str, str]] = set()
    new_lots: set[str] = set()
    new_complaints: set[str] = set()
    moved: dict = {}
    report.new_rows = 0
    held = lookup.complaints(row["complaint_id"] for _, row in rows) if entity == "complaints" else {}
    for line, row in rows:
        if entity == "products":
            product = lookup.product(row["product_id"])
            adds = False
            if product is None and row["product_id"] not in new_products:
                new_products.add(row["product_id"])
                new += 1
                adds = True
            version_key = (row["product_id"], row.get("version") or "")
            if (
                row.get("version")
                and version_key not in new_versions
                and (product is None or lookup.version(product, row["version"]) is None)
            ):
                new_versions.add(version_key)
                new += 1
                adds = True
            report.new_rows += adds
            continue
        product = lookup.product(row["product_id"])
        if product is None:
            report.add(line, "product_id", f"Product '{row['product_id']}' is not in your workspace. Load it first.")
            continue
        version = None
        if row.get("version"):
            version = lookup.version(product, row["version"])
            if version is None:
                report.add(line, "version", f"Version '{row['version']}' of '{row['product_id']}' is not loaded yet.")
        if entity == "lots":
            if row.get("site_id") and lookup.site(row["site_id"]) is None:
                report.add(line, "site_id", f"Site '{row['site_id']}' is not in your workspace. Load it first.")
            existing = lookup.lot(row["lot_id"])
            if existing is None:
                if row["lot_id"] not in new_lots:
                    new_lots.add(row["lot_id"])
                    new += 1
                    report.new_rows += 1
            elif version is not None and existing.product_version_id not in (None, version.id):
                report.add(line, "lot_id", f"Lot '{row['lot_id']}' already belongs to another version.")
            continue
        stored = held.get(row["complaint_id"])
        if row.get("lot_id"):
            lot = lookup.lot(row["lot_id"])
            if lot is None:
                report.add(line, "lot_id", f"Lot '{row['lot_id']}' is not loaded yet.")
            else:
                lot_version = lookup.version_by_id(lot.product_version_id)
                if lot_version is not None and lot_version.product_id != product.id:
                    report.add(line, "lot_id", f"Lot '{row['lot_id']}' belongs to a different product.")
                else:
                    _check_lot_version(line, row, version, lot_version, stored, report)
        _check_held(line, row, product, version, stored, report, moved)
        if row["complaint_id"] not in held and row["complaint_id"] not in new_complaints:
            new_complaints.add(row["complaint_id"])
            new += 1
            report.new_rows += 1
    _note_cases(lookup, moved, report)
    return new


def _check_lot_version(line, row, version, lot_version, stored, report: _Report) -> None:
    """PV-1 F4: a complaint's version must be its lot's version when both are known. A blank version cell means the
    stored version (F5), or the lot's for a new complaint."""
    own = version.id if version is not None else (stored.product_version_id if stored is not None else None)
    if lot_version is not None and own is not None and own != lot_version.id:
        named = repr(row["version"]) if row.get("version") else "the stored version"
        report.add(
            line,
            "version",
            f"Lot '{row['lot_id']}' is of version '{lot_version.version_identifier}', not {named}: correct one of them.",
        )


def _check_held(line, row, product, version, stored, report: _Report, moved: dict) -> None:
    """PV-1 F6: a re-upload never moves a complaint to another product; a version change is noted when the complaint
    is in a case (``moved``: complaint id to its row, for ``_note_cases``)."""
    if stored is None:
        return
    if product is None or stored.product_id != product.id:
        report.add(
            line,
            "product_id",
            f"Complaint '{row['complaint_id']}' is held for another product; a file cannot move it to "
            f"'{row['product_id']}'.",
        )
    elif version is not None and version.id != stored.product_version_id:
        moved[stored.id] = (line, row["complaint_id"])


def _note_cases(lookup: _Lookup, moved: dict, report: _Report) -> None:
    """The cases holding a complaint whose version a re-upload changes: a note for each, to check the case's scope."""
    if not moved:
        return
    rows = (
        lookup.db.query(InvestigationComplaint.complaint_id, Investigation.investigation_identifier)
        .join(
            Investigation,
            (Investigation.tenant_id == InvestigationComplaint.tenant_id)
            & (Investigation.id == InvestigationComplaint.investigation_id),
        )
        .filter(
            InvestigationComplaint.tenant_id == lookup.tenant_id, InvestigationComplaint.complaint_id.in_(list(moved))
        )
        .all()
    )
    for complaint_id, case in rows:
        line, identifier = moved[complaint_id]
        report.notes.append(
            f"Line {line}: complaint '{identifier}' changes version while it is in case {case}; check the case's scope."
        )


def _check_complaints_creating(rows, lookup: _Lookup, report: _Report) -> int:
    """A complaints file that also adds the products, versions and lots it names (``_check_references`` with create):
    each is counted once; a lot the workspace already holds must still belong to the complaint's product. The rows
    that add a complaint are ``report.new_rows``; the products, versions and lots they name are not rows."""
    new = 0
    complaints: set[str] = set()
    products: set[str] = set()
    versions: set[tuple[str, str]] = set()
    lots: dict[str, str] = {}
    moved: dict = {}
    held = lookup.complaints(row["complaint_id"] for _, row in rows)
    for line, row in rows:
        product_id = row["product_id"]
        product = lookup.product(product_id)
        if product is None and product_id not in products:
            products.add(product_id)
        version_id = row.get("version")
        version = lookup.version(product, version_id) if product is not None and version_id else None
        if version_id and version is None:
            versions.add((product_id, version_id))
        stored = held.get(row["complaint_id"])
        _check_held(line, row, product, version, stored, report, moved)
        lot_id = row.get("lot_id")
        if lot_id:
            lot = lookup.lot(lot_id)
            if lot is None:
                if lots.setdefault(lot_id, product_id) != product_id:
                    report.add(line, "lot_id", f"Lot '{lot_id}' is named for two products in this file.")
            else:
                # A lot tied to a version belongs to that version's product; a lot without a version belongs to none.
                lot_version = lookup.version_by_id(lot.product_version_id) if lot.product_version_id else None
                if lot_version is not None and (product is None or lot_version.product_id != product.id):
                    report.add(line, "lot_id", f"Lot '{lot_id}' belongs to a different product.")
                elif lot_version is not None and version_id and version is None:
                    # A version the file adds is never the lot's (the lot already has its version).
                    report.add(
                        line,
                        "version",
                        f"Lot '{lot_id}' is of version '{lot_version.version_identifier}', not '{version_id}': "
                        "correct one of them.",
                    )
                else:
                    _check_lot_version(line, row, version, lot_version, stored, report)
        if row["complaint_id"] not in held and row["complaint_id"] not in complaints:
            complaints.add(row["complaint_id"])
            new += 1
    _note_cases(lookup, moved, report)
    report.new_rows = new
    report.creates = {
        key: value
        for key, value in (("products", len(products)), ("versions", len(versions)), ("lots", len(lots)))
        if value
    }
    return new + len(products) + len(versions) + len(lots)


def rows_from_records(entity: str, records: list[dict], report: _Report) -> list[tuple[int, dict]]:
    """Mapped connector records as template rows (record number instead of a file line)."""
    if entity not in TEMPLATES:
        raise HTTPException(404, detail={"code": "TEMPLATE_NOT_FOUND", "message": "Unknown template"})
    spec = TEMPLATES[entity]
    allowed = set(spec["required"] + spec["optional"])
    rows = []
    for number, record in enumerate(records, 1):
        unknown = sorted(set(record) - allowed)
        if unknown:
            report.add(number, unknown[0], f"Field '{unknown[0]}' is not part of the {entity} template.")
            continue
        rows.append((number, {column: str(record.get(column) or "").strip() for column in record}))
    if not records:
        report.add(None, None, "No records to import.")
    return rows


def _named_by_a_complaint(model, column, source: str):
    """True for a product, version or lot a complaints file added because a complaint named it: written in the same
    import as that complaint (one import stamps every record it adds with the same ``created_at``)."""
    from sqlalchemy import and_, exists

    return exists().where(
        and_(
            Complaint.tenant_id == model.tenant_id,
            column == model.id,
            Complaint.source_system == source,
            Complaint.created_at == model.created_at,
        )
    )


def upload_counters(source: str = UPLOAD_SOURCE) -> list[tuple]:
    """``(model, conditions)`` for every kind of record an upload's rows load: what ``uploaded_rows`` counts, per tenant
    here and for many tenants at once in the Platform Admin trial overview (backend/app/trial/story.py). One row is one
    row, as the customer counts the rows of a file: a products row with a version counts its version (the product it
    adds with it does not count again), and the products, versions and lots a complaints file names do not count."""
    from sqlalchemy import and_, exists
    from sqlalchemy.orm import aliased

    from retrieval.record_evidence import RECORD_EVIDENCE_TYPE

    version = aliased(ProductVersion)
    counters = []
    for model in (Product, ProductVersion, LotBatch, Complaint, *business_imports.MODELS):
        conditions = [model.source_system == source]
        if model is business_imports.Evidence:
            # The searchable copy of each imported record is not a row the customer loaded.
            conditions.append(model.evidence_type != RECORD_EVIDENCE_TYPE)
        if model is Product:
            conditions.append(~_named_by_a_complaint(Product, Complaint.product_id, source))
            # Added in the same import as one of its versions: that row counts as the version.
            conditions.append(
                ~exists().where(
                    and_(
                        version.tenant_id == Product.tenant_id,
                        version.product_id == Product.id,
                        version.source_system == source,
                        version.created_at == Product.created_at,
                    )
                )
            )
        elif model is ProductVersion:
            conditions.append(~_named_by_a_complaint(ProductVersion, Complaint.product_version_id, source))
        elif model is LotBatch:
            conditions.append(~_named_by_a_complaint(LotBatch, Complaint.lot_batch_id, source))
        counters.append((model, tuple(conditions)))
    if source == UPLOAD_SOURCE:
        # B7: a free trial's imported Cases count in its row allowance (every CASE_IMPORT Case of a trial is one).
        from backend.app.db.models.intake import IntakeEvent

        counters.append((IntakeEvent, (IntakeEvent.source_system == case_import.SOURCE,)))
    return counters


def upload_counts(tenant_id, source: str = UPLOAD_SOURCE) -> list:
    """One count per kind of record ``upload_counters`` names, each a scalar subquery, to be read in one statement
    with others (``uploaded_rows``, GET /api/v1/trial/status)."""
    from sqlalchemy import select

    return [
        select(func.count(model.id)).where(model.tenant_id == tenant_id, *conditions).scalar_subquery()
        for model, conditions in upload_counters(source)
    ]


def hold_allowance(db: Session, tenant_id, policy: ImportPolicy) -> None:
    """An import into an organization with a row allowance waits for any other one into the same organization to
    commit or roll back, so both never count the same rows left (DEV-04, 0.10.86). A transaction-level advisory lock
    on the organization: taken first, before any row lock of the import, held until this transaction ends (a rollback
    releases it too), and never shared with another organization. The rows used are counted after it is held."""
    if policy.row_limit is not None:
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"mdarix:row-allowance:{policy.source}:{tenant_id}"},
        )


def uploaded_rows(db: Session, tenant_id, source: str = UPLOAD_SOURCE) -> int:
    """The rows the organization uploaded that are in its workspace (``upload_counters``): a free trial's allowance.
    Read in one statement (0.10.44; it was one per kind of record, 15 round trips)."""
    from sqlalchemy import select

    return int(sum(value or 0 for value in db.execute(select(*upload_counts(tenant_id, source))).one()))


ON_PROBLEMS = ("refuse", "skip")
PERSONAL_DATA_HANDLING = ("refuse", "mask")


def import_options(on_problems: str, personal_data: str) -> tuple[bool, bool]:
    """The ``on_problems`` (refuse | skip) and ``personal_data`` (refuse | mask) query parameters, as
    (skip_problem_rows, mask_personal_data). Refusing is the default for both; anything else is a 422."""
    on_problems, personal_data = (on_problems or "refuse").lower(), (personal_data or "refuse").lower()
    if on_problems not in ON_PROBLEMS or personal_data not in PERSONAL_DATA_HANDLING:
        raise HTTPException(
            422,
            detail={
                "code": "INVALID_IMPORT_OPTION",
                "message": "on_problems is refuse or skip; personal_data is refuse or mask",
            },
        )
    return on_problems == "skip", personal_data == "mask"


def check_file(
    db: Session,
    tenant_id,
    entity: str,
    raw: bytes,
    policy: ImportPolicy = TRIAL_POLICY,
    date_format: str = "ISO",
    skip_problem_rows: bool = False,
    mask_personal_data: bool = False,
    reading: FileReading | None = None,
) -> dict:
    """The check report of an upload. A file without a single data row (empty, or a header alone, such as a JSON
    body read as a one-line table) is refused with 422, as importing it is, with its first problem as the message and
    the report (DEV-018); any other file answers its report, ready or with the problems to fix."""
    report = _Report()
    rows = _parse(entity, raw, report, policy, date_format, reading)
    result, _kept = _check_rows(
        db, tenant_id, entity, rows, report, policy, report.date_order, skip_problem_rows, mask_personal_data
    )
    if report.no_rows:
        raise HTTPException(
            422,
            detail={
                "code": "IMPORT_FILE_EMPTY",
                "message": result["issues"][0]["message"] if result["issues"] else "The file has no data rows.",
                "report": result,
            },
        )
    return result


def check_records(db: Session, tenant_id, entity: str, records: list[dict], policy: ImportPolicy) -> dict:
    if not offered(entity, policy):
        raise HTTPException(404, detail={"code": "TEMPLATE_NOT_FOUND", "message": "Unknown template"})
    report = _Report()
    rows = rows_from_records(entity, records, report)
    return _check_rows(db, tenant_id, entity, rows, report, policy)[0]


def _rejects_csv(rows, report: _Report) -> str:
    """The rows set aside, as the uploader sent them (masking undone), with a ``problems`` column: returned to the
    uploader to fix and import again, never stored. Text a spreadsheet would run as a formula is quoted with '."""
    rejected = [(line, row) for line, row in rows if line in report.row_problems]
    if not rejected:
        return ""
    columns = list(rejected[0][1])
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow([*columns, "problems"])
    for line, row in rejected:
        values = [report.originals.get((line, column), row.get(column, "")) for column in columns]
        problems = "; ".join(report.row_problems[line])
        writer.writerow(
            ["'" + value if _spreadsheet_formula(value) else value for value in (*values, f"Row {line}: {problems}")]
        )
    return out.getvalue()


def _check_rows(
    db: Session,
    tenant_id,
    entity: str,
    rows,
    report: _Report,
    policy: ImportPolicy,
    date_format: str = "ISO",
    skip_problem_rows: bool = False,
    mask_personal_data: bool = False,
) -> tuple[dict, list]:
    """Check the rows. By default any problem stops the whole file. With ``skip_problem_rows`` a problem in a row
    sets only that row aside; a problem of the file itself (columns, encoding, size, limits) still stops it all."""
    new_rows = 0
    kept = rows
    # B7 (spec 3.2): a Cases file is masked always (call notes are full of names) and holds up to 5,000 rows.
    mask_personal_data = mask_personal_data or entity == "cases"
    most = case_import.MAX_ROWS if entity == "cases" else MAX_ROWS_PER_FILE
    oversized = len(rows) > most
    if oversized:
        report.add(
            None,
            None,
            f"This file has {len(rows):,} rows; one file can have up to {most:,}. Split it into smaller files.",
        )
    if rows and not oversized:
        _check_values(entity, rows, report, date_format, mask_personal_data)
        if entity == "complaints":
            _claimed_twice(db, tenant_id, rows, report)
        create = policy.create_references
        if skip_problem_rows:
            if not report.file_problems:
                kept = [(line, row) for line, row in rows if line not in report.row_problems]
                if kept:
                    read_notes = len(report.notes)
                    new_rows = _check_references(entity, kept, _Lookup(db, tenant_id), report, create)
                    if any(line in report.row_problems for line, _ in kept):
                        # A row whose references do not resolve is set aside too; the rest are counted again.
                        kept = [(line, row) for line, row in kept if line not in report.row_problems]
                        recount = _Report()
                        new_rows = (
                            _check_references(entity, kept, _Lookup(db, tenant_id), recount, create) if kept else 0
                        )
                        report.creates = recount.creates
                        report.new_rows = recount.new_rows
                        # PV-1 F6: the case notes of the rows still imported, not of the rows now set aside.
                        report.notes[read_notes:] = recount.notes
        elif not report.error_count:
            new_rows = _check_references(entity, rows, _Lookup(db, tenant_id), report, create)
    # The allowance counts the file's own rows that add a record: one row in the file is one row, whatever products,
    # versions or lots a complaints file names besides (uploaded_rows counts the same way).
    used = uploaded_rows(db, tenant_id, policy.source)
    adds = report.new_rows if new_rows else 0
    if policy.row_limit is not None and adds and used + adds > policy.row_limit:
        report.add(
            None,
            None,
            f"This file adds {adds:,} {'row' if adds == 1 else 'rows'}; {policy.limit_label} has "
            f"{max(policy.row_limit - used, 0):,} of {policy.row_limit:,} rows left.",
        )
    if skip_problem_rows:
        ready = bool(kept) and not report.file_problems and not oversized
    else:
        ready = bool(rows) and report.error_count == 0
    rejected = sum(1 for line, _ in rows if line in report.row_problems) if skip_problem_rows else 0
    result = {
        "entity": entity,
        "rows": len(rows),
        "new_records": new_rows,
        # The rows that add a record, as the row allowance counts them (uploaded_rows).
        "new_rows": adds,
        # Rows that update a record already there (the products, versions and lots a file adds are not rows).
        "updated_records": max(len(kept) - adds, 0) if entity != "products" else None,
        "error_count": report.error_count,
        "issues": report.issues,
        "ready": ready,
        "preview": [row for _, row in kept[:8]],
        "rows_used": used,
        "row_limit": policy.row_limit,
        "skip_problem_rows": skip_problem_rows,
        "mask_personal_data": mask_personal_data,
        "rows_to_import": len(kept) if ready else 0,
        "rejected_rows": rejected,
        "masked_values": report.masked_values,
        # How the file was read: headers read under another name, columns left out, notes, and what a complaints file
        # adds besides its complaints (a free trial).
        "columns": report.mapping,
        "ignored_columns": report.ignored,
        "duplicate_columns": report.duplicates,
        "notes": report.notes,
        "also_creates": report.creates,
        # Where and how the file was read (J4-J6): the column names' row, the workbook sheet and its other visible
        # sheets, the date order and number format used, and, for a complaints file without a date column, the
        # columns the uploader may choose for the date.
        "header_row": report.header_line,
        "sheet": report.sheet,
        "sheets": report.sheets,
        "date_format_used": report.date_order,
        "number_format": report.numbers,
        "needs_date_column": report.needs_date_column,
        "date_column_choices": report.date_candidates,
        # Accepted complaint rows that contradict themselves or lack a fact a reporting step needs (0.10.81).
        "row_flags": complaint_flags(kept, report) if entity == "complaints" else [],
    }
    if entity == "complaints":
        # B6a G10 (B6-38): the complaints whose signed conclusion used a fact this file changes.
        signed = signed_fact_changes(db, tenant_id, kept) if ready else []
        result["signed_decisions_changed"] = signed
        result["change_reason_required"] = reason_required(signed, policy)
    if skip_problem_rows and rejected and not report.file_problems:
        result["rejects_csv"] = _rejects_csv(rows, report)
    return result, (kept if ready else [])


def _stamp(now: datetime, row_date: datetime | None = None, source: str = UPLOAD_SOURCE) -> dict:
    when = row_date or now
    return {
        "source_system": source,
        "source_timestamp": when,
        "effective_timestamp": when,
        "recorded_timestamp": now,
        "ingestion_timestamp": now,
        "created_at": now,
        "updated_at": now,
    }


def complaint_flags(rows, report: _Report) -> list[dict]:
    """Complaint rows that are accepted but contradict themselves or lack a fact a reporting step needs (0.10.81, the
    functional review's F3, F4 and F9): flagged in the check and the run's data-quality report, never refused. The
    product asks for a missing country or awareness date at the step that needs it (reportability/facts.py)."""
    from backend.app.reportability import facts

    found: list[dict] = []
    for line, row in rows:
        if line in report.row_problems:
            continue

        def flag(message: str) -> None:
            found.append({"row": line, "complaint_id": row.get("complaint_id"), "message": message})

        def said(column: str) -> bool | None:
            return FLAG_VALUES.get((row.get(column) or "").lower())

        harm = any(said(column) for column in ("death", "serious_injury", "malfunction"))
        if line in report.short_rows:
            cells, columns = report.short_rows[line]
            flag(f"Has {cells} of the header's {columns} columns: the others are read as blank.")
        country = row.get("country") or ""
        if country and not facts.country_known(country):
            flag(f'"{country}" is not a country MDARIX knows: the country will be asked for before reporting.')
        elif harm and not country:
            flag("No country: it decides which market's reporting rules apply, so it will be asked for.")
        if harm and not row.get("awareness_date") and not row.get("received_date"):
            flag("No awareness or received date: the reporting clock stays provisional until the date is entered.")
        if row.get("awareness_date") and row.get("event_date") and row["awareness_date"] < row["event_date"]:
            flag("The awareness date is before the event date: check both.")
        if harm and not said("death") and said("serious_injury") is None:
            # Never pre-filled (0.10.82, D1.10): the tree asks it as a judgement.
            flag("Serious injury left blank: asked at the decision tree, never filled in for you.")
        if (said("death") or said("serious_injury")) and said("patient_involved") is False:
            flag("A death or serious injury, but no patient involved: check both columns.")
    return found


def import_file(
    db: Session,
    tenant_id,
    entity: str,
    raw: bytes,
    policy: ImportPolicy = TRIAL_POLICY,
    date_format: str = "ISO",
    skip_problem_rows: bool = False,
    mask_personal_data: bool = False,
    reading: FileReading | None = None,
    actor: str | None = None,
    change_reason: str | None = None,
) -> dict:
    """Check the file and write it (all or nothing, unless problem rows are set aside). A governed import keeps each
    row's lineage and stores the rows set aside; a set-aside row of an earlier import closes once its record comes in
    with this one (J11), and is replaced when this one sets the same record aside again. ``actor`` is recorded on the
    rows it closes. ``change_reason`` is the run's one reason when it changes facts behind a signed decision."""
    hold_allowance(db, tenant_id, policy)
    checked = _Report()
    parsed = _parse(entity, raw, checked, policy, date_format, reading)
    date_format = checked.date_order
    report, rows = _check_rows(
        db, tenant_id, entity, parsed, checked, policy, date_format, skip_problem_rows, mask_personal_data
    )
    if not report["ready"]:
        raise HTTPException(
            422, detail={"code": "IMPORT_CHECK_FAILED", "message": "Fix the listed problems first", "report": report}
        )
    change_reason = _signed_reason(report, change_reason, policy)
    # The checked rows themselves: masked where asked, without the rows set aside.
    result = _write_rows(db, tenant_id, entity, rows, policy, actor)
    if report.get("signed_decisions_changed"):
        result.update(signed_decisions_changed=report["signed_decisions_changed"], change_reason=change_reason)
    import_ref = uuid.uuid4()
    _after_complaints(db, tenant_id, entity, rows, result, import_ref if policy.quarantine else None, policy.source)
    if policy.quarantine:
        # A governed import: each written row keeps its lineage (R16), each set-aside row is stored for correction
        # (R14), under one import reference that the import's audit event (DATA_IMPORTED, TRIAL_DATA_IMPORTED) carries.
        from backend.app import import_lineage, import_quarantine

        version = import_lineage.mapping_version(entity, report["columns"], date_format)
        import_lineage.write(
            db, tenant_id, import_ref, entity, TEMPLATES[entity]["required"], rows, version, policy.source
        )
        set_aside = [(line, row, checked.row_problems[line]) for line, row in parsed if line in checked.row_problems]
        columns = identity_columns(entity)
        closed = import_quarantine.close_fixed(
            db,
            tenant_id,
            entity,
            columns,
            written={import_quarantine.record_identity(row, columns) for _, row in rows},
            again={import_quarantine.record_identity(row, columns) for _, row, _ in set_aside},
            actor=actor or "system:import",
            source=policy.source,
        )
        import_quarantine.store(db, tenant_id, import_ref, entity, policy.source, set_aside, stored_value)
        result.update(
            import_ref=str(import_ref),
            mapping_version=version,
            quarantined_rows=len(set_aside),
            set_aside_closed=closed,
            quality_report=quality_report(
                checked.data_lines,
                len(rows),
                len(set_aside),
                None if entity == "products" else result["updated"],
                new=report["new_rows"],
                not_used=not_used_columns(report),
            ),
        )
        if entity == "complaints":
            result["quality_report"]["row_flags"] = report["row_flags"]
            # The products and versions it created, kept with the run: Import's checklist shows them loaded (0.10.84).
            if result.get("also_created"):
                result["quality_report"]["also_created"] = result["also_created"]
        if entity == "distribution":
            # Units shipped beyond the units a lot released are flagged, never refused (T-G5).
            result["quality_report"]["flags"] = business_imports.distribution_flags(
                db, tenant_id, [row["lot_id"] for _, row in rows]
            )
    result.update(
        rejected_rows=report["rejected_rows"],
        masked_values=report["masked_values"],
        skip_problem_rows=skip_problem_rows,
        mask_personal_data=report["mask_personal_data"],
    )
    if report.get("rejects_csv"):
        result["rejects_csv"] = report["rejects_csv"]
    return result


def not_used_columns(report: dict) -> list[str]:
    """The file's columns MDARIX did not use, for the run's data-quality report: each header (personal data masked,
    as a file name is), and for a second column of the same field which one was used ("Complaint Received Date (the
    same as Date of Complaint)")."""
    same = {item["header"]: item["kept"] for item in report.get("duplicate_columns") or []}
    return [
        f"{file_label(header)} (the same as {file_label(same[header])})" if header in same else file_label(header)
        for header in report.get("ignored_columns") or []
        if file_label(header)
    ]


def quality_report(
    read: int,
    accepted: int,
    quarantined: int,
    changed: int | None,
    new: int | None = None,
    not_used: list[str] | None = None,
) -> dict:
    """The data-quality report of one governed import run (R17): ``read`` is the file's non-blank data lines, each of
    which must end accepted or quarantined; ``balanced`` says the counts agree with the file. Accepted rows are new
    (``new``, by default every row that changed nothing), changed (they changed a field of a record already there) or
    unchanged (a record already there, as the file has it: J9). The three are None for a products file, whose rows may
    add versions to an existing product."""
    # The file's columns not used (J5): kept with the run so its report names every column the file had.
    columns = {"columns_not_used": not_used} if not_used is not None else {}
    if changed is None:
        return {
            "rows_read": read,
            "rows_accepted": accepted,
            "rows_quarantined": quarantined,
            "rows_changed": None,
            "rows_new": None,
            "rows_unchanged": None,
            "balanced": read == accepted + quarantined,
            **columns,
        }
    new = accepted - changed if new is None else new
    return {
        "rows_read": read,
        "rows_accepted": accepted,
        "rows_quarantined": quarantined,
        "rows_changed": changed,
        "rows_new": new,
        "rows_unchanged": max(accepted - new - changed, 0),
        "balanced": read == accepted + quarantined,
        **columns,
    }


def import_records(db: Session, tenant_id, entity: str, records: list[dict], policy: ImportPolicy) -> dict:
    hold_allowance(db, tenant_id, policy)
    report = check_records(db, tenant_id, entity, records, policy)
    if not report["ready"]:
        raise HTTPException(
            422, detail={"code": "IMPORT_CHECK_FAILED", "message": "Fix the listed problems first", "report": report}
        )
    _signed_reason(report, None, policy)
    rows = rows_from_records(entity, records, _Report())
    result = _write_rows(db, tenant_id, entity, rows, policy)
    _after_complaints(db, tenant_id, entity, rows, result, None, policy.source)
    if report.get("signed_decisions_changed"):
        # A QMS sync: its reason, "QMS sync <run>", is recorded with the run (access/connector_sync.py).
        result["signed_decisions_changed"] = report["signed_decisions_changed"]
    return result


def _write_rows(db: Session, tenant_id, entity: str, rows, policy: ImportPolicy, actor: str | None = None) -> dict:
    source = policy.source
    lookup = _Lookup(db, tenant_id)
    now = datetime.now(timezone.utc)
    if entity == "cases":
        return {"entity": entity, "rows": len(rows), **case_import.write(db, tenant_id, rows, lookup, now, actor)}
    created = updated = 0
    also_created: dict[str, int] = {}
    # A complaints file: its complaints that exist already, read at once; their evidence written in one batch after
    # the rows (NEW-4). Each row used to cost about 13 statements; the result is the same.
    complaints = lookup.complaints(row["complaint_id"] for _, row in rows) if entity == "complaints" else {}
    # TA-20.4 / CI-31 (B2, Connect): a QMS ID that an MDARIX complaint (or its Case) holds updates that complaint.
    merged = (
        _qms_matches(
            db,
            tenant_id,
            complaints,
            [row["complaint_id"] for _, row in rows],
            {row["complaint_id"]: row.get("mdarix_ref") for _, row in rows},
        )
        if entity == "complaints"
        else {}
    )
    complaints.update(merged)
    new_complaints: dict[str, dict] = {}
    evidence: list = []
    proposed: dict = {}  # complaint id -> (use environment, user type) as the file gives them
    changes: list[dict] = []  # each field a re-upload changes on a complaint already there (G20)
    file_lots: dict[str, list[str]] = {}  # complaint id -> the lots its rows name, in file order (a kit's, J32)
    if entity in business_imports.TEMPLATES:
        created, updated, changes = business_imports.write(
            entity, rows, db, tenant_id, lookup, lambda when: _stamp(now, when, source), _date, now, source
        )
        return {"entity": entity, "created": created, "updated": updated, "rows": len(rows), "_changes": changes}
    for _, row in rows:
        if entity == "products":
            product = lookup.product(row["product_id"])
            if product is None:
                product = Product(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    product_identifier=row["product_id"],
                    name=row["product_name"],
                    product_family=row.get("product_family") or None,
                    device_category=product_facts.category_code(row.get("device_category")),
                    **_single_use_values(row, None),
                    lifecycle_status="active",
                    source_identifier=row["product_id"],
                    **_stamp(now, None, source),
                )
                db.add(product)
                db.flush()
                lookup.products[row["product_id"]] = product
                created += 1
            elif product.source_system == source:
                product.name = row["product_name"]
                product.product_family = row.get("product_family") or product.product_family
                product.device_category = (
                    product_facts.category_code(row.get("device_category")) or product.device_category
                )
                for name, value in _single_use_values(row, product).items():
                    setattr(product, name, value)
                product.updated_at = now
            if not row.get("version"):
                db.flush()
                continue
            released = _date(row["version_release_date"]) if row.get("version_release_date") else None
            version = lookup.version(product, row["version"])
            if version is None:
                version = ProductVersion(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    product_id=product.id,
                    version_identifier=row["version"],
                    lifecycle_status="active",
                    release_timestamp=released,
                    source_identifier=f"{row['product_id']}:{row['version']}",
                    **_stamp(now, released, source),
                )
                db.add(version)
                lookup.versions[(row["product_id"], row["version"])] = version
                created += 1
            else:
                if released:
                    version.release_timestamp = released
                version.updated_at = now
                updated += 1
            db.flush()
            continue
        if entity == "complaints" and policy.create_references:
            # A free trial's complaints file adds the products, versions and lots it names that are not loaded yet;
            # they count as created, and are also told apart (``also_created``) so the complaints are not overstated.
            for kind, count in _add_named_references(db, tenant_id, row, lookup, now, source).items():
                also_created[kind] = also_created.get(kind, 0) + count
                created += count
        product = lookup.product(row["product_id"])
        version = lookup.version(product, row["version"]) if row.get("version") else None
        if entity == "lots":
            built = _date(row["manufacture_date"]) if row.get("manufacture_date") else None
            site = lookup.site(row["site_id"]) if row.get("site_id") else None
            quantity = _count(row["quantity"]) if row.get("quantity") else None
            expiry = _date(row["expiry_date"]).date() if row.get("expiry_date") else None
            lot = lookup.lot(row["lot_id"])
            if lot is None:
                lot = LotBatch(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    lot_identifier=row["lot_id"],
                    product_version_id=version.id if version else None,
                    manufacturing_site_id=site.id if site else None,
                    status="active",
                    quantity=quantity,
                    expiry_date=expiry,
                    source_identifier=row["lot_id"],
                    **_stamp(now, built, source),
                )
                db.add(lot)
                lookup.lots[row["lot_id"]] = lot
                created += 1
            else:
                changed = business_imports.apply_values(
                    lot,
                    {
                        "product_version_id": version.id if version else lot.product_version_id,
                        "manufacturing_site_id": site.id if site else lot.manufacturing_site_id,
                        "effective_timestamp": built or lot.effective_timestamp,
                        "quantity": quantity if quantity is not None else lot.quantity,
                        "expiry_date": expiry or lot.expiry_date,
                    },
                )
                if changed:
                    lot.updated_at = now
                    updated += 1
            db.flush()
            continue
        lot = lookup.lot(row["lot_id"]) if row.get("lot_id") else None
        if row["complaint_id"] in file_lots:
            # The complaint's next lot (a kit): its first row gave the complaint; this one adds only the lot.
            if lot is not None and lot.lot_identifier not in file_lots[row["complaint_id"]]:
                file_lots[row["complaint_id"]].append(lot.lot_identifier)
            continue
        if "lot_id" in row:
            file_lots[row["complaint_id"]] = [lot.lot_identifier] if lot else []
        event = _date(row["event_date"]) if row.get("event_date") else None
        received = _date(row["received_date"]) if row.get("received_date") else None
        complaint = complaints.get(row["complaint_id"])
        values = {
            "product_id": product.id,
            "product_version_id": version.id if version else (lot.product_version_id if lot else None),
            "lot_batch_id": lot.id if lot else None,
            "event_timestamp": event,
            # Only the received date the file gives (0.10.81, F10): an event date is never shown as "received".
            "complaint_timestamp": received,
            "description": row["description"],
            "status": (row.get("status") or "open").lower(),
            **_complaint_details(row),
        }
        if complaint is not None and row["complaint_id"] not in new_complaints:
            # A re-upload sets only what its file holds: a column it leaves out (or a blank status) keeps the stored
            # value, so a file without a status column never reopens a closed complaint (J9).
            values = {name: value for name, value in values.items() if _from_file(name, row)}
            # PV-1 F5: a blank version cell keeps a stored version; it only fills an unknown one from the lot.
            if not row.get("version") and complaint.product_version_id is not None:
                values.pop("product_version_id", None)
        if complaint is None:
            fields = {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "complaint_identifier": row["complaint_id"],
                "source_identifier": row["complaint_id"],
                "other_lots": None,
                **values,
                **_stamp(now, received or event, source),
                # Owner Q3: set only by 0.10.93 and later, so it tells which imports go on "To triage" (intake/service).
                "last_synced_at": now,
            }
            # Not added to the session: the new complaints are inserted together after the rows (db/bulk.py).
            complaint = Complaint(**fields)
            complaints[row["complaint_id"]] = complaint
            new_complaints[row["complaint_id"]] = fields
            created += 1
        elif row["complaint_id"] in new_complaints:  # named twice in the file: the later row wins, as before
            for name, value in values.items():
                setattr(complaint, name, value)
            new_complaints[row["complaint_id"]].update(values, updated_at=now)
        else:
            found = _field_changes(complaint, values, row["complaint_id"])
            changes.extend(found)
            for name, value in values.items():
                setattr(complaint, name, value)
            if row["complaint_id"] in merged:  # the QMS now owns it: its file wins on the master fields
                complaint.qms_ref, complaint.record_owner, complaint.last_synced_at = (
                    row["complaint_id"],
                    "EXTERNAL",
                    now,
                )
            elif complaint.last_synced_at is not None:  # imported from 0.10.93 on: the file was read again now
                complaint.last_synced_at = now
            if found:  # "updated" counts the rows that changed a field, not every row seen again
                complaint.updated_at = now
                updated += 1
        # PV-1 F5: a version taken from the lot says so in the record.
        from_lot = (
            lookup.version_by_id(lot.product_version_id)
            if version is None
            and lot is not None
            and lot.product_version_id is not None
            and lot.product_version_id == complaint.product_version_id
            else None
        )
        evidence.append(_complaint_evidence(complaint, row, product, version, lot, source, from_lot))
        if row.get("use_environment") or row.get("user_type"):
            proposed[row["complaint_id"]] = (row.get("use_environment"), row.get("user_type"))
    for identifier, names in file_lots.items():
        other = names[1:] or None
        if identifier in new_complaints:
            new_complaints[identifier]["other_lots"] = other
        else:
            found = _field_changes(complaints[identifier], {"other_lots": other}, identifier)
            changes.extend(found)
            complaints[identifier].other_lots = other
            if found:
                complaints[identifier].updated_at = now
    if evidence:
        from backend.app.db.bulk import insert_rows
        from retrieval.record_evidence import upsert_record_evidences

        db.flush()
        insert_rows(db, Complaint, list(new_complaints.values()))
        upsert_record_evidences(db, tenant_id, evidence)
        _propose_classifications(db, tenant_id, complaints, proposed, now)
    result = {"entity": entity, "created": created, "updated": updated, "rows": len(rows), "_changes": changes}
    if entity == "complaints":
        qms = _qms_triage(db, tenant_id, rows, complaints, now)
        if qms["accepted"] or qms["to_confirm"]:
            result["qms_triage"] = qms
    if also_created:
        result["also_created"] = also_created
    return result


QMS_TRIAGE_COLUMNS = ("triage_date", "triage_severity", "triage_owner", "immediate_action")


def _qms_triage(db: Session, tenant_id, rows, complaints: dict, now: datetime) -> dict:
    """T-D9 (0.10.93, B2; TR-14, TR-37, TR-38): a complaint row with the QMS triage columns gets a triage record with
    source QMS. With no flag (no death, injury, harm, malfunction or harm words) it is accepted as triaged, no click
    needed; with one it waits for a person to confirm it ("From your QMS: confirm", on the triage list because it is
    flagged). A complaint that already has a triage record keeps it: a file never changes a person's triage."""
    from backend.app.db.bulk import insert_rows
    from backend.app.db.models.intake import TriageRecord, TriageRecordVersion
    from backend.app.intake import rules as intake_rules
    from backend.app.intake import service as intake_service
    from backend.app.intake import triage_rules
    from backend.app.reportability import markets

    wanted: dict[str, dict] = {}
    for _, row in rows:
        if row["complaint_id"] not in wanted and any(row.get(column) for column in QMS_TRIAGE_COLUMNS):
            wanted[row["complaint_id"]] = row
    found = {"accepted": 0, "to_confirm": 0}
    if not wanted:
        return found
    ids = [complaints[key].id for key in wanted]
    had: set = set()
    for start in range(0, len(ids), 5000):
        had |= {
            row[0]
            for row in db.query(TriageRecord.subject_id).filter(
                TriageRecord.tenant_id == tenant_id,
                TriageRecord.subject_kind == intake_service.COMPLAINT,
                TriageRecord.subject_id.in_(ids[start : start + 5000]),
            )
        }
    records, versions = [], []
    for identifier, row in wanted.items():
        complaint = complaints[identifier]
        if complaint.id in had:
            continue
        flags = intake_rules.complaint_flags(intake_service._complaint_record(complaint))
        action = row.get("immediate_action") or None
        fields = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "subject_kind": intake_service.COMPLAINT,
            "subject_id": complaint.id,
            "opened_at": now,
            "source_system": "QMS",
            "source_identifier": identifier,
            "qms_triaged_at": _date(row["triage_date"]) if row.get("triage_date") else None,
            "qms_owner_text": row.get("triage_owner") or None,
            "severity": markets.level_of_severity(row.get("triage_severity")),
            "immediate_action": action,
            "created_by": intake_service.QMS_IMPORT_ACTOR,
            "created_at": now,
            "updated_at": now,
        }
        if flags:
            found["to_confirm"] += 1
        else:
            # TR-37: accepted as the QMS recorded it, version 1, no person's click.
            fields.update(
                speed="ROUTINE",
                flags_at_completion={"facts": triage_rules.facts([]), "codes": []},
                containment={"choices": ["OTHER" if action else "NONE_NEEDED"], "text": action or ""},
                completed_by=intake_service.QMS_IMPORT_ACTOR,
                completed_at=now,
            )
            versions.append(
                {
                    "tenant_id": tenant_id,
                    "triage_record_id": fields["id"],
                    "version": 1,
                    "snapshot": intake_service.triage_snapshot(TriageRecord(**fields)),
                    "changed_fields": {},
                    "change_reason": "Triaged in your QMS (imported)",
                    "changed_by": intake_service.QMS_IMPORT_ACTOR,
                    "changed_at": now,
                }
            )
            found["accepted"] += 1
        records.append(fields)
    insert_rows(db, TriageRecord, records)
    insert_rows(db, TriageRecordVersion, versions)
    return found


# The complaint fields a re-upload sets, and the file columns each comes from (the other fields come from
# _complaint_details, which reads only the columns a file has).
_COMPLAINT_FIELD_COLUMNS = {
    "product_version_id": ("version", "lot_id"),
    "lot_batch_id": ("lot_id",),
    "event_timestamp": ("event_date",),
    "complaint_timestamp": ("received_date",),
}


def _from_file(field: str, row: dict) -> bool:
    """Whether the row's file gives this complaint field (a blank status gives none: it keeps the stored one)."""
    if field == "status":
        return bool(row.get("status"))
    columns = _COMPLAINT_FIELD_COLUMNS.get(field)
    return columns is None or any(column in row for column in columns)


def _shown(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == datetime.min.time() else value.isoformat()
    return str(value)


def _field_changes(complaint: Complaint, values: dict, identifier: str) -> list[dict]:
    """The fields a re-upload changes on a complaint, with the value before and after (the history of field changes,
    G20); an unchanged field is not listed."""
    found = []
    for name, value in values.items():
        before = getattr(complaint, name)
        if isinstance(before, datetime) and isinstance(value, datetime):
            same = before.replace(tzinfo=None) == value.replace(tzinfo=None)
        else:
            same = before == value
        if not same:
            found.append(
                {
                    "entity": "complaints",
                    "record_id": complaint.id,
                    "record_key": identifier,
                    "field": name,
                    "before": _shown(before),
                    "after": _shown(value),
                }
            )
    return found


# B6a G10 (B6-38): the complaint facts a signed market conclusion is counted from, as the check names them.
SIGNED_FACTS = {
    "country": "country",
    "awareness_timestamp": "awareness date",
    "event_timestamp": "event date",
    "death": "death",
    "serious_injury": "serious injury",
    "product_id": "product",
    "lot_batch_id": "lot",
}
SIGNED_FACTS_REIMPORTED = "COMPLAINT_FACTS_REIMPORTED"


def signed_fact_changes(db: Session, tenant_id, rows) -> list[dict]:
    """B6a G10 (B6-38): the complaints already here with a signed market conclusion whose facts (SIGNED_FACTS) these
    rows change, each with the facts' values before and after, read the way _write_rows sets them (a column the file
    leaves out keeps its value; a complaint's first row counts). Nothing signed is rewritten: the conclusion then
    reads "Facts changed after signing: re-check" (reportability/assessment_router.facts_changed)."""
    from backend.app.db.models.market_assessment import ComplaintMarketAssessment as Conclusion

    lookup = _Lookup(db, tenant_id)
    ids = [row["complaint_id"] for _, row in rows]
    stored = lookup.complaints(ids)
    stored.update(
        _qms_matches(db, tenant_id, stored, ids, {row["complaint_id"]: row.get("mdarix_ref") for _, row in rows})
    )
    keys = [complaint.id for complaint in stored.values()]
    signed: set = set()
    for start in range(0, len(keys), 1000):
        signed |= {
            row[0]
            for row in db.query(Conclusion.complaint_id)
            .filter(
                Conclusion.tenant_id == tenant_id,
                Conclusion.complaint_id.in_(keys[start : start + 1000]),
                Conclusion.signed_at.isnot(None),
            )
            .distinct()
        }
    found: list[dict] = []
    seen: set = set()
    for _, row in rows:
        complaint = stored.get(row["complaint_id"])
        if complaint is None or complaint.id not in signed or row["complaint_id"] in seen:
            continue
        seen.add(row["complaint_id"])
        values = {name: value for name, value in _complaint_details(row).items() if name in SIGNED_FACTS}
        product = lookup.product(row["product_id"])
        values["product_id"] = product.id if product else None
        if "event_date" in row:
            values["event_timestamp"] = _date(row["event_date"]) if row["event_date"] else None
        if "lot_id" in row:
            lot = lookup.lot(row["lot_id"]) if row["lot_id"] else None
            values["lot_batch_id"] = lot.id if lot else None
        changes = _field_changes(complaint, values, row["complaint_id"])
        if changes:
            found.append(
                {
                    "complaint_id": row["complaint_id"],
                    "record_id": str(complaint.id),
                    "fields": [SIGNED_FACTS[change["field"]] for change in changes],
                    "before": {SIGNED_FACTS[change["field"]]: change["before"] for change in changes},
                    "after": {SIGNED_FACTS[change["field"]]: change["after"] for change in changes},
                }
            )
    return found


def _automatic_reason(policy: ImportPolicy) -> bool:
    """A QMS sync records its own reason, "QMS sync <run>" (access/connector_sync.py)."""
    return policy.source.startswith("CONNECTOR:")


def reason_required(signed: list[dict], policy: ImportPolicy) -> bool:
    from backend.app import feature_set

    return bool(signed) and not _automatic_reason(policy) and feature_set.switched_on("MDARIX_B6_CHANGE_REASON")


def _signed_reason(report: dict, change_reason: str | None, policy: ImportPolicy) -> str | None:
    """The run's one reason, whitespace collapsed; refused (422 CHANGE_REASON_REQUIRED) when the file changes facts
    behind a signed decision and no reason is given (B6a G10, D3)."""
    reason = " ".join((change_reason or "").split())[:2000] or None
    signed = report.get("signed_decisions_changed") or []
    if reason is None and reason_required(signed, policy):
        raise HTTPException(
            422,
            detail={
                "code": "CHANGE_REASON_REQUIRED",
                "message": f"This file changes facts behind the signed conclusion of {len(signed):,} "
                f"{'complaint' if len(signed) == 1 else 'complaints'}: say why, once for the whole import.",
                "signed_decisions_changed": signed,
            },
        )
    return reason


def signed_change_events(tenant_id, actor_ref, signed: list[dict], reason: str | None) -> list:
    """One audit event per complaint whose signed facts a run changed, with the run's reason and the values before
    and after: an edit on a signed record, so the audit trail review lists it under "edits after a signature"."""
    from backend.app.enterprise_audit import make_audit_event

    return [
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=actor_ref,
            action=SIGNED_FACTS_REIMPORTED,
            entity_type="Complaint",
            entity_id=uuid.UUID(item["record_id"]),
            reason=reason,
            details={"complaint": item["complaint_id"], "fields": item["fields"]},
            old_values=item["before"],
            new_values=item["after"],
        )
        for item in signed
    ]


def _after_complaints(db: Session, tenant_id, entity: str, rows, result: dict, import_ref, source: str) -> None:
    """A file's field changes are stored with the run (a complaint's fields; the product and version of a risk,
    requirement, investigation or CAPA, PV-1 F7), and each QMS-complaint task whose complaint ID a complaints file
    brings is closed (T-G20)."""
    changes = result.pop("_changes", [])
    if entity != "complaints" and not changes:
        return
    from backend.app.intake import service as intake

    now = datetime.now(timezone.utc)
    result["field_changes"] = intake.record_changes(db, tenant_id, changes, import_ref, source, now)
    if entity != "complaints":
        return
    result["qms_tasks_closed"] = intake.confirm_by_import(
        db, tenant_id, [row.get("complaint_id") for _, row in rows], "system:import", now
    )


def _add_named_references(
    db: Session, tenant_id, row: dict, lookup: _Lookup, now: datetime, source: str
) -> dict[str, int]:
    """The product, version and lot a complaint row names, added when not loaded yet (marked as uploaded, like every
    imported record). Returns how many of each were added, keyed like the check's ``also_creates``."""
    added: dict[str, int] = {}
    product = lookup.product(row["product_id"])
    if product is None:
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_identifier=row["product_id"],
            name=(row.get("product_name") or row["product_id"])[:255],
            lifecycle_status="active",
            source_identifier=row["product_id"],
            **_stamp(now, None, source),
        )
        db.add(product)
        db.flush()
        lookup.products[row["product_id"]] = product
        added["products"] = 1
    version = None
    if row.get("version"):
        version = lookup.version(product, row["version"])
        if version is None:
            version = ProductVersion(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                product_id=product.id,
                version_identifier=row["version"],
                lifecycle_status="active",
                source_identifier=f"{row['product_id']}:{row['version']}",
                **_stamp(now, None, source),
            )
            db.add(version)
            db.flush()
            lookup.versions[(row["product_id"], row["version"])] = version
            added["versions"] = 1
    if row.get("lot_id") and lookup.lot(row["lot_id"]) is None:
        lot = LotBatch(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            lot_identifier=row["lot_id"],
            product_version_id=version.id if version else None,
            status="active",
            source_identifier=row["lot_id"],
            **_stamp(now, None, source),
        )
        db.add(lot)
        db.flush()
        lookup.lots[row["lot_id"]] = lot
        added["lots"] = 1
    return added


def _qms_claims(db: Session, tenant_id, known: dict, identifiers, refs: dict | None = None) -> dict[str, set]:
    """QMS ID -> the complaints MDARIX created that claim it (their ``qms_ref``, or the ``qms_ref`` typed on the Case
    they escalated from), for the file's IDs that are not a complaint's own identifier already (``known``). B7: a row
    whose ``mdarix_ref`` (``refs``: QMS ID -> MDARIX ID) is a complaint MDARIX made from a Case, with no QMS ID yet,
    claims that complaint too (the export for QMS entry coming back)."""
    from backend.app.db.models.intake import IntakeEvent

    wanted = sorted({value for value in identifiers if value and value not in known})
    claims: dict[str, set] = {}
    named = {qms: ref for qms, ref in (refs or {}).items() if qms in wanted and ref}
    if named:
        found = dict(
            db.query(Complaint.business_id, Complaint.id).filter(
                Complaint.tenant_id == tenant_id,
                Complaint.business_id.in_(sorted(set(named.values()))),
                Complaint.source_system == "MDARIX_CASE",
                Complaint.qms_ref.is_(None),
            )
        )
        for qms, ref in named.items():
            if ref in found:
                claims.setdefault(qms, set()).add(found[ref])
    for start in range(0, len(wanted), 1000):
        chunk = wanted[start : start + 1000]
        for qms_ref, complaint_id in db.query(Complaint.qms_ref, Complaint.id).filter(
            Complaint.tenant_id == tenant_id, Complaint.qms_ref.in_(chunk)
        ):
            claims.setdefault(qms_ref, set()).add(complaint_id)
        for qms_ref, complaint_id in db.query(IntakeEvent.qms_ref, IntakeEvent.complaint_id).filter(
            IntakeEvent.tenant_id == tenant_id, IntakeEvent.qms_ref.in_(chunk), IntakeEvent.complaint_id.isnot(None)
        ):
            claims.setdefault(qms_ref, set()).add(complaint_id)
    return claims


def _claimed_twice(db: Session, tenant_id, rows, report: _Report) -> None:
    """IN-14 (spec 3.3): a row whose ID two complaints claim as their QMS ID is set aside, never merged into one of
    them nor made a third complaint."""
    ids = [row.get("complaint_id") for _, row in rows]
    refs = {row.get("complaint_id"): row.get("mdarix_ref") for _, row in rows if row.get("mdarix_ref")}
    claims = _qms_claims(db, tenant_id, _Lookup(db, tenant_id).complaints(value for value in ids if value), ids, refs)
    for line, row in rows:
        if len(claims.get(row.get("complaint_id"), ())) > 1:
            report.add(line, "complaint_id", f"Two complaints claim QMS ID {row['complaint_id']}: reconcile them")


def _qms_matches(db: Session, tenant_id, known: dict, identifiers: list[str], refs: dict | None = None) -> dict:
    """The file's complaint IDs that are the QMS ID of a complaint MDARIX created: ID -> that complaint, so the row
    updates it instead of making a second one (TA-20.4). An ID two complaints claim was set aside at the check (IN-14)
    and is left out here too."""
    claims = _qms_claims(db, tenant_id, known, identifiers, refs)
    single = {qms_ref: next(iter(ids)) for qms_ref, ids in claims.items() if len(ids) == 1}
    if not single:
        return {}
    rows = db.query(Complaint).filter(Complaint.tenant_id == tenant_id, Complaint.id.in_(list(single.values())))
    by_id = {row.id: row for row in rows}
    return {qms_ref: by_id[complaint_id] for qms_ref, complaint_id in single.items() if complaint_id in by_id}


def _propose_classifications(db: Session, tenant_id, complaints: dict, proposed: dict, now: datetime) -> None:
    """The optional use environment and user type columns as proposed classifications (T-G39), for a person to confirm
    when the disposition is signed. A value outside the fixed lists stays Unknown, with the value kept as given;
    nothing is inferred from free text. A complaint already classified keeps its classification."""
    from backend.app.complaint_classification import rules as coding
    from backend.app.db.models.market_assessment import ComplaintClassification

    if not proposed:
        return
    ids = {complaints[ref].id: ref for ref in proposed if ref in complaints}
    classified = {
        row[0]
        for row in db.query(ComplaintClassification.complaint_id).filter(
            ComplaintClassification.tenant_id == tenant_id, ComplaintClassification.complaint_id.in_(list(ids))
        )
    }
    for complaint_id, ref in ids.items():
        if complaint_id in classified:
            continue
        environment, environment_source = coding.code_source_value("use_environment", proposed[ref][0])
        user, user_source = coding.code_source_value("user_type", proposed[ref][1])
        db.add(
            ComplaintClassification(
                tenant_id=tenant_id,
                complaint_id=complaint_id,
                version=1,
                use_environment=environment,
                user_type=user,
                source_values={"use_environment": environment_source, "user_type": user_source},
                state="PROPOSED",
                coding_criteria_version=coding.CODING_CRITERIA_VERSION,
                created_by="system:trial-import",
                created_at=now,
            )
        )
    db.flush()


def _single_use_values(row: dict, product) -> dict:
    """A products row's single-use flag and use period; a blank or absent column keeps the stored value."""
    flag = FLAG_VALUES.get((row.get("single_use") or "").lower())
    period = int(row["use_period_days"]) if row.get("use_period_days") else None
    return {
        "single_use": flag if flag is not None else getattr(product, "single_use", None),
        "use_period_days": period if period is not None else getattr(product, "use_period_days", None),
    }


def _complaint_details(row: dict) -> dict:
    """The optional regulatory columns of a complaint row; a column the batch leaves out keeps its stored value."""
    details: dict = {}
    for column in ("severity", "country", "reporter_type", "complaint_type", "problem_code", "serial_number", "udi"):
        if column in row:
            details[column] = row[column] or None
    for column in FLAG_COLUMNS:
        if column in row:
            details[column] = FLAG_VALUES.get(row[column].lower()) if row[column] else None
    if "awareness_date" in row:
        details["awareness_timestamp"] = _date(row["awareness_date"]) if row["awareness_date"] else None
    return details


def _complaint_evidence(complaint: Complaint, row: dict, product, version, lot, source: str, from_lot=None):
    """What makes the complaint searchable by Ask MDARIX and the investigator (retrieval/record_evidence.py): its
    evidence row, written for the whole file at once by upsert_record_evidences."""
    from retrieval.record_evidence import RecordEvidence, summary

    facts = {
        "Product": row["product_id"],
        "Version": row.get("version") or (f"{from_lot.version_identifier} (from the lot)" if from_lot else None),
        "Lot": row.get("lot_id"),
        "Event date": complaint.event_timestamp,
        "Received": complaint.complaint_timestamp,
        "Status": complaint.status,
        "Severity": complaint.severity,
        "Country": complaint.country,
        "Complaint type": complaint.complaint_type,
        "Problem code": complaint.problem_code,
        "Device returned": complaint.device_returned,
        "Patient involved": complaint.patient_involved,
        "Serious injury": complaint.serious_injury,
        "Death": complaint.death,
        "Malfunction": complaint.malfunction,
    }
    return RecordEvidence(
        kind="COMPLAINT",
        identifier=complaint.complaint_identifier,
        title=f"Complaint {complaint.complaint_identifier}",
        content=summary(f"Complaint {complaint.complaint_identifier}", facts, f"Description: {complaint.description}"),
        links=[
            ("Complaint", complaint.id),
            ("Product", product.id if product else None),
            ("ProductVersion", version.id if version else complaint.product_version_id),
            ("LotBatch", lot.id if lot else None),
        ],
        source=source,
    )


def after_import(background, tenant_id, result: dict, *, source: str) -> dict:
    """Schedule what follows an import, after its response (``background``: the route's BackgroundTasks, run in
    order): signals from the complaints it created or changed (backend/app/signals/hooks.py ``detect_after_import``,
    in a session of its own bound to the organization), then, once they are found, the embeddings for semantic search
    over its records are queued for the background service (retrieval/record_evidence.py ``queue_embeddings``; their
    text is already searchable). Neither can fail or undo the import. The answer says when signals are being found
    (``signals: "FINDING"``, until ``hooks.detection_pending`` turns false); the insights are read from their own
    route (GET /api/v1/trial/insights), so the answer does not wait for them."""
    from backend.app.db.data_plane import open_tenant_data_session
    from backend.app.signals import hooks as signal_hooks
    from retrieval.record_evidence import queue_embeddings

    records = int(result.get("rows") or 0)
    if signal_hooks.imported_complaints(result):
        background.add_task(
            signal_hooks.detect_after_import, open_tenant_data_session, tenant_id, source=source, records=records
        )
        result = {**result, "signals": "FINDING"}
    if records:
        imported_at = datetime.now(timezone.utc).isoformat()
        background.add_task(queue_embeddings, tenant_id, source=source, records=records, imported_at=imported_at)
    return result


def insights(db: Session, tenant_id, source: str | None = None) -> dict:
    """Counts and concentrations computed from the workspace's complaints; facts for a person to interpret. ``source``
    names the data (the top bar's "Sample data · Your data", 0.10.80); without it, the imported data, else the sample."""
    if source in (UPLOAD_SOURCE, SAMPLE_SOURCE):
        scope = source
    else:
        own = (
            db.query(Complaint.id)
            .filter(Complaint.tenant_id == tenant_id, Complaint.source_system == UPLOAD_SOURCE)
            .first()
            is not None
        )
        scope = UPLOAD_SOURCE if own else SAMPLE_SOURCE
    own = scope == UPLOAD_SOURCE
    # The columns the panel reads and each complaint's month, not whole records (insight_questions.COMPLAINT_COLUMNS);
    # the same filter as before and no order, so the complaints come in the same order.
    complaints = (
        db.query(*insight_questions.COMPLAINT_COLUMNS)
        .filter(Complaint.tenant_id == tenant_id, Complaint.source_system == scope)
        .all()
    )
    total = len(complaints)
    products = {p.id: p for p in db.query(Product).filter(Product.tenant_id == tenant_id).all()}
    versions = {v.id: v for v in db.query(ProductVersion).filter(ProductVersion.tenant_id == tenant_id).all()}
    lots = {lot.id: lot for lot in db.query(LotBatch).filter(LotBatch.tenant_id == tenant_id).all()}

    def tally(key):
        counts: dict = {}
        for complaint in complaints:
            value = key(complaint)
            if value is not None:
                counts[value] = counts.get(value, 0) + 1
        return sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))

    by_product = [
        {
            "product_id": products[pid].product_identifier,
            "product_business_id": products[pid].business_id,
            "name": products[pid].name,
            "complaints": n,
        }
        for pid, n in tally(lambda c: c.product_id)
        if pid in products
    ]
    by_version = [
        {
            "product_id": products[versions[vid].product_id].product_identifier
            if versions[vid].product_id in products
            else None,
            "product_business_id": products[versions[vid].product_id].business_id
            if versions[vid].product_id in products
            else None,
            "version": versions[vid].version_identifier,
            "version_business_id": versions[vid].business_id,
            "complaints": n,
        }
        for vid, n in tally(lambda c: c.product_version_id)
        if vid in versions
    ]
    by_lot = [
        {"lot_id": lots[lid].lot_identifier, "lot_business_id": lots[lid].business_id, "complaints": n}
        for lid, n in tally(lambda c: c.lot_batch_id)
        if lid in lots
    ][:5]
    by_month = sorted(
        ({"month": month, "complaints": n} for month, n in tally(lambda c: c.month)),
        key=lambda item: item["month"],
    )
    findings = []
    if by_version and total:
        top = by_version[0]
        share = round(100 * top["complaints"] / total)
        if share >= 40 and len(by_version) > 1:
            # The product's name, as people read it, rather than its identifier.
            named = next((item["name"] for item in by_product if item["product_id"] == top["product_id"]), None)
            findings.append(
                f"{share}% of complaints ({top['complaints']:,} of {total:,}) concern "
                f"{named or top['product_id']} {top['version']}."
            )
    if by_lot and total:
        top_lots = by_lot[:2]
        share = round(100 * sum(item["complaints"] for item in top_lots) / total)
        if share >= 30 and len(by_lot) > 2:
            findings.append(
                f"{share}% of complaints come from lots {' and '.join(item['lot_id'] for item in top_lots)}."
            )
    # The headline numbers, the trend, the complaints for filtering on screen and the questions answered in place.
    # The rise is measured on the same months the trend shows (months without complaints count as zero).
    extra = insight_questions.build(db, tenant_id, scope, complaints, products, versions, lots)
    rate = extra["headline"]["rate"]
    if rate and rate["earlier"] and rate["recent"] >= 1.5 * rate["earlier"]:
        findings.append(
            f"Complaints in the last {insight_questions.RECENT_MONTHS} months average {rate['recent']:.1f} per month, "
            f"up from {rate['earlier']:.1f} before."
        )
    return {
        "scope": "your data" if own else "sample data",
        # The complaints' source, so "Open these complaints" lists the same ones (GET /api/v1/complaints?source_system=).
        "source_system": scope,
        "total_complaints": total,
        "by_product": by_product,
        "by_version": by_version[:6],
        "by_lot": by_lot,
        "by_month": by_month,
        "findings": findings,
        "suggested_questions": [item["question"] for item in extra["questions"]],
        "note": "Counts and patterns from your records. They point to where to look; people decide what they mean.",
        **extra,
    }
