"""A guide version for an audit, as a PDF (reports/pdf.py, as the report worksheets) and a DOCX (python-docx), from the
screen's view: the title block with the version and its state, every question with its definition, help note, clause
and basis, the test cases with their expected and actual outcomes, and the approval manifestation (21 CFR 11.50: the
printed name, the date and time, the meaning)."""

from __future__ import annotations

import io

from backend.app.reportability import markets


def _label(code: str | None) -> str:
    return markets.CONCLUSION_LABELS.get(code or "", code or "-")


def _kind(code: str | None) -> str:
    kind = markets.REPORT_TYPES.get(code or "")
    return f" ({kind.label})" if kind else ""


def header_lines(view: dict, organization: str | None) -> list[str]:
    lines = [
        f"Organization: {organization or '-'}",
        f"Market: {view['market_label']}",
        f"Version: {view['code']} (version {view['version']}); {view['state_label'].lower()}",
        f"Based on: {view['based_on'] or 'written by MDARIX'}",
        view["never_decides"],
    ]
    if view.get("practice_label"):
        lines.append(view["practice_label"])
    return lines


def _mark(question: dict) -> str:
    if question.get("extra"):
        return "Your extra question: recorded and printed with the answer; it never changes the conclusion."
    return "Starter text." if question.get("starter") else "Your wording of a question that drives the conclusion."


def _answers(test: dict, labels: dict) -> str:
    given = test.get("answers") or {}
    return ", ".join(f"{key} {labels.get(value, value)}" for key, value in given.items()) or "none (all Unknown)"


def manifestation(view: dict) -> list[str]:
    if view.get("starter"):
        return ["MDARIX's starter guide: not approved by your organization. Adopt it by approving your own version."]
    signature = view.get("signature")
    if not signature:
        return ["Not approved: a version being prepared is not in use."]
    return [
        f"Approved by {signature['signer_name']} ({signature['signer_role']}) on {signature['signed_at']}.",
        f"Meaning: {signature['meaning']}",
        f"Signature record: {signature['record_business_id'] or signature['record_id']}.",
        f"Content checksum (SHA-256 of the questions and test cases): {signature['content_fingerprint']}",
    ]


def lines(view: dict) -> list[tuple[str, str]]:
    labels = view.get("answer_labels") or markets.ANSWER_LABELS
    question_set = view["question_set"]
    out: list[tuple[str, str]] = [
        (view["core_rule"], "muted"),
        (view["scale_note"], "muted"),
        (view["starter_mark"], "muted"),
    ]
    if question_set.get("note"):
        out.append((question_set["note"], "muted"))
    if view.get("change_reason"):
        out += [("", "body"), ("What changed and why", "heading"), (view["change_reason"], "body")]
    out += [("", "body"), ("Questions", "heading")]
    for question in question_set["questions"]:
        out.append((f"{question['id']}  {question['text']}", "body"))
        if question.get("definition"):
            out.append((f"    Definition: {question['definition']}", "muted"))
        if question.get("note"):
            out.append((f"    Help: {question['note']}", "muted"))
        basis = ", ".join(question.get("basis") or []) or "none"
        out.append((f"    Clause: {question.get('clause') or 'none'}; basis: {basis}", "muted"))
        out.append((f"    {_mark(question)}", "muted"))
    results = {item["id"]: item for item in ((view.get("test_results") or {}).get("results") or [])}
    run = view.get("test_results") or {}
    out += [("", "body"), ("Test cases", "heading")]
    if run:
        stale = "" if run.get("current", True) else " (run before the last change: run them again)"
        out.append(
            (
                f"{run.get('passed', 0)} passed, {run.get('failed', 0)} failed; run {run.get('run_at') or '-'}{stale}",
                "muted",
            )
        )
    for test in view.get("test_cases") or []:
        result = results.get(test["id"])
        out.append((f"{test['id']}  {test['name']}", "body"))
        out.append((f"    Answers: {_answers(test, labels)}", "muted"))
        out.append((f"    Expected: {_label(test['expected'])}{_kind(test.get('expected_report_type'))}", "muted"))
        if result:
            verdict = "passed" if result["passed"] else "FAILED"
            out.append(
                (
                    f"    Result: {_label(result['actual'])}{_kind(result.get('actual_report_type'))}; {verdict}",
                    "muted",
                )
            )
        else:
            out.append(("    Result: not run", "muted"))
    out += [("", "body"), ("Approval", "heading"), *((line, "body") for line in manifestation(view))]
    return out


def render_pdf(view: dict, organization: str | None) -> bytes:
    from reports import pdf

    watermark = "PRACTICE RECORD - NOT YOUR REGULATORY RECORD" if view.get("practice_label") else "DECISION GUIDE"
    footer = f"{view['code']} - {view['state_label']} - MDARIX never decides"
    return pdf.render(
        f"MDARIX decision guide: {view['title']}",
        header_lines(view, organization),
        lines(view),
        watermark=watermark,
        footer=footer,
    )


def render_docx(view: dict, organization: str | None) -> bytes:
    from docx import Document
    from docx.shared import Pt

    document = Document()
    document.core_properties.title = f"MDARIX decision guide {view['code']}"
    document.add_heading(f"Decision guide: {view['title']}", level=0)
    for line in header_lines(view, organization):
        document.add_paragraph(line)
    for text, style in lines(view):
        if not text:
            continue
        if style == "heading":
            document.add_heading(text, level=1)
        elif text.startswith("    "):
            run = document.add_paragraph().add_run(text.strip())
            run.italic, run.font.size = True, Pt(8)
        elif style == "muted":
            document.add_paragraph().add_run(text).italic = True
        else:
            document.add_paragraph(text)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def render(view: dict, kind: str, *, organization: str | None) -> bytes:
    return render_pdf(view, organization) if kind == "pdf" else render_docx(view, organization)
