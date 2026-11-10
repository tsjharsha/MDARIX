"""The facts of one investigation, read once from the records it links (B5 spec 2.2), for the draft and question rules.

Built from the case's current scope: its complaints, the versions of the case's product with their release dates,
predecessors and configuration, the lots of those versions with units released, units shipped and genealogy, the
changes affecting a component of those versions (or the whole product), same-problem complaints outside the scope,
the supplier-part pattern (W1 rule P-1) and the case's hypotheses, evidence links and open questions.

PV-1: a complaint with no version stays "version unknown" and a lot keeps the version it records; nothing is borrowed.
IV-10: only structured fields and codes are read, never evidence or complaint text as instructions. Every fact keeps
its record IDs and origin so each sentence can cite them. A read only: nothing is written.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from backend.app.case_workflow import scope as scope_module
from backend.app.complaint_review.rules import nff_family
from backend.app.decision_brief import rules as brief_rules
from backend.app.decision_brief.compose import hypotheses_rows
from backend.app.db.models.foundation import Complaint, Evidence, Hypothesis, Product, Unknown
from backend.app.product360 import supplier_service
from backend.app.product360.origin import origin

EVENT_AT = func.coalesce(Complaint.event_timestamp, Complaint.complaint_timestamp, Complaint.created_at)
# Same-problem complaints outside the scope read at most this many (newest first): they are shown, never counted in.
OUTSIDE_MAX = 500
CLOSED_UNKNOWN = ("resolved", "accepted_limitation", "superseded")


def _day(value) -> date | None:
    if value is None:
        return None
    return value.date() if isinstance(value, datetime) else value


def _origin(row) -> str:
    return origin(row.source_system, row.source_identifier, row.ingestion_timestamp, row.created_at)["kind"]


def _ids(values) -> list[uuid.UUID]:
    return [uuid.UUID(str(item)) for item in values or () if item]


def _complaint(row) -> dict:
    return {
        "id": str(row.id),
        "ref": row.complaint_identifier or row.business_id,
        "version_id": str(row.product_version_id) if row.product_version_id else None,
        "lot_id": str(row.lot_batch_id) if row.lot_batch_id else None,
        "problem": (row.problem_code or "").strip() or None,
        "event_on": _day(row.event_at),
        "harm": bool(row.death or row.serious_injury),
        "country": (row.country or "").strip().upper() or None,
        "returned": row.device_returned,
        "service_status": row.service_status,
        "code_class": nff_family(row.problem_code, row.complaint_type),
        "origin": _origin(row),
    }


def _complaints(db: Session, tenant_id, where, limit: int | None = None) -> list[dict]:
    query = db.query(Complaint, EVENT_AT.label("event_at")).filter(Complaint.tenant_id == tenant_id, *where)
    query = query.order_by(EVENT_AT.desc(), Complaint.complaint_identifier)
    if limit:
        query = query.limit(limit)
    found = []
    for complaint, event_at in query.all():
        complaint.event_at = event_at
        found.append(_complaint(complaint))
    return found


def _versions(db: Session, t: str, product_ids: list[str]) -> dict[str, dict]:
    rows = db.execute(
        text(
            "SELECT v.id, v.product_id, v.version_identifier, v.release_timestamp, v.source_system, p.name AS product "
            "FROM product_versions v JOIN products p ON p.tenant_id = v.tenant_id AND p.id = v.product_id "
            "WHERE v.tenant_id = :t AND v.product_id = ANY(CAST(:p AS uuid[]))"
        ),
        {"t": t, "p": product_ids},
    ).mappings()
    versions = {
        str(r["id"]): {
            "id": str(r["id"]),
            "ref": r["version_identifier"],
            "product_id": str(r["product_id"]),
            "product": r["product"],
            "released": _day(r["release_timestamp"]),
            "predecessor_id": None,
            "in_scope": False,
            "components": [],
        }
        for r in rows
    }
    # The predecessor: the product's latest version released before this one (signals/insight.py reads it the same way).
    for item in versions.values():
        earlier = [
            other
            for other in versions.values()
            if other["product_id"] == item["product_id"]
            and item["released"]
            and other["released"]
            and other["released"] < item["released"]
        ]
        if earlier:
            item["predecessor_id"] = max(earlier, key=lambda other: other["released"])["id"]
    return versions


def _configuration(db: Session, t: str, version_ids: list[str]) -> tuple[dict[str, dict], list[tuple[str, str]]]:
    """``{component id: {id, ref, name, suppliers: [{id, name}]}}`` and the (version, component) pairs."""
    rows = db.execute(
        text(
            "SELECT pc.product_version_id, c.id, c.component_identifier, c.name, s.id AS supplier_id, "
            "s.name AS supplier FROM product_components pc "
            "JOIN components c ON c.tenant_id = pc.tenant_id AND c.id = pc.component_id "
            "LEFT JOIN component_suppliers cs ON cs.tenant_id = c.tenant_id AND cs.component_id = c.id "
            "LEFT JOIN suppliers s ON s.tenant_id = cs.tenant_id AND s.id = cs.supplier_id "
            "WHERE pc.tenant_id = :t AND pc.product_version_id = ANY(CAST(:v AS uuid[]))"
        ),
        {"t": t, "v": version_ids},
    ).mappings()
    components: dict[str, dict] = {}
    pairs: set[tuple[str, str]] = set()
    for r in rows:
        item = components.setdefault(
            str(r["id"]), {"id": str(r["id"]), "ref": r["component_identifier"], "name": r["name"], "suppliers": []}
        )
        if r["supplier_id"] and all(s["id"] != str(r["supplier_id"]) for s in item["suppliers"]):
            item["suppliers"].append({"id": str(r["supplier_id"]), "name": r["supplier"]})
        pairs.add((str(r["product_version_id"]), str(r["id"])))
    return components, sorted(pairs)


def _lots(db: Session, t: str, version_ids: list[str]) -> dict[str, dict]:
    """Each lot of the versions: released on its manufacture date (else the day it was recorded), as the trend check
    reads it; its units released, its units shipped when it has distribution rows, and its genealogy components."""
    rows = db.execute(
        text(
            "SELECT l.id, l.lot_identifier, l.product_version_id, coalesce(l.effective_timestamp, l.created_at) AS made, "
            "l.quantity, (SELECT sum(d.quantity) FROM lot_distributions d WHERE d.tenant_id = l.tenant_id "
            "AND d.lot_batch_id = l.id) AS shipped, (SELECT array_agg(DISTINCT lc.component_id::text) "
            "FROM lot_components lc WHERE lc.tenant_id = l.tenant_id AND lc.lot_batch_id = l.id) AS genealogy "
            "FROM lot_batches l WHERE l.tenant_id = :t AND l.product_version_id = ANY(CAST(:v AS uuid[]))"
        ),
        {"t": t, "v": version_ids},
    ).mappings()
    return {
        str(r["id"]): {
            "id": str(r["id"]),
            "ref": r["lot_identifier"],
            "version_id": str(r["product_version_id"]),
            "released": _day(r["made"]),
            "units_released": r["quantity"],
            "units_shipped": int(r["shipped"]) if r["shipped"] is not None else None,
            "genealogy": sorted(r["genealogy"] or []),
        }
        for r in rows
    }


def _changes(db: Session, t: str, product_id: str, component_ids: list[str], pairs) -> list[dict]:
    """Changes recorded as affecting a component of the versions (the W1 join), or the whole product (every version)."""
    rows = db.execute(
        text(
            "SELECT ch.id, ch.change_identifier, ch.change_type, ch.description, "
            "coalesce(ch.event_timestamp, r.effective_timestamp) AS effective, r.target_entity_type, "
            "r.target_entity_id FROM reality_relationships r JOIN changes ch ON ch.tenant_id = r.tenant_id "
            "AND ch.id = r.source_entity_id WHERE r.tenant_id = :t AND r.source_entity_type = 'Change' AND "
            "((r.target_entity_type = 'Component' AND r.target_entity_id = ANY(CAST(:c AS uuid[]))) OR "
            "(r.target_entity_type = 'Product' AND r.target_entity_id = CAST(:p AS uuid)))"
        ),
        {"t": t, "c": component_ids, "p": product_id},
    ).mappings()
    found: dict[str, dict] = {}
    for r in rows:
        item = found.setdefault(
            str(r["id"]),
            {
                "id": str(r["id"]),
                "ref": r["change_identifier"],
                "kind": r["change_type"],
                "title": (r["description"] or "")[:200],
                "effective_on": _day(r["effective"]),
                "component_ids": [],
                "whole_product": False,
            },
        )
        if r["target_entity_type"] == "Product":
            item["whole_product"] = True
        elif str(r["target_entity_id"]) not in item["component_ids"]:
            item["component_ids"].append(str(r["target_entity_id"]))
    for item in found.values():
        item["version_ids"] = sorted({v for v, c in pairs if c in item["component_ids"]})
    return sorted(found.values(), key=lambda item: (item["effective_on"] or date.min, item["ref"]))


def _pattern(db: Session, t: str, components: dict, problems: set[str], now: datetime) -> dict | None:
    """W1 rule P-1 for the supplier of a scope part, over the scope's problem codes only: the first supplier whose
    parts show the same problem on 2 or more versions (rule order: supplier name)."""
    suppliers = sorted({(s["name"], s["id"]) for c in components.values() for s in c["suppliers"]})
    since = now - timedelta(days=supplier_service.WINDOW_DAYS)
    for name, supplier_id in suppliers:
        parts = supplier_service._parts(db, t, supplier_id)
        _, versions, _ = supplier_service._shape_parts(parts)
        ids = [item["version_id"] for item in versions]
        if len(ids) < supplier_service.MIN_VERSIONS:
            continue
        rows = [row for row in supplier_service._problems(db, t, ids, since) if row["problem"] in problems]
        box = supplier_service.pattern(name, True, versions, rows, supplier_service._units(db, t, ids), [], {})
        if box["found"]:
            part_versions = [
                {"id": v["version_id"], "ref": v["version_identifier"], "product": v["product_name"]} for v in versions
            ]
            return {**box, "supplier": name, "supplier_id": supplier_id, "part_versions": part_versions}
    return None


def _entity_evidence(db: Session, t: str, entity_ids: list[str]) -> dict[str, list[str]]:
    """``{component or supplier id: [evidence refs]}``: evidence linked to the part or its supplier (H-1's "missing")."""
    if not entity_ids:
        return {}
    rows = db.execute(
        text(
            "SELECT l.entity_id, e.business_id FROM evidence_entity_links l JOIN evidence e ON e.tenant_id = l.tenant_id "
            "AND e.id = l.evidence_id WHERE l.tenant_id = :t AND l.entity_type IN ('Component', 'Supplier') "
            "AND l.entity_id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"t": t, "ids": entity_ids},
    ).mappings()
    found: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        found[str(r["entity_id"])].append(r["business_id"])
    return dict(found)


def _brief_conclusion(db: Session, case) -> str | None:
    from backend.app.db.models.reviews import DecisionBriefVersion

    row = (
        db.query(DecisionBriefVersion.narrative)
        .filter(DecisionBriefVersion.tenant_id == case.tenant_id, DecisionBriefVersion.investigation_id == case.id)
        .order_by(DecisionBriefVersion.version.desc())
        .first()
    )
    narrative = brief_rules.normalize_narrative(row[0] if row else None)
    return narrative.get("proposed_conclusion") or None


def _evidence_links(db: Session, case, hypotheses: list[dict]) -> list[dict]:
    """Links (not withdrawn) of the considered hypotheses, with the evidence's kind: C-6 reads whether support comes
    only from a supplier's statement (its type or source names the supplier; never its content)."""
    from backend.app.db.models.foundation import HypothesisEvidence

    ids = _ids(item["id"] for item in hypotheses if brief_rules.considered(item))
    if not ids:
        return []
    rows = (
        db.query(HypothesisEvidence.hypothesis_id, HypothesisEvidence.relation_type, Evidence)
        .join(
            Evidence,
            (Evidence.tenant_id == HypothesisEvidence.tenant_id) & (Evidence.id == HypothesisEvidence.evidence_id),
        )
        .filter(
            HypothesisEvidence.tenant_id == case.tenant_id,
            HypothesisEvidence.hypothesis_id.in_(ids),
            HypothesisEvidence.retracted_at.is_(None),
        )
        .all()
    )
    return [
        {
            "hypothesis_id": str(hypothesis_id),
            "relation": str(relation or "").lower(),
            "evidence_id": str(ev.id),
            "ref": ev.business_id or ev.evidence_identifier,
            "evidence_type": ev.evidence_type,
            "source_reference": ev.source_reference,
            "fact_type": ev.fact_type,
            "reviewed": str(ev.reliability_status or "").lower() != "unreviewed",
        }
        for hypothesis_id, relation, ev in rows
    ]


def read(db: Session, case, now: datetime) -> dict:
    """The facts of the case's current scope. One read per table (about ten queries)."""
    t = str(case.tenant_id)
    data = scope_module.current_scope(db, case)
    included = _ids(data["included_complaint_ids"])
    complaints = _complaints(db, case.tenant_id, [Complaint.id.in_(included)]) if included else []
    product_ids = sorted({str(case.product_id)})
    product = db.query(Product.name).filter(Product.tenant_id == case.tenant_id, Product.id == case.product_id).scalar()
    versions = _versions(db, t, product_ids)
    for version_id in data["product_version_ids"]:
        if version_id in versions:
            versions[version_id]["in_scope"] = True
    for item in complaints:
        if item["version_id"] in versions:
            versions[item["version_id"]]["in_scope"] = True
    components, pairs = _configuration(db, t, list(versions))
    for version_id, component_id in pairs:
        versions[version_id]["components"].append(component_id)
    lots = _lots(db, t, list(versions))
    changes = _changes(db, t, str(case.product_id), list(components), pairs)
    for item in changes:
        if item["whole_product"]:
            item["version_ids"] = sorted(versions)
    problems = {item["problem"] for item in complaints if item["problem"]}
    outside = []
    if problems:
        outside = _complaints(
            db,
            case.tenant_id,
            [
                Complaint.product_id == case.product_id,
                Complaint.problem_code.in_(sorted(problems)),
                ~Complaint.id.in_(included or [uuid.uuid4()]),
            ],
            OUTSIDE_MAX,
        )
    hypotheses, _ = hypotheses_rows(db, case)
    rule_tags = dict(
        db.query(Hypothesis.id, Hypothesis.draft_rule)
        .filter(Hypothesis.tenant_id == case.tenant_id, Hypothesis.investigation_id == case.id)
        .all()
    )
    for item in hypotheses:
        item["draft_rule"] = rule_tags.get(uuid.UUID(item["id"]))
    unknowns = [
        {
            "id": str(row.id),
            "ref": row.business_id,
            "hypothesis_id": str(row.hypothesis_id) if row.hypothesis_id else None,
            "status": row.status,
            "open": str(row.status or "").lower() not in CLOSED_UNKNOWN,
            "description": row.description,
        }
        for row in db.query(Unknown).filter(Unknown.tenant_id == case.tenant_id, Unknown.investigation_id == case.id)
    ]
    return {
        "as_of": now,
        "case": {
            "id": str(case.id),
            "ref": case.investigation_identifier,
            "product_id": str(case.product_id),
            "product": product,
        },
        "scope_version": data["version"],
        "problems": sorted(problems),
        "complaints": complaints,
        "outside": outside,
        "versions": versions,
        "components": components,
        "lots": lots,
        "changes": changes,
        "pattern": _pattern(db, t, components, problems, now) if problems else None,
        "entity_evidence": _entity_evidence(
            db, t, sorted({*components, *(s["id"] for c in components.values() for s in c["suppliers"])})
        ),
        "hypotheses": hypotheses,
        "links": _evidence_links(db, case, hypotheses),
        "unknowns": unknowns,
        "conclusion": _brief_conclusion(db, case),
    }


def fingerprint(facts: dict) -> str:
    """A short digest of the records behind the facts (record IDs and the scope version): the audit of an adopted or
    dismissed draft keeps it, so a later reader sees whether the records changed since."""
    import hashlib

    parts = [str(facts["scope_version"])]
    parts += sorted(item["id"] for item in facts["complaints"])
    parts += sorted(facts["lots"]) + [item["id"] for item in facts["changes"]]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def by_version(complaints) -> dict[str | None, list[dict]]:
    found: dict[str | None, list[dict]] = defaultdict(list)
    for item in complaints:
        found[item["version_id"]].append(item)
    return found
