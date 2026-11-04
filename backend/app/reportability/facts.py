"""The facts a reporting step needs and a complaint does not give (0.10.81, the functional review's F3 and F4; the
usability review's U-01): MDARIX never guesses a mandatory fact. It asks for it at the step that needs it, and that
step is not signed until it is entered.

- **The incident country** of a complaint on the reportability watch (harm, a malfunction, or a patient's outcome
  unknown): blank, or not a country (ISO 3166-1,
  backend/app/countries.py, by code or name). It decides which authorities' rules and deadlines apply. A known country
  outside the five markets needs nothing (no market's rule applies).
- **The awareness date**: neither an awareness nor a received date. Every deadline counts from it. Until it is entered
  the clocks are provisional, counted from the earliest date the record has (the event date, else when it was
  recorded), and a market conclusion cannot be signed.

Starter rules, for the consultant to confirm.
"""

from __future__ import annotations

from backend.app.countries import code_of
from backend.app.reportability import markets, rules

COUNTRY, AWARENESS = "COUNTRY", "AWARENESS_DATE"
COUNTRY_RULE = "21 CFR 803; EU MDR Art. 87; UK MDR 2002; SOR/98-282 s. 59; India MDR 2017 Rule 26"
AWARENESS_RULE = "21 CFR 803.50(a); EU MDR Art. 87(3)-(5); UK MDR 2002; SOR/98-282 s. 60(1); India MDR 2017 Rule 26"


def country_known(value: object) -> bool:
    """Whether a country field names a country: a reportability market's name, or an ISO 3166-1 code or name (each
    part of a cell naming several)."""
    if markets.markets_of(value) or code_of(value):
        return True
    parts = rules.countries(value)
    return bool(parts) and all(markets.markets_of(part) or code_of(part) for part in parts)


def needed(record: dict, awareness_given: bool) -> list[dict]:
    """The facts a complaint's reporting steps still need, each with why and which rule needs it (none for a complaint
    off the reportability watch). ``awareness_given``: an awareness or received date is recorded. A complaint on the
    watch only because a patient's outcome is unknown is assessed and signed like the rest, so it is asked too
    (0.10.87, DEV-09)."""
    if not rules.watched(record):
        return []
    found = []
    country = str(record.get("country") or "").strip()
    if not country_known(country):
        found.append(
            {
                "fact": COUNTRY,
                "label": "Incident country",
                "given": country or None,
                "message": (
                    f'"{country}" is not a country MDARIX knows. ' if country else "No incident country is recorded. "
                )
                + "Enter the country where it happened: it decides which authorities' reporting rules and deadlines "
                "apply. Until then every market's shortest clock runs, provisional.",
                "rule": COUNTRY_RULE,
            }
        )
    if not awareness_given:
        found.append(
            {
                "fact": AWARENESS,
                "label": "Awareness date",
                "given": None,
                "message": "No awareness or received date is recorded. Enter the day your organization became aware "
                "of it: every reporting deadline counts from it. Until then the clock is provisional, counted from the "
                "earliest date the record has, and no market conclusion can be signed.",
                "rule": AWARENESS_RULE,
            }
        )
    return found


def of_complaint(complaint, record: dict) -> list[dict]:
    """``needed`` for a Complaint row."""
    return needed(record, complaint.awareness_timestamp is not None or complaint.complaint_timestamp is not None)


def labels(needs: list[dict]) -> str:
    """ "the incident country and the awareness date"."""
    return " and ".join(f"the {item['label'].lower()}" for item in needs)
