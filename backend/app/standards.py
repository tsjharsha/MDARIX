"""The regulatory basis of every report and finding, from one catalog.

Each entry names a clause, section or article MDARIX organizes evidence for: its id (what code and stored data refer
to), its short form (the chip text), its title and its jurisdiction. Readiness checks, the management review summary,
the inspection pack, the reporting window templates and the trial's citation themes all take their basis from here, so
a citation reads the same everywhere. Only these entries are cited; nothing here is legal advice.

The web app mirrors the catalog in ``frontend/src/features/shared/standards.json``; ``tests/test_standards_unit.py``
keeps the two identical.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# Carried once by every page, report or file that shows a basis (never once per chip).
DISCLAIMER = (
    "MDARIX organizes the evidence these ask for; it does not certify compliance. Your quality system and its "
    "validation stay yours."
)

INTERNATIONAL, UNITED_STATES, EUROPEAN_UNION = "International", "United States", "European Union"
UNITED_KINGDOM, CANADA, INDIA = "United Kingdom", "Canada", "India"
# Entries whose wording the regulatory consultant has not confirmed yet (T-B6): screens and exports mark them, in one
# wording everywhere (0.10.83, D2.9; usability U-11).
STARTER_MARK = "Starter, for your consultant to confirm."


def version_words(code: str) -> str:
    """A document version in words for what a person signs or confirms, never its code (J18): "MDARIX starter,
    version 1" for disposition-starter-1 or US-starter-1, "your version 2" for an organization's own US-v2."""
    starter = re.fullmatch(r".+-starter-(\d+)", code or "")
    if starter:
        return f"MDARIX starter, version {starter.group(1)}"
    own = re.fullmatch(r".+-v(\d+)", code or "")
    return f"your version {own.group(1)}" if own else f"version {code}"


@dataclass(frozen=True)
class Standard:
    id: str
    short: str
    title: str
    jurisdiction: str
    starter: bool = False  # the wording awaits the consultant's confirmation (STARTER_MARK)

    def chip(self) -> dict:
        return {"id": self.id, "short": self.short, "title": self.title}

    def as_dict(self) -> dict:
        found = {**self.chip(), "jurisdiction": self.jurisdiction}
        return {**found, "starter": True} if self.starter else found


CATALOG: tuple[Standard, ...] = (
    Standard("ISO13485_4_2_5", "ISO 13485 4.2.5", "Control of records", INTERNATIONAL),
    Standard("ISO13485_5_6_2", "ISO 13485 5.6.2", "Management review input", INTERNATIONAL),
    Standard(
        "ISO13485_6_2", "ISO 13485 6.2", "Human resources: competence, training and awareness", INTERNATIONAL, True
    ),
    Standard("ISO13485_7_3_9", "ISO 13485 7.3.9", "Control of design and development changes", INTERNATIONAL),
    Standard("ISO13485_7_4", "ISO 13485 7.4", "Purchasing (suppliers)", INTERNATIONAL),
    # Printed by the ready-to-use documents (T-G35, 0.10.54): starter text until the consultant confirms the wording.
    Standard("ISO13485_8_2_1", "ISO 13485 8.2.1", "Feedback", INTERNATIONAL, True),
    Standard("ISO13485_8_2_2", "ISO 13485 8.2.2", "Complaint handling", INTERNATIONAL, True),
    Standard("ISO13485_8_2_3", "ISO 13485 8.2.3", "Reporting to regulatory authorities", INTERNATIONAL),
    Standard("ISO13485_8_4", "ISO 13485 8.4", "Analysis of data", INTERNATIONAL),
    Standard("ISO13485_8_5_2", "ISO 13485 8.5.2", "Corrective action", INTERNATIONAL),
    Standard(
        "QMSR",
        "21 CFR 820 (QMSR)",
        "Quality Management System Regulation, incorporating ISO 13485:2016 since 2 February 2026",
        UNITED_STATES,
    ),
    Standard("CFR820_35", "21 CFR 820.35", "Control of records (QMSR)", UNITED_STATES),
    Standard(
        "CFR803_3",
        "21 CFR 803.3",
        "Definitions: serious injury, caused or contributed, malfunction, remedial action",
        UNITED_STATES,
        True,
    ),
    Standard("CFR803_17", "21 CFR 803.17", "Written MDR procedures", UNITED_STATES),
    # Cited by a customer's own guide question on VMSR participation (T-G15, 0.10.59): starter text.
    Standard(
        "CFR803_19",
        "21 CFR 803.19",
        "Exemptions, variances and alternative reporting (FDA's VMSR program)",
        UNITED_STATES,
        True,
    ),
    # B9 Part C: user facility and importer reports (starter text).
    Standard("CFR803_30", "21 CFR 803.30", "Reports by user facilities", UNITED_STATES, True),
    Standard("CFR803_40", "21 CFR 803.40", "Reports by importers", UNITED_STATES, True),
    Standard("CFR803_50", "21 CFR 803.50", "30-day reports by manufacturers", UNITED_STATES),
    Standard("CFR803_53", "21 CFR 803.53", "5-day reports", UNITED_STATES),
    Standard("CFR11_10E", "21 CFR 11.10(e)", "Audit trails", UNITED_STATES),
    Standard("CFR11_50", "21 CFR 11.50", "Signature manifestations", UNITED_STATES),
    Standard("CFR11_70", "21 CFR 11.70", "Signature/record linking", UNITED_STATES),
    Standard("CFR11_200", "21 CFR 11.200", "Electronic signature components and controls", UNITED_STATES),
    Standard(
        "MDR_2",
        "EU MDR Art. 2(64)–(66)",
        "Definitions: incident, serious incident, serious public health threat",
        EUROPEAN_UNION,
        True,
    ),
    Standard("MDR_83", "EU MDR Art. 83", "Post-market surveillance system", EUROPEAN_UNION),
    Standard(
        "MDR_87",
        "EU MDR Art. 87",
        "Reporting of serious incidents and field safety corrective actions",
        EUROPEAN_UNION,
    ),
    Standard("MDR_88", "EU MDR Art. 88", "Trend reporting", EUROPEAN_UNION),
    # B8: the manufacturer's final report after its investigation (Art. 89(5)); starter until the consultant confirms.
    Standard(
        "MDR_89",
        "EU MDR Art. 89",
        "Analysis of serious incidents and field safety corrective actions (final report)",
        EUROPEAN_UNION,
        True,
    ),
    # The IVDR's counterpart of MDR Art. 87 for in-vitro diagnostics (Regulation (EU) 2017/746); starter until the
    # consultant confirms it (0.10.63).
    Standard(
        "IVDR_82",
        "EU IVDR Art. 82",
        "Reporting of serious incidents and field safety corrective actions (in-vitro diagnostics)",
        EUROPEAN_UNION,
        True,
    ),
    Standard(
        "IVDR_84",
        "EU IVDR Art. 84",
        "Analysis of serious incidents and field safety corrective actions (in-vitro diagnostics, final report)",
        EUROPEAN_UNION,
        True,
    ),
    Standard(
        "MDCG_2023_3",
        "MDCG 2023-3",
        "Questions and answers on vigilance terms and concepts (EU MDR)",
        EUROPEAN_UNION,
        True,
    ),
    Standard("ISO14971_10", "ISO 14971 clause 10", "Production and post-production activities", INTERNATIONAL),
    Standard("IEC62304_9", "IEC 62304 clause 9", "Software problem resolution process", INTERNATIONAL),
    Standard("IMDRF_AET", "IMDRF AET", "Adverse event terminology", INTERNATIONAL),
    Standard(
        "UK_MDR",
        "UK MDR 2002 (as amended)",
        "Post-market surveillance and vigilance (Great Britain)",
        UNITED_KINGDOM,
    ),
    Standard("CA_MDR", "SOR/98-282 ss. 59–61", "Mandatory problem reporting (Canada)", CANADA),
    Standard(
        "IN_MDR",
        "India MDR 2017 Rules 3, 26",
        "Medical Devices Rules 2017: definitions and post-market reporting of adverse events",
        INDIA,
        True,
    ),
    # B9b: the generic starter questions for a country outside the five markets (OTHER-floor-1); not any country's law.
    Standard(
        "IMDRF_GHTF_COMMON",
        "IMDRF/GHTF common criteria",
        "Adverse event reporting criteria common to most regulators (generic starter, not a country's law)",
        INTERNATIONAL,
        True,
    ),
)

BY_ID: dict[str, Standard] = {standard.id: standard for standard in CATALOG}


def known(ids: Iterable[str] | None) -> list[str]:
    """The catalog ids among ``ids``, once each, in their order (for stored data, where an unknown id is dropped)."""
    found: list[str] = []
    for item in ids or ():
        code = str(item or "").strip().upper()
        if code in BY_ID and code not in found:
            found.append(code)
    return found


def chips(ids: Iterable[str]) -> list[dict]:
    """``{id, short, title}`` for each id, as a screen shows them. An id outside the catalog is a programming error."""
    return [BY_ID[code].chip() for code in ids]


def entries(ids: Iterable[str]) -> list[dict]:
    """The full entries of ``ids`` (with the jurisdiction), once each, in catalog order: a report's table."""
    wanted = set(ids)
    return [standard.as_dict() for standard in CATALOG if standard.id in wanted]


def cite(*parts: str) -> str:
    """One reference line: catalog ids by their short form, any other part (no catalog entry) as written."""
    return "; ".join(BY_ID[part].short if part in BY_ID else part for part in parts)


def catalog() -> list[dict]:
    return [standard.as_dict() for standard in CATALOG]
