"""What a free trial's organization was cited for: the story starts there.

A short list of the themes FDA warning letters and form 483 observations, and notified body nonconformities, keep
citing, each tied to the story chapter that answers it. The organization ticks what it was cited for (Getting started);
those chapters are marked and come first as the next step, and the MDARIX team sees them in Platform Admin to prepare
the one-to-one demo. Kept in the trial request's profile (``citations``), so it belongs to the organization and is
deleted with the trial's data. References name ISO 13485 clauses (part of FDA's QMSR since 2 February 2026), 21 CFR 803,
the EU MDR and ISO 14971.
"""

from __future__ import annotations

# code -> (label, reference, chapter it is answered by), in story order.
CITATIONS: dict[str, tuple[str, str, str]] = {
    "COMPLAINT_HANDLING": (
        "Complaints not evaluated, or closed off as inquiries or cancellations",
        "ISO 13485 clause 8.2.2",
        "HIDDEN_COMPLAINTS",
    ),
    "REPORTING": (
        "Medical device reports or vigilance reports late or missing",
        "21 CFR 803; EU MDR Article 87",
        "REPORTING_CLOCKS",
    ),
    "TRENDING": (
        "Complaint and quality data not analysed for trends",
        "ISO 13485 clause 8.4; EU MDR Article 88",
        "TRENDS_TO_CASES",
    ),
    "INVESTIGATION": (
        "Investigations without a documented root cause",
        "ISO 13485 clauses 8.2.2 and 8.5.2",
        "INVESTIGATE_WITH_AI",
    ),
    "DECISIONS": (
        "Decisions on nonconformities without a documented rationale or approval",
        "ISO 13485 clauses 8.3 and 4.2.5",
        "DECIDE_AND_SIGN",
    ),
    "CAPA_EFFECTIVENESS": (
        "CAPAs closed without verifying they were effective",
        "ISO 13485 clause 8.5.2",
        "CAPA_EFFECTIVE",
    ),
    "RISK_FILE": (
        "Risk management file not updated with post-market data",
        "ISO 14971:2019 clause 10",
        "RISK_FILE",
    ),
    "MANAGEMENT_REVIEW": (
        "Management review without the quality data it needs",
        "ISO 13485 clause 5.6",
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
    return [
        {"code": code, "label": label, "reference": reference, "chapter": chapter}
        for code, (label, reference, chapter) in CITATIONS.items()
    ]


def labels(codes) -> list[str]:
    return [CITATIONS[code][0] for code in clean(codes)]
