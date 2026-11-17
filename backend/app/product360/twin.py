"""The Product Lifecycle Twin (W5, spec sections 2 to 4): one product version's records connected, a change's impact,
and a component lot's field-action scope. Reads only, from records the organization already holds; every query names
the tenant on every table it reads; a free trial only (the router answers 404 elsewhere).

- **The connected view** (U1): version, parts, suppliers, component lots, finished lots, markets, complaints (open and
  total), investigations, risk rows, CAPAs with their check state and changes, each with where it came from. With no
  version (PV-1) only what belongs to the product: no parts, lots or markets.
- **Change impact** (U2): for a recorded change (the versions it affects: ``affected_versions``) or a preview of one by
  component or supplier (the versions whose bill of materials uses it; nothing is saved), what to re-check: versions,
  lots (complaints first), markets, open complaints, before and after, investigations, risk rows and CAPAs with their
  check state. Each row says why it is listed.
- **Field-action scope** (U3): the lot impact list (``lot_impact.service.build``, its fingerprint unchanged) for one
  factor across the organization's lots, with units by market and by site added beside it, never inside the
  fingerprinted material.

MDARIX lists; it recommends no recall and no other field action, and decides no notification.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from types import SimpleNamespace
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.business_ids import as_uuid
from backend.app.lot_impact import service as lot_impact
from backend.app.product360 import links
from backend.app.product360.service import Product360Error, Product360Service, rowdict

# Generic system names only (D9): which simulated system each node's records came from.
NODE_SYSTEM = {
    "version": ("products", "PLM"),
    "parts": ("bom", "PLM"),
    "changes": ("changes", "PLM"),
    "suppliers": ("suppliers", "ERP"),
    "component_lots": ("lot_genealogy", "ERP"),
    "lots": ("lots", "ERP"),
    "markets": ("distribution", "ERP"),
    "complaints": ("complaints", "eQMS"),
    "capas": ("capas", "eQMS"),
    "investigations": (None, None),
    "risks": (None, None),
}
CANNOT_TELL = [
    "Only what was imported: lots, genealogy and shipments not loaded into MDARIX are not in the list.",
    "The first consignee only: where a distributor sent the units on is not known.",
    '"In stock" is units released minus units shipped, not a stock count.',
    "One genealogy level: a component lot inside another component's lot is not followed.",
    "A complaint counts on a lot only when it names that lot.",
    "Lots that shipped more units than they released are flagged, not corrected.",
    "No recall recommendation and no notification decision: you decide any field action in your QMS. The sources "
    "behind the sample are simulated.",
    f"Up to {lot_impact.LOTS_MAX:,} lots.",
]


def _sources(db: Session, tenant_id) -> dict[str, Any]:
    """Where each node's records came from: the simulated systems (labelled), your imports, or MDARIX."""
    from backend.app.trial.sample_data import SAMPLE_SOURCE
    from backend.app.trial.sample_sources import LABEL, MARKER_ENTITY

    loaded = {
        (row["entity"], row["source"])
        for row in db.execute(
            text("SELECT DISTINCT entity, source FROM import_lineage WHERE tenant_id=:t"), {"t": tenant_id}
        ).mappings()
    }
    simulated = (MARKER_ENTITY, SAMPLE_SOURCE) in loaded
    captions = {}
    for node, (entity, system) in NODE_SYSTEM.items():
        if simulated:
            where = f"From {system}" if system else "Kept in MDARIX (sample)"
            captions[node] = f"{where} · {LABEL}"
        elif any(item[0] == entity and item[1] != SAMPLE_SOURCE for item in loaded):
            captions[node] = "From your import"
        else:
            captions[node] = "Recorded in MDARIX"
    return {"simulated": simulated, "label": LABEL if simulated else None, "captions": captions}


def _lots(db: Session, tenant_id, version_ids: list[str]) -> list[dict]:
    """The versions' lots with their complaints (all and open), oldest identifier first."""
    if not version_ids:
        return []
    rows = db.execute(
        text(
            "SELECT l.id, l.business_id, l.lot_identifier, l.quantity, l.effective_timestamp AS made_on, "
            "pv.version_identifier, count(c.id) AS complaints, "
            "count(c.id) FILTER (WHERE lower(coalesce(c.status,'')) <> 'closed') AS open_complaints "
            "FROM lot_batches l JOIN product_versions pv ON pv.tenant_id=l.tenant_id AND pv.id=l.product_version_id "
            "LEFT JOIN complaints c ON c.tenant_id=l.tenant_id AND c.lot_batch_id=l.id "
            "WHERE l.tenant_id=:t AND l.product_version_id = ANY(CAST(:v AS uuid[])) "
            "GROUP BY l.id, pv.version_identifier ORDER BY l.lot_identifier"
        ),
        {"t": tenant_id, "v": version_ids},
    ).mappings()
    return [
        {
            **rowdict(row),
            "complaints": int(row["complaints"]),
            "open_complaints": int(row["open_complaints"]),
            "per_1000": lot_impact.per_thousand(int(row["complaints"]), row["quantity"]),
        }
        for row in rows
    ]


def _with_shipments(db: Session, tenant_id, lots: list[dict]) -> dict[str, Any]:
    """Each lot's countries and units shipped (or "distribution not imported"), and the markets over all of them."""
    shipments = lot_impact._shipments(db, tenant_id, [uuid.UUID(lot["id"]) for lot in lots])
    sites: dict[tuple, dict] = {}
    for lot in lots:
        rows = shipments.get(lot["id"], [])
        lot["distribution_imported"] = bool(rows)
        lot["shipped"] = sum(row.quantity for row in rows) if rows else None
        lot["countries"] = [item["country"] for item in lot_impact._by_country((r.country, r.quantity) for r in rows)]
        for row in rows:
            site = sites.setdefault(
                (row.consignee, row.consignee_type, row.country),
                {
                    "consignee": row.consignee,
                    "consignee_type": row.consignee_type,
                    "country": row.country,
                    "units": 0,
                    "lots": set(),
                },
            )
            site["units"] += row.quantity
            site["lots"].add(lot["lot_identifier"])
    every = [row for rows in shipments.values() for row in rows]
    return {
        "by_country": lot_impact._by_country((row.country, row.quantity) for row in every),
        "sites": _sites(sites.values()),
        "not_imported": sum(1 for lot in lots if not lot["distribution_imported"]),
        "not_imported_label": lot_impact.NOT_IMPORTED,
    }


def _sites(sites) -> list[dict]:
    return sorted(
        ({**site, "lots": sorted(site["lots"])} for site in sites),
        key=lambda site: (-site["units"], site["country"], site["consignee"]),
    )


def _component_lots(db: Session, tenant_id, lots: list[dict], components: list[str] | None = None) -> list[dict]:
    """The component lots the lots' genealogy names, each with its lots and how many of them have complaints, the one
    with most complaint lots first (the one to trace)."""
    if not lots:
        return []
    by_id = {lot["id"]: lot for lot in lots}
    sql = (
        "SELECT lc.component_id, c.component_identifier, c.name, lc.component_lot_identifier AS lot, "
        "array_agg(DISTINCT lc.lot_batch_id::text) AS lots FROM lot_components lc "
        "JOIN components c ON c.tenant_id=lc.tenant_id AND c.id=lc.component_id "
        "WHERE lc.tenant_id=:t AND lc.lot_batch_id = ANY(CAST(:l AS uuid[])) AND lc.component_lot_identifier IS NOT NULL "
        "AND (CAST(:c AS uuid[]) IS NULL OR lc.component_id = ANY(CAST(:c AS uuid[]))) GROUP BY 1, 2, 3, 4"
    )
    found = []
    for row in db.execute(text(sql), {"t": tenant_id, "l": list(by_id), "c": components}).mappings():
        held = [by_id[item] for item in row["lots"]]
        found.append(
            {
                "component_id": str(row["component_id"]),
                "component_identifier": row["component_identifier"],
                "component_name": row["name"],
                "lot": row["lot"],
                "label": f"{row['name']} lot {row['lot']}",
                "lots": sorted(lot["lot_identifier"] for lot in held),
                "lots_with_complaints": sum(1 for lot in held if lot["complaints"]),
                "complaints": sum(lot["complaints"] for lot in held),
                "scope": f"{lot_impact.COMPONENT_LOT}:{row['component_id']}:{row['lot']}",
            }
        )
    found.sort(key=lambda item: (-item["lots_with_complaints"], -item["complaints"], -len(item["lots"]), item["label"]))
    return found


def _complaint_counts(db: Session, tenant_id, product_id, version_ids: list[str] | None) -> dict[str, int]:
    row = (
        db.execute(
            text(
                "SELECT count(*) AS total, count(*) FILTER (WHERE lower(coalesce(status,'')) <> 'closed') AS open "
                "FROM complaints WHERE tenant_id=:t AND product_id=:p "
                "AND (CAST(:v AS uuid[]) IS NULL OR product_version_id = ANY(CAST(:v AS uuid[])))"
            ),
            {"t": tenant_id, "p": product_id, "v": version_ids},
        )
        .mappings()
        .one()
    )
    return {"total": int(row["total"]), "open": int(row["open"])}


def twin(db: Session, tenant_id: str, product_ref: str, version_ref: str | None) -> dict[str, Any]:
    """The connected view of one product version (or, with no version, of the product alone)."""
    product, versions, version = links.resolve(db, tenant_id, product_ref, version_ref)
    service = Product360Service()
    version_id = str(version["id"]) if version else None
    components = [links._row(row) for row in service.components(db, tenant_id, version_id)]
    suppliers = [links._row(row) for row in service.suppliers(db, tenant_id, components)]
    lots = _lots(db, tenant_id, [version_id] if version_id else [])
    markets = _with_shipments(db, tenant_id, lots)
    component_lots = _component_lots(db, tenant_id, lots)
    changes = [rowdict(row) for row in service.changes(db, tenant_id, str(product["id"]))]
    if version_id:
        changes = [row for row in changes if row["affects_product"] or version_id in row["versions"]]
    limits = [
        "Lots, component lots and markets are this version's; the field-action scope lists every lot of the "
        "organization built with the component lot.",
        "A complaint is on a lot only when it names that lot.",
    ]
    if version is None:
        limits.insert(0, "No version chosen: only what belongs to the product is shown (no parts, lots or markets).")
    return {
        **links._head(product, version),
        "versions": [rowdict(row) for row in versions],
        "components": components,
        "suppliers": suppliers,
        "lots": lots,
        "component_lots": component_lots,
        "trace": next((item for item in component_lots if item["lots_with_complaints"]), None),
        "markets": markets,
        "complaints": _complaint_counts(db, tenant_id, product["id"], [version_id] if version_id else None),
        "investigations": links.investigations(db, tenant_id, product, version),
        "risks": links.risks(db, tenant_id, product, version),
        "capas": links.capas(db, tenant_id, product, version),
        "changes": changes,
        "sources": _sources(db, tenant_id),
        "limits": limits,
    }


# ------------------------------------------------------------------------------------------------ change impact


def _change(db: Session, tenant_id, ref: str):
    return (
        db.execute(
            text(
                "SELECT id, business_id, change_identifier, change_type, description, event_timestamp, "
                "effective_timestamp FROM changes WHERE tenant_id=:t "
                "AND (id::text=:r OR business_id=:r OR change_identifier=:r) LIMIT 1"
            ),
            {"t": tenant_id, "r": str(ref)},
        )
        .mappings()
        .one_or_none()
    )


def _one(db: Session, sql: str, tenant_id, ref: str):
    return db.execute(text(sql), {"t": tenant_id, "r": str(ref)}).mappings().one_or_none()


def change_impact(
    db: Session,
    tenant_id: str,
    product_ref: str,
    change_ref: str | None = None,
    component_ref: str | None = None,
    supplier_ref: str | None = None,
) -> dict[str, Any]:
    """What to re-check if a recorded change (or, as a preview, a change of a component or a supplier) holds."""
    from backend.app.qms_documents.content import affected_versions

    product, versions, _ = links.resolve(db, tenant_id, product_ref, None)
    names = {str(v["id"]): v["version_identifier"] for v in versions}
    head: dict[str, Any] = {}
    before_after = None
    if change_ref:
        change = _change(db, tenant_id, change_ref)
        if change is None:
            raise Product360Error("CHANGE_NOT_FOUND", "Change record not found")
        record = SimpleNamespace(id=change["id"])
        affected = [str(v) for v in affected_versions(db, uuid.UUID(str(tenant_id)), record) if str(v) in names]
        parts = db.execute(
            text(
                "SELECT c.id, c.component_identifier, c.name FROM reality_relationships rr "
                "JOIN components c ON c.tenant_id=rr.tenant_id AND c.id=rr.target_entity_id "
                "WHERE rr.tenant_id=:t AND rr.source_entity_type='Change' AND rr.source_entity_id=:c "
                "AND rr.target_entity_type='Component'"
            ),
            {"t": tenant_id, "c": change["id"]},
        ).mappings()
        parts = [dict(row) for row in parts]
        recorded = next(
            (
                row
                for row in Product360Service().changes(db, tenant_id, str(product["id"]))
                if str(row["id"]) == str(change["id"])
            ),
            None,
        )
        if recorded is None:
            raise Product360Error("CHANGE_NOT_FOUND", "This change is not recorded as affecting this product")
        before_after = {
            "before": recorded["complaints_before"],
            "after": recorded["complaints_after"],
            "since": rowdict(change)["effective_timestamp"] or rowdict(change)["event_timestamp"],
            "basis": "Complaints on the affected versions, by event date, before and after the change took effect",
        }
        head = {"change": rowdict(change), "preview": False}
        why = "The change record names {part}; {version} uses it (bill of materials)"
    else:
        component = supplier = None
        if component_ref:
            component = _one(
                db,
                "SELECT id, component_identifier, name FROM components WHERE tenant_id=:t "
                "AND (id::text=:r OR business_id=:r) LIMIT 1",
                tenant_id,
                component_ref,
            )
            if component is None:
                raise Product360Error("COMPONENT_NOT_FOUND", "Component not found")
        if supplier_ref:
            supplier = _one(
                db,
                "SELECT id, supplier_identifier, name FROM suppliers WHERE tenant_id=:t "
                "AND (id::text=:r OR business_id=:r OR supplier_identifier=:r) LIMIT 1",
                tenant_id,
                supplier_ref,
            )
            if supplier is None:
                raise Product360Error("SUPPLIER_NOT_FOUND", "Supplier not found")
        if component is None and supplier is None:
            raise Product360Error("COMPONENT_NOT_FOUND", "Choose a component or a supplier to preview")
        parts = [
            dict(row)
            for row in db.execute(
                text(
                    "SELECT c.id, c.component_identifier, c.name FROM components c WHERE c.tenant_id=:t "
                    "AND (CAST(:c AS uuid) IS NULL OR c.id = CAST(:c AS uuid)) AND (CAST(:s AS uuid) IS NULL OR "
                    "EXISTS (SELECT 1 FROM component_suppliers cs WHERE cs.tenant_id=:t AND cs.component_id=c.id "
                    "AND cs.supplier_id = CAST(:s AS uuid)))"
                ),
                {
                    "t": tenant_id,
                    "c": str(component["id"]) if component else None,
                    "s": str(supplier["id"]) if supplier else None,
                },
            ).mappings()
        ]
        affected = None
        head = {
            "change": None,
            "preview": True,
            "previewed": {
                "component": rowdict(component) if component else None,
                "supplier": rowdict(supplier) if supplier else None,
            },
        }
        why = "Bill of materials: {version} uses {part}"
    part_ids = [str(row["id"]) for row in parts]
    uses = db.execute(
        text(
            "SELECT DISTINCT pc.product_version_id, c.name FROM product_components pc "
            "JOIN components c ON c.tenant_id=pc.tenant_id AND c.id=pc.component_id "
            "WHERE pc.tenant_id=:t AND pc.component_id = ANY(CAST(:c AS uuid[])) "
            "AND pc.product_version_id = ANY(CAST(:v AS uuid[]))"
        ),
        {"t": tenant_id, "c": part_ids, "v": list(names)},
    ).mappings()
    used: dict[str, list[str]] = defaultdict(list)
    for row in uses:
        used[str(row["product_version_id"])].append(row["name"])
    version_ids = [v for v in names if (v in affected if affected is not None else v in used)]
    affected_versions_rows = [
        {
            "id": v,
            "version_identifier": names[v],
            "basis": why.format(
                version=names[v], part=", ".join(sorted(used.get(v) or [p["name"] for p in parts])) or "it"
            ),
        }
        for v in version_ids
    ]
    labels = {names[v] for v in version_ids}
    lots = _lots(db, tenant_id, version_ids)
    markets = _with_shipments(db, tenant_id, lots)
    for lot in lots:
        lot["basis"] = f"Builds {lot['version_identifier']} (lot record)"
    lots.sort(key=lambda lot: (lot["complaints"] == 0, -lot["complaints"], lot["lot_identifier"]))
    open_rows = db.execute(
        text(
            "SELECT c.id, c.business_id, c.complaint_identifier, c.status, c.event_timestamp, c.problem_code, "
            "l.lot_identifier, pv.version_identifier, count(*) OVER () AS total FROM complaints c "
            "LEFT JOIN lot_batches l ON l.tenant_id=c.tenant_id AND l.id=c.lot_batch_id "
            "JOIN product_versions pv ON pv.tenant_id=c.tenant_id AND pv.id=c.product_version_id "
            "WHERE c.tenant_id=:t AND c.product_version_id = ANY(CAST(:v AS uuid[])) "
            "AND lower(coalesce(c.status,'')) <> 'closed' ORDER BY c.event_timestamp DESC NULLS LAST LIMIT 50"
        ),
        {"t": tenant_id, "v": version_ids},
    ).mappings()
    open_rows = [rowdict(row) for row in open_rows]
    for row in open_rows:
        row["basis"] = f"Open complaint on {row.pop('version_identifier')}"
    investigations = [
        {
            **row,
            "basis": (
                f"Holds complaints on {', '.join(sorted(labels & set(row['versions'])))}"
                if row["versions"]
                else "Records no version: listed at product level"
            ),
        }
        for row in links.investigations(db, tenant_id, product, None)
        if not row["versions"] or labels & set(row["versions"])
    ]
    kept = {row["id"] for row in investigations}
    risks = [
        {
            **row,
            "basis": (
                f"Risk row on {product['name']} (no version recorded)"
                if row["applies_to"] == "PRODUCT"
                else f"Risk row on {names.get(str(row['product_version_id']), 'the version')}"
            ),
        }
        for row in links.risks(db, tenant_id, product, None)
        if row["applies_to"] == "PRODUCT" or str(row["product_version_id"]) in version_ids
    ]
    capas = [
        row
        for row in links.capas(db, tenant_id, product, None)
        if not row["investigation_id"] or str(row["investigation_id"]) in {str(k) for k in kept}
    ]
    scopes = _component_lots(db, tenant_id, lots, part_ids)
    return {
        **links._head(product, None),
        **head,
        "components": [{**rowdict(row), "id": str(row["id"])} for row in parts],
        "versions": affected_versions_rows,
        "lots": lots,
        "markets": markets,
        "open_complaints": {"count": int(open_rows[0]["total"]) if open_rows else 0, "items": open_rows},
        "before_after": before_after,
        "investigations": investigations,
        "risks": risks,
        "capas": capas,
        "scope": next((item for item in scopes if item["lots_with_complaints"]), scopes[0] if scopes else None),
        "never_decides": lot_impact.NEVER_DECIDES,
    }


# --------------------------------------------------------------------------------------------- field-action scope


def factor_of(db: Session, tenant_id, kind: str | None, ref: str | None, lot: str | None) -> dict | None:
    """The scope's factor: ``ref`` is the record's id, or for a component lot the component's identifier (the one
    whose genealogy names that lot)."""
    if str(kind or "").upper() == lot_impact.COMPONENT_LOT and ref and as_uuid(ref) is None:
        ref = db.execute(
            text(
                "SELECT lc.component_id FROM lot_components lc JOIN components c ON c.tenant_id=lc.tenant_id "
                "AND c.id=lc.component_id WHERE lc.tenant_id=:t AND c.component_identifier=:r "
                "AND lc.component_lot_identifier=:l LIMIT 1"
            ),
            {"t": tenant_id, "r": ref, "l": " ".join(str(lot or "").split())},
        ).scalar()
    return lot_impact.resolve(db, tenant_id, lot_impact.clean_factor(kind, ref, lot))


def by_market(lots: list[dict]) -> list[dict]:
    markets: dict[str, dict] = {}
    for lot in lots:
        for shipment in lot["shipments"]:
            item = markets.setdefault(
                shipment["country"], {"country": shipment["country"], "units": 0, "sites": set(), "lots": set()}
            )
            item["units"] += shipment["units"]
            item["sites"].add(shipment["consignee"])
            item["lots"].add(lot["lot_identifier"])
    return sorted(
        ({**item, "sites": len(item["sites"]), "lots": sorted(item["lots"])} for item in markets.values()),
        key=lambda item: (-item["units"], item["country"]),
    )


def by_site(lots: list[dict]) -> list[dict]:
    sites: dict[tuple, dict] = {}
    for lot in lots:
        for shipment in lot["shipments"]:
            key = (shipment["consignee"], shipment["consignee_type"], shipment["country"])
            item = sites.setdefault(
                key,
                {
                    "consignee": key[0],
                    "consignee_type": key[1],
                    "country": key[2],
                    "units": 0,
                    "lots": set(),
                },
            )
            item["units"] += shipment["units"]
            item["lots"].add(lot["lot_identifier"])
    return _sites(sites.values())


def field_scope(db: Session, tenant_id, factor: dict) -> dict[str, Any]:
    """The lot impact list for ``factor`` over the organization's lots (its fingerprint as the case's list gives it),
    with by market and by site beside the fingerprinted material, the cases that hold its lots' complaints, and the
    changes recorded on the component."""
    listed = lot_impact.build(db, tenant_id, factor, [])
    ids = [row["id"] for row in listed["lots"]]
    cases = (
        [
            rowdict(row)
            for row in db.execute(
                text(
                    "SELECT DISTINCT i.id, i.business_id, i.investigation_identifier FROM investigations i "
                    "JOIN investigation_complaints ic ON ic.tenant_id=i.tenant_id AND ic.investigation_id=i.id "
                    "JOIN complaints c ON c.tenant_id=ic.tenant_id AND c.id=ic.complaint_id "
                    "WHERE i.tenant_id=:t AND c.lot_batch_id = ANY(CAST(:l AS uuid[])) "
                    "ORDER BY i.investigation_identifier"
                ),
                {"t": tenant_id, "l": ids},
            ).mappings()
        ]
        if ids
        else []
    )
    changes = []
    if factor["kind"] == lot_impact.COMPONENT_LOT:
        changes = [
            rowdict(row)
            for row in db.execute(
                text(
                    "SELECT ch.id, ch.business_id, ch.change_identifier, ch.change_type FROM reality_relationships rr "
                    "JOIN changes ch ON ch.tenant_id=rr.tenant_id AND ch.id=rr.source_entity_id "
                    "WHERE rr.tenant_id=:t AND rr.source_entity_type='Change' AND rr.target_entity_type='Component' "
                    "AND rr.target_entity_id=CAST(:c AS uuid) ORDER BY ch.change_identifier"
                ),
                {"t": tenant_id, "c": factor["id"]},
            ).mappings()
        ]
    return {
        **listed,
        "factor": {**listed["factor"], "kind_label": lot_impact.KIND_LABELS[factor["kind"]]},
        # Beside the fingerprinted list, never inside it: the same list signs the same whatever the view adds.
        "by_market": by_market(listed["lots"]),
        "by_site": by_site(listed["lots"]),
        "investigations": cases,
        "changes": changes,
        "whole_organization": True,
        "never_decides": lot_impact.NEVER_DECIDES,
        "not_imported": lot_impact.NOT_IMPORTED,
        "cannot_tell": CANNOT_TELL,
    }
