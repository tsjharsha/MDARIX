"""Mask personal information before any text leaves for an AI model.

Investigations need product, lot, change, supplier and complaint identifiers, so those are kept. What identifies a
person is replaced with a typed placeholder (``[EMAIL]``, ``[PHONE]``, ``[PERSON]`` ...): email addresses, phone
numbers, national/insurance/card-style numbers, labelled IP addresses, values after labels such as "Patient:", "Reporter:",
"DOB:" or "Address:", names after a personal title (Mr, Mrs, Ms, Dr ...) or "reported by", and the values of
dictionary keys that hold personal data. Masking runs on every model request (``genai/provider.py``); it can be
switched off only for local work on synthetic data (``MDARIX_GENAI_PII_MASKING=false``), never in staging or
production.
"""

from __future__ import annotations

import os
import re

EMAIL = re.compile(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
# Grouped phone numbers: optional country code, then at least three groups (617 555 0100, (617) 555-0100, +44 20 7946
# 0958). Requiring separators keeps lot numbers, dates and serials such as L24-0815 or 2026-10-03 intact.
PHONE = re.compile(r"(?<![\w-])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,5}\)[\s.-]?|\d{2,5}[\s.-])\d{3,4}[\s.-]\d{3,5}(?![\w-])")
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
# IP addresses only when labelled: a bare dotted number is usually a firmware or software version (2.10.3.4).
IPV4 = re.compile(
    r"(?i)\b(ip(?:\s+address)?|client\s+ip|remote\s+addr(?:ess)?|source\s+ip)(\s*[:=]?\s*)"
    r"(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
)
# An address runs to the end of its clause, commas included ("Address: 1 High Street, Leeds LS1 4AP").
ADDRESS = re.compile(r"(?i)\b((?:home\s+|postal\s+|street\s+)?address)(\s*[:#=]\s*)([^\n;|]{1,160})")
# A labelled value: "Patient: Jane Doe", "Reporter name = J. Smith", "DOB: 1961-04-02", "Address: 1 High St". The label
# needs a ':', '#' or '=' so ordinary sentences ("the patient experienced", "mobile app", "address the issue") stay.
LABELLED = re.compile(
    r"(?i)\b(patient(?:\s+name)?|reporter(?:\s+name)?|caller|complainant|user\s+name|full\s+name|contact(?:\s+name)?|"
    r"date\s+of\s+birth|d\.?o\.?b\.?|mrn|medical\s+record(?:\s+number)?|nhs\s+number|ssn|social\s+security(?:\s+number)?|"
    r"home\s+address|address|phone|telephone|mobile|e-?mail)(\s*[:#=]\s*)([^\n;,|]{1,80})"
)
# Record numbers often follow their label with a space only: "MRN 004512", "NHS number 943 476 5919".
RECORD_NUMBER = re.compile(r"(?i)\b(mrn|nhs\s+number|medical\s+record\s+number|ssn)(\s+)(\d[\d -]{3,}\d)")
REPORTED_BY = re.compile(
    r"\b([Rr]eported by|[Cc]alled by|[Ss]ubmitted by)(\s+)[A-Z][a-zA-Z'-]+(?:\s+[A-Z][a-zA-Z'-]+)?"
)
TITLE = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof)\.?\s+[A-Z][a-zA-Z'-]+(?:\s+[A-Z][a-zA-Z'-]+)?")
# Dictionary keys whose values identify a person. Clinical keys such as patient_harm or patient_impact are kept.
PERSONAL_KEYS = re.compile(
    r"(?i)^(?:[a-z0-9]+_)*(e_?mail|phone|phone_number|mobile|telephone|patient_name|patient_id|patient_identifier|"
    r"reporter|reporter_name|complainant|complainant_name|caller_name|contact_name|dob|date_of_birth|birth_?date|"
    r"address|street|street_address|home_address|postcode|postal_code|zip|zip_code|ssn|mrn|national_id|"
    r"first_name|last_name|full_name|person_name)$"
)

_ID_LABELS = {"mrn", "medical record", "medical record number", "nhs number", "ssn", "social security"}
_ID_LABELS |= {"social security number"}


def enabled() -> bool:
    """Masking is on unless switched off for local work on synthetic data (staging and production ignore that)."""
    from backend.app.runtime_env import is_production_like

    if is_production_like():
        return True
    return os.getenv("MDARIX_GENAI_PII_MASKING", "true").strip().lower() not in {"0", "false", "no", "off"}


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
    label = re.sub(r"\s+", " ", label.lower()).replace(".", "")
    if label in {"date of birth", "dob"}:
        return "[DATE_OF_BIRTH]"
    if label in _ID_LABELS:
        return "[ID_NUMBER]"
    if label.endswith("address"):
        return "[ADDRESS]"
    if label in {"phone", "telephone", "mobile"}:
        return "[PHONE]"
    if label in {"email", "e-mail"}:
        return "[EMAIL]"
    return "[PERSON]"


def mask_text(text: str) -> str:
    """The text with personal information replaced by typed placeholders."""
    if not text:
        return text
    masked = EMAIL.sub("[EMAIL]", text)
    masked = ADDRESS.sub(lambda m: f"{m.group(1)}{m.group(2)}[ADDRESS]", masked)
    masked = LABELLED.sub(lambda m: f"{m.group(1)}{m.group(2)}{_placeholder(m.group(1))}", masked)
    masked = RECORD_NUMBER.sub(lambda m: f"{m.group(1)}{m.group(2)}[ID_NUMBER]", masked)
    masked = REPORTED_BY.sub(lambda m: f"{m.group(1)}{m.group(2)}[PERSON]", masked)
    masked = SSN.sub("[ID_NUMBER]", masked)
    masked = CARD.sub(_card, masked)
    masked = PHONE.sub("[PHONE]", masked)
    masked = IPV4.sub(lambda m: f"{m.group(1)}{m.group(2)}[IP_ADDRESS]", masked)
    return TITLE.sub("[PERSON]", masked)


def mask(value):
    """Mask strings anywhere in a JSON-like value; values under personal-data keys are replaced entirely."""
    if isinstance(value, dict):
        return {
            key: (
                "[PERSONAL_DATA]"
                if PERSONAL_KEYS.match(str(key).replace("-", "_")) and item not in (None, "")
                else mask(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [mask(item) for item in value]
    if isinstance(value, tuple):
        return tuple(mask(item) for item in value)
    if isinstance(value, str):
        return mask_text(value)
    return value
