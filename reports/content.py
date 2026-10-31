"""What each governed report contains, read from the organization's own records.

Every builder takes the tenant's data-plane session (and, when the caller has one, the control-plane session that
holds signatures and the audit trail) and returns plain data: a ``summary`` of counts, named tables (lists of rows)
and ``limitations`` that say what the records do and do not support. Nothing here infers causality or a decision;
the renderer (reports/service.py) adds the watermark, the data cut-off and the human-review notice.

Lists are bounded (``MAX_ROWS``) so a report never tries to hold a whole history in one request; when a table is cut,
``truncated`` records how many rows exist in all.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.app.business_ids import business_id_map
from backend.app.db.models.foundation import (
    AIExecution,
    AssuranceCheck,
    AssuranceResult,
    AuditEvent,
    Capa,
    Complaint,
    Decision,
    Evidence,
    FailureChain,
    HumanReview,
    Hypothesis,
    HypothesisEvidence,
    Investigation,
    InvestigationBrief,
    InvestigationComplaint,
    InvestigationEvidence,
    LotBatch,
    Product,
    ProductVersion,
    Requirement,
    Risk,
    Scenario,
    SignedApprovalRecord,
    Unknown,
)

MAX_ROWS = 1000
CLOSED_STATUSES = ("closed", "resolved", "completed", "rejected", "cancelled", "archived")
SIGNED_DECISION_STATUSES = ("APPROVED", "REJECTED")


def _iso(value) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else (str(value) if value is not None else None)


def _is_open(status) -> bool:
    return str(status or "").lower() not in CLOSED_STATUSES


def _bounded(query, order_by) -> tuple[list, int]:
    """The first MAX_ROWS rows of ``query`` and how many exist in all."""
    total = query.order_by(None).count()
    return query.order_by(order_by).limit(MAX_ROWS).all(), total


def _truncation(name: str, shown: int, total: int) -> dict:
    return {"table": name, "shown": shown, "total": total}


def _products(db: Session, tenant_id) -> dict:
    return {row.id: row for row in db.query(Product).filter(Product.tenant_id == tenant_id).all()}


def _versions(db: Session, tenant_id) -> dict:
    return {row.id: row for row in db.query(ProductVersion).filter(ProductVersion.tenant_id == tenant_id).all()}


def _investigation_labels(db: Session, tenant_id) -> dict:
    """{investigation id: (source identifier, business identifier)}, for labelling records that belong to a case."""
    return {
        row.id: (row.investigation_identifier, row.business_id)
        for row in db.query(Investigation.id, Investigation.investigation_identifier, Investigation.business_id).filter(
            Investigation.tenant_id == tenant_id
        )
    }


def _case_labels(investigations: dict, investigation_id) -> dict:
    """The ``investigation_identifier`` / ``investigation_business_id`` cells of a record's case."""
    identifier, business_id = investigations.get(investigation_id, (None, None))
    return {"investigation_identifier": identifier, "investigation_business_id": business_id}


def _count_by(db: Session, column, tenant_column, tenant_id, *filters) -> dict:
    rows = (
        db.query(column, func.count())
        .filter(tenant_column == tenant_id, column.is_not(None), *filters)
        .group_by(column)
        .all()
    )
    return {key: int(count) for key, count in rows}


def _label_counts(rows, attribute: str) -> list[dict]:
    counter = Counter(str(getattr(row, attribute) or "UNKNOWN") for row in rows)
    return [{"label": label, "count": count} for label, count in sorted(counter.items(), key=lambda kv: -kv[1])]


# --------------------------------------------------------------------------------------------- signatures / audit


def signature_verification_rows(control_db: Session, tenant_id, *, limit: int = 500, decision_ids=None) -> list[dict]:
    """Each signed approval re-verified from its stored material (the same check as the Decision Center)."""
    query = control_db.query(SignedApprovalRecord).filter(SignedApprovalRecord.tenant_id == tenant_id)
    if decision_ids is not None:
        if not decision_ids:
            return []
        query = query.filter(SignedApprovalRecord.object_id.in_(list(decision_ids)))
    rows = query.order_by(SignedApprovalRecord.signed_at.desc()).limit(limit).all()
    result = []
    for item in rows:
        material = {
            "decision_id": str(item.object_id),
            "version": item.object_version,
            "type": item.decision_type,
            "decision": item.decision,
            "remarks": item.remarks,
        }
        fingerprint = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
        expected = hashlib.sha256((fingerprint + item.signer_user_id + item.object_version).encode()).hexdigest()
        result.append(
            {
                "business_id": item.business_id,
                "signature_id": str(item.id),
                "decision_id": str(item.object_id),
                "decision": item.decision,
                "valid": fingerprint == item.content_fingerprint
                and expected == item.signature_hash
                and item.status == "SIGNED",
                "signer_user_id": item.signer_user_id,
                "signer_role": item.signer_role,
                "object_version": item.object_version,
                "signature_meaning": item.signature_meaning,
                "signed_at": _iso(item.signed_at),
                "status": item.status,
            }
        )
    return result


def with_decision_business_ids(db: Session, signatures: list[dict]) -> list[dict]:
    """``signatures`` (from ``signature_verification_rows``) with each signed decision's business identifier.

    Signatures live in the control plane and decisions in the organization's data plane, so ``db`` is the data-plane
    session; a decision it does not hold gets None."""
    known = business_id_map(db, Decision, (item["decision_id"] for item in signatures))
    return [{**item, "decision_business_id": known.get(item["decision_id"])} for item in signatures]


def audit_event_rows(db: Session, tenant_id, *, limit: int = 1000, entity_ids=None, actions=None) -> list[dict]:
    query = db.query(AuditEvent).filter(AuditEvent.tenant_id == tenant_id)
    if entity_ids is not None:
        if not entity_ids:
            return []
        query = query.filter(AuditEvent.entity_id.in_(list(entity_ids)))
    if actions:
        query = query.filter(AuditEvent.action.in_(list(actions)))
    rows = query.order_by(AuditEvent.created_at.desc()).limit(limit).all()
    return [
        {
            "id": str(row.id),
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": str(row.entity_id) if row.entity_id else None,
            "actor_ref": row.actor_ref,
            "correlation_id": row.correlation_id,
            "source_ip": row.source_ip,
            "user_agent": row.user_agent,
            "reason": row.reason,
            "details": row.details,
            "old_values": row.old_values,
            "new_values": row.new_values,
            "chain_seq": row.chain_seq,
            "event_hash": row.event_hash,
            "created_at": _iso(row.created_at),
            "retention_until": _iso(row.retention_until),
        }
        for row in rows
    ]


# --------------------------------------------------------------------------------------------- the twelve reports


def product_intelligence(db: Session, tenant_id, control_db=None) -> dict:
    products = _products(db, tenant_id)
    versions = _count_by(db, ProductVersion.product_id, ProductVersion.tenant_id, tenant_id)
    complaints = _count_by(db, Complaint.product_id, Complaint.tenant_id, tenant_id)
    open_complaints = _count_by(
        db,
        Complaint.product_id,
        Complaint.tenant_id,
        tenant_id,
        func.lower(Complaint.status).notin_(CLOSED_STATUSES),
    )
    investigations = _count_by(db, Investigation.product_id, Investigation.tenant_id, tenant_id)
    open_investigations = _count_by(
        db,
        Investigation.product_id,
        Investigation.tenant_id,
        tenant_id,
        func.lower(Investigation.status).notin_(CLOSED_STATUSES),
    )
    risks = _count_by(db, Risk.product_id, Risk.tenant_id, tenant_id, func.lower(Risk.status) != "retired")
    capas = _count_by(db, Capa.product_id, Capa.tenant_id, tenant_id, func.lower(Capa.status).notin_(CLOSED_STATUSES))
    rows = [
        {
            "business_id": product.business_id,
            "product_identifier": product.product_identifier,
            "name": product.name,
            "product_family": product.product_family,
            "lifecycle_status": product.lifecycle_status,
            "versions": versions.get(product.id, 0),
            "complaints_total": complaints.get(product.id, 0),
            "complaints_open": open_complaints.get(product.id, 0),
            "investigations_total": investigations.get(product.id, 0),
            "investigations_open": open_investigations.get(product.id, 0),
            "risks": risks.get(product.id, 0),
            "capas_open": capas.get(product.id, 0),
        }
        for product in sorted(products.values(), key=lambda row: row.product_identifier)
    ]
    return {
        "summary": {
            "products": len(rows),
            "product_versions": sum(versions.values()),
            "complaints_open": sum(open_complaints.values()),
            "investigations_open": sum(open_investigations.values()),
        },
        "products": rows,
        "limitations": ["Counts are of records in MDARIX; a product without imported complaints shows zero."],
    }


def product_version_impact(db: Session, tenant_id, control_db=None) -> dict:
    products = _products(db, tenant_id)
    versions = db.query(ProductVersion).filter(ProductVersion.tenant_id == tenant_id).all()
    complaints = _count_by(db, Complaint.product_version_id, Complaint.tenant_id, tenant_id)
    open_complaints = _count_by(
        db,
        Complaint.product_version_id,
        Complaint.tenant_id,
        tenant_id,
        func.lower(Complaint.status).notin_(CLOSED_STATUSES),
    )
    lots = _count_by(db, LotBatch.product_version_id, LotBatch.tenant_id, tenant_id)
    risks = _count_by(db, Risk.product_version_id, Risk.tenant_id, tenant_id)
    requirements = _count_by(db, Requirement.product_version_id, Requirement.tenant_id, tenant_id)
    decisions = _count_by(db, Decision.product_version_id, Decision.tenant_id, tenant_id)
    # Investigations carry no version column; a version's investigations are those linked to its complaints.
    linked = (
        db.query(Complaint.product_version_id, func.count(func.distinct(InvestigationComplaint.investigation_id)))
        .join(
            InvestigationComplaint,
            (InvestigationComplaint.complaint_id == Complaint.id) & (InvestigationComplaint.tenant_id == tenant_id),
        )
        .filter(Complaint.tenant_id == tenant_id, Complaint.product_version_id.is_not(None))
        .group_by(Complaint.product_version_id)
        .all()
    )
    investigations = {version_id: int(count) for version_id, count in linked}
    rows = []
    for version in sorted(versions, key=lambda row: (str(row.product_id), row.version_identifier)):
        product = products.get(version.product_id)
        rows.append(
            {
                "business_id": version.business_id,
                "product_business_id": product.business_id if product else None,
                "product_identifier": product.product_identifier if product else None,
                "product_name": product.name if product else None,
                "version_identifier": version.version_identifier,
                "lifecycle_status": version.lifecycle_status,
                "release_timestamp": _iso(version.release_timestamp),
                "complaints_total": complaints.get(version.id, 0),
                "complaints_open": open_complaints.get(version.id, 0),
                "investigations_via_complaints": investigations.get(version.id, 0),
                "lots": lots.get(version.id, 0),
                "risks": risks.get(version.id, 0),
                "requirements": requirements.get(version.id, 0),
                "decisions": decisions.get(version.id, 0),
            }
        )
    return {
        "summary": {
            "product_versions": len(rows),
            "versions_with_open_complaints": sum(1 for r in rows if r["complaints_open"]),
        },
        "versions": rows,
        "limitations": [
            "Investigations are attributed to a version through the complaints linked to them; MDARIX does not "
            "record a version on the investigation itself.",
            "Impact is a count of records, not an assessment of cause.",
        ],
    }


def complaint_trend(db: Session, tenant_id, control_db=None) -> dict:
    products = _products(db, tenant_id)
    rows, total = _bounded(
        db.query(Complaint).filter(Complaint.tenant_id == tenant_id),
        func.coalesce(Complaint.complaint_timestamp, Complaint.event_timestamp).desc(),
    )
    by_month: dict[str, dict] = defaultdict(lambda: {"count": 0, "serious_injury": 0, "death": 0, "malfunction": 0})
    for row in rows:
        stamp = row.complaint_timestamp or row.event_timestamp or row.created_at
        month = stamp.strftime("%Y-%m") if stamp else "undated"
        bucket = by_month[month]
        bucket["count"] += 1
        bucket["serious_injury"] += int(bool(row.serious_injury))
        bucket["death"] += int(bool(row.death))
        bucket["malfunction"] += int(bool(row.malfunction))
    by_product = Counter(
        products[row.product_id].product_identifier if row.product_id in products else "UNLINKED" for row in rows
    )
    return {
        "summary": {
            "complaints": total,
            "open": sum(1 for row in rows if _is_open(row.status)),
            "serious_injury": sum(1 for row in rows if row.serious_injury),
            "death": sum(1 for row in rows if row.death),
            "months_covered": len(by_month),
        },
        "by_month": [{"month": month, **values} for month, values in sorted(by_month.items())],
        "by_severity": _label_counts(rows, "severity"),
        "by_status": _label_counts(rows, "status"),
        "by_problem_code": _label_counts(rows, "problem_code")[:25],
        "by_country": _label_counts(rows, "country")[:25],
        "by_product": [{"label": label, "count": count} for label, count in by_product.most_common()],
        "truncated": [_truncation("complaints", len(rows), total)] if total > len(rows) else [],
        "limitations": [
            "Severity, problem code and country are shown only as the source system recorded them.",
            "A trend is a count over time; it does not establish a cause.",
        ],
    }


def signal_assessment(db: Session, tenant_id, control_db=None) -> dict:
    products = _products(db, tenant_id)
    flagged_filter = or_(
        Complaint.serious_injury.is_(True),
        Complaint.death.is_(True),
        Complaint.malfunction.is_(True),
        Complaint.patient_involved.is_(True),
    )
    rows, total = _bounded(
        db.query(Complaint).filter(Complaint.tenant_id == tenant_id, flagged_filter),
        func.coalesce(Complaint.event_timestamp, Complaint.complaint_timestamp).desc(),
    )
    investigated = {
        complaint_id
        for (complaint_id,) in db.query(InvestigationComplaint.complaint_id).filter(
            InvestigationComplaint.tenant_id == tenant_id
        )
    }
    items = []
    for row in rows:
        lag_days = None
        if row.awareness_timestamp and row.event_timestamp:
            lag_days = (row.awareness_timestamp - row.event_timestamp).days
        items.append(
            {
                "business_id": row.business_id,
                "complaint_identifier": row.complaint_identifier,
                "product_business_id": products[row.product_id].business_id if row.product_id in products else None,
                "product_identifier": products[row.product_id].product_identifier
                if row.product_id in products
                else None,
                "status": row.status,
                "severity": row.severity,
                "event_timestamp": _iso(row.event_timestamp),
                "awareness_timestamp": _iso(row.awareness_timestamp),
                "awareness_lag_days": lag_days,
                "serious_injury": bool(row.serious_injury),
                "death": bool(row.death),
                "malfunction": bool(row.malfunction),
                "patient_involved": bool(row.patient_involved),
                "device_returned": row.device_returned,
                "problem_code": row.problem_code,
                "country": row.country,
                "linked_to_investigation": row.id in investigated,
            }
        )
    return {
        "summary": {
            "flagged_complaints": total,
            "without_investigation": sum(1 for item in items if not item["linked_to_investigation"]),
            "serious_injury_or_death": sum(1 for item in items if item["serious_injury"] or item["death"]),
            "awareness_lag_over_30_days": sum(
                1 for item in items if item["awareness_lag_days"] is not None and item["awareness_lag_days"] > 30
            ),
        },
        "signals": items,
        "truncated": [_truncation("signals", len(items), total)] if total > len(items) else [],
        "limitations": [
            "A signal is a complaint the source system flagged (serious injury, death, malfunction or patient "
            "involvement); MDARIX does not infer new signals here.",
            "Reportability and causality are decided by people.",
        ],
    }


def _investigation_rows(db: Session, tenant_id, control_db=None, *, investigation_ids=None):
    query = db.query(Investigation).filter(Investigation.tenant_id == tenant_id)
    if investigation_ids is not None:
        query = query.filter(Investigation.id.in_(list(investigation_ids)))
    rows, total = _bounded(query, func.coalesce(Investigation.opened_at, Investigation.created_at).desc())
    ids = [row.id for row in rows]
    products = _products(db, tenant_id)
    if not ids:
        return rows, total, products, {}, {}, {}, {}, {}, {}
    complaints = _count_by(
        db,
        InvestigationComplaint.investigation_id,
        InvestigationComplaint.tenant_id,
        tenant_id,
        InvestigationComplaint.investigation_id.in_(ids),
    )
    direct_evidence = _count_by(
        db, Evidence.investigation_id, Evidence.tenant_id, tenant_id, Evidence.investigation_id.in_(ids)
    )
    linked_evidence = _count_by(
        db,
        InvestigationEvidence.investigation_id,
        InvestigationEvidence.tenant_id,
        tenant_id,
        InvestigationEvidence.investigation_id.in_(ids),
    )
    hypotheses = _count_by(
        db, Hypothesis.investigation_id, Hypothesis.tenant_id, tenant_id, Hypothesis.investigation_id.in_(ids)
    )
    unknowns = _count_by(
        db,
        Unknown.investigation_id,
        Unknown.tenant_id,
        tenant_id,
        Unknown.investigation_id.in_(ids),
        func.lower(Unknown.status).notin_(CLOSED_STATUSES),
    )
    decisions = defaultdict(Counter)
    for investigation_id, status in db.query(Decision.investigation_id, Decision.decision_status).filter(
        Decision.tenant_id == tenant_id, Decision.investigation_id.in_(ids)
    ):
        decisions[investigation_id][status or "UNKNOWN"] += 1
    evidence = {
        key: direct_evidence.get(key, 0) + linked_evidence.get(key, 0)
        for key in set(direct_evidence) | set(linked_evidence)
    }
    return rows, total, products, complaints, evidence, hypotheses, unknowns, decisions, {}


def investigation_report(db: Session, tenant_id, control_db=None) -> dict:
    rows, total, products, complaints, evidence, hypotheses, unknowns, decisions, _ = _investigation_rows(
        db, tenant_id, control_db
    )
    signatures = Counter()
    if control_db is not None and rows:
        decision_ids = [
            decision_id
            for (decision_id,) in db.query(Decision.id).filter(
                Decision.tenant_id == tenant_id, Decision.investigation_id.in_([row.id for row in rows])
            )
        ]
        owner = (
            dict(
                db.query(Decision.id, Decision.investigation_id).filter(
                    Decision.tenant_id == tenant_id, Decision.id.in_(decision_ids)
                )
            )
            if decision_ids
            else {}
        )
        for item in signature_verification_rows(control_db, tenant_id, limit=5000, decision_ids=decision_ids):
            if item["valid"]:
                signatures[owner.get(uuid.UUID(item["decision_id"]))] += 1
    cases = []
    for row in rows:
        product = products.get(row.product_id)
        days_open = None
        if row.opened_at:
            end = row.closed_at or datetime.now(timezone.utc)
            days_open = (end - row.opened_at).days
        cases.append(
            {
                "business_id": row.business_id,
                "investigation_identifier": row.investigation_identifier,
                "investigation_question": row.investigation_question,
                "status": row.status,
                "owner_ref": row.owner_ref,
                "product_business_id": product.business_id if product else None,
                "product_identifier": product.product_identifier if product else None,
                "opened_at": _iso(row.opened_at),
                "closed_at": _iso(row.closed_at),
                "days_open": days_open,
                "linked_complaints": complaints.get(row.id, 0),
                "evidence": evidence.get(row.id, 0),
                "hypotheses": hypotheses.get(row.id, 0),
                "open_unknowns": unknowns.get(row.id, 0),
                "decisions_by_status": dict(decisions.get(row.id, {})),
                "valid_signatures": signatures.get(row.id, 0),
            }
        )
    return {
        "summary": {
            "investigations": total,
            "open": sum(1 for case in cases if _is_open(case["status"])),
            "unassigned_open": sum(1 for case in cases if _is_open(case["status"]) and not case["owner_ref"]),
            "with_decisions": sum(1 for case in cases if case["decisions_by_status"]),
        },
        "investigations": cases,
        "truncated": [_truncation("investigations", len(cases), total)] if total > len(cases) else [],
        "limitations": [
            "Per-case detail (evidence, hypotheses, decisions, signatures, audit) is in the investigation record "
            "export; this report lists the cases.",
            "Signature counts need the control-plane session; a report rendered by the worker shows zero.",
        ]
        if control_db is None
        else ["Per-case detail is in the investigation record export; this report lists the cases."],
    }


def evidence_provenance(db: Session, tenant_id, control_db=None) -> dict:
    rows, total = _bounded(db.query(Evidence).filter(Evidence.tenant_id == tenant_id), Evidence.created_at.desc())
    investigations = _investigation_labels(db, tenant_id)
    items = [
        {
            "business_id": row.business_id,
            "evidence_identifier": row.evidence_identifier,
            "title": row.title,
            "evidence_type": row.evidence_type,
            "fact_type": row.fact_type,
            "reliability_status": row.reliability_status,
            **_case_labels(investigations, row.investigation_id),
            "source_system": row.source_system,
            "source_identifier": row.source_identifier,
            "source_reference": row.source_reference,
            "document_ref": row.document_ref,
            "source_timestamp": _iso(row.source_timestamp),
            "effective_timestamp": _iso(row.effective_timestamp),
            "recorded_timestamp": _iso(row.recorded_timestamp),
            "ingestion_timestamp": _iso(row.ingestion_timestamp),
        }
        for row in rows
    ]
    return {
        "summary": {
            "evidence": total,
            "ai_inferences": sum(1 for row in rows if row.fact_type == "ai_inference"),
            "unreviewed": sum(1 for row in rows if str(row.reliability_status).lower() == "unreviewed"),
        },
        "by_reliability": _label_counts(rows, "reliability_status"),
        "by_fact_type": _label_counts(rows, "fact_type"),
        "by_source_system": _label_counts(rows, "source_system"),
        "by_type": _label_counts(rows, "evidence_type"),
        "evidence": items,
        "truncated": [_truncation("evidence", len(items), total)] if total > len(items) else [],
        "limitations": ["Provenance is what the source recorded; MDARIX never changes a source timestamp."],
    }


def risk_impact(db: Session, tenant_id, control_db=None) -> dict:
    from backend.app.risk.service import register, traceability

    full = register(db, tenant_id)
    trace = traceability(db, tenant_id)
    rows = [
        {
            "business_id": item["business_id"],
            "risk_identifier": item["risk_identifier"],
            "description": item["description"],
            "status": item["status"],
            "product_business_id": item["product"]["business_id"] if item["product"] else None,
            "product_identifier": item["product"]["product_identifier"] if item["product"] else None,
            "residual_risk_state": item["residual_risk"]["state"],
            "failure_modes": [row["failure_mode_identifier"] for row in item["failure_modes"]],
            "controls": [row["control_identifier"] for row in item["controls"]],
            "requirements": [row["requirement_identifier"] for row in item["requirements"]],
            "verification_evidence": [
                evidence["evidence_identifier"] for row in item["controls"] for evidence in row["verification_evidence"]
            ],
            "open_complaints_on_product": item["open_complaints_on_product"],
        }
        for item in full["items"]
    ]
    # Each risk review's risk-control answers and the risk file updates it requires (T-G1aR, ISO 14971:2019 clause 10).
    from backend.app.qms_documents.content import finding_rows, risk_reviews

    answers, updates = finding_rows(
        db, uuid.UUID(str(tenant_id)), risk_reviews(db, uuid.UUID(str(tenant_id))), control_db
    )

    def listed(found: list[dict]) -> list[dict]:
        return [{"statement": item["text"], "records": [source["ref"] for source in item["sources"]]} for item in found]

    return {
        "summary": {
            "risks": len(rows),
            "risk_control_answers": len(answers),
            "risk_file_updates_required": len(updates),
            "by_status": [{"label": k, "count": v} for k, v in Counter(r["status"] or "UNKNOWN" for r in rows).items()],
            "without_controls": trace["counts"]["unlinked"]["risks_without_control"],
            "complete_traceability_chains": trace["counts"]["complete_chains"],
        },
        "risks": rows,
        "risk_control_answers": listed(answers),
        "risk_file_updates": listed(updates),
        "unlinked": trace["unlinked"],
        "unlinked_business_ids": trace["unlinked_business_ids"],
        "fields_not_captured": full["fields_not_captured"],
        "limitations": [
            full["data_notice"],
            "Open complaints on a product are context, not evidence that a risk occurred.",
        ],
    }


def scenario_comparison(db: Session, tenant_id, control_db=None) -> dict:
    investigations = _investigation_labels(db, tenant_id)
    scenarios, scenario_total = _bounded(
        db.query(Scenario).filter(Scenario.tenant_id == tenant_id), Scenario.created_at.desc()
    )
    if scenarios:
        rows = [
            {
                "business_id": row.business_id,
                **_case_labels(investigations, row.investigation_id),
                "scenario_identifier": row.scenario_identifier,
                "question": row.question,
                "assumptions": row.assumptions,
                "uncertainty": row.uncertainty,
                "status": row.status,
            }
            for row in scenarios
        ]
        return {
            "summary": {
                "scenarios": scenario_total,
                "investigations_with_scenarios": len({r["investigation_identifier"] for r in rows}),
            },
            "basis": "SCENARIO_RECORDS",
            "scenarios": rows,
            "truncated": [_truncation("scenarios", len(rows), scenario_total)] if scenario_total > len(rows) else [],
            "limitations": ["Scenarios are compared side by side; the report does not rank or choose one."],
        }
    # No scenario records exist for this organization: the competing explanations under investigation are its
    # hypotheses, which the report lists as such (and says so).
    hypotheses, total = _bounded(
        db.query(Hypothesis).filter(Hypothesis.tenant_id == tenant_id), Hypothesis.created_at.desc()
    )
    relations = defaultdict(Counter)
    if hypotheses:
        for hypothesis_id, relation in db.query(
            HypothesisEvidence.hypothesis_id, HypothesisEvidence.relation_type
        ).filter(
            HypothesisEvidence.tenant_id == tenant_id,
            HypothesisEvidence.hypothesis_id.in_([h.id for h in hypotheses]),
            HypothesisEvidence.retracted_at.is_(None),  # withdrawn links no longer count
        ):
            relations[hypothesis_id][relation] += 1
    rows = [
        {
            "business_id": row.business_id,
            **_case_labels(investigations, row.investigation_id),
            "statement": row.statement,
            "status": row.status,
            "origin": row.origin,
            "reviewer_disposition": row.reviewer_disposition,
            "supporting_evidence": relations[row.id].get("support", 0),
            "contradicting_evidence": relations[row.id].get("contradict", 0),
        }
        for row in hypotheses
    ]
    return {
        "summary": {
            "scenarios": 0,
            "hypotheses": total,
            "investigations_with_hypotheses": len({r["investigation_identifier"] for r in rows}),
        },
        "basis": "COMPETING_HYPOTHESES",
        "hypotheses": rows,
        "truncated": [_truncation("hypotheses", len(rows), total)] if total > len(rows) else [],
        "limitations": [
            "This organization has no scenario records, so the report lists the competing hypotheses of its "
            "investigations instead. Hypotheses are explanations under test, not findings.",
        ],
    }


def decision_brief(db: Session, tenant_id, control_db=None) -> dict:
    investigations = _investigation_labels(db, tenant_id)
    rows, total = _bounded(
        db.query(Decision).filter(Decision.tenant_id == tenant_id),
        func.coalesce(Decision.decision_timestamp, Decision.created_at).desc(),
    )
    signatures: dict[str, list] = defaultdict(list)
    if control_db is not None and rows:
        for item in signature_verification_rows(control_db, tenant_id, limit=5000, decision_ids=[r.id for r in rows]):
            signatures[item["decision_id"]].append(item)
    reviews = Counter()
    if rows:
        for (decision_id,) in db.query(HumanReview.decision_id).filter(
            HumanReview.tenant_id == tenant_id, HumanReview.decision_id.in_([r.id for r in rows])
        ):
            reviews[decision_id] += 1
    items = [
        {
            "business_id": row.business_id,
            "decision_identifier": row.decision_identifier,
            **_case_labels(investigations, row.investigation_id),
            "decision_type": row.decision_type,
            "selected_action": row.selected_action or row.disposition,
            "decision_status": row.decision_status,
            "decision_readiness": row.decision_readiness,
            "rationale": row.rationale,
            "authorized_by_ref": row.authorized_by_ref,
            "decision_timestamp": _iso(row.decision_timestamp),
            "updated_at": _iso(row.updated_at),
            "human_reviews": reviews.get(row.id, 0),
            "signatures": [
                {
                    "business_id": s["business_id"],
                    "signer_user_id": s["signer_user_id"],
                    "decision": s["decision"],
                    "valid": s["valid"],
                    "signed_at": s["signed_at"],
                }
                for s in signatures.get(str(row.id), [])
            ],
            "limitations": (row.limitations or {}).get("items")
            if isinstance(row.limitations, dict)
            else row.limitations,
        }
        for row in rows
    ]
    return {
        "summary": {
            "decisions": total,
            "awaiting_review": sum(1 for item in items if item["decision_status"] in ("REQUIRES_REVIEW", "DRAFT")),
            "signed": sum(1 for item in items if item["decision_status"] in SIGNED_DECISION_STATUSES),
            "valid_signatures": sum(1 for item in items for s in item["signatures"] if s["valid"]),
        },
        "by_status": _label_counts(rows, "decision_status"),
        "decisions": items,
        "truncated": [_truncation("decisions", len(items), total)] if total > len(items) else [],
        "limitations": ["A decision brief records what people decided and why; MDARIX never decides."]
        + (
            []
            if control_db is not None
            else ["Signatures need the control-plane session; a worker-rendered report shows none."]
        ),
    }


def ai_assurance(db: Session, tenant_id, control_db=None) -> dict:
    executions = db.query(AIExecution).filter(AIExecution.tenant_id == tenant_id)
    total = executions.count()
    recent = executions.order_by(AIExecution.execution_timestamp.desc()).limit(MAX_ROWS).all()
    failures = [
        row for row in recent if row.error_state or str(row.validation_status or "").upper() in {"FAILED", "BLOCKED"}
    ]
    latencies = sorted(row.latency_ms for row in recent if row.latency_ms is not None)
    results = db.query(AssuranceResult).filter(AssuranceResult.tenant_id == tenant_id)
    result_rows = results.order_by(AssuranceResult.generated_at.desc()).limit(MAX_ROWS).all()
    execution_ids = business_id_map(db, AIExecution, (row.ai_execution_id for row in result_rows[:100]))
    checks = (
        db.query(AssuranceCheck.check_type, AssuranceCheck.status, func.count())
        .filter(AssuranceCheck.tenant_id == tenant_id)
        .group_by(AssuranceCheck.check_type, AssuranceCheck.status)
        .all()
    )
    return {
        "summary": {
            "ai_executions": total,
            "executions_examined": len(recent),
            "failed_or_blocked": len(failures),
            "p95_latency_ms": latencies[max(0, int(len(latencies) * 0.95) - 1)] if latencies else None,
            "assurance_results": results.count(),
            "human_review_required": sum(1 for row in result_rows if row.human_review_required),
            "revalidation_required": sum(1 for row in result_rows if row.revalidation_required),
        },
        "executions_by_provider": _label_counts(recent, "provider"),
        "executions_by_validation_status": _label_counts(recent, "validation_status"),
        "assurance_by_status": _label_counts(result_rows, "status"),
        "checks": [
            {"check_type": check_type, "status": status, "count": int(count)}
            for check_type, status, count in sorted(checks, key=lambda row: (row[0], row[1]))
        ],
        "recent_assurance_results": [
            {
                "ai_execution_id": str(row.ai_execution_id),
                "ai_execution_business_id": execution_ids.get(str(row.ai_execution_id)),
                "output_type": row.output_type,
                "status": row.status,
                "trust_policy_version": row.trust_policy_version,
                "generated_at": _iso(row.generated_at),
                "human_review_required": row.human_review_required,
                "revalidation_required": row.revalidation_required,
            }
            for row in result_rows[:100]
        ],
        "limitations": [
            "Assurance checks are MDARIX's own controls on model output (grounding, citations, causal restraint); "
            "they are internal assurance, not regulatory certification.",
            f"Execution statistics cover the most recent {len(recent)} of {total} executions."
            if total > len(recent)
            else "Execution statistics cover every recorded execution.",
        ],
    }


def audit_approval(db: Session, tenant_id, control_db=None) -> dict:
    """The audit trail and signature verification. Both live in the control plane; without that session (a report
    rendered by the worker) the data plane's own audit events are listed and signatures cannot be verified."""
    source = control_db if control_db is not None else db
    events = audit_event_rows(source, tenant_id, limit=1000)
    signatures = signature_verification_rows(source, tenant_id, limit=500) if control_db is not None else []
    signatures = with_decision_business_ids(db, signatures)
    return {
        "audit_events": events,
        "signature_verification": signatures,
        "counts": {
            "audit_events": len(events),
            "signatures": len(signatures),
            "valid_signatures": sum(1 for item in signatures if item["valid"]),
            "audit_events_total": source.query(AuditEvent).filter(AuditEvent.tenant_id == tenant_id).count(),
            "signatures_total": source.query(SignedApprovalRecord)
            .filter(SignedApprovalRecord.tenant_id == tenant_id)
            .count()
            if control_db is not None
            else None,
        },
        "by_action": [
            {"label": label, "count": count}
            for label, count in Counter(event["action"] for event in events).most_common(40)
        ],
        "scope": "The latest 1,000 audit events and 500 signatures; the complete trail is in the audit export.",
        "limitations": []
        if control_db is not None
        else ["Signatures are kept in the control plane and could not be verified in this rendering."],
    }


def executive_quality_review(db: Session, tenant_id, control_db=None) -> dict:
    now = datetime.now(timezone.utc)
    since_30 = now - timedelta(days=30)
    since_90 = now - timedelta(days=90)
    complaints = db.query(Complaint).filter(Complaint.tenant_id == tenant_id)
    stamp = func.coalesce(Complaint.complaint_timestamp, Complaint.event_timestamp, Complaint.created_at)
    investigations = db.query(Investigation).filter(Investigation.tenant_id == tenant_id)
    closed = investigations.filter(Investigation.closed_at.is_not(None), Investigation.opened_at.is_not(None)).all()
    days_to_close = [(row.closed_at - row.opened_at).days for row in closed]
    decisions = _count_by(db, Decision.decision_status, Decision.tenant_id, tenant_id)
    capas = db.query(Capa).filter(Capa.tenant_id == tenant_id)
    risks = db.query(Risk).filter(Risk.tenant_id == tenant_id)
    evidence = db.query(Evidence).filter(Evidence.tenant_id == tenant_id)
    signed = (
        control_db.query(SignedApprovalRecord)
        .filter(SignedApprovalRecord.tenant_id == tenant_id, SignedApprovalRecord.status == "SIGNED")
        .count()
        if control_db is not None
        else None
    )
    return {
        "kpis": {
            "products": db.query(Product).filter(Product.tenant_id == tenant_id).count(),
            "product_versions": db.query(ProductVersion).filter(ProductVersion.tenant_id == tenant_id).count(),
            "complaints_total": complaints.count(),
            "complaints_open": complaints.filter(func.lower(Complaint.status).notin_(CLOSED_STATUSES)).count(),
            "complaints_last_30_days": complaints.filter(stamp >= since_30).count(),
            "complaints_last_90_days": complaints.filter(stamp >= since_90).count(),
            "complaints_serious_injury_or_death": complaints.filter(
                or_(Complaint.serious_injury.is_(True), Complaint.death.is_(True))
            ).count(),
            "investigations_open": investigations.filter(
                func.lower(Investigation.status).notin_(CLOSED_STATUSES)
            ).count(),
            "investigations_closed": investigations.filter(
                func.lower(Investigation.status).in_(CLOSED_STATUSES)
            ).count(),
            "median_days_to_close": sorted(days_to_close)[len(days_to_close) // 2] if days_to_close else None,
            "decisions_by_status": decisions,
            "signed_approvals": signed,
            "capas_open": capas.filter(func.lower(Capa.status).notin_(CLOSED_STATUSES)).count(),
            "capas_overdue": capas.filter(
                func.lower(Capa.status).notin_(CLOSED_STATUSES), Capa.due_at.is_not(None), Capa.due_at < now
            ).count(),
            "risks_total": risks.count(),
            "evidence_total": evidence.count(),
            "evidence_unreviewed": evidence.filter(func.lower(Evidence.reliability_status) == "unreviewed").count(),
            "ai_executions_last_30_days": db.query(AIExecution)
            .filter(AIExecution.tenant_id == tenant_id, AIExecution.execution_timestamp >= since_30)
            .count(),
        },
        "window": {"last_30_days_from": _iso(since_30), "last_90_days_from": _iso(since_90)},
        "limitations": [
            "Key figures are counts of the organization's records in MDARIX at the data cut-off.",
            "Trends and attention items need a person's judgement; nothing here ranks products or decides actions.",
        ]
        + (
            []
            if control_db is not None
            else ["Signed approvals need the control-plane session and are not counted here."]
        ),
    }


BUILDERS = {
    "PRODUCT_INTELLIGENCE": product_intelligence,
    "PRODUCT_VERSION_IMPACT": product_version_impact,
    "COMPLAINT_TREND": complaint_trend,
    "SIGNAL_ASSESSMENT": signal_assessment,
    "INVESTIGATION": investigation_report,
    "EVIDENCE_PROVENANCE": evidence_provenance,
    "RISK_IMPACT": risk_impact,
    "SCENARIO_COMPARISON": scenario_comparison,
    "DECISION_BRIEF": decision_brief,
    "AI_ASSURANCE": ai_assurance,
    "AUDIT_APPROVAL": audit_approval,
    "EXECUTIVE_QUALITY_REVIEW": executive_quality_review,
}


def build_report_context(db: Session, tenant_id, code: str, *, control_db: Session | None = None) -> dict:
    """The content of report ``code`` for one organization, with the instant its records were read."""
    builder = BUILDERS.get(str(code).upper())
    if builder is None:
        raise ValueError("REPORT_TYPE_NOT_SUPPORTED")
    tenant = uuid.UUID(str(tenant_id))
    content = builder(db, tenant, control_db)
    content["data_cut_off"] = datetime.now(timezone.utc).isoformat()
    return content


# --------------------------------------------------------------------------------------------- investigation record


def investigation_record(db: Session, tenant_id, investigation_id, *, control_db: Session | None = None) -> dict | None:
    """Everything recorded about one case: its fields, linked complaints, evidence with provenance, hypotheses and
    their evidence, unknowns, failure chains, scenarios, decisions with reviews and signatures, the latest brief, AI
    executions and the audit events about the case. None when the case is not this organization's."""
    tenant = uuid.UUID(str(tenant_id))
    case = (
        db.query(Investigation)
        .filter(Investigation.tenant_id == tenant, Investigation.id == uuid.UUID(str(investigation_id)))
        .first()
    )
    if case is None:
        return None
    product = db.query(Product).filter(Product.tenant_id == tenant, Product.id == case.product_id).first()
    complaint_ids = [
        complaint_id
        for (complaint_id,) in db.query(InvestigationComplaint.complaint_id).filter(
            InvestigationComplaint.tenant_id == tenant, InvestigationComplaint.investigation_id == case.id
        )
    ]
    complaints = (
        db.query(Complaint).filter(Complaint.tenant_id == tenant, Complaint.id.in_(complaint_ids)).all()
        if complaint_ids
        else []
    )
    linked_evidence = db.query(InvestigationEvidence.evidence_id).filter(
        InvestigationEvidence.tenant_id == tenant, InvestigationEvidence.investigation_id == case.id
    )
    evidence = (
        db.query(Evidence)
        .filter(
            Evidence.tenant_id == tenant, or_(Evidence.investigation_id == case.id, Evidence.id.in_(linked_evidence))
        )
        .order_by(Evidence.evidence_identifier)
        .all()
    )
    evidence_by_id = {row.id: row for row in evidence}
    hypotheses = (
        db.query(Hypothesis)
        .filter(Hypothesis.tenant_id == tenant, Hypothesis.investigation_id == case.id)
        .order_by(Hypothesis.created_at)
        .all()
    )
    relations = defaultdict(list)
    if hypotheses:
        for row in db.query(HypothesisEvidence).filter(
            HypothesisEvidence.tenant_id == tenant,
            HypothesisEvidence.hypothesis_id.in_([h.id for h in hypotheses]),
            HypothesisEvidence.retracted_at.is_(None),  # withdrawn links no longer count
        ):
            linked = evidence_by_id.get(row.evidence_id)
            relations[row.hypothesis_id].append(
                {
                    "evidence_business_id": linked.business_id if linked else None,
                    "evidence_identifier": linked.evidence_identifier if linked else str(row.evidence_id),
                    "relation_type": row.relation_type,
                    "rationale": row.rationale,
                    "created_by_type": row.created_by_type,
                }
            )
    unknowns = db.query(Unknown).filter(Unknown.tenant_id == tenant, Unknown.investigation_id == case.id).all()
    chains = (
        db.query(FailureChain).filter(FailureChain.tenant_id == tenant, FailureChain.investigation_id == case.id).all()
    )
    scenarios = db.query(Scenario).filter(Scenario.tenant_id == tenant, Scenario.investigation_id == case.id).all()
    decisions = (
        db.query(Decision)
        .filter(Decision.tenant_id == tenant, Decision.investigation_id == case.id)
        .order_by(Decision.created_at)
        .all()
    )
    reviews = defaultdict(list)
    for row in db.query(HumanReview).filter(HumanReview.tenant_id == tenant, HumanReview.investigation_id == case.id):
        reviews[row.decision_id].append(
            {
                "reviewer_ref": row.reviewer_ref,
                "disposition": row.disposition,
                "comments": row.comments,
                "review_timestamp": _iso(row.review_timestamp),
            }
        )
    signatures = defaultdict(list)
    audit_events: list[dict] = []
    if control_db is not None:
        decision_ids = [d.id for d in decisions]
        for item in with_decision_business_ids(
            db, signature_verification_rows(control_db, tenant, limit=5000, decision_ids=decision_ids)
        ):
            signatures[item["decision_id"]].append(item)
        related_ids = {case.id, *[d.id for d in decisions], *[e.id for e in evidence], *[h.id for h in hypotheses]}
        audit_events = audit_event_rows(control_db, tenant, limit=1000, entity_ids=related_ids)
    plane_events = (
        audit_event_rows(db, tenant, limit=1000, entity_ids={case.id, *[d.id for d in decisions]})
        if control_db is not db
        else []
    )
    seen = {event["id"] for event in audit_events}
    audit_events += [event for event in plane_events if event["id"] not in seen]
    audit_events.sort(key=lambda event: event["created_at"] or "", reverse=True)
    brief = (
        db.query(InvestigationBrief)
        .filter(InvestigationBrief.tenant_id == tenant, InvestigationBrief.investigation_id == case.id)
        .order_by(InvestigationBrief.brief_version.desc())
        .first()
    )
    executions = (
        db.query(AIExecution)
        .filter(AIExecution.tenant_id == tenant, AIExecution.investigation_id == case.id)
        .order_by(AIExecution.execution_timestamp.desc())
        .limit(50)
        .all()
    )
    return {
        "investigation": {
            "id": str(case.id),
            "business_id": case.business_id,
            "investigation_identifier": case.investigation_identifier,
            "investigation_question": case.investigation_question,
            "status": case.status,
            "owner_ref": case.owner_ref,
            "opened_at": _iso(case.opened_at),
            "closed_at": _iso(case.closed_at),
            "source_system": case.source_system,
            "source_identifier": case.source_identifier,
            "recorded_timestamp": _iso(case.recorded_timestamp),
            "product": {
                "id": str(product.id),
                "business_id": product.business_id,
                "product_identifier": product.product_identifier,
                "name": product.name,
            }
            if product
            else None,
        },
        "complaints": [
            {
                "business_id": row.business_id,
                "complaint_identifier": row.complaint_identifier,
                "description": row.description,
                "status": row.status,
                "severity": row.severity,
                "event_timestamp": _iso(row.event_timestamp),
                "complaint_timestamp": _iso(row.complaint_timestamp),
                "serious_injury": row.serious_injury,
                "death": row.death,
                "malfunction": row.malfunction,
                "problem_code": row.problem_code,
                "country": row.country,
            }
            for row in sorted(complaints, key=lambda row: row.complaint_identifier)
        ],
        "evidence": [
            {
                "business_id": row.business_id,
                "evidence_identifier": row.evidence_identifier,
                "title": row.title,
                "evidence_type": row.evidence_type,
                "fact_type": row.fact_type,
                "reliability_status": row.reliability_status,
                "source_system": row.source_system,
                "source_identifier": row.source_identifier,
                "source_reference": row.source_reference,
                "document_ref": row.document_ref,
                "effective_timestamp": _iso(row.effective_timestamp),
                "recorded_timestamp": _iso(row.recorded_timestamp),
                "ingestion_timestamp": _iso(row.ingestion_timestamp),
            }
            for row in evidence
        ],
        "hypotheses": [
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "statement": row.statement,
                "status": row.status,
                "origin": row.origin,
                "reviewer_disposition": row.reviewer_disposition,
                "evidence": relations.get(row.id, []),
            }
            for row in hypotheses
        ],
        "unknowns": [
            {
                "business_id": row.business_id,
                "category": row.category,
                "description": row.description,
                "evidence_needed": row.evidence_needed,
                "status": row.status,
                "resolution": row.resolution,
            }
            for row in unknowns
        ],
        "failure_chains": [{"business_id": row.business_id, "name": row.name, "status": row.status} for row in chains],
        "scenarios": [
            {
                "business_id": row.business_id,
                "scenario_identifier": row.scenario_identifier,
                "question": row.question,
                "assumptions": row.assumptions,
                "uncertainty": row.uncertainty,
                "status": row.status,
            }
            for row in scenarios
        ],
        "decisions": [
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "decision_identifier": row.decision_identifier,
                "decision_type": row.decision_type,
                "selected_action": row.selected_action or row.disposition,
                "decision_status": row.decision_status,
                "decision_readiness": row.decision_readiness,
                "rationale": row.rationale,
                "human_decision": row.human_decision,
                "authorized_by_ref": row.authorized_by_ref,
                "decision_timestamp": _iso(row.decision_timestamp),
                "updated_at": _iso(row.updated_at),
                "limitations": row.limitations,
                "reviews": reviews.get(row.id, []),
                "signatures": signatures.get(str(row.id), []),
            }
            for row in decisions
        ],
        "latest_brief": {
            "business_id": brief.business_id,
            "brief_version": brief.brief_version,
            "title": brief.title,
            "status": brief.status,
            "human_review_state": brief.human_review_state,
            "generated_by": brief.generated_by,
            "created_at": _iso(brief.created_at),
        }
        if brief
        else None,
        "ai_executions": [
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "provider": row.provider,
                "model_name": row.model_name,
                "validation_status": row.validation_status,
                "confidence_label": row.confidence_label,
                "error_state": row.error_state,
                "execution_timestamp": _iso(row.execution_timestamp),
            }
            for row in executions
        ],
        "audit_events": audit_events,
        "counts": {
            "complaints": len(complaints),
            "evidence": len(evidence),
            "hypotheses": len(hypotheses),
            "unknowns": len(unknowns),
            "decisions": len(decisions),
            "signatures": sum(len(items) for items in signatures.values()),
            "audit_events": len(audit_events),
        },
        "limitations": [
            "The record lists what is stored about the case; relationships are traceability, not causal conclusions.",
            "AI output in the record is advisory and was subject to human review.",
        ]
        + (
            []
            if control_db is not None
            else ["Signatures and the control-plane audit trail were not available in this rendering."]
        ),
    }
