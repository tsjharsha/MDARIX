"""The ready-to-use documents' rules without a database (T-G35): the five templates and their clauses "pending
approval", which sections a person may write, which version supersedes a signed one, and the PDF and DOCX made from one
view (version, template version, clauses, practice label, starter mark, records per row, the signature manifestation
and the export note)."""

from __future__ import annotations

import io
import uuid
from types import SimpleNamespace

import pytest

from backend.app.qms_documents import render, service, templates
from backend.app.standards import STARTER_MARK

pytestmark = pytest.mark.unit

PRACTICE = "Practice record: made in a free trial with sample or de-identified data. Not your regulatory record."


def test_each_template_names_its_clauses_and_none_is_confirmed_yet():
    assert templates.CODES == (
        "MANAGEMENT_REVIEW",
        "CAPA_LOG",
        "INVESTIGATION_REPORT",
        "RISK_REVIEW_EXTRACT",
        "CHANGE_IMPACT",
    )
    clauses = {code: template.clauses for code, template in templates.TEMPLATES.items()}
    assert clauses["MANAGEMENT_REVIEW"] == ("ISO13485_5_6_2", "ISO13485_8_2_1")
    assert clauses["INVESTIGATION_REPORT"] == ("ISO13485_8_2_2", "ISO14971_10")
    assert clauses["RISK_REVIEW_EXTRACT"] == ("ISO14971_10",)
    assert templates.CONFIRMED_CLAUSES == frozenset()
    for template in templates.TEMPLATES.values():
        assert {clause["state"] for clause in template.clause_list()} == {"pending approval"}
        assert "starter" in template.version and template.as_dict()["starter_mark"] == STARTER_MARK


def test_only_a_judgement_section_is_written_and_never_too_short():
    review = templates.TEMPLATES["MANAGEMENT_REVIEW"]
    assert service.judgement_problem(review, "COMPLAINTS", "A figure I would like changed.") == templates.DATA_NOTE
    assert (
        service.judgement_problem(review, "ACTIONS_DECIDED", "Short") == "Write the section in at least 10 characters"
    )
    assert service.judgement_problem(review, "ACTIONS_DECIDED", "Open an investigation into cable wear.") is None
    assert service.judgement_problem(templates.TEMPLATES["CAPA_LOG"], "ANY", "No judgement section here.") is not None


def _job(version: int, status: str, scope=None):
    return SimpleNamespace(
        report_code="MANAGEMENT_REVIEW", status=status, context={"version": version, "scope_id": scope}
    )


def test_a_signed_version_is_superseded_by_the_next_signed_one_only():
    one, two, three = _job(1, "SIGNED"), _job(2, "DRAFT"), _job(3, "SIGNED")
    other = _job(4, "SIGNED", scope=str(uuid.uuid4()))
    rows = [one, two, three, other]
    assert service.superseded_by(rows, one) == 3
    assert service.superseded_by(rows, three) is None and service.superseded_by(rows, two) is None


def _view(signed: bool) -> dict:
    view = {
        "id": str(uuid.uuid4()),
        "business_id": "RPT000042",
        "title": "Management review report",
        "version": 2,
        "template_version": "mrr-starter-1",
        "organization": "Sample Devices",
        "period": {"from": "2026-08-03", "to": "2026-10-31", "days": 90},
        "cut_off": "2026-10-31T09:00:00+00:00",
        "scope_ref": None,
        "clauses": templates.TEMPLATES["MANAGEMENT_REVIEW"].clause_list(),
        "practice_label": PRACTICE,
        "starter_mark": STARTER_MARK,
        "footer_note": service.FOOTER_NOTE,
        "sections": [
            {
                "key": "DISPOSITIONS",
                "title": "Complaint dispositions",
                "kind": "data",
                "rows": [
                    {
                        "text": "Resolved at service level: 3.",
                        "sources": [{"type": "Disposition", "id": "x", "ref": f"CMP00000{i} v1"} for i in range(3)],
                    }
                ],
            },
            {"key": "ACTIONS_DECIDED", "title": "Actions decided", "kind": "judgement", "prompt": "The actions."},
        ],
        "judgement": {
            "ACTIONS_DECIDED": {
                "text": "Review cable wear in 30 days.",
                "written_by_name": "Priya",
                "written_at": "2026-10-31T09:05:00+00:00",
            }
        },
        "signature": None,
        "writer_note": None,
    }
    if signed:
        view["signature"] = {
            "signer_name": "Priya",
            "signer_role": "Leader",
            "signed_at": "2026-10-31T09:10:00+00:00",
            "meaning": "I approve version 2 of the management review report.",
            "record_business_id": "SIG000007",
            "record_id": "r",
            "content_fingerprint": "a" * 64,
            "pdf_sha256": "b" * 64,
        }
        view["writer_note"] = "Writer of the judgement sections and signer: same person."
    return view


def test_the_pdf_and_the_docx_carry_the_version_clauses_labels_records_and_signature():
    from docx import Document

    pdf = render.render_pdf(_view(signed=True))
    assert pdf.startswith(b"%PDF")
    text = pdf.decode("latin-1")
    for expected in (
        "Template version: mrr-starter-1",
        "ISO 13485 5.6.2 Management review input \\(pending approval\\)",
        PRACTICE,
        "Records: CMP000000 v1, CMP000001 v1, CMP000002 v1",
        "[Written by the manufacturer]",
        "Signed by Priya \\(Leader\\)",
        "a" * 64,
        "Dispositions: CMP000000 v1",
    ):
        assert expected in text, expected
    docx = Document(io.BytesIO(render.render_docx(_view(signed=True))))
    paragraphs = "\n".join(paragraph.text for paragraph in docx.paragraphs)
    assert paragraphs.startswith(
        "Management review report\nExported from signed version 2 (RPT000042, PDF SHA-256 " + "b" * 64
    )
    assert "edits outside MDARIX are not part of this record" in paragraphs and PRACTICE in paragraphs
    assert "Written by the manufacturer. The actions." in paragraphs and "Review cable wear in 30 days." in paragraphs
    draft = render.render_docx(_view(signed=False))
    paragraphs = "\n".join(paragraph.text for paragraph in Document(io.BytesIO(draft)).paragraphs)
    assert "Exported from draft version 2, not signed" in paragraphs and "Not signed: this is a draft." in paragraphs
    assert b"PRACTICE RECORD - NOT YOUR REGULATORY RECORD" in render.render_pdf(_view(signed=False))
    no_trial = {**_view(signed=False), "practice_label": None}
    assert b"DRAFT - NOT SIGNED" in render.render_pdf(no_trial)


def test_the_pms_loop_arrows_print_in_the_pdf():
    from reports.pdf import escape

    from backend.app.readiness_home.summary import PMS_FRAMING

    assert "PMS -> risk management -> clinical evaluation -> PSUR -> back to the PMS plan" in escape(PMS_FRAMING)
