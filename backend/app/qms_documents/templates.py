"""The five ready-to-use documents (T-G35, MVP G35's first part): each template's code, title, version, the clauses it
serves, what it is generated for, and its judgement sections.

A template's wording is starter text until the regulatory consultant confirms it (T-B6), and each clause it prints
shows "pending approval" until the source register records the consultant's confirmation of its wording (MVP 5.5,
not in the trial: ``CONFIRMED_CLAUSES`` stays empty). Template versions are code strings printed on every document; a
change of wording is a new template version, never an edit of one in use.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.standards import BY_ID, STARTER_MARK

ORGANIZATION, CASE, CHANGE = "ORGANIZATION", "CASE", "CHANGE"
PENDING_APPROVAL = "pending approval"
# Clauses whose printed wording the consultant has confirmed (the source register, MVP 5.5). None yet.
CONFIRMED_CLAUSES: frozenset[str] = frozenset()
WRITTEN_BY_MANUFACTURER = "Written by the manufacturer"
DATA_NOTE = "A data section cannot be edited. Correct the record, then generate again."
PERIODS = (30, 90, 180, 365)
PERIOD_DEFAULT, PERIOD_MIN, PERIOD_MAX = 90, 30, 1095
JUDGEMENT_MIN, JUDGEMENT_MAX = 10, 6000


@dataclass(frozen=True)
class Judgement:
    key: str
    title: str
    prompt: str


@dataclass(frozen=True)
class Template:
    code: str
    title: str
    version: str
    clauses: tuple[str, ...]
    scope: str
    purpose: str
    judgements: tuple[Judgement, ...] = ()

    def clause_list(self) -> list[dict]:
        return [
            {
                **BY_ID[code].chip(),
                "state": "confirmed" if code in CONFIRMED_CLAUSES else PENDING_APPROVAL,
            }
            for code in self.clauses
        ]

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "title": self.title,
            "template_version": self.version,
            "clauses": self.clause_list(),
            "scope": self.scope,
            "purpose": self.purpose,
            "judgements": [{"key": item.key, "title": item.title, "prompt": item.prompt} for item in self.judgements],
            "starter_mark": STARTER_MARK,
        }


TEMPLATES: dict[str, Template] = {
    template.code: template
    for template in (
        Template(
            "MANAGEMENT_REVIEW",
            "Management review report",
            "mrr-starter-1",
            ("ISO13485_5_6_2", "ISO13485_8_2_1"),
            ORGANIZATION,
            "The management review inputs MDARIX holds records for, for a period: complaints, the second look, "
            "vigilance by market, signals and trends, post-market data against the risk file, CAPAs and the PMS "
            "section.",
            (
                Judgement(
                    "PMS_CONCLUSION",
                    "PMS conclusion",
                    "What the post-market data of the period means for the risk file, the clinical evaluation, the "
                    "PSUR and the PMS plan.",
                ),
                Judgement(
                    "ACTIONS_DECIDED",
                    "Actions decided",
                    "The actions management decided, each with its owner and date.",
                ),
            ),
        ),
        Template(
            "CAPA_LOG",
            "CAPA log",
            "capa-log-starter-1",
            ("ISO13485_8_5_2",),
            ORGANIZATION,
            "Every CAPA imported from your QMS with its QMS ID, the complaints and cases it came from, its status, due "
            "date and effectiveness.",
        ),
        Template(
            "INVESTIGATION_REPORT",
            "Investigation report",
            "investigation-report-starter-1",
            ("ISO13485_8_2_2", "ISO14971_10"),
            CASE,
            "One case: its scope by version, evidence, hypotheses with their support states, the root cause and its "
            "attribution as recorded in the decision, and the signed decision.",
            (
                Judgement(
                    "ROOT_CAUSE_CATEGORY",
                    "Root-cause category",
                    "The root-cause category under your own coding (until MDARIX codes it).",
                ),
            ),
        ),
        Template(
            "RISK_REVIEW_EXTRACT",
            "Risk-review extract",
            "risk-extract-starter-1",
            ("ISO14971_10",),
            CASE,
            "One case's risk reviews: the risk-register entries named, each risk-control answer and risk file update, "
            "post-market data against the risk file and the impact decisions.",
            (
                Judgement(
                    "CONCLUSION",
                    "Conclusion",
                    "What the risk file must now say, and whether the benefit-risk conclusion still holds.",
                ),
            ),
        ),
        Template(
            "CHANGE_IMPACT",
            "Change-impact input",
            "change-impact-starter-1",
            ("ISO13485_7_3_9",),
            CHANGE,
            "For one change record: the affected products and lots, the risk and PMS impacts recorded, and the "
            "complaints whose market assessments may need review. The change itself is run in your QMS.",
        ),
    )
}
CODES = tuple(TEMPLATES)


def template_of(code: str) -> Template | None:
    return TEMPLATES.get(str(code or "").strip().upper())


def signature_meaning(title: str, version: int, ref: str | None) -> str:
    """What the signer confirms, printed in the signature manifestation."""
    scope = f" for {ref}" if ref else ""
    return (
        f"I approve version {version} of the {title.lower()}{scope}: its data sections as generated from the records "
        "and its judgement sections as written."
    )
