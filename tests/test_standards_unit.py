"""The regulatory basis of every report and finding comes from one catalog (backend/app/standards.py), without a
database: the catalog itself and its web mirror, the readiness checks, the management review summary, the inspection
pack's README, the reporting window templates and the trial's citation themes."""

from __future__ import annotations

import csv
import io
import json
from datetime import date
from pathlib import Path

import pytest

from backend.app import standards
from backend.app.readiness_home import pack, service, summary
from backend.app.reportability import rules
from backend.app.trial import citations
from reports import pdf

MIRROR = Path(__file__).resolve().parents[1] / "frontend" / "src" / "features" / "shared" / "standards.json"

# The catalog as agreed, word for word.
EXPECTED = [
    ("ISO13485_4_2_5", "ISO 13485 4.2.5", "Control of records", "International"),
    ("ISO13485_5_6_2", "ISO 13485 5.6.2", "Management review input", "International"),
    ("ISO13485_6_2", "ISO 13485 6.2", "Human resources: competence, training and awareness", "International"),
    ("ISO13485_7_3_9", "ISO 13485 7.3.9", "Control of design and development changes", "International"),
    ("ISO13485_7_4", "ISO 13485 7.4", "Purchasing (suppliers)", "International"),
    ("ISO13485_8_2_1", "ISO 13485 8.2.1", "Feedback", "International"),
    ("ISO13485_8_2_2", "ISO 13485 8.2.2", "Complaint handling", "International"),
    ("ISO13485_8_2_3", "ISO 13485 8.2.3", "Reporting to regulatory authorities", "International"),
    ("ISO13485_8_4", "ISO 13485 8.4", "Analysis of data", "International"),
    ("ISO13485_8_5_2", "ISO 13485 8.5.2", "Corrective action", "International"),
    (
        "QMSR",
        "21 CFR 820 (QMSR)",
        "Quality Management System Regulation, incorporating ISO 13485:2016 since 2 February 2026",
        "United States",
    ),
    ("CFR820_35", "21 CFR 820.35", "Control of records (QMSR)", "United States"),
    (
        "CFR803_3",
        "21 CFR 803.3",
        "Definitions: serious injury, caused or contributed, malfunction, remedial action",
        "United States",
    ),
    ("CFR803_17", "21 CFR 803.17", "Written MDR procedures", "United States"),
    (
        "CFR803_19",
        "21 CFR 803.19",
        "Exemptions, variances and alternative reporting (FDA's VMSR program)",
        "United States",
    ),
    ("CFR803_50", "21 CFR 803.50", "30-day reports by manufacturers", "United States"),
    ("CFR803_53", "21 CFR 803.53", "5-day reports", "United States"),
    ("CFR11_10E", "21 CFR 11.10(e)", "Audit trails", "United States"),
    ("CFR11_50", "21 CFR 11.50", "Signature manifestations", "United States"),
    ("CFR11_70", "21 CFR 11.70", "Signature/record linking", "United States"),
    ("CFR11_200", "21 CFR 11.200", "Electronic signature components and controls", "United States"),
    (
        "MDR_2",
        "EU MDR Art. 2(64)–(66)",
        "Definitions: incident, serious incident, serious public health threat",
        "European Union",
    ),
    ("MDR_83", "EU MDR Art. 83", "Post-market surveillance system", "European Union"),
    (
        "MDR_87",
        "EU MDR Art. 87",
        "Reporting of serious incidents and field safety corrective actions",
        "European Union",
    ),
    ("MDR_88", "EU MDR Art. 88", "Trend reporting", "European Union"),
    ("MDCG_2023_3", "MDCG 2023-3", "Questions and answers on vigilance terms and concepts (EU MDR)", "European Union"),
    ("ISO14971_10", "ISO 14971 clause 10", "Production and post-production activities", "International"),
    ("IEC62304_9", "IEC 62304 clause 9", "Software problem resolution process", "International"),
    ("IMDRF_AET", "IMDRF AET", "Adverse event terminology", "International"),
    ("UK_MDR", "UK MDR 2002 (as amended)", "Post-market surveillance and vigilance (Great Britain)", "United Kingdom"),
    ("CA_MDR", "SOR/98-282 ss. 59–61", "Mandatory problem reporting (Canada)", "Canada"),
    (
        "IN_MDR",
        "India MDR 2017 Rules 3, 26",
        "Medical Devices Rules 2017: definitions and post-market reporting of adverse events",
        "India",
    ),
]
# Entries whose wording awaits the regulatory consultant (T-B6): marked starter text on screen and in exports.
STARTER = {
    "ISO13485_6_2",
    "ISO13485_8_2_1",
    "ISO13485_8_2_2",
    "CFR803_3",
    "CFR803_19",
    "MDR_2",
    "MDCG_2023_3",
    "IN_MDR",
}
DISCLAIMER = (
    "MDARIX organizes the evidence these ask for; it does not certify compliance. Your quality system and its "
    "validation stay yours."
)


# ------------------------------------------------------------------------------------------------- the catalog


def test_the_catalog_holds_exactly_the_agreed_entries():
    assert [(s.id, s.short, s.title, s.jurisdiction) for s in standards.CATALOG] == EXPECTED
    assert standards.DISCLAIMER == DISCLAIMER
    for word in ("compliant", "certified", "Part 11"):
        assert all(word not in s.title for s in standards.CATALOG)
    assert {s.id for s in standards.CATALOG if s.starter} == STARTER
    assert (
        standards.BY_ID["MDR_2"].as_dict()["starter"] is True and "starter" not in standards.BY_ID["MDR_87"].as_dict()
    )


def test_the_web_app_mirror_is_identical():
    mirror = json.loads(MIRROR.read_text(encoding="utf-8"))
    assert mirror == {"disclaimer": standards.DISCLAIMER, "standards": standards.catalog()}


def test_helpers_read_the_catalog():
    assert standards.chips(["MDR_88"]) == [{"id": "MDR_88", "short": "EU MDR Art. 88", "title": "Trend reporting"}]
    assert standards.known(["mdr_88", "NOPE", "MDR_88", "QMSR"]) == ["MDR_88", "QMSR"]
    assert [entry["id"] for entry in standards.entries(["MDR_88", "ISO13485_4_2_5"])] == ["ISO13485_4_2_5", "MDR_88"]
    assert standards.cite("21 CFR 803", "MDR_87") == "21 CFR 803; EU MDR Art. 87"
    with pytest.raises(KeyError):
        standards.chips(["NOT_IN_THE_CATALOG"])


# ------------------------------------------------------------------------------------------------- readiness checks


def test_every_check_has_its_basis_from_the_catalog():
    codes = {step.__name__.upper() for step in service.CHECKS}
    assert set(service.BASIS) == codes
    for ids in service.BASIS.values():
        assert all(code in standards.BY_ID for code in ids)
    assert service.BASIS["COMPLAINTS_TO_RECHECK"] == ("ISO13485_8_2_2", "CFR820_35")
    assert service.BASIS["REPORTING_CLOCKS"] == ("ISO13485_8_2_3", "CFR803_50", "CFR803_53", "MDR_87")
    assert service.BASIS["TRENDS_WITHOUT_ACTION"] == ("ISO13485_8_4", "MDR_88")
    assert service.BASIS["CAPA_EFFECTIVENESS"] == ("ISO13485_8_5_2",)
    assert service.BASIS["RISK_FILE_INPUT"] == ("ISO14971_10",)


def test_a_check_returns_its_basis_as_chips():
    check = service._check("TRENDS_WITHOUT_ACTION", "Trends", 0, service.CLEAR, "", None)
    assert check["basis"] == [
        {"id": "ISO13485_8_4", "short": "ISO 13485 8.4", "title": "Analysis of data"},
        {"id": "MDR_88", "short": "EU MDR Art. 88", "title": "Trend reporting"},
    ]


# ------------------------------------------------------------------------------------------------- the summary PDF


def _summary_data(checks: list[dict], window_basis: list[str]) -> dict:
    return {
        "period": {"from": "2026-01-01", "to": "2026-06-30", "days": 180},
        "readiness": {
            "summary": {"clear": 1, "checks": 1, "critical": 0, "attention": 0, "not_set": 0},
            "checks": checks,
        },
        "complaints": {
            "received": 0,
            "closed": 0,
            "death": 0,
            "serious_injury": 0,
            "malfunction": 0,
            "by_product_version": [],
            "more_groups": 0,
        },
        "second_look": {"confirmed": 0, "dismissed": 0},
        "reporting": {
            "decisions": 0,
            "reported": 0,
            "not_reportable": 0,
            "inside_window": 0,
            "after_window": 0,
            "windows": ["Health Canada: death or serious deterioration (10 days)"],
            "basis": window_basis,
        },
        "trends": {"signals_by_status": {}, "signals_raised": 0, "rising": []},
        "risk_file": {
            "summary": {
                "products": 0,
                "not_reviewed": 0,
                "reassessment_overdue": 0,
                "reassessment_open": 0,
                "no_risk_register": 0,
                "reviewed": 0,
            },
            "products": [],
        },
        "capa": {"opened": 0, "checks_signed_effective": 0, "checks_signed_not_effective": 0, "now": ""},
        "limitations": [],
    }


def test_the_summary_ends_with_the_standards_it_references():
    check = service._check("CAPA_EFFECTIVENESS", "CAPAs without a verified effect", 0, service.CLEAR, "None", None)
    data = _summary_data([check], ["CA_MDR"])
    out = summary.lines(data)
    text = [line for line, _ in out]
    # Each section keeps its clause; each check names its basis.
    assert any("ISO 13485:2016 clause 5.6.2" in line for line in text)
    assert "    Basis: ISO 13485 8.5.2" in text
    assert "    Basis of the windows: SOR/98-282 ss. 59–61" in text
    at = text.index("8. Standards referenced")
    table = text[at + 1 :]
    assert table[0].startswith("Standard") and table[0].rstrip().endswith("Jurisdiction")
    assert table[-1] == DISCLAIMER and out[-1][1] == "muted"
    rows = "\n".join(table)
    # Only the standards the report uses, each once (the table in catalog order).
    assert summary.referenced(data) == ["ISO13485_5_6_2", "ISO14971_10", "ISO13485_8_5_2", "CA_MDR"]
    for short in ("ISO 13485 5.6.2", "ISO 13485 8.5.2", "ISO 14971 clause 10", "SOR/98-282 ss. 59–61"):
        assert rows.count(short) == 1
    assert "Corrective action" in rows and "Canada" in rows
    assert "EU MDR Art. 88" not in rows and "QMSR" not in rows
    # The PDF writes the dash in the fonts' encoding, not as a question mark.
    rendered = summary.render_pdf(data, "Example Medical", "2026-10-17 10:00 UTC")
    assert b"SOR/98-282 ss. 59\\22661" in rendered


def test_long_titles_wrap_inside_their_column():
    data = _summary_data([], [])
    basis = standards.chips(["QMSR", "MDR_87"])
    data["readiness"]["checks"] = [
        {"title": "x", "value": 0, "state": "CLEAR", "detail": "", "why": "", "basis": basis}
    ]
    text = [line for line, _ in summary.lines(data)]
    table = text[text.index("8. Standards referenced") : -1]  # the disclaimer after it wraps as any text does
    assert all(len(line) <= pdf.CHARS_PER_LINE for line in table)
    qmsr = next(index for index, line in enumerate(table) if line.startswith("21 CFR 820 (QMSR)"))
    assert table[qmsr].rstrip().endswith("United States")
    assert table[qmsr + 1].startswith(" " * summary.SHORT_WIDTH) and "2 February 2026" in "".join(
        table[qmsr : qmsr + 3]
    )


# ------------------------------------------------------------------------------------------------- the inspection pack


def test_the_pack_readme_names_the_basis_of_every_file():
    names = ["01-readiness-summary.pdf", "02-inspection-checks.csv", *[name for name, _, _ in pack.CHECK_FILES]]
    period = {"from": "2026-01-01", "to": "2026-06-30", "days": 180}
    readme = pack._readme("Example Medical", "2026-10-17 10:00 UTC", period, {"summary": {}}, names).decode("utf-8")
    assert "  03-hidden-complaints.csv; basis: ISO 13485 8.2.2; 21 CFR 820.35" in readme
    assert "  05-reporting-clocks.csv; basis: ISO 13485 8.2.3; 21 CFR 803.50; 21 CFR 803.53; EU MDR Art. 87" in readme
    assert "  01-readiness-summary.pdf; basis: ISO 13485 5.6.2" in readme
    assert "  manifest.json (the SHA-256 of every file above); basis: ISO 13485 4.2.5" in readme
    assert "  ISO 14971 clause 10: Production and post-production activities (International)" in readme
    assert readme.count(DISCLAIMER) == 1
    for name in names:
        assert pack.file_basis(name), name


def test_the_list_of_checks_carries_each_basis():
    check = service._check("RISK_FILE_INPUT", "Post-market data not in the risk file", 0, service.CLEAR, "", None)
    rows = list(csv.reader(io.StringIO(pack._checks_csv({"checks": [check]}).decode("utf-8-sig"))))
    assert rows[0][6] == "Basis" and rows[1][6] == "ISO 14971 clause 10"


# ------------------------------------------------------------------------------------------------- reporting windows


def test_each_template_names_its_basis():
    by_market = {}
    for template in rules.TEMPLATES:
        by_market.setdefault(template["markets"][0], set()).update(template["basis"])
    assert by_market == {
        "US": {"CFR803_50", "CFR803_53"},
        "EU": {"MDR_87"},
        "United Kingdom": {"UK_MDR"},
        "Canada": {"CA_MDR"},
        "India": {"IN_MDR"},
    }
    assert all(rules.clean_window(template)["basis"] == template["basis"] for template in rules.TEMPLATES)


def test_a_window_keeps_its_basis_and_an_older_one_takes_its_templates():
    fda = rules.TEMPLATES[0]
    older = {key: value for key, value in fda.items() if key != "basis"}
    assert rules.clean_window(older)["basis"] == ["CFR803_50", "CFR803_53"]
    assert rules.clean_window({**older, "basis": []})["basis"] == []
    assert rules.clean_window({**older, "name": "Our own window"})["basis"] == []
    assert rules.clean_window({**older, "basis": ["mdr_87", "MADE_UP"]})["basis"] == ["MDR_87"]


def test_a_clock_carries_its_windows_basis():
    window = rules.clean_window(rules.TEMPLATES[0])
    record = {"country": "US", "death": True, "serious_injury": None, "malfunction": None}
    clock = rules.clocks(record, [window], date(2026, 10, 1), date(2026, 10, 3))[0]
    assert clock.as_dict()["basis"] == ["CFR803_50", "CFR803_53"]


# ------------------------------------------------------------------------------------------------- trial citations


def test_citation_themes_cite_the_catalog_where_it_has_the_entry():
    options = {option["code"]: option for option in citations.options()}
    assert options["COMPLAINT_HANDLING"]["reference"] == "ISO 13485 8.2.2"
    assert options["REPORTING"]["reference"] == "21 CFR 803; EU MDR Art. 87"
    assert options["REPORTING"]["basis"] == ["MDR_87"]
    assert options["TRENDING"]["reference"] == "ISO 13485 8.4; EU MDR Art. 88"
    assert options["DECISIONS"]["reference"] == "ISO 13485 clause 8.3; ISO 13485 4.2.5"
    assert options["RISK_FILE"]["reference"] == "ISO 14971 clause 10"
    assert options["MANAGEMENT_REVIEW"]["reference"] == "ISO 13485 clause 5.6"
    for option in options.values():
        assert all(code in standards.BY_ID for code in option["basis"])


def test_the_pdf_writer_keeps_typographic_dashes_and_quotes():
    assert pdf.escape("59–61 — ‘a’ “b”") == "59\\22661 \\227 \\221a\\222 \\223b\\224"
    assert pdf.escape("→") == "?"
