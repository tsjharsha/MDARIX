"""The Decision trees tab (release 0.10.75, Release C part C3): one tree per market, read from the decision guides.

- ``GET /api/v1/decision-trees``: each market's tree: the guide version in use (the organization's approved version,
  else MDARIX's starter), its status, its questions in order (each with its clause) and its test matrix result; and
  the complaints walked through a tree, the signed ones first;
- ``?complaint_id=``: also the path that complaint took in each market it was assessed for: question, answer, clause,
  outcome (the signed conclusion, else the suggestion of the answers so far, marked not signed), and its report.

Read only, open to every signed-in member like the guides and the assessments it reads. A tree points to a
conclusion; a person confirms or overrides it and signs. MDARIX never decides and never submits.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.authority_reports import forms
from backend.app.business_ids import complaint_ref
from backend.app.complaint_review.service import people
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.authority_reports import ReportObligation
from backend.app.db.models.foundation import Complaint
from backend.app.db.models.guides_communications import DecisionGuideVersion
from backend.app.db.models.market_assessment import ComplaintMarketAssessment
from backend.app.db.session import get_db
from backend.app.decision_guides import rules
from backend.app.decision_guides import router as guides
from backend.app.decision_guides import service
from backend.app.reportability import assessments, markets
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.standards import STARTER_MARK

router = APIRouter(prefix="/api/v1/decision-trees", tags=["Decision trees"])

COMPLAINTS_MAX = 200
NEVER_DECIDES = (
    "Each tree points to a conclusion from the answers; a person confirms or overrides it with a reason, and signs. A "
    "reportable conclusion creates the market's report."
)


def _tree(market: str, row: DecisionGuideVersion | None, names: dict) -> dict:
    """A market's tree from the guide version in use: an approved version of the organization, else the starter."""
    view = guides.version_view(None, row, names) if row is not None else guides._starter_view(market, False)
    results = view["test_results"] or {}
    passed, failed = results.get("passed", 0), results.get("failed", 0)
    approved = row is not None
    return {
        "market": market,
        "label": markets.MARKET_LABELS[market],
        "title": view["title"],
        "code": view["code"],
        "version": view["version"],
        "status": "APPROVED" if approved else "STARTER",
        "status_label": "Approved" if approved else "Starter",
        "version_label": (
            f"Your version {view['version']} · approved {row.approved_at.day} {row.approved_at:%b %Y}"
            if approved and row.approved_at
            else f"Your version {view['version']}"
            if approved
            else "MDARIX starter · version 1, for your consultant to confirm"
        ),
        "tests": {"passed": passed, "total": passed + failed, "current": bool(results.get("current"))},
        "questions": [
            {"id": item["id"], "text": item["text"], "clause": item["clause"], "extra": item["extra"]}
            for item in view["question_set"]["questions"]
        ],
        # The report a reportable outcome creates (0.10.76: EU / NI, Great Britain and Canada join, as starters).
        "form": (
            {"title": forms.BY_MARKET[market].title, "starter": forms.BY_MARKET[market].starter}
            if market in forms.BY_MARKET
            else None
        ),
    }


def _path(db, tenant_id, market: str, versions: list, names: dict, reports: dict) -> dict:
    """The path one complaint took in one market: each question with its answer and clause, then the outcome."""
    current, draft = assessments.current_and_draft(versions)
    row = current or draft
    question_set = service.by_code(db, tenant_id, market, row.question_set)
    answers = row.answers or {}
    folded = markets.not_asked(market, answers)
    nodes = [
        {
            "id": question.id,
            "text": question.text,
            "clause": question.clause,
            "extra": question.extra,
            "answer": (answers.get(question.id) or {}).get("answer"),
            "answer_label": markets.ANSWER_LABELS.get((answers.get(question.id) or {}).get("answer"), "Not answered"),
            "not_asked": folded.get(question.id),
        }
        for question in question_set.questions
    ]
    signed = current is not None and current is row
    code = row.conclusion if signed else markets.evaluate(market, answers)["suggested"]
    kind = markets.REPORT_TYPES.get((row.report_type if signed else None) or "")
    report = reports.get(market)
    return {
        "market": market,
        "label": markets.MARKET_LABELS[market],
        "question_set": row.question_set,
        "nodes": nodes,
        "outcome": {
            "code": code,
            "label": markets.CONCLUSION_LABELS.get(code, code),
            "signed": signed,
            "report_type_label": kind.label if kind else None,
            "due_on": row.due_on.isoformat() if signed and row.due_on else None,
            "signed_by": (names.get(row.signed_by) or "A colleague") if signed and row.signed_by else None,
            "signed_at": row.signed_at.isoformat() if signed and row.signed_at else None,
            "version": row.version,
        },
        "report": {"id": str(report.id), "state": report.state} if report is not None else None,
        "has_form": market in forms.BY_MARKET,
    }


@router.get("")
def decision_trees(
    complaint_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from backend.app.reportability import service as reporting

    tenant_id = uuid.UUID(ctx.tenant_id)
    enabled = markets.enabled_markets(reporting.settings_of(db, tenant_id)["windows"])
    published = {
        row.market: row
        for row in db.query(DecisionGuideVersion).filter(
            DecisionGuideVersion.tenant_id == tenant_id, DecisionGuideVersion.state == rules.PUBLISHED
        )
    }
    rows = (
        db.query(ComplaintMarketAssessment)
        .filter(ComplaintMarketAssessment.tenant_id == tenant_id)
        .order_by(ComplaintMarketAssessment.version)
        .all()
    )
    by_complaint: dict = {}
    for row in rows:
        by_complaint.setdefault(row.complaint_id, {}).setdefault(row.market, []).append(row)
    complaints = {
        row.id: row
        for row in (
            db.query(Complaint).filter(Complaint.tenant_id == tenant_id, Complaint.id.in_(list(by_complaint))).all()
            if by_complaint
            else []
        )
    }
    walked = []
    for key, by_market in by_complaint.items():
        complaint = complaints.get(key)
        if complaint is None:
            continue
        signed = {market for market, versions in by_market.items() if assessments.current_and_draft(versions)[0]}
        latest = max(row.updated_at for versions in by_market.values() for row in versions)
        walked.append(
            (
                not signed,
                -latest.timestamp(),
                {
                    "id": str(complaint.id),
                    "ref": complaint_ref(complaint),
                    "description": complaint.description,
                    "markets": [market for market in markets.MARKETS if market in by_market],
                    "signed": [market for market in markets.MARKETS if market in signed],
                },
            )
        )
    walked.sort(key=lambda item: item[:2])
    # 0.10.83 (D2): the tree is where a complaint is answered, so the complaints still to assess come too, after the
    # walked ones: the watch's open ones, most urgent first.
    known = {item[2]["id"] for item in walked}
    waiting = [
        {
            "id": item["id"],
            "ref": complaint_ref(item),
            "description": item.get("description"),
            "markets": [],
            "signed": [],
        }
        for item in reporting.watch(db, control_db, tenant_id, show="open", page_size=COMPLAINTS_MAX)["items"]
        if item["id"] not in known
    ]
    ordered = [item[2] for item in walked] + waiting
    # Every market's tree (0.10.76): one not in the organization's reporting windows says so ("enabled").
    shown = list(markets.MARKETS)
    names = people(control_db, tenant_id, [row.approved_by for row in published.values() if row.approved_by])
    out = {
        "markets": [{**_tree(market, published.get(market), names), "enabled": market in enabled} for market in shown],
        "complaints": ordered[:COMPLAINTS_MAX],
        "complaint": None,
        "paths": {},
        "never_decides": NEVER_DECIDES,
        "starter_mark": STARTER_MARK,
    }
    if complaint_id is not None:
        complaint = complaints.get(complaint_id) or (
            db.query(Complaint).filter(Complaint.tenant_id == tenant_id, Complaint.id == complaint_id).one_or_none()
        )
        if complaint is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "COMPLAINT_NOT_FOUND", "message": "No such complaint in your organization"},
            )
        by_market = by_complaint.get(complaint.id, {})
        reports = {
            row.market: row
            for row in db.query(ReportObligation).filter(
                ReportObligation.tenant_id == tenant_id,
                ReportObligation.complaint_id == complaint.id,
                ReportObligation.kind == "INITIAL",
            )
        }
        signers = people(
            control_db, tenant_id, [row.signed_by for v in by_market.values() for row in v if row.signed_by]
        )
        out["complaint"] = {
            "id": str(complaint.id),
            "ref": complaint_ref(complaint),
            "description": complaint.description,
        }
        out["paths"] = {
            market: _path(db, tenant_id, market, versions, signers, reports) for market, versions in by_market.items()
        }
    return out
