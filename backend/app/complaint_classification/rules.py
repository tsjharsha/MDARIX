"""The fixed lists, the written coding criteria and the rules of complaint classification (T-G39), as plain functions.

Landed with migration tr01 ahead of its screens (0.10.52 ships the table and these rules dark; the disposition release
adds the screens, the sample's proposed values and the trend grouping). Every complaint carries two classifications,
each from a fixed list or Unknown; Unknown is never assumed to be a value, and "Other" needs a short text. A source
value outside the lists stays Unknown, with the source value kept beside it: nothing is inferred from free text. A
person confirms the classification; a classification never sets a deadline, a trigger, a market conclusion or the
reportability watch.
"""

from __future__ import annotations

from backend.app.db.models.market_assessment import USE_ENVIRONMENTS, USER_TYPES

CODING_CRITERIA_VERSION = "coding-starter-1"
OTHER, UNKNOWN = "OTHER", "UNKNOWN"
TEXT_MAX = 200

USE_ENVIRONMENT_LABELS = {
    "HOSPITAL_WARD": "Hospital ward",
    "INTENSIVE_CARE_UNIT": "Intensive care unit",
    "OPERATING_THEATRE": "Operating theatre",
    "HOME": "Home",
    "AMBULANCE": "Ambulance",
    "CLINIC": "Clinic",
    OTHER: "Other",
    UNKNOWN: "Unknown",
}
USER_TYPE_LABELS = {
    "HEALTHCARE_PROFESSIONAL": "Healthcare professional",
    "LAY_USER": "Lay user",
    "PATIENT": "Patient",
    "SERVICE_ENGINEER": "Service engineer",
    OTHER: "Other",
    UNKNOWN: "Unknown",
}
# The written coding criteria (starter text, T-B6), shown beside the fields; their version is kept on each record.
CODING_CRITERIA = (
    "Code where the device was in use when the event happened, not where the complaint was received.",
    "A step-down or high-dependency unit is coded hospital ward; an intensive care or critical care unit is coded "
    "intensive care unit.",
    "Transport between hospitals, or by ambulance or air ambulance, is coded ambulance.",
    "A nursing home or care home is coded home when the device is used as at home, and other (with the text) otherwise.",
    "The user is the person operating the device: a nurse, doctor or therapist is a healthcare professional; a carer "
    "or relative is a lay user; the patient operating their own device is the patient.",
    "Code Unknown when the record does not say; never guess from free text.",
)


def _lookup(labels: dict[str, str]) -> dict[str, str]:
    return {" ".join(label.lower().split()): code for code, label in labels.items() if code not in (OTHER, UNKNOWN)}


_ENVIRONMENTS = _lookup(USE_ENVIRONMENT_LABELS)
_USER_TYPES = _lookup(USER_TYPE_LABELS)


def code_source_value(kind: str, value: object) -> tuple[str, str | None]:
    """``(code, source value)`` for a value from the sample data or an import: an exact list label gives its code; any
    other value stays Unknown, with the value kept as given."""
    text = " ".join(str(value or "").split())
    table = _ENVIRONMENTS if kind == "use_environment" else _USER_TYPES
    code = table.get(text.lower())
    return (code, text or None) if code else (UNKNOWN, text or None)


def classification_problem(
    use_environment: str, use_environment_text: str | None, user_type: str, user_type_text: str | None
) -> str | None:
    """Why a classification cannot be kept, or None."""
    if use_environment not in USE_ENVIRONMENTS:
        return "Choose a use environment from the list, or Unknown"
    if user_type not in USER_TYPES:
        return "Choose a user type from the list, or Unknown"
    for code, text, what in (
        (use_environment, use_environment_text, "use environment"),
        (user_type, user_type_text, "user type"),
    ):
        if code == OTHER and not " ".join(str(text or "").split()):
            return f'Say in a few words what the "other" {what} is'
        if text and len(text) > TEXT_MAX:
            return f"Keep the {what} text under {TEXT_MAX} characters"
    return None
