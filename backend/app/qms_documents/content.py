"""The data sections of the ready-to-use documents, filled from the organization's records (T-G35.2-.5; the management
review report, T-G35.1, extends the readiness summary in backend/app/readiness_home/summary.py).

A document is a list of sections. A data section holds rows: a statement or a figure, with the records it comes from
(``sources``: type, id, the ID people read, and the case a record belongs to), so the screen links each row to its
records and the PDF prints their IDs. A judgement section is only its title and prompt: a person writes it, MDARIX
never does. Nothing here names a patient or a reporter: complaints appear by their IDs, product and codes, never by
their free text.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import date

from sqlalchemy.orm import Session

from backend.app.db.models.decision_outcomes import DecisionFollowUp
from backend.app.db.models.foundation import (
    Capa,
    Change,
    Complaint,
    Decision,
    Evidence,
    Hypothesis,
    HypothesisEvidence,
    Investigation,
    InvestigationComplaint,
    InvestigationEvidence,
    LotBatch,
    Product,
    ProductComponent,
    ProductVersion,
    RealityRelationship,
    Risk,
    SignedApprovalRecord,
)
from backend.app.db.models.market_assessment import ComplaintMarketAssessment
from backend.app.db.models.reviews import CaseReview
from backend.app.qms_documents.templates import TEMPLATES

# The records a row cites, at most (the row says how many more); the PDF's source list repeats every one cited.
SOURCES_MAX = 60


def src(kind: str, record_id, ref: str | None, case=None) -> dict:
    found = {
        "type": kind,
        "id": str(record_id) if record_id else None,
        "ref": ref or (str(record_id) if record_id else ""),
    }
    if case:
        found["case"] = str(case)
    return found


def row(text: str, sources: list[dict] | None = None) -> dict:
    sources = sources or []
    found = {"text": text, "sources": sources[:SOURCES_MAX]}
    if len(sources) > SOURCES_MAX:
        found["more"] = len(sources) - SOURCES_MAX
    return found


def data(key: str, title: str, rows: list[dict], note: str | None = None) -> dict:
    section = {"key": key, "title": title, "kind": "data", "rows": rows}
    if note:
        section["note"] = note
    return section


def judgement(code: str, key: str) -> dict:
    item = next(item for item in TEMPLATES[code].judgements if item.key == key)
    return {"key": item.key, "title": item.title, "kind": "judgement", "prompt": item.prompt}


def plural(count: int, noun: str, many: str | None = None) -> str:
    return f"{count:,} {noun if count == 1 else (many or noun + 's')}"


def label(code: str | None) -> str:
    return str(code or "not recorded").replace("_", " ").lower()


def day(value) -> str | None:
    if value is None:
        return None
    return (value.date() if hasattr(value, "date") else value).isoformat()


def complaint_ref(row) -> str:
    return row.business_id or row.complaint_identifier


def _people(control_db, tenant_id, refs) -> dict[str, str]:
    from backend.app.complaint_review.service import people

    return people(control_db, tenant_id, refs)


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------------------------------------- the CAPA log


def capa_log(db: Session, tenant_id: uuid.UUID, *, control_db=None, today: date, **_) -> dict:
    """Every imported CAPA: QMS ID, the complaints and cases it came from, status, due date and effectiveness (in the
    trial, MDARIX's effectiveness check; T-G35.2)."""
    from backend.app.capa_effectiveness import rules as check_rules
    from backend.app.capa_effectiveness.service import current_checks

    capas = (
        db.query(Capa, Investigation.business_id, Investigation.investigation_identifier)
        .outerjoin(
            Investigation, (Investigation.tenant_id == Capa.tenant_id) & (Investigation.id == Capa.investigation_id)
        )
        .filter(Capa.tenant_id == tenant_id)
        .order_by(Capa.capa_identifier)
        .all()
    )
    checks = current_checks(db, tenant_id, [capa.id for capa, _, _ in capas])
    case_ids = [capa.investigation_id for capa, _, _ in capas if capa.investigation_id]
    complaints = defaultdict(list)
    if case_ids:
        for link, ref, identifier in (
            db.query(InvestigationComplaint.investigation_id, Complaint.business_id, Complaint.complaint_identifier)
            .join(
                Complaint,
                (Complaint.tenant_id == InvestigationComplaint.tenant_id)
                & (Complaint.id == InvestigationComplaint.complaint_id),
            )
            .filter(
                InvestigationComplaint.tenant_id == tenant_id, InvestigationComplaint.investigation_id.in_(case_ids)
            )
            .order_by(Complaint.complaint_identifier)
        ):
            complaints[link].append(ref or identifier)
    rows = []
    states = Counter()
    for capa, case_ref, case_identifier in capas:
        check = checks.get(capa.id)
        planned = check.planned_on if check is not None else day(capa.effectiveness_check_at)
        state = check_rules.state_of(check.status if check else None, _date(planned), today)
        states[state] += 1
        effectiveness = {
            check_rules.EFFECTIVE: f"signed effective on {day(check.signed_at) if check else ''}",
            check_rules.NOT_EFFECTIVE: f"signed not effective on {day(check.signed_at) if check else ''}",
            check_rules.OVERDUE: f"check overdue since {_date(planned)}",
            check_rules.DUE_SOON: f"check due on {_date(planned)}",
            check_rules.SCHEDULED: f"check planned for {_date(planned)}",
            check_rules.NOT_PLANNED: "no effectiveness check planned",
        }.get(state, label(state))
        came_from = []
        if capa.investigation_id:
            came_from.append(f"case {case_ref or case_identifier}")
            linked = complaints.get(capa.investigation_id) or []
            if linked:
                came_from.append(
                    f"complaints {', '.join(linked[:8])}" + (f" and {len(linked) - 8} more" if len(linked) > 8 else "")
                )
        elif capa.source_reference:
            came_from.append(f"{label(capa.source_type)} {capa.source_reference}")
        sources = [src("Capa", capa.id, capa.business_id or capa.capa_identifier)]
        if capa.investigation_id:
            sources.append(src("Case", capa.investigation_id, case_ref or case_identifier, capa.investigation_id))
        rows.append(
            row(
                f"{capa.capa_identifier}: {capa.title}. From {'; '.join(came_from) or 'no source recorded'}. "
                f"Status {label(capa.status)}; due {day(capa.due_at) or 'not recorded'}; effectiveness: {effectiveness}.",
                sources,
            )
        )
    summary = row(
        f"{plural(len(capas), 'CAPA')} imported: {states.get(check_rules.EFFECTIVE, 0)} signed effective, "
        f"{states.get(check_rules.NOT_EFFECTIVE, 0)} signed not effective, {states.get(check_rules.OVERDUE, 0)} with the "
        f"check overdue, {states.get(check_rules.NOT_PLANNED, 0)} with no check planned.",
        [src("Capa", capa.id, capa.business_id or capa.capa_identifier) for capa, _, _ in capas],
    )
    return {
        "sections": [
            data("SUMMARY", "Summary", [summary]),
            data(
                "CAPAS",
                "CAPAs",
                rows or [row("No CAPA is imported yet.")],
                note="CAPAs as imported from your QMS; the effectiveness is the check signed in MDARIX.",
            ),
        ]
    }


def _date(value) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


# ------------------------------------------------------------------------------------------ the investigation report


def case_of(db: Session, tenant_id: uuid.UUID, case_id) -> Investigation | None:
    key = _uuid(case_id)
    if key is None:
        return None
    return db.query(Investigation).filter(Investigation.tenant_id == tenant_id, Investigation.id == key).first()


def case_ref(case: Investigation) -> str:
    """ "SAMPLE-INV-001 (INV000001)": the case's own identifier and the ID MDARIX gave it."""
    if case.business_id and case.investigation_identifier and case.business_id != case.investigation_identifier:
        return f"{case.investigation_identifier} ({case.business_id})"
    return case.business_id or case.investigation_identifier


def _refs(db: Session, model, tenant_id, ids, *fields) -> dict[str, str]:
    keys = [key for key in (_uuid(value) for value in ids) if key]
    if not keys:
        return {}
    return {
        str(found.id): next((getattr(found, field) for field in fields if getattr(found, field)), str(found.id))
        for found in db.query(model.id, *(getattr(model, field) for field in fields)).filter(
            model.tenant_id == tenant_id, model.id.in_(keys)
        )
    }


def _current_decision(db: Session, tenant_id, case_id) -> Decision | None:
    return (
        db.query(Decision)
        .filter(
            Decision.tenant_id == tenant_id,
            Decision.investigation_id == case_id,
            Decision.decision_kind == "BRIEF",
            Decision.superseded_by_decision_id.is_(None),
        )
        .order_by(Decision.created_at.desc())
        .first()
    )


def investigation_report(db: Session, tenant_id: uuid.UUID, *, case: Investigation, control_db=None, **_) -> dict:
    """One case (T-G35.3): scope by version, evidence, hypotheses with their support states, the root cause as
    recorded in the decision, its attribution and the signed decision; the root-cause category is written by the
    manufacturer."""
    from backend.app.case_workflow import scope as case_scope
    from backend.app.complaint_disposition.rules import ATTRIBUTION_LABELS
    from backend.app.human_decision.rules import outcome_label

    ref = case_ref(case)
    product = db.query(Product).filter(Product.tenant_id == tenant_id, Product.id == case.product_id).first()
    versions = list(reversed(case_scope.versions_of(db, tenant_id, case.id)))
    every_complaint = {
        item for version in versions for item in case_scope.as_data(version)["included_complaint_ids"]
    } | {item["complaint_id"] for version in versions for item in case_scope.as_data(version)["excluded_complaints"]}
    linked = [
        str(value)
        for (value,) in db.query(InvestigationComplaint.complaint_id).filter(
            InvestigationComplaint.tenant_id == tenant_id, InvestigationComplaint.investigation_id == case.id
        )
    ]
    complaint_refs = _refs(
        db, Complaint, tenant_id, every_complaint | set(linked), "business_id", "complaint_identifier"
    )
    lot_ids = {item for version in versions for item in case_scope.as_data(version)["lot_ids"]}
    version_ids = {item for version in versions for item in case_scope.as_data(version)["product_version_ids"]}
    lot_refs = _refs(db, LotBatch, tenant_id, lot_ids, "lot_identifier")
    version_refs = _refs(db, ProductVersion, tenant_id, version_ids, "version_identifier")

    def complaints_of(ids) -> list[dict]:
        return [src("Complaint", item, complaint_refs.get(item), case.id) for item in ids]

    scope_rows = [
        row(
            f"Case {ref} on {product.name if product else 'its product'}: {plural(len(linked), 'complaint')} in scope now.",
            [src("Case", case.id, ref, case.id), *complaints_of(linked)],
        )
    ]
    for version in versions:
        found = case_scope.as_data(version)
        parts = [
            plural(len(found["included_complaint_ids"]), "complaint") + " included",
            plural(len(found["excluded_complaints"]), "complaint") + " excluded",
        ]
        if found["product_version_ids"]:
            parts.append("versions " + ", ".join(version_refs.get(item, item) for item in found["product_version_ids"]))
        if found["lot_ids"]:
            parts.append("lots " + ", ".join(lot_refs.get(item, item) for item in found["lot_ids"]))
        if found["markets"]:
            parts.append("markets " + ", ".join(found["markets"]))
        if found["date_from"] or found["date_to"]:
            parts.append(f"from {day(found['date_from']) or 'the start'} to {day(found['date_to']) or 'now'}")
        excluded = [
            f"{complaint_refs.get(item['complaint_id'], item['complaint_id'])} ({item['reason']})"
            for item in found["excluded_complaints"]
        ]
        text = f"Scope version {found['version']}: " + "; ".join(parts) + "."
        if excluded:
            text += " Excluded: " + "; ".join(excluded) + "."
        if found["change_reason"]:
            text += f" Why it changed: {found['change_reason']}"
        scope_rows.append(
            row(
                text,
                complaints_of(
                    [*found["included_complaint_ids"], *(item["complaint_id"] for item in found["excluded_complaints"])]
                ),
            )
        )

    linked_evidence = db.query(InvestigationEvidence.evidence_id).filter(
        InvestigationEvidence.tenant_id == tenant_id, InvestigationEvidence.investigation_id == case.id
    )
    evidence = (
        db.query(Evidence)
        .filter(
            Evidence.tenant_id == tenant_id,
            (Evidence.investigation_id == case.id) | Evidence.id.in_(linked_evidence),
        )
        .order_by(Evidence.evidence_identifier)
        .all()
    )
    evidence_rows = [
        row(
            f"{item.evidence_identifier}: {item.title or label(item.evidence_type)} ({label(item.evidence_type)}; "
            f"reliability {label(item.reliability_status)}).",
            [src("Evidence", item.id, item.business_id or item.evidence_identifier, case.id)],
        )
        for item in evidence
    ]
    hypotheses = (
        db.query(Hypothesis)
        .filter(Hypothesis.tenant_id == tenant_id, Hypothesis.investigation_id == case.id)
        .order_by(Hypothesis.created_at)
        .all()
    )
    relations = defaultdict(Counter)
    if hypotheses:
        for hypothesis_id, relation in db.query(
            HypothesisEvidence.hypothesis_id, HypothesisEvidence.relation_type
        ).filter(
            HypothesisEvidence.tenant_id == tenant_id,
            HypothesisEvidence.hypothesis_id.in_([item.id for item in hypotheses]),
            HypothesisEvidence.retracted_at.is_(None),
        ):
            relations[hypothesis_id][str(relation).lower()] += 1
    hypothesis_rows = [
        row(
            f"{item.business_id}: {item.statement} Support state: {label(item.status)}"
            + (f", reviewer {label(item.reviewer_disposition)}" if item.reviewer_disposition else "")
            + f"; {relations[item.id].get('support', 0)} supporting and {relations[item.id].get('contradict', 0)} "
            "contradicting evidence links.",
            [src("Hypothesis", item.id, item.business_id, case.id)],
        )
        for item in hypotheses
    ]

    decision = _current_decision(db, tenant_id, case.id)
    record = None
    if decision is not None and control_db is not None:
        record = (
            control_db.query(SignedApprovalRecord)
            .filter(
                SignedApprovalRecord.tenant_id == tenant_id,
                SignedApprovalRecord.object_type == "Decision",
                SignedApprovalRecord.object_id == decision.id,
                SignedApprovalRecord.status == "SIGNED",
            )
            .order_by(SignedApprovalRecord.signed_at.desc())
            .first()
        )
    if decision is None:
        decision_rows = [row("No decision is signed on this case yet.", [src("Case", case.id, ref, case.id)])]
        attribution_rows = [row("No root-cause attribution yet: it is recorded with the signed decision.")]
    else:
        decision_ref = decision.business_id or decision.decision_identifier
        decision_source = [src("Decision", decision.id, decision_ref, case.id)]
        decision_rows = [
            row(
                f"Root cause as recorded in decision {decision_ref} ({outcome_label(decision.outcome) or label(decision.outcome)}): "
                f"{decision.rationale}",
                decision_source,
            )
        ]
        attribution = decision.root_cause_attribution
        attribution_rows = [
            row(
                f"Root-cause attribution: {ATTRIBUTION_LABELS.get(attribution, label(attribution)).lower()}"
                + (f" ({decision.attribution_reason})" if decision.attribution_reason else "")
                + "."
                if attribution
                else "Recorded before root-cause attribution: none on this decision.",
                decision_source,
            )
        ]
        if record is not None:
            signer = _people(control_db, tenant_id, [record.signer_user_id]).get(record.signer_user_id, "A colleague")
            decision_rows.append(
                row(
                    f"Signed decision: record {record.business_id}, signed by {signer} ({label(record.signer_role)}) on "
                    f"{record.signed_at.isoformat(timespec='minutes')}; meaning: {record.signature_meaning.rstrip('. ')}. "
                    f"Fingerprint (SHA-256): {record.content_fingerprint}.",
                    [*decision_source, src("Signature", record.id, record.business_id, case.id)],
                )
            )
        else:
            decision_rows.append(
                row(f"Decision {decision_ref} is {label(decision.decision_status)}; not signed yet.", decision_source)
            )
    return {
        "scope": {"case": {"id": str(case.id), "ref": ref, "question": case.investigation_question}},
        "sections": [
            data("SCOPE", "Scope", scope_rows),
            data("EVIDENCE", "Evidence", evidence_rows or [row("No evidence is linked to the case yet.")]),
            data("HYPOTHESES", "Hypotheses and their support states", hypothesis_rows or [row("No hypothesis yet.")]),
            data("ROOT_CAUSE", "Root cause and the signed decision", decision_rows),
            data("ATTRIBUTION", "Root-cause attribution", attribution_rows),
            judgement("INVESTIGATION_REPORT", "ROOT_CAUSE_CATEGORY"),
        ],
    }


# ---------------------------------------------------------------------------------------- the risk-review extract


def risk_reviews(db: Session, tenant_id: uuid.UUID, case_ids=None, begin=None, end=None) -> list[CaseReview]:
    query = db.query(CaseReview).filter(CaseReview.tenant_id == tenant_id, CaseReview.review_type == "RISK")
    if case_ids is not None:
        query = query.filter(CaseReview.investigation_id.in_(list(case_ids) or [uuid.uuid4()]))
    if begin is not None:
        query = query.filter(CaseReview.completed_at >= begin, CaseReview.completed_at < end)
    return query.order_by(CaseReview.created_at).all()


def finding_rows(db: Session, tenant_id, reviews: list[CaseReview], control_db=None) -> tuple[list[dict], list[dict]]:
    """Each finding's risk-control answer, and each risk file update required (T-G1aR), as rows: the answers to "did
    the risk control work?" and the updates with their owner and due date."""
    from backend.app.case_reviews.rules import CONTROL_LABELS

    risk_ids = {
        key
        for review in reviews
        for key, item in ((review.assessed or {}).get("findings") or {}).items()
        if item.get("risk_id")
    }
    risks = {
        str(item.id): item
        for item in db.query(Risk).filter(
            Risk.tenant_id == tenant_id, Risk.id.in_([_uuid(k) for k in risk_ids if _uuid(k)] or [uuid.uuid4()])
        )
    }
    owners = _people(
        control_db,
        tenant_id,
        [
            (item.get("risk_file_update") or {}).get("owner_user_id")
            for review in reviews
            for item in ((review.assessed or {}).get("findings") or {}).values()
        ],
    )
    answers, updates = [], []
    for review in reviews:
        for key, item in ((review.assessed or {}).get("findings") or {}).items():
            review_source = src("CaseReview", review.id, review.business_id, review.investigation_id)
            if item.get("kind") == "IN_RISK_FILE":
                risk = risks.get(str(item.get("risk_id")))
                name = f"{risk.risk_identifier} ({risk.description})" if risk else str(item.get("risk_id"))
                sources = [review_source] + (
                    [src("Risk", risk.id, risk.business_id or risk.risk_identifier)] if risk else []
                )
                answers.append(
                    row(
                        f"{name}: did its risk control work? {CONTROL_LABELS.get(item.get('control_worked'), label(item.get('control_worked')))}. "
                        f"Reason: {item.get('reason')}",
                        sources,
                    )
                )
                subject = f"{risk.risk_identifier if risk else 'the risk'}: risk control to be reassessed"
            else:
                sources = [review_source]
                subject = f"not in the risk file: {item.get('description')}"
            update = item.get("risk_file_update")
            if update:
                updates.append(
                    row(
                        f"Risk file update required ({subject}); owner {owners.get(update.get('owner_user_id'), 'a colleague')}, "
                        f"due {update.get('due_on')}"
                        + (f", QMS reference {update['qms_reference']}" if update.get("qms_reference") else "")
                        + f" (review {review.business_id}"
                        + (f", finding {key})." if key.startswith("NEW-") else ")."),
                        sources,
                    )
                )
    return answers, updates


def risk_review_extract(
    db: Session, tenant_id: uuid.UUID, *, case: Investigation, control_db=None, today: date, **_
) -> dict:
    """One case's risk reviews (T-G35.4): the risk-register entries named, each risk-control answer and risk file update,
    post-market data against the risk file for the case's product, the impact decisions with their owners and states,
    and the signed closure; the conclusion is written by the manufacturer."""
    from backend.app.case_reviews.rules import outcome_label as review_outcome
    from backend.app.post_market import risk_file

    ref = case_ref(case)
    reviews = risk_reviews(db, tenant_id, [case.id])
    names = _people(
        control_db, tenant_id, [str(review.reviewer_user_id) for review in reviews if review.reviewer_user_id]
    )
    review_rows = [
        row(
            f"Risk review {review.business_id}: {label(review.status)}"
            + (f", outcome {review_outcome(review.outcome).lower()}" if review.outcome else "")
            + (f", completed on {day(review.completed_at)}" if review.completed_at else "")
            + (f" by {names.get(str(review.reviewer_user_id), 'a colleague')}" if review.reviewer_user_id else "")
            + (f". {review.rationale}" if review.rationale else "."),
            [src("CaseReview", review.id, review.business_id, case.id)],
        )
        for review in reviews
    ]
    named = sorted({str(key) for review in reviews for key in ((review.assessed or {}).get("risk_ids") or [])})
    risks = (
        db.query(Risk)
        .filter(Risk.tenant_id == tenant_id, Risk.id.in_([_uuid(k) for k in named if _uuid(k)]))
        .order_by(Risk.risk_identifier)
        .all()
        if named
        else []
    )
    risk_rows = [
        row(
            f"{risk.risk_identifier}: {risk.description} ({label(risk.status)}).",
            [src("Risk", risk.id, risk.business_id or risk.risk_identifier)],
        )
        for risk in risks
    ]
    answers, updates = finding_rows(db, tenant_id, reviews, control_db)
    detail = risk_file.detail(db, tenant_id, case.product_id, today=today) if case.product_id else None
    post_market = []
    if detail is not None:
        pm, rf = detail["post_market"], detail["risk_file"]
        post_market.append(
            row(
                f"{detail['product']['name']}, last {detail['period']['days']} days: {plural(pm['complaints'], 'complaint')} "
                f"({pm['harm']} with harm, {pm['malfunction']} malfunctions), {plural(pm['signals_raised'], 'signal')} raised; "
                f"{rf['risks_assessed']} of {plural(rf['risks'], 'risk')} assessed in {plural(rf['risk_reviews'], 'risk review')}; "
                f"{detail['label'].lower()}.",
                [
                    src(
                        "Product",
                        detail["product"]["id"],
                        detail["product"]["business_id"] or detail["product"]["name"],
                    )
                ],
            )
        )
    follow_ups = (
        db.query(DecisionFollowUp)
        .filter(DecisionFollowUp.tenant_id == tenant_id, DecisionFollowUp.investigation_id == case.id)
        .order_by(DecisionFollowUp.created_at)
        .all()
    )
    owners = _people(
        control_db, tenant_id, [str(item.assignee_user_id) for item in follow_ups if item.assignee_user_id]
    )
    impact_rows = [
        row(
            f"{item.business_id}: {item.title} ({label(item.action_type)}); owner "
            f"{owners.get(str(item.assignee_user_id)) or label(item.assigned_role) if (item.assignee_user_id or item.assigned_role) else 'not named'}; "
            f"{label(item.status)}" + (f", due {day(item.due_at)}" if item.due_at else "") + ".",
            [src("FollowUp", item.id, item.business_id, case.id)],
        )
        for item in follow_ups
    ]
    closure = [
        row(
            f"Risk review {review.business_id} completed on {day(review.completed_at)} by "
            f"{names.get(str(review.reviewer_user_id), 'a colleague')}.",
            [src("CaseReview", review.id, review.business_id, case.id)],
        )
        for review in reviews
        if review.status == "COMPLETED"
    ]
    return {
        "scope": {"case": {"id": str(case.id), "ref": ref, "question": case.investigation_question}},
        "sections": [
            data(
                "REVIEWS",
                f"Risk reviews of case {ref}",
                review_rows or [row("No risk review on this case yet.", [src("Case", case.id, ref, case.id)])],
            ),
            data("RISKS", "Risk-register entries named", risk_rows or [row("No risk-register entry named yet.")]),
            data(
                "CONTROL_ANSWERS",
                "Did each risk control work?",
                answers or [row("No risk-control answer recorded yet.")],
            ),
            data("RISK_FILE_UPDATES", "Risk file updates required", updates or [row("No risk file update required.")]),
            data(
                "POST_MARKET", "Post-market data against the risk file", post_market or [row("No product on the case.")]
            ),
            data("IMPACT_DECISIONS", "Impact decisions", impact_rows or [row("No impact decision recorded yet.")]),
            data("CLOSURE", "Closure", closure or [row("No risk review completed yet.")]),
            judgement("RISK_REVIEW_EXTRACT", "CONCLUSION"),
        ],
    }


# ---------------------------------------------------------------------------------------- the change-impact input


def change_of(db: Session, tenant_id: uuid.UUID, change_id) -> Change | None:
    key = _uuid(change_id)
    if key is None:
        return None
    return db.query(Change).filter(Change.tenant_id == tenant_id, Change.id == key).first()


def affected_versions(db: Session, tenant_id: uuid.UUID, change: Change) -> list[uuid.UUID]:
    """The product versions a change record affects: named directly, or through a component it affects."""
    links = db.query(RealityRelationship.target_entity_type, RealityRelationship.target_entity_id).filter(
        RealityRelationship.tenant_id == tenant_id,
        RealityRelationship.source_entity_type == "Change",
        RealityRelationship.source_entity_id == change.id,
    )
    found: list[uuid.UUID] = []
    for kind, target in links:
        if kind == "ProductVersion":
            found.append(target)
        elif kind == "Product":
            found += [
                item
                for (item,) in db.query(ProductVersion.id).filter(
                    ProductVersion.tenant_id == tenant_id, ProductVersion.product_id == target
                )
            ]
        elif kind == "Component":
            found += [
                item
                for (item,) in db.query(ProductComponent.product_version_id).filter(
                    ProductComponent.tenant_id == tenant_id, ProductComponent.component_id == target
                )
            ]
        elif kind == "LotBatch":
            found += [
                item
                for (item,) in db.query(LotBatch.product_version_id).filter(
                    LotBatch.tenant_id == tenant_id, LotBatch.id == target
                )
                if item
            ]
    return list(dict.fromkeys(found))


def change_impact(db: Session, tenant_id: uuid.UUID, *, change: Change, control_db=None, **_) -> dict:
    """For one change record (T-G35.5): the affected products and lots, the risk and PMS impacts recorded in risk
    reviews and impact decisions, and the complaints whose market assessments may need review."""
    ref = change.change_identifier
    version_ids = affected_versions(db, tenant_id, change)
    versions = (
        db.query(ProductVersion, Product)
        .join(Product, (Product.tenant_id == ProductVersion.tenant_id) & (Product.id == ProductVersion.product_id))
        .filter(ProductVersion.tenant_id == tenant_id, ProductVersion.id.in_(version_ids or [uuid.uuid4()]))
        .order_by(Product.name, ProductVersion.version_identifier)
        .all()
    )
    lots = (
        db.query(LotBatch)
        .filter(LotBatch.tenant_id == tenant_id, LotBatch.product_version_id.in_(version_ids or [uuid.uuid4()]))
        .order_by(LotBatch.lot_identifier)
        .all()
    )
    complaints = (
        db.query(Complaint)
        .filter(Complaint.tenant_id == tenant_id, Complaint.product_version_id.in_(version_ids or [uuid.uuid4()]))
        .order_by(Complaint.complaint_identifier)
        .all()
    )
    with_complaints = Counter(item.lot_batch_id for item in complaints if item.lot_batch_id)
    affected_rows = [
        row(
            f"{product.name} {version.version_identifier}.",
            [src("Product", product.id, product.business_id or product.name)],
        )
        for version, product in versions
    ]
    lot_rows = [
        row(
            f"{lot.lot_identifier}: {plural(with_complaints.get(lot.id, 0), 'complaint')} on it"
            + (f"; quantity {lot.quantity:,}" if lot.quantity else "")
            + ".",
            [src("Lot", lot.id, lot.business_id or lot.lot_identifier)]
            + [src("Complaint", item.id, complaint_ref(item)) for item in complaints if item.lot_batch_id == lot.id],
        )
        for lot in lots
    ]
    case_ids = {
        case_id
        for (case_id,) in db.query(InvestigationComplaint.investigation_id).filter(
            InvestigationComplaint.tenant_id == tenant_id,
            InvestigationComplaint.complaint_id.in_([item.id for item in complaints] or [uuid.uuid4()]),
        )
    }
    reviews = risk_reviews(db, tenant_id, case_ids)
    answers, updates = finding_rows(db, tenant_id, reviews, control_db)
    follow_ups = (
        db.query(DecisionFollowUp, Investigation.business_id)
        .join(
            Investigation,
            (Investigation.tenant_id == DecisionFollowUp.tenant_id)
            & (Investigation.id == DecisionFollowUp.investigation_id),
        )
        .filter(
            DecisionFollowUp.tenant_id == tenant_id,
            DecisionFollowUp.investigation_id.in_(list(case_ids) or [uuid.uuid4()]),
        )
        .order_by(DecisionFollowUp.created_at)
        .all()
    )
    impact_rows = [
        *answers,
        *updates,
        *(
            row(
                f"{item.business_id} on case {case}: {item.title} ({label(item.action_type)}; {label(item.status)}).",
                [src("FollowUp", item.id, item.business_id, item.investigation_id)],
            )
            for item, case in follow_ups
        ),
    ]
    assessed = (
        db.query(
            ComplaintMarketAssessment.complaint_id,
            ComplaintMarketAssessment.market,
            ComplaintMarketAssessment.conclusion,
        )
        .filter(
            ComplaintMarketAssessment.tenant_id == tenant_id,
            ComplaintMarketAssessment.superseded_by.is_(None),
            ComplaintMarketAssessment.question_set != "ROUTINE-BASIS",
            ComplaintMarketAssessment.complaint_id.in_([item.id for item in complaints] or [uuid.uuid4()]),
        )
        .all()
    )
    by_complaint = defaultdict(list)
    for complaint_id, market, conclusion in assessed:
        by_complaint[complaint_id].append(f"{market} {label(conclusion) if conclusion else 'pending'}")
    # A complaint reporting a death or a serious injury needs its market assessment even before one is saved.
    for item in complaints:
        if (item.death or item.serious_injury) and item.id not in by_complaint:
            by_complaint[item.id].append("harm reported, no market assessment yet")
    refs = {item.id: complaint_ref(item) for item in complaints}
    review_rows = [
        row(
            f"{refs[complaint_id]}: {', '.join(sorted(markets))}.",
            [src("MarketAssessment", complaint_id, refs[complaint_id])],
        )
        for complaint_id, markets in sorted(by_complaint.items(), key=lambda pair: refs[pair[0]])
    ]
    return {
        "scope": {"change": {"id": str(change.id), "ref": ref, "type": change.change_type}},
        "sections": [
            data(
                "CHANGE",
                "The change record",
                [
                    row(
                        f"{ref} ({change.change_type}, {day(change.event_timestamp) or 'date not recorded'}): {change.description}",
                        [src("Change", change.id, ref)],
                    )
                ],
                note="The change itself is run in your QMS. This document is an input to its impact assessment.",
            ),
            data(
                "AFFECTED",
                "Affected products",
                affected_rows or [row("The change record names no product, version or component in MDARIX.")],
            ),
            data("LOTS", "Affected lots", lot_rows or [row("No lot of the affected versions is imported.")]),
            data(
                "IMPACTS",
                "Risk and PMS impacts recorded",
                impact_rows or [row("No risk review or impact decision on the affected products yet.")],
            ),
            data(
                "REASSESS",
                "Complaints whose market assessments may need review",
                review_rows or [row("No complaint on the affected versions has a market assessment.")],
            ),
        ],
    }
