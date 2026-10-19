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

Files arrive as bytes (a raw ``text/csv`` body or a multipart upload, ``read_upload``) and are decoded strictly as
UTF-8, with or without a byte-order mark: a file in another encoding is refused with instructions rather than read
with replaced characters. The delimiter is detected from the header line (comma, semicolon or tab, as spreadsheets
in different countries save them). Dates are YYYY-MM-DD; DD/MM/YYYY or MM/DD/YYYY is read only when the uploader
says which one (``date_format`` DMY or MDY), because 03/04/2026 is a different day in each and is never guessed.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from fastapi import HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import Complaint, LotBatch, ManufacturingSite, Product, ProductVersion
from backend.app.trial import business_imports, insight_questions
from backend.app.trial.columns import examples as column_examples
from backend.app.trial.columns import match as columns_match
from backend.app.trial.sample_data import SAMPLE_SOURCE
from backend.app.trial.service import TRIAL_FILE_LIMIT_BYTES, TRIAL_ROW_LIMIT

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


TRIAL_POLICY = ImportPolicy(
    source=UPLOAD_SOURCE,
    row_limit=TRIAL_ROW_LIMIT,
    file_limit_bytes=TRIAL_FILE_LIMIT_BYTES,
    file_too_large="Files can be up to 2 MB during the free trial",
    limit_label="your trial",
    xlsx_max_bytes=20 * 1024 * 1024,
    create_references=True,
)
WORKSPACE_POLICY = ImportPolicy(source=WORKSPACE_UPLOAD_SOURCE)
# A complaint's status as its quality system names it (complaints.status holds 40 characters).
COMPLAINT_STATUS_MAX = 40

# What a column is for, in plain words, for the columns whose meaning changes what MDARIX finds (shown beside each
# template in the import panel; templates_for() keeps only the template's own columns).
COLUMN_HELP: dict[str, dict[str, str]] = {
    "products": {
        "version_release_date": "The day the version was released (YYYY-MM-DD). A version younger than 90 days is "
        "compared with the version it replaced, from this day.",
    },
    "lots": {
        "version": "The product version the lot builds. Its complaints are counted against this version's lots.",
        "manufacture_date": "The day the lot was released to the field (YYYY-MM-DD). Its units count from this day.",
        "quantity": "How many devices the lot released, a whole number (1,250 is fine). With a quantity on every lot "
        "of a version, the trend check counts complaints per unit in the field instead of per calendar day, so a "
        "version shipped in growing numbers is not mistaken for a rising trend.",
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
    },
}


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
        "optional": ["version", "product_family", "version_release_date"],
        "example": [
            ["PUMP-200", "AquaFlow 200 Infusion Pump", "Rev C", "Infusion therapy", "2026-03-15"],
            ["PUMP-200", "AquaFlow 200 Infusion Pump", "Rev D", "Infusion therapy", "2026-07-01"],
        ],
    },
    "lots": {
        "title": "Lots and batches",
        "required": ["lot_id", "product_id", "version"],
        # quantity: devices the lot released; the trend check then counts complaints per unit in the field.
        "optional": ["manufacture_date", "site_id", "quantity"],
        "example": [
            ["L24-0815", "PUMP-200", "Rev D", "2026-07-20", "", "250"],
            ["L24-0902", "PUMP-200", "Rev D", "2026-08-11", "", "300"],
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
            ]
        ],
    },
    **business_imports.TEMPLATES,
}
# Yes/no columns, and columns that hold longer text than the 255-character default.
FLAG_COLUMNS = {"device_returned", "patient_involved", "serious_injury", "death", "malfunction"}
FLAG_VALUES = {"y": True, "yes": True, "true": True, "1": True, "n": False, "no": False, "false": False, "0": False}
LONG_TEXT = {"description": 4000, "text": 4000, "question": 4000, "content": 20000}

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/#:-]{0,119}$")
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
    (re.compile(r"\b(mr|mrs|ms|miss|dr)\.?\s+[A-Z][a-z]+"), "a person's name", False),
]
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


def _spreadsheet_formula(value: str) -> bool:
    """Text a spreadsheet would run as a formula when the data is exported and opened (CSV injection)."""
    first = value[:1]
    return first in {"=", "+", "@", "\t", "\r"} or (first == "-" and "(" in value[:40])


def _personal_data(value: str, labels: bool = True) -> str | None:
    """What personal data the text seems to hold. ``labels=False`` (after masking) ignores a label such as "MRN" or
    "date of birth" left in front of a placeholder; the values themselves are still looked for."""
    if not labels:
        value = _MASK_PLACEHOLDER.sub(" ", value)
    for pattern, label, label_only in _PERSONAL_DATA:
        if label_only and not labels:
            continue
        if pattern.search(value):
            return label
    return None


def _mask(value: str) -> str:
    """Personal data replaced by typed placeholders, the masking every AI request gets (genai/pii.py)."""
    from genai.pii import mask_text

    return mask_text(value)


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


# Whole-number columns (a lot's quantity): digits only, separators allowed ("1,250", "1 250").
COUNT_COLUMNS = frozenset({"quantity"})
COUNT_MAX = 10_000_000


def _count(value: str) -> int | None:
    """A whole number from 0 to COUNT_MAX, else None."""
    text = str(value or "").strip().replace(",", "").replace(" ", "").replace("_", "")
    if not text.isdigit():
        return None
    number = int(text)
    return number if number <= COUNT_MAX else None


def _date(value: str) -> datetime | None:
    return datetime.combine(date.fromisoformat(value), time(12, 0), tzinfo=timezone.utc)


DATE_FORMATS = {"ISO": "YYYY-MM-DD", "DMY": "DD/MM/YYYY", "MDY": "MM/DD/YYYY"}
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DAY_MONTH_YEAR = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$")
_DELIMITERS = ",;\t"
# A multipart upload carries a little framing around the file; allowed on top of the file limit.
MULTIPART_OVERHEAD_BYTES = 64 * 1024


def date_format_or_422(value: str | None) -> str:
    """The ``date_format`` query parameter: ISO (default), DMY or MDY; anything else is refused, never guessed."""
    chosen = (value or "ISO").strip().upper()
    if chosen not in DATE_FORMATS:
        raise HTTPException(
            422,
            detail={
                "code": "DATE_FORMAT_INVALID",
                "message": "date_format must be ISO (YYYY-MM-DD), DMY (DD/MM/YYYY) or MDY (MM/DD/YYYY)",
            },
        )
    return chosen


def iso_date(value: str, date_format: str = "ISO") -> str | None:
    """``value`` as YYYY-MM-DD, or None when it is not a real date in ``date_format``.

    YYYY-MM-DD is accepted in every format (it cannot be misread); day and month in another order only when the
    uploader declared that order.
    """
    value = value.strip()
    try:
        if _ISO_DATE.match(value):
            return date.fromisoformat(value).isoformat()
        match = _DAY_MONTH_YEAR.match(value)
        if match and date_format in ("DMY", "MDY"):
            first, second, year = (int(part) for part in match.groups())
            day, month = (first, second) if date_format == "DMY" else (second, first)
            return date(year, month, day).isoformat()
    except ValueError:
        return None
    return None


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


def _table(raw: bytes, report: "_Report", policy: ImportPolicy = TRIAL_POLICY) -> list[list[str]] | None:
    """The upload as rows of cells: an Excel workbook's first sheet (backend/app/trial/xlsx.py), else delimited text
    (comma, semicolon or tab). None when it cannot be read (the reason is in the report). A workbook is read no
    further than the rows the policy takes (plus a margin), within the policy's unpacked size."""
    from backend.app.trial import xlsx

    if xlsx.is_xlsx(raw):
        try:
            rows = xlsx.read_rows(
                raw,
                max_rows=min(policy.row_limit or MAX_ROWS_PER_FILE, MAX_ROWS_PER_FILE),
                max_bytes=policy.xlsx_max_bytes,
            )
        except xlsx.XlsxError as exc:
            report.add(None, None, str(exc))
            return None
        report.notes.append("Read the first sheet of the Excel workbook.")
        return rows
    text = _decode(raw, report)
    if text is None:
        return None
    return list(csv.reader(io.StringIO(text, newline=""), delimiter=_delimiter(text)))


def _delimiter(text: str) -> str:
    """Comma, semicolon or tab, whichever the header line uses (comma when it cannot tell, e.g. one column)."""
    header = text.split("\n", 1)[0]
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
        # under another name, the columns left out, and the products, versions and lots a complaints file adds.
        self.notes: list[str] = []
        self.mapping: list[dict] = []
        self.ignored: list[str] = []
        self.creates: dict[str, int] = {}

    def add(self, row: int | None, column: str | None, message: str) -> None:
        self.error_count += 1
        if len(self.issues) < MAX_ISSUES:
            self.issues.append({"row": row, "column": column, "message": message})
        if row is None or row == 1:  # line 1 is the header
            self.file_problems += 1
        else:
            self.row_problems.setdefault(row, []).append(f"{column}: {message}" if column else message)


def _parse(
    entity: str, raw: bytes, report: _Report, policy: ImportPolicy = TRIAL_POLICY, date_format: str = "ISO"
) -> list[tuple[int, dict]]:
    if entity not in TEMPLATES:
        raise HTTPException(404, detail={"code": "TEMPLATE_NOT_FOUND", "message": "Unknown template"})
    if len(raw) > policy.file_limit_bytes:
        raise HTTPException(413, detail={"code": "FILE_TOO_LARGE", "message": policy.file_too_large})
    table = _table(raw, report, policy)
    if table is None:
        return []
    reader = iter(table)
    header = next(reader, None)
    if not header or not any(cell.strip() for cell in header):
        report.add(None, None, "The file is empty.")
        return []
    spec = TEMPLATES[entity]
    allowed = spec["required"] + spec["optional"]
    # The export's headers matched to the template (backend/app/trial/columns.py): a header under another name is
    # read as its column, one the template does not know is left out (never stored) and listed back.
    matched = columns_match(entity, [cell.strip() for cell in header], allowed)
    fields = matched["fields"]
    report.mapping = matched["mapping"]
    report.ignored = matched["ignored"] + [item["header"] for item in matched["duplicates"]]
    for column in spec["required"]:
        if column not in fields:
            names = column_examples(entity, column)
            hint = f" (for example {' or '.join(repr(name) for name in names)})" if names else ""
            report.add(1, column, f"Required column '{column}'{hint} is missing.")
    if report.error_count:
        return []
    rows = []
    for line_number, cells in enumerate(reader, 2):
        if not any(cell.strip() for cell in cells):
            continue
        if any(cell.strip() for cell in cells[len(fields) :]):
            report.add(line_number, None, "This row has more values than the header has columns.")
            continue
        row = {
            column: (cells[i].strip() if i < len(cells) else "")
            for i, column in enumerate(fields)
            if column is not None
        }
        for column, value in row.items():
            # Dates in the declared order become YYYY-MM-DD here; a value that is not one is left as typed and
            # reported by _check_values with the expected format.
            if column.endswith("_date") and value:
                row[column] = iso_date(value, date_format) or value
        rows.append((line_number, row))
    if not rows:
        report.add(None, None, "The file has a header but no data rows.")
    return rows


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
    identity_columns = spec.get("identity")
    seen: dict[tuple, int] = {}
    for line, row in rows:
        for column in spec["required"]:
            if not row.get(column):
                report.add(line, column, f"'{column}' is required.")
        for column, value in row.items():
            if not value:
                continue
            if column.endswith("_id") or column == "version":
                if not _ID.match(value):
                    report.add(line, column, "Use up to 120 letters, numbers, spaces or . _ / # : - characters.")
            elif column.endswith("_ids"):
                if any(not _ID.match(part) for part in business_imports.split_ids(value)):
                    report.add(line, column, "List identifiers separated by ; (letters, numbers, . _ / # : -).")
            elif column in FLAG_COLUMNS:
                if value.lower() not in FLAG_VALUES:
                    report.add(line, column, "Use Y or N.")
            elif column in COUNT_COLUMNS:
                if _count(value) is None:
                    report.add(line, column, f"Use a whole number from 0 to {COUNT_MAX:,}.")
            elif column.endswith("_date"):
                if iso_date(value) is None:
                    expected = "YYYY-MM-DD" + (f" or {DATE_FORMATS[date_format]}" if date_format != "ISO" else "")
                    report.add(line, column, f"'{value}' is not a date in {expected} format.")
            else:
                # The same detection both ways: refusing flags whatever masking would replace.
                masked = _mask(value)
                if mask_personal_data:
                    if masked != value:
                        report.masked_values += 1
                        report.originals[(line, column)] = value
                        row[column] = value = masked
                    found = _personal_data(value, labels=False)
                else:
                    found = _masking_found(value, masked) or _personal_data(value)
                limit = LONG_TEXT.get(column, 255)
                if len(value) > limit:
                    report.add(line, column, f"Keep this under {limit} characters.")
                if found:
                    advice = (
                        "Masking could not remove it; remove it from the file."
                        if mask_personal_data
                        else "Remove personal data and retry, or choose to mask it."
                    )
                    report.add(line, column, f"This looks like it contains {found}. {advice}")
                if _spreadsheet_formula(value):
                    report.add(line, column, "Text cannot start with =, +, @ or a formula; spreadsheets would run it.")
        # The quality system's own status is kept (Cancelled, Void, Closed - no action, Inquiry...): the second look
        # reads those words to find complaints that were closed off (backend/app/complaint_review/rules.py).
        if entity == "complaints" and len(row.get("status") or "") > COMPLAINT_STATUS_MAX:
            report.add(line, "status", f"Keep the status under {COMPLAINT_STATUS_MAX} characters.")
        if identity_columns:
            identity = tuple(row.get(column) for column in identity_columns)
        else:
            identity = (row.get(key), row.get("version")) if entity == "products" else (row.get(key),)
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
    """Validate references and count the rows that would be new records. With ``create`` (a free trial) a complaints
    file may name products, versions and lots not loaded yet: they are counted as records it adds
    (``report.creates``) instead of refused."""
    if entity in business_imports.TEMPLATES:
        return business_imports.check(entity, rows, lookup, report)
    if create and entity == "complaints":
        return _check_complaints_creating(rows, lookup, report)
    new = 0
    new_products: set[str] = set()
    for line, row in rows:
        if entity == "products":
            product = lookup.product(row["product_id"])
            if product is None and row["product_id"] not in new_products:
                new_products.add(row["product_id"])
                new += 1
            if row.get("version") and (product is None or lookup.version(product, row["version"]) is None):
                new += 1
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
                new += 1
            elif version is not None and existing.product_version_id not in (None, version.id):
                report.add(line, "lot_id", f"Lot '{row['lot_id']}' already belongs to another version.")
            continue
        if row.get("lot_id"):
            lot = lookup.lot(row["lot_id"])
            if lot is None:
                report.add(line, "lot_id", f"Lot '{row['lot_id']}' is not loaded yet.")
            else:
                lot_version = (
                    lookup.db.query(ProductVersion).filter(ProductVersion.id == lot.product_version_id).first()
                )
                if lot_version is not None and lot_version.product_id != product.id:
                    report.add(line, "lot_id", f"Lot '{row['lot_id']}' belongs to a different product.")
        exists = (
            lookup.db.query(Complaint.id)
            .filter(Complaint.tenant_id == lookup.tenant_id, Complaint.complaint_identifier == row["complaint_id"])
            .first()
        )
        if exists is None:
            new += 1
    return new


def _check_complaints_creating(rows, lookup: _Lookup, report: _Report) -> int:
    """A complaints file that also adds the products, versions and lots it names (``_check_references`` with create):
    each is counted once; a lot the workspace already holds must still belong to the complaint's product."""
    new = 0
    products: set[str] = set()
    versions: set[tuple[str, str]] = set()
    lots: dict[str, str] = {}
    for line, row in rows:
        product_id = row["product_id"]
        product = lookup.product(product_id)
        if product is None and product_id not in products:
            products.add(product_id)
        version_id = row.get("version")
        if version_id and (product is None or lookup.version(product, version_id) is None):
            versions.add((product_id, version_id))
        lot_id = row.get("lot_id")
        if lot_id:
            lot = lookup.lot(lot_id)
            if lot is None:
                if lots.setdefault(lot_id, product_id) != product_id:
                    report.add(line, "lot_id", f"Lot '{lot_id}' is named for two products in this file.")
            else:
                # A lot tied to a version belongs to that version's product; a lot without a version belongs to none.
                lot_version = (
                    lookup.db.query(ProductVersion).filter(ProductVersion.id == lot.product_version_id).first()
                    if lot.product_version_id
                    else None
                )
                if lot_version is not None and (product is None or lot_version.product_id != product.id):
                    report.add(line, "lot_id", f"Lot '{lot_id}' belongs to a different product.")
        exists = (
            lookup.db.query(Complaint.id)
            .filter(Complaint.tenant_id == lookup.tenant_id, Complaint.complaint_identifier == row["complaint_id"])
            .first()
        )
        if exists is None:
            new += 1
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


def upload_counters(source: str = UPLOAD_SOURCE) -> list[tuple]:
    """``(model, conditions)`` for every kind of record an upload loads: what ``uploaded_rows`` counts, per tenant here
    and for many tenants at once in the Platform Admin trial overview (backend/app/trial/story.py)."""
    from retrieval.record_evidence import RECORD_EVIDENCE_TYPE

    counters = []
    for model in (Product, ProductVersion, LotBatch, Complaint, *business_imports.MODELS):
        conditions = [model.source_system == source]
        if model is business_imports.Evidence:
            # The searchable copy of each imported record is not a row the customer loaded.
            conditions.append(model.evidence_type != RECORD_EVIDENCE_TYPE)
        counters.append((model, tuple(conditions)))
    return counters


def uploaded_rows(db: Session, tenant_id, source: str = UPLOAD_SOURCE) -> int:
    total = 0
    for model, conditions in upload_counters(source):
        total += db.query(func.count(model.id)).filter(model.tenant_id == tenant_id, *conditions).scalar() or 0
    return int(total)


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
) -> dict:
    return _checked_file(db, tenant_id, entity, raw, policy, date_format, skip_problem_rows, mask_personal_data)[0]


def _checked_file(
    db: Session,
    tenant_id,
    entity: str,
    raw: bytes,
    policy: ImportPolicy,
    date_format: str,
    skip_problem_rows: bool,
    mask_personal_data: bool,
) -> tuple[dict, list]:
    """The check report and the rows that would be imported (masked when asked; without the set-aside rows)."""
    report = _Report()
    rows = _parse(entity, raw, report, policy, date_format)
    return _check_rows(db, tenant_id, entity, rows, report, policy, date_format, skip_problem_rows, mask_personal_data)


def check_records(db: Session, tenant_id, entity: str, records: list[dict], policy: ImportPolicy) -> dict:
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
    oversized = len(rows) > MAX_ROWS_PER_FILE
    if oversized:
        report.add(
            None,
            None,
            f"This file has {len(rows):,} rows; one file can have up to {MAX_ROWS_PER_FILE:,}. Split it into smaller files.",
        )
    if rows and not oversized:
        _check_values(entity, rows, report, date_format, mask_personal_data)
        create = policy.create_references
        if skip_problem_rows:
            if not report.file_problems:
                kept = [(line, row) for line, row in rows if line not in report.row_problems]
                if kept:
                    new_rows = _check_references(entity, kept, _Lookup(db, tenant_id), report, create)
                    if any(line in report.row_problems for line, _ in kept):
                        # A row whose references do not resolve is set aside too; the rest are counted again.
                        kept = [(line, row) for line, row in kept if line not in report.row_problems]
                        recount = _Report()
                        new_rows = (
                            _check_references(entity, kept, _Lookup(db, tenant_id), recount, create) if kept else 0
                        )
                        report.creates = recount.creates
        elif not report.error_count:
            new_rows = _check_references(entity, rows, _Lookup(db, tenant_id), report, create)
    used = uploaded_rows(db, tenant_id, policy.source)
    if policy.row_limit is not None and new_rows and used + new_rows > policy.row_limit:
        report.add(
            None,
            None,
            f"This file adds {new_rows} records; {policy.limit_label} has {max(policy.row_limit - used, 0)} of "
            f"{policy.row_limit} left.",
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
        # Rows that update a record already there (the products, versions and lots a file adds are not rows).
        "updated_records": max(len(kept) - (new_rows - sum(report.creates.values())), 0)
        if entity != "products"
        else None,
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
        "notes": report.notes,
        "also_creates": report.creates,
    }
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


def import_file(
    db: Session,
    tenant_id,
    entity: str,
    raw: bytes,
    policy: ImportPolicy = TRIAL_POLICY,
    date_format: str = "ISO",
    skip_problem_rows: bool = False,
    mask_personal_data: bool = False,
) -> dict:
    report, rows = _checked_file(db, tenant_id, entity, raw, policy, date_format, skip_problem_rows, mask_personal_data)
    if not report["ready"]:
        raise HTTPException(
            422, detail={"code": "IMPORT_CHECK_FAILED", "message": "Fix the listed problems first", "report": report}
        )
    # The checked rows themselves: masked where asked, without the rows set aside.
    result = _write_rows(db, tenant_id, entity, rows, policy)
    result.update(
        rejected_rows=report["rejected_rows"],
        masked_values=report["masked_values"],
        skip_problem_rows=skip_problem_rows,
        mask_personal_data=mask_personal_data,
    )
    if report.get("rejects_csv"):
        result["rejects_csv"] = report["rejects_csv"]
    return result


def import_records(db: Session, tenant_id, entity: str, records: list[dict], policy: ImportPolicy) -> dict:
    report = check_records(db, tenant_id, entity, records, policy)
    if not report["ready"]:
        raise HTTPException(
            422, detail={"code": "IMPORT_CHECK_FAILED", "message": "Fix the listed problems first", "report": report}
        )
    return _write_rows(db, tenant_id, entity, rows_from_records(entity, records, _Report()), policy)


def _write_rows(db: Session, tenant_id, entity: str, rows, policy: ImportPolicy) -> dict:
    source = policy.source
    lookup = _Lookup(db, tenant_id)
    now = datetime.now(timezone.utc)
    created = updated = 0
    also_created: dict[str, int] = {}
    if entity in business_imports.TEMPLATES:
        created, updated = business_imports.write(
            entity, rows, db, tenant_id, lookup, lambda when: _stamp(now, when, source), _date, now, source
        )
        return {"entity": entity, "created": created, "updated": updated, "rows": len(rows)}
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
                    source_identifier=row["lot_id"],
                    **_stamp(now, built, source),
                )
                db.add(lot)
                lookup.lots[row["lot_id"]] = lot
                created += 1
            else:
                lot.product_version_id = version.id if version else lot.product_version_id
                lot.manufacturing_site_id = site.id if site else lot.manufacturing_site_id
                if built:
                    lot.effective_timestamp = built
                if quantity is not None:
                    lot.quantity = quantity
                lot.updated_at = now
                updated += 1
            db.flush()
            continue
        lot = lookup.lot(row["lot_id"]) if row.get("lot_id") else None
        event = _date(row["event_date"]) if row.get("event_date") else None
        received = _date(row["received_date"]) if row.get("received_date") else None
        complaint = (
            db.query(Complaint)
            .filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == row["complaint_id"])
            .first()
        )
        values = {
            "product_id": product.id,
            "product_version_id": version.id if version else (lot.product_version_id if lot else None),
            "lot_batch_id": lot.id if lot else None,
            "event_timestamp": event,
            "complaint_timestamp": received or event,
            "description": row["description"],
            "status": (row.get("status") or "open").lower(),
            **_complaint_details(row),
        }
        if complaint is None:
            complaint = Complaint(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                complaint_identifier=row["complaint_id"],
                source_identifier=row["complaint_id"],
                **values,
                **_stamp(now, received or event, source),
            )
            db.add(complaint)
            created += 1
        else:
            for name, value in values.items():
                setattr(complaint, name, value)
            complaint.updated_at = now
            updated += 1
        db.flush()
        _index_complaint(db, tenant_id, complaint, row, product, version, lot, source)
    result = {"entity": entity, "created": created, "updated": updated, "rows": len(rows)}
    if also_created:
        result["also_created"] = also_created
    return result


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


def _index_complaint(db: Session, tenant_id, complaint: Complaint, row: dict, product, version, lot, source: str):
    """Make the complaint searchable by Ask MDARIX and the investigator (retrieval/record_evidence.py)."""
    from retrieval.record_evidence import summary, upsert_record_evidence

    facts = {
        "Product": row["product_id"],
        "Version": row.get("version"),
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
    upsert_record_evidence(
        db,
        tenant_id,
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


def insights(db: Session, tenant_id) -> dict:
    """Counts and concentrations computed from the workspace's complaints; facts for a person to interpret."""
    own = (
        db.query(Complaint.id)
        .filter(Complaint.tenant_id == tenant_id, Complaint.source_system == UPLOAD_SOURCE)
        .first()
        is not None
    )
    scope = UPLOAD_SOURCE if own else SAMPLE_SOURCE
    base = db.query(Complaint).filter(Complaint.tenant_id == tenant_id, Complaint.source_system == scope)
    complaints = base.all()
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
        (
            {"month": month, "complaints": n}
            for month, n in tally(
                lambda c: (
                    (c.complaint_timestamp or c.event_timestamp or c.created_at).strftime("%Y-%m")
                    if (c.complaint_timestamp or c.event_timestamp or c.created_at)
                    else None
                )
            )
        ),
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
                f"{share}% of complaints ({top['complaints']} of {total}) concern "
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
