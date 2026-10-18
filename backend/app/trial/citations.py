"""What a free trial's organization was cited for: the story starts there.

A short list of the themes FDA warning letters and form 483 observations, and notified body nonconformities, keep
citing, each tied to the story chapter that answers it. The organization ticks what it was cited for (Getting started);
those chapters are marked and come first as the next step, and the MDARIX team sees them in Platform Admin to prepare
the one-to-one demo. Kept in the trial request's profile (``citations``), so it belongs to the organization and is
deleted with the trial's data. References name ISO 13485 clauses (part of FDA's QMSR since 2 February 2026), 21 CFR 803,
the EU MDR and ISO 14971: from the one catalog (backend/app/standards.py) where it has the exact entry, as written where
it has none (21 CFR 803 as a whole, ISO 13485 8.3 and 5.6).
"""

from __future__ import annotations

from backend.app.standards import BY_ID, cite

# code -> (label, reference parts: catalog ids or, without an exact entry, the text, chapter it is answered by), in
# story order.
CITATIONS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "COMPLAINT_HANDLING": (
        "Complaints not evaluated, or closed off as inquiries or cancellations",
        ("ISO13485_8_2_2",),
        "HIDDEN_COMPLAINTS",
    ),
    "REPORTING": (
        "Medical device reports or vigilance reports late or missing",
        ("21 CFR 803", "MDR_87"),
        "REPORTING_CLOCKS",
    ),
    "TRENDING": (
        "Complaint and quality data not analysed for trends",
        ("ISO13485_8_4", "MDR_88"),
        "TRENDS_TO_CASES",
    ),
    "INVESTIGATION": (
        "Investigations without a documented root cause",
        ("ISO13485_8_2_2", "ISO13485_8_5_2"),
        "INVESTIGATE_WITH_AI",
    ),
    "DECISIONS": (
        "Decisions on nonconformities without a documented rationale or approval",
        ("ISO 13485 clause 8.3", "ISO13485_4_2_5"),
        "DECIDE_AND_SIGN",
    ),
    "CAPA_EFFECTIVENESS": (
        "CAPAs closed without verifying they were effective",
        ("ISO13485_8_5_2",),
        "CAPA_EFFECTIVE",
    ),
    "RISK_FILE": (
        "Risk management file not updated with post-market data",
        ("ISO14971_10",),
        "RISK_FILE",
    ),
    "MANAGEMENT_REVIEW": (
        "Management review without the quality data it needs",
        ("ISO 13485 clause 5.6",),
        "SHOW_THE_INSPECTOR",
    ),
}


def clean(codes) -> list[str]:
    """The known codes among ``codes``, once each, in story order."""
    wanted = set(codes or ())
    return [code for code in CITATIONS if code in wanted]


def chapters_for(codes) -> list[str]:
    """The story chapters the cited themes are answered by, in story order."""
    return [CITATIONS[code][2] for code in clean(codes)]


def options() -> list[dict]:
    """Each theme with its reference line and the catalog ids it cites (``basis``)."""
    return [
        {
            "code": code,
            "label": label,
            "reference": cite(*parts),
            "basis": [part for part in parts if part in BY_ID],
            "chapter": chapter,
        }
        for code, (label, parts, chapter) in CITATIONS.items()
    ]


def labels(codes) -> list[str]:
    return [CITATIONS[code][0] for code in clean(codes)]
