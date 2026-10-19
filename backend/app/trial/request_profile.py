"""What a trial requester tells MDARIX about their company and their trial (``OnboardingRequest.profile``).

Asked on the public sign-up page so a Platform Administrator can review the request and prepare the trial. It holds no
password: the requester creates one from the invitation email after approval, and MDARIX staff never see it. The
personal parts (job title, phone, the free-text goal) are erased with the rest of the request's personal data when the
trial is purged (``tenant_purge._pseudonymize_people``).

Required: job title, country, and the confirmation that no patient-identifiable data will be uploaded (the Free Trial
Agreement asks for synthetic or non-identifying data). Everything else is optional and chosen from fixed lists, so the
review screen and reports read the same codes.
"""

from __future__ import annotations

import re

COMPANY_SIZES = {
    "1-50": "1-50 employees",
    "51-200": "51-200 employees",
    "201-1000": "201-1,000 employees",
    "1001-5000": "1,001-5,000 employees",
    "5000+": "More than 5,000 employees",
}
DEVICE_CLASSES = {
    "CLASS_I": "Class I",
    "CLASS_II": "Class II",
    "CLASS_III": "Class III",
    "IVD": "In vitro diagnostic (IVD)",
    "NOT_SURE": "Not sure",
}
MARKETS = {
    "US": "United States (FDA)",
    "EU": "European Union (MDR/IVDR)",
    "UK": "United Kingdom",
    "CA": "Canada",
    "IN": "India",
    "OTHER": "Other",
}
COMPLAINT_SYSTEMS = {
    "TRACKWISE": "TrackWise",
    "VEEVA_QMS": "Veeva QMS",
    "MASTERCONTROL": "MasterControl",
    "GREENLIGHT_GURU": "Greenlight Guru",
    "ETQ": "ETQ Reliance",
    "SAP": "SAP",
    "SALESFORCE": "Salesforce",
    "SPREADSHEETS": "Spreadsheets or email",
    "OTHER": "Other",
}
COMPLAINT_VOLUMES = {
    "LT_50": "Fewer than 50 a month",
    "50_500": "50-500 a month",
    "501_5000": "501-5,000 a month",
    "GT_5000": "More than 5,000 a month",
    "NOT_SURE": "Not sure",
}
TRIAL_DATA = {
    "SAMPLE_ONLY": "Sample data only",
    "ANONYMIZED_EXPORTS": "Our anonymized exports",
}

# Countries and regions under comprehensive sanctions, where MDARIX does not offer trials: Cuba, Iran, North Korea,
# Syria, and the Crimea, so-called Donetsk People's Republic and Luhansk People's Republic regions of Ukraine. The
# sign-up list leaves them out (frontend/src/features/auth/trialProfile.ts SANCTIONED_REGIONS); this refuses them when
# typed or sent another way. Names are compared lower-cased, with punctuation and "the" / "republic of" ignored. Which
# places belong here is a legal decision (docs/compliance/LEGAL_DRAFTS_FOR_REVIEW.md).
SANCTIONED_COUNTRY_CODES = frozenset({"CU", "IR", "KP", "SY"})
_SANCTIONED_NAMES = frozenset(
    {
        "cuba",
        "iran",
        "islamic iran",
        "iran islamic",
        "persia",
        "north korea",
        "korea north",
        "korea democratic peoples",
        "democratic peoples korea",
        "dprk",
        "syria",
        "syrian arab",
        "crimea",
        "sevastopol",
        "donetsk peoples",
        "dpr",
        "dnr",
        "luhansk peoples",
        "lugansk peoples",
        "lpr",
        "lnr",
    }
)
_SANCTIONED_MARKERS = ("crimea", "sevastopol", "donetsk", "luhansk", "lugansk")
COUNTRY_NOT_SERVED = (
    "MDARIX cannot offer a free trial to organizations in this country or region. If you think this is a mistake, "
    "write to support@mdarix.in."
)


def _country_key(value: str) -> str:
    words = re.sub(r"[^a-z ]", " ", value.lower().replace("'", "").replace("\u2019", "")).split()
    return " ".join(word for word in words if word not in {"the", "of", "republic", "so", "called"})


def is_sanctioned_region(country: str | None) -> bool:
    """Whether a sign-up's country names a place under comprehensive sanctions (see ``SANCTIONED_COUNTRY_CODES``)."""
    text = (country or "").strip()
    if not text:
        return False
    if text.upper() in SANCTIONED_COUNTRY_CODES:
        return True
    key = _country_key(text)
    return key in _SANCTIONED_NAMES or any(marker in key.split() for marker in _SANCTIONED_MARKERS)


# A phone number in international format: +, the country code and the number (E.164: at most 15 digits), with the
# spaces, dashes, dots or brackets people type.
_PHONE_CHARS = re.compile(r"^\+[1-9][0-9 ().-]*$")
PHONE_FORMAT = "+ country code and number, for example +91 98765 43210"


class ProfileError(ValueError):
    """A sign-up answer that cannot be stored; ``code`` and ``message`` go to the visitor (HTTP 422)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _text(value: str | None) -> str:
    return " ".join((value or "").split())


def _choice(value: str | None, options: dict[str, str], code: str, what: str) -> str | None:
    if value in (None, ""):
        return None
    if value not in options:
        raise ProfileError(code, f"Choose a {what} from the list")
    return value


def build_profile(data) -> dict:
    """The stored profile for a sign-up (``data`` is the ``Signup`` body); raises ``ProfileError`` when an answer is
    missing or not one of the offered choices. Empty optional answers are left out."""
    job_title = _text(data.job_title)
    if not job_title:
        raise ProfileError("JOB_TITLE_REQUIRED", "Enter your job title")
    country = _text(data.country)
    if not country:
        raise ProfileError("COUNTRY_REQUIRED", "Enter your country")
    if is_sanctioned_region(country):
        raise ProfileError("COUNTRY_NOT_SERVED", COUNTRY_NOT_SERVED)
    if data.no_patient_data is not True:
        raise ProfileError(
            "NO_PATIENT_DATA_CONFIRMATION_REQUIRED",
            "Confirm that you will not upload patient-identifiable data during the trial",
        )
    phone = _text(data.phone)
    if phone and (not _PHONE_CHARS.match(phone) or not 8 <= sum(ch.isdigit() for ch in phone) <= 15):
        raise ProfileError(
            "VALID_PHONE_REQUIRED",
            f"Enter the phone number in international format ({PHONE_FORMAT}), or leave it empty",
        )
    markets = []
    for market in data.markets or []:
        if market not in MARKETS:
            raise ProfileError("INVALID_MARKET", "Choose your markets from the list")
        if market not in markets:
            markets.append(market)
    profile = {
        "job_title": job_title,
        "country": country,
        "phone": phone or None,
        "company_size": _choice(data.company_size, COMPANY_SIZES, "INVALID_COMPANY_SIZE", "company size"),
        "device_types": _text(data.device_types) or None,
        "device_class": _choice(data.device_class, DEVICE_CLASSES, "INVALID_DEVICE_CLASS", "device class"),
        "markets": markets or None,
        "complaint_system": _choice(
            data.complaint_system, COMPLAINT_SYSTEMS, "INVALID_COMPLAINT_SYSTEM", "complaint system"
        ),
        "complaint_volume": _choice(
            data.complaint_volume, COMPLAINT_VOLUMES, "INVALID_COMPLAINT_VOLUME", "complaint volume"
        ),
        "trial_data": _choice(data.trial_data, TRIAL_DATA, "INVALID_TRIAL_DATA", "trial data choice"),
        "evaluation_goal": (data.evaluation_goal or "").strip() or None,
        "no_patient_data_confirmed": True,
    }
    return {key: value for key, value in profile.items() if value is not None}


PERSONAL_FIELDS = ("job_title", "phone", "evaluation_goal")


def erase_personal(profile: dict | None) -> dict:
    """What is kept of a profile after the trial's purge: the company facts only. The person's job title and phone go,
    and so does the free-text goal, which may name people."""
    return {key: value for key, value in (profile or {}).items() if key not in PERSONAL_FIELDS}


def describe(profile: dict | None) -> list[tuple[str, str]]:
    """The profile as (label, words) pairs for people: the review email and screen read the same lines."""
    profile = profile or {}
    lines = [
        ("Job title", profile.get("job_title")),
        ("Country", profile.get("country")),
        ("Phone", profile.get("phone")),
        ("Company size", COMPANY_SIZES.get(profile.get("company_size") or "")),
        ("Devices", profile.get("device_types")),
        ("Highest device class", DEVICE_CLASSES.get(profile.get("device_class") or "")),
        ("Markets", ", ".join(MARKETS[m] for m in profile.get("markets") or [] if m in MARKETS) or None),
        ("Complaint system", COMPLAINT_SYSTEMS.get(profile.get("complaint_system") or "")),
        ("Complaint volume", COMPLAINT_VOLUMES.get(profile.get("complaint_volume") or "")),
        ("Trial data", TRIAL_DATA.get(profile.get("trial_data") or "")),
        ("Wants to evaluate", profile.get("evaluation_goal")),
        ("No patient data", "Confirmed" if profile.get("no_patient_data_confirmed") else None),
    ]
    return [(label, words) for label, words in lines if words]
