"""The risk register and traceability of one organization, read from its own records.

Risks, failure modes, controls and requirements are imported from the quality system (backend/app/trial/
business_imports.py, connector mappings). Their links are ``reality_relationships`` rows written by the import:
Control CONTROLS Risk, FailureMode CAN_LEAD_TO Risk, Requirement MITIGATES Risk. Verification evidence is evidence
linked to a control (``evidence_entity_links``) other than the control's own imported narrative.

The quality system export MDARIX takes in today has no hazard, harm, severity or probability columns (see the risks
template in business_imports.py), so the register reports those fields as not captured rather than inventing a score.
The residual-risk state is derived only from what is recorded: whether controls are linked and whether any of them
has verification evidence.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.models.evidence_intelligence import EvidenceEntityLink
from backend.app.db.models.foundation import (
    Complaint,
    Control,
    Evidence,
    FailureMode,
    Product,
    ProductVersion,
    RealityRelationship,
    Requirement,
    Risk,
)
from retrieval.record_evidence import RECORD_EVIDENCE_TYPE

# The direction and kind the business import writes for each link to a risk.
LINK_KINDS = {"Control": "CONTROLS", "FailureMode": "CAN_LEAD_TO", "Requirement": "MITIGATES"}
# Columns an ISO 14971 register normally carries that the imported records do not; reported as not captured.
FIELDS_NOT_CAPTURED = ("hazard", "harm", "severity", "probability", "risk_level")
OPEN_COMPLAINT_EXCLUDED = ("closed", "resolved", "completed", "rejected", "cancelled", "archived")


def _by_id(rows) -> dict:
    return {row.id: row for row in rows}


def _risk_links(db: Session, tenant_id) -> dict[str, dict[uuid.UUID, set[uuid.UUID]]]:
    """{entity type: {risk id: {linked ids}}}, accepting either direction of the relationship."""
    rows = (
        db.query(RealityRelationship)
        .filter(
            RealityRelationship.tenant_id == tenant_id,
            (RealityRelationship.source_entity_type == "Risk") | (RealityRelationship.target_entity_type == "Risk"),
        )
        .all()
    )
    links: dict[str, dict[uuid.UUID, set[uuid.UUID]]] = {kind: defaultdict(set) for kind in LINK_KINDS}
    for row in rows:
        if row.source_entity_type == "Risk" and row.target_entity_type in LINK_KINDS:
            links[row.target_entity_type][row.source_entity_id].add(row.target_entity_id)
        elif row.target_entity_type == "Risk" and row.source_entity_type in LINK_KINDS:
            links[row.source_entity_type][row.target_entity_id].add(row.source_entity_id)
    return links


def _verification_evidence(db: Session, tenant_id) -> dict[uuid.UUID, list[dict]]:
    """Evidence linked to each control, leaving out the control's own imported narrative record."""
    rows = (
        db.query(EvidenceEntityLink.entity_id, Evidence)
        .join(Evidence, (Evidence.id == EvidenceEntityLink.evidence_id) & (Evidence.tenant_id == tenant_id))
        .filter(
            EvidenceEntityLink.tenant_id == tenant_id,
            EvidenceEntityLink.entity_type == "Control",
            Evidence.evidence_type != RECORD_EVIDENCE_TYPE,
        )
        .all()
    )
    found: dict[uuid.UUID, list[dict]] = defaultdict(list)
    for control_id, evidence in rows:
        found[control_id].append(
            {
                "id": str(evidence.id),
                "business_id": evidence.business_id,
                "evidence_identifier": evidence.evidence_identifier,
                "title": evidence.title,
                "evidence_type": evidence.evidence_type,
                "reliability_status": evidence.reliability_status,
            }
        )
    return found


def _open_complaints_by_product(db: Session, tenant_id) -> dict[uuid.UUID, int]:
    rows = (
        db.query(Complaint.product_id, func.count(Complaint.id))
        .filter(
            Complaint.tenant_id == tenant_id,
            Complaint.product_id.is_not(None),
            func.lower(Complaint.status).notin_(OPEN_COMPLAINT_EXCLUDED),
        )
        .group_by(Complaint.product_id)
        .all()
    )
    return {product_id: int(count) for product_id, count in rows}


def _residual_state(controls: list[dict]) -> dict:
    """What the records support about residual risk: controls linked or not, verified or not. Never a score."""
    if not controls:
        return {"state": "NO_CONTROLS_LINKED", "basis": "No control is linked to this risk."}
    verified = [item for item in controls if item["verification_evidence"]]
    if verified:
        return {
            "state": "CONTROLLED_WITH_VERIFICATION_EVIDENCE",
            "basis": f"{len(verified)} of {len(controls)} linked controls have verification evidence.",
        }
    return {
        "state": "CONTROLLED_WITHOUT_VERIFICATION_EVIDENCE",
        "basis": f"{len(controls)} linked controls; none has verification evidence linked.",
    }


def risk_query(db: Session, tenant_id, *, product_id: uuid.UUID | None = None, status: str | None = None):
    """The organization's risks (optionally of one product / in one status), ordered by risk identifier."""
    query = db.query(Risk).filter(Risk.tenant_id == tenant_id)
    if product_id is not None:
        query = query.filter(Risk.product_id == product_id)
    if status:
        query = query.filter(func.lower(Risk.status) == status.lower())
    return query.order_by(Risk.risk_identifier)


def register(
    db: Session,
    tenant_id,
    *,
    product_id: uuid.UUID | None = None,
    status: str | None = None,
    risks: list | None = None,
) -> dict:
    """Every risk of the organization with its product, linked failure modes, controls (and their verification
    evidence), requirements and open complaints on the product. ``items`` is ordered by risk identifier.

    ``risks`` (rows from ``risk_query``, for example one page of it) limits the register to those risks."""
    if risks is None:
        risks = risk_query(db, tenant_id, product_id=product_id, status=status).all()
    products = _by_id(db.query(Product).filter(Product.tenant_id == tenant_id).all())
    versions = _by_id(db.query(ProductVersion).filter(ProductVersion.tenant_id == tenant_id).all())
    failure_modes = _by_id(db.query(FailureMode).filter(FailureMode.tenant_id == tenant_id).all())
    controls = _by_id(db.query(Control).filter(Control.tenant_id == tenant_id).all())
    requirements = _by_id(db.query(Requirement).filter(Requirement.tenant_id == tenant_id).all())
    links = _risk_links(db, tenant_id)
    verification = _verification_evidence(db, tenant_id)
    open_complaints = _open_complaints_by_product(db, tenant_id)
    items = []
    for risk in risks:
        product = products.get(risk.product_id)
        version = versions.get(risk.product_version_id)
        linked_controls = [
            {
                "id": str(control.id),
                "business_id": control.business_id,
                "control_identifier": control.control_identifier,
                "control_type": control.control_type,
                "description": control.description,
                "status": control.status,
                "verification_evidence": verification.get(control.id, []),
            }
            for control in sorted(
                (controls[cid] for cid in links["Control"].get(risk.id, ()) if cid in controls),
                key=lambda row: row.control_identifier,
            )
        ]
        items.append(
            {
                "id": str(risk.id),
                "business_id": risk.business_id,
                "risk_identifier": risk.risk_identifier,
                "description": risk.description,
                "status": risk.status,
                "product": {
                    "id": str(product.id),
                    "business_id": product.business_id,
                    "product_identifier": product.product_identifier,
                    "name": product.name,
                }
                if product
                else None,
                "product_version": {
                    "id": str(version.id),
                    "business_id": version.business_id,
                    "version_identifier": version.version_identifier,
                }
                if version
                else None,
                # Not in the imported records: reported as unknown, never estimated (see module docstring).
                **{field: None for field in FIELDS_NOT_CAPTURED},
                "residual_risk": _residual_state(linked_controls),
                "failure_modes": [
                    {
                        "id": str(mode.id),
                        "business_id": mode.business_id,
                        "failure_mode_identifier": mode.failure_mode_identifier,
                        "name": mode.name,
                        "description": mode.description,
                    }
                    for mode in sorted(
                        (failure_modes[fid] for fid in links["FailureMode"].get(risk.id, ()) if fid in failure_modes),
                        key=lambda row: row.failure_mode_identifier,
                    )
                ],
                "controls": linked_controls,
                "requirements": [
                    {
                        "id": str(requirement.id),
                        "business_id": requirement.business_id,
                        "requirement_identifier": requirement.requirement_identifier,
                        "requirement_type": requirement.requirement_type,
                        "text": requirement.text,
                        "status": requirement.status,
                    }
                    for requirement in sorted(
                        (requirements[rid] for rid in links["Requirement"].get(risk.id, ()) if rid in requirements),
                        key=lambda row: row.requirement_identifier,
                    )
                ],
                "open_complaints_on_product": open_complaints.get(risk.product_id, 0) if risk.product_id else 0,
                "source_system": risk.source_system,
                "recorded_at": risk.recorded_timestamp.isoformat() if risk.recorded_timestamp else None,
            }
        )
    return {
        "items": items,
        "fields_not_captured": list(FIELDS_NOT_CAPTURED),
        "data_notice": (
            "Hazard, harm, severity, probability and risk level are not part of the imported risk records; MDARIX "
            "shows them as not captured rather than estimating them. The residual-risk state reflects linked "
            "controls and their verification evidence only."
        ),
    }


def traceability(db: Session, tenant_id) -> dict:
    """ISO 14971 traceability: requirement -> risk -> failure mode -> control -> verification evidence, plus every
    record that is not linked into that chain."""
    full = register(db, tenant_id)
    risks = full["items"]
    links = _risk_links(db, tenant_id)
    linked_requirements = {rid for ids in links["Requirement"].values() for rid in ids}
    linked_failure_modes = {fid for ids in links["FailureMode"].values() for fid in ids}
    linked_controls = {cid for ids in links["Control"].values() for cid in ids}
    verification = _verification_evidence(db, tenant_id)
    requirements = (
        db.query(Requirement)
        .filter(Requirement.tenant_id == tenant_id)
        .order_by(Requirement.requirement_identifier)
        .all()
    )
    failure_modes = (
        db.query(FailureMode)
        .filter(FailureMode.tenant_id == tenant_id)
        .order_by(FailureMode.failure_mode_identifier)
        .all()
    )
    controls = db.query(Control).filter(Control.tenant_id == tenant_id).order_by(Control.control_identifier).all()
    chains = [
        {
            "risk_id": item["id"],
            "risk_business_id": item["business_id"],
            "risk_identifier": item["risk_identifier"],
            "product": item["product"]["product_identifier"] if item["product"] else None,
            "product_business_id": item["product"]["business_id"] if item["product"] else None,
            # Each list of source identifiers has a business-identifier list in the same order.
            "requirements": [row["requirement_identifier"] for row in item["requirements"]],
            "requirement_business_ids": [row["business_id"] for row in item["requirements"]],
            "failure_modes": [row["failure_mode_identifier"] for row in item["failure_modes"]],
            "failure_mode_business_ids": [row["business_id"] for row in item["failure_modes"]],
            "controls": [row["control_identifier"] for row in item["controls"]],
            "control_business_ids": [row["business_id"] for row in item["controls"]],
            "verification_evidence": [
                evidence["evidence_identifier"] for row in item["controls"] for evidence in row["verification_evidence"]
            ],
            "verification_evidence_business_ids": [
                evidence["business_id"] for row in item["controls"] for evidence in row["verification_evidence"]
            ],
            "residual_risk": item["residual_risk"]["state"],
            "complete": bool(item["requirements"] and item["failure_modes"] and item["controls"])
            and any(row["verification_evidence"] for row in item["controls"]),
        }
        for item in risks
    ]
    # Each gap as (source identifier, business identifier) pairs.
    gaps = {
        "requirements_without_risk": [
            (row.requirement_identifier, row.business_id) for row in requirements if row.id not in linked_requirements
        ],
        "failure_modes_without_risk": [
            (row.failure_mode_identifier, row.business_id)
            for row in failure_modes
            if row.id not in linked_failure_modes
        ],
        "controls_without_risk": [
            (row.control_identifier, row.business_id) for row in controls if row.id not in linked_controls
        ],
        "controls_without_verification_evidence": [
            (row.control_identifier, row.business_id) for row in controls if not verification.get(row.id)
        ],
        "risks_without_requirement": [
            (item["risk_identifier"], item["business_id"]) for item in risks if not item["requirements"]
        ],
        "risks_without_failure_mode": [
            (item["risk_identifier"], item["business_id"]) for item in risks if not item["failure_modes"]
        ],
        "risks_without_control": [
            (item["risk_identifier"], item["business_id"]) for item in risks if not item["controls"]
        ],
    }
    unlinked = {key: [identifier for identifier, _ in value] for key, value in gaps.items()}
    return {
        "chains": chains,
        "counts": {
            "risks": len(risks),
            "requirements": len(requirements),
            "failure_modes": len(failure_modes),
            "controls": len(controls),
            "complete_chains": sum(1 for chain in chains if chain["complete"]),
            "unlinked": {key: len(value) for key, value in unlinked.items()},
        },
        "unlinked": unlinked,
        # The same records as ``unlinked``, in the same order, by business identifier.
        "unlinked_business_ids": {key: [business_id for _, business_id in value] for key, value in gaps.items()},
        "standard": "ISO 14971 traceability (requirement -> risk -> failure mode -> control -> verification)",
        "data_notice": full["data_notice"],
    }


def register_csv_rows(items: list[dict]) -> list[list]:
    """One row per risk for the CSV export; linked records are joined with ';' inside a cell."""
    header = [
        "business_id",
        "risk_identifier",
        "description",
        "status",
        "product",
        "product_version",
        "hazard",
        "harm",
        "severity",
        "probability",
        "risk_level",
        "residual_risk_state",
        "failure_modes",
        "controls",
        "requirements",
        "verification_evidence",
        "open_complaints_on_product",
    ]
    rows = [header]
    for item in items:
        rows.append(
            [
                item["business_id"],
                item["risk_identifier"],
                item["description"],
                item["status"],
                item["product"]["product_identifier"] if item["product"] else "",
                item["product_version"]["version_identifier"] if item["product_version"] else "",
                "not captured",
                "not captured",
                "not captured",
                "not captured",
                "not captured",
                item["residual_risk"]["state"],
                ";".join(row["failure_mode_identifier"] for row in item["failure_modes"]),
                ";".join(row["control_identifier"] for row in item["controls"]),
                ";".join(row["requirement_identifier"] for row in item["requirements"]),
                ";".join(
                    evidence["evidence_identifier"]
                    for row in item["controls"]
                    for evidence in row["verification_evidence"]
                ),
                item["open_complaints_on_product"],
            ]
        )
    return rows
