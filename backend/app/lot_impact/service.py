"""The lot impact list, read from the records (no AI): every lot that shares the suspect factor a person chose.

- **The factor** is a component lot (genealogy: ``lot_components.component_lot_identifier``), a supplier (a recorded
  supplier of a component the lot's genealogy names, ``component_suppliers``) or a product version. MDARIX suggests
  the one most of the case's in-scope lots share; the person chooses.
- **Each lot**: units released (``lot_batches.quantity``), its complaints and complaints per 1,000 units released,
  units shipped by country and consignee, still in stock (released minus shipped), and the evidence that it shares the
  factor. A lot without distribution rows is "distribution not imported", never zero units.
- **Totals** over the lots kept in the list (an excluded lot needs a reason), with units shipped by country.
- **The fingerprint** (SHA-256 of the list) is what a person signs; a later change of the data or the list shows as
  "changed since signed", with what changed.

MDARIX never decides: it lists, recommends no recall or other field action, and submits nothing.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.business_ids import as_uuid
from backend.app.db.models.foundation import (
    Complaint,
    Component,
    ComponentSupplier,
    LotBatch,
    LotComponent,
    Product,
    ProductVersion,
    Supplier,
)
from backend.app.db.models.lot_impact import LotDistribution

COMPONENT_LOT, SUPPLIER, PRODUCT_VERSION = "COMPONENT_LOT", "SUPPLIER", "PRODUCT_VERSION"
FACTOR_KINDS = (COMPONENT_LOT, SUPPLIER, PRODUCT_VERSION)
KIND_LABELS = {COMPONENT_LOT: "Component lot", SUPPLIER: "Supplier", PRODUCT_VERSION: "Product version"}
# The most specific factor wins a tie in the suggestion.
_SPECIFIC = {COMPONENT_LOT: 0, SUPPLIER: 1, PRODUCT_VERSION: 2}
REASON_MIN, REASON_MAX = 10, 500
NOT_IMPORTED = "Distribution not imported"
NEVER_DECIDES = (
    "MDARIX lists the lots that share the factor you chose, from your records. It recommends no recall and no other "
    "field action: you decide any field action in your QMS, under your procedure. MDARIX submits nothing."
)
LOTS_MAX = 2000


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _day(value) -> str | None:
    if value is None:
        return None
    return (value.date() if hasattr(value, "date") else value).isoformat()


def clean_factor(kind, ref, lot=None) -> dict | None:
    """``{kind, id, lot}`` from a request or a stored list, or None when it names no factor."""
    kind = str(kind or "").upper()
    key = as_uuid(ref)
    if kind not in FACTOR_KINDS or key is None:
        return None
    lot_text = " ".join(str(lot or "").split())[:120] or None
    if kind == COMPONENT_LOT and not lot_text:
        return None
    return {"kind": kind, "id": str(key), "lot": lot_text if kind == COMPONENT_LOT else None}


# ------------------------------------------------------------------------------------------------- reading


def _product_names(db: Session, tenant_id, version_ids) -> dict[str, tuple[str, str]]:
    """``{version id: (product name, version)}``."""
    ids = [item for item in {as_uuid(value) for value in version_ids} if item is not None]
    if not ids:
        return {}
    rows = (
        db.query(ProductVersion.id, Product.name, ProductVersion.version_identifier)
        .join(Product, (Product.id == ProductVersion.product_id) & (Product.tenant_id == ProductVersion.tenant_id))
        .filter(ProductVersion.tenant_id == tenant_id, ProductVersion.id.in_(ids))
        .all()
    )
    return {str(row[0]): (row[1], row[2]) for row in rows}


def resolve(db: Session, tenant_id, factor: dict | None) -> dict | None:
    """The factor with its label, when it is one of the organization's records (and, for a component lot, when a
    genealogy row names it); None otherwise."""
    if not factor:
        return None
    key = uuid.UUID(factor["id"])
    if factor["kind"] == COMPONENT_LOT:
        component = db.query(Component).filter(Component.tenant_id == tenant_id, Component.id == key).first()
        named = (
            component is not None
            and db.query(LotComponent.id)
            .filter(
                LotComponent.tenant_id == tenant_id,
                LotComponent.component_id == key,
                LotComponent.component_lot_identifier == factor["lot"],
            )
            .first()
            is not None
        )
        if not named:
            return None
        return {**factor, "label": f"{component.name} lot {factor['lot']}", "kind_label": KIND_LABELS[COMPONENT_LOT]}
    if factor["kind"] == SUPPLIER:
        supplier = db.query(Supplier).filter(Supplier.tenant_id == tenant_id, Supplier.id == key).first()
        if supplier is None:
            return None
        return {**factor, "label": supplier.name, "kind_label": KIND_LABELS[SUPPLIER]}
    names = _product_names(db, tenant_id, [key])
    if str(key) not in names:
        return None
    product, version = names[str(key)]
    return {**factor, "label": f"{product} {version}", "kind_label": KIND_LABELS[PRODUCT_VERSION]}


def matching(db: Session, tenant_id, factor: dict) -> dict[str, list[str]]:
    """``{lot id: [evidence]}``: every lot of the organization that shares the factor, with the record that says so."""
    found: dict[str, list[str]] = defaultdict(list)
    key = uuid.UUID(factor["id"])
    if factor["kind"] == PRODUCT_VERSION:
        product, version = _product_names(db, tenant_id, [key]).get(str(key), ("", ""))
        for (lot_id,) in db.query(LotBatch.id).filter(
            LotBatch.tenant_id == tenant_id, LotBatch.product_version_id == key
        ):
            found[str(lot_id)].append(f"The lot builds {product} {version} (lot record)")
        return dict(found)
    query = db.query(LotComponent.lot_batch_id, LotComponent.component_lot_identifier, Component).join(
        Component, (Component.id == LotComponent.component_id) & (Component.tenant_id == LotComponent.tenant_id)
    )
    if factor["kind"] == COMPONENT_LOT:
        rows = query.filter(
            LotComponent.tenant_id == tenant_id,
            LotComponent.component_id == key,
            LotComponent.component_lot_identifier == factor["lot"],
        )
        for lot_id, component_lot, component in rows:
            found[str(lot_id)].append(f"Lot genealogy: built with {component.name} lot {component_lot}")
        return dict(found)
    supplier = db.query(Supplier.name).filter(Supplier.tenant_id == tenant_id, Supplier.id == key).scalar()
    rows = query.join(
        ComponentSupplier,
        (ComponentSupplier.component_id == LotComponent.component_id)
        & (ComponentSupplier.tenant_id == LotComponent.tenant_id),
    ).filter(LotComponent.tenant_id == tenant_id, ComponentSupplier.supplier_id == key)
    for lot_id, component_lot, component in rows:
        part = component.name + (f" lot {component_lot}" if component_lot else "")
        found[str(lot_id)].append(f"Lot genealogy: built with {part}; {supplier} is a recorded supplier of it")
    return dict(found)


def in_scope_lots(db: Session, tenant_id, scope_data: dict) -> list[str]:
    """The case's lots: the scope's lots, else the lots its included complaints name."""
    from backend.app.case_workflow.scope import lots_of_complaints

    lots = list(scope_data.get("lot_ids") or ())
    if lots:
        return lots
    return lots_of_complaints(db, tenant_id, scope_data.get("included_complaint_ids") or ())


def options(db: Session, tenant_id, product_id, scope_lots: list[str]) -> dict:
    """The factors a person can choose for a case of ``product_id``: the component lots and suppliers its lots'
    genealogy names, and its versions, each with how many of the product's lots and of the case's lots share it, and
    the suggestion: the factor most of the case's lots share (the most specific one on a tie). Never chosen for the
    person."""
    product_lots = {
        str(lot_id): str(version_id) if version_id else None
        for lot_id, version_id in db.query(LotBatch.id, LotBatch.product_version_id)
        .join(
            ProductVersion,
            (ProductVersion.id == LotBatch.product_version_id) & (ProductVersion.tenant_id == LotBatch.tenant_id),
        )
        .filter(LotBatch.tenant_id == tenant_id, ProductVersion.product_id == product_id)
    }
    scope = set(scope_lots)
    counts: dict[tuple, set[str]] = defaultdict(set)
    labels: dict[tuple, str] = {}
    genealogy = (
        db.query(LotComponent.lot_batch_id, LotComponent.component_id, LotComponent.component_lot_identifier, Component)
        .join(Component, (Component.id == LotComponent.component_id) & (Component.tenant_id == LotComponent.tenant_id))
        .filter(
            LotComponent.tenant_id == tenant_id, LotComponent.lot_batch_id.in_([uuid.UUID(i) for i in product_lots])
        )
        .all()
        if product_lots
        else []
    )
    components: dict[str, set[str]] = defaultdict(set)
    for lot_id, component_id, component_lot, component in genealogy:
        components[str(component_id)].add(str(lot_id))
        if component_lot:
            key = (COMPONENT_LOT, str(component_id), component_lot)
            counts[key].add(str(lot_id))
            labels[key] = f"{component.name} lot {component_lot}"
    if components:
        for component_id, supplier_id, name in (
            db.query(ComponentSupplier.component_id, Supplier.id, Supplier.name)
            .join(Supplier, (Supplier.id == ComponentSupplier.supplier_id) & (Supplier.tenant_id == tenant_id))
            .filter(
                ComponentSupplier.tenant_id == tenant_id,
                ComponentSupplier.component_id.in_([uuid.UUID(i) for i in components]),
            )
        ):
            key = (SUPPLIER, str(supplier_id), None)
            counts[key] |= components[str(component_id)]
            labels[key] = name
    versions = [
        str(row[0])
        for row in db.query(ProductVersion.id).filter(
            ProductVersion.tenant_id == tenant_id, ProductVersion.product_id == product_id
        )
    ]
    names = _product_names(db, tenant_id, versions)
    for version_id in versions:
        key = (PRODUCT_VERSION, version_id, None)
        counts[key] |= {lot for lot, version in product_lots.items() if version == version_id}
        labels[key] = " ".join(names.get(version_id, ("", "")))
    items = [
        {
            "kind": kind,
            "kind_label": KIND_LABELS[kind],
            "id": ref,
            "lot": lot,
            "label": labels[(kind, ref, lot)],
            "lots": len(lots),
            "case_lots": len(lots & scope),
        }
        for (kind, ref, lot), lots in counts.items()
    ]
    items.sort(key=lambda item: (_SPECIFIC[item["kind"]], -item["case_lots"], -item["lots"], item["label"]))
    best = min(
        (item for item in items if item["case_lots"]),
        key=lambda item: (-item["case_lots"], _SPECIFIC[item["kind"]], -item["lots"], item["label"]),
        default=None,
    )
    suggestion = None
    if best is not None:
        suggestion = {
            **{key: best[key] for key in ("kind", "id", "lot", "label", "kind_label")},
            "why": f"{best['case_lots']} of the investigation's {len(scope)} {'lot' if len(scope) == 1 else 'lots'} share it",
        }
    return {"items": items, "suggestion": suggestion, "case_lots": len(scope), "genealogy": bool(genealogy)}


def _shipments(db: Session, tenant_id, lot_ids: list[uuid.UUID]) -> dict[str, list[LotDistribution]]:
    found: dict[str, list[LotDistribution]] = defaultdict(list)
    if not lot_ids:
        return found
    for row in (
        db.query(LotDistribution)
        .filter(LotDistribution.tenant_id == tenant_id, LotDistribution.lot_batch_id.in_(lot_ids))
        .order_by(LotDistribution.ship_date, LotDistribution.country, LotDistribution.consignee)
    ):
        found[str(row.lot_batch_id)].append(row)
    return found


def _by_country(pairs) -> list[dict]:
    totals: dict[str, int] = defaultdict(int)
    for country, quantity in pairs:
        totals[country] += quantity
    return [
        {"country": country, "units": units} for country, units in sorted(totals.items(), key=lambda i: (-i[1], i[0]))
    ]


def per_thousand(complaints: int, released: int | None) -> float | None:
    return round(1000 * complaints / released, 1) if released else None


def build(db: Session, tenant_id, factor: dict, excluded: list[dict]) -> dict:
    """The list for a resolved factor: each lot sharing it, with complaints first, then the totals of the lots kept.
    ``excluded`` is ``[{lot_id, reason}]``; an excluded lot stays listed, marked, and out of the totals."""
    from backend.app.human_decision.rules import fingerprint

    matches = matching(db, tenant_id, factor)
    ids = [uuid.UUID(item) for item in list(matches)[:LOTS_MAX]]
    lots = db.query(LotBatch).filter(LotBatch.tenant_id == tenant_id, LotBatch.id.in_(ids)).all() if ids else []
    names = _product_names(db, tenant_id, [lot.product_version_id for lot in lots if lot.product_version_id])
    complaints = dict(
        db.query(Complaint.lot_batch_id, func.count(Complaint.id))
        .filter(Complaint.tenant_id == tenant_id, Complaint.lot_batch_id.in_(ids))
        .group_by(Complaint.lot_batch_id)
        .all()
        if ids
        else []
    )
    shipments = _shipments(db, tenant_id, ids)
    reasons = {item["lot_id"]: item["reason"] for item in excluded}
    rows = []
    for lot in lots:
        key = str(lot.id)
        shipped_rows = shipments.get(key, [])
        imported = bool(shipped_rows)
        shipped = sum(row.quantity for row in shipped_rows) if imported else None
        count = int(complaints.get(lot.id, 0))
        product, version = names.get(str(lot.product_version_id), (None, None))
        rows.append(
            {
                "id": key,
                "business_id": lot.business_id,
                "lot_identifier": lot.lot_identifier,
                "product": product,
                "version": version,
                "made_on": _day(lot.effective_timestamp or lot.created_at),
                "released": lot.quantity,
                "complaints": count,
                "per_1000": per_thousand(count, lot.quantity),
                "distribution_imported": imported,
                "shipped": shipped,
                "in_stock": (lot.quantity - shipped) if imported and lot.quantity is not None else None,
                "over_shipped": bool(imported and lot.quantity is not None and shipped > lot.quantity),
                "by_country": _by_country((row.country, row.quantity) for row in shipped_rows),
                "shipments": [
                    {
                        "consignee": row.consignee,
                        "consignee_type": row.consignee_type,
                        "consignee_reference": row.consignee_reference,
                        "country": row.country,
                        "units": row.quantity,
                        "ship_date": _iso(row.ship_date),
                    }
                    for row in shipped_rows
                ],
                "evidence": matches.get(key, []),
                "excluded": key in reasons,
                "exclusion_reason": reasons.get(key),
            }
        )
    rows.sort(key=lambda row: (row["complaints"] == 0, -row["complaints"], row["lot_identifier"]))
    kept = [row for row in rows if not row["excluded"]]
    imported = [row for row in kept if row["distribution_imported"]]
    totals = {
        "lots": len(kept),
        "with_complaints": sum(1 for row in kept if row["complaints"]),
        "without_complaints": sum(1 for row in kept if not row["complaints"]),
        "excluded": len(rows) - len(kept),
        "complaints": sum(row["complaints"] for row in kept),
        "released": sum(row["released"] or 0 for row in kept),
        "released_unknown": sum(1 for row in kept if row["released"] is None),
        "shipped": sum(row["shipped"] for row in imported),
        "in_stock": sum(row["in_stock"] for row in imported if row["in_stock"] is not None),
        "not_imported": len(kept) - len(imported),
        "by_country": _by_country(
            (country["country"], country["units"]) for row in imported for country in row["by_country"]
        ),
    }
    material = {"factor": {key: factor[key] for key in ("kind", "id", "lot", "label")}, "lots": rows, "totals": totals}
    return {**material, "fingerprint": fingerprint(material), "truncated": len(matches) > LOTS_MAX}


_COMPARED = (
    ("complaints", "complaints"),
    ("released", "units released"),
    ("shipped", "units shipped"),
    ("in_stock", "units in stock"),
)


def changes(signed: dict, current: dict) -> list[str]:
    """What differs between the signed list and the list now, in plain words (empty when nothing does)."""
    found: list[str] = []
    if signed["factor"]["label"] != current["factor"]["label"] or signed["factor"]["id"] != current["factor"]["id"]:
        found.append(f"The suspect factor is now {current['factor']['label']} (signed: {signed['factor']['label']})")
    before = {row["id"]: row for row in signed["lots"]}
    after = {row["id"]: row for row in current["lots"]}
    for row in current["lots"]:
        if row["id"] not in before:
            found.append(f"{row['lot_identifier']} now shares the factor")
    for row in signed["lots"]:
        if row["id"] not in after:
            found.append(f"{row['lot_identifier']} no longer shares the factor")
    for row in current["lots"]:
        old = before.get(row["id"])
        if old is None:
            continue
        name = row["lot_identifier"]
        moved = old["distribution_imported"] != row["distribution_imported"]
        if moved:
            found.append(
                f"{name}: distribution now imported ({row['shipped']} units shipped)"
                if row["distribution_imported"]
                else f"{name}: distribution no longer imported"
            )
        for key, label in _COMPARED:
            if old[key] != row[key] and not (moved and key in ("shipped", "in_stock")):
                found.append(f"{name}: {label} {old[key] if old[key] is not None else '-'} to {row[key]}")
        if old["excluded"] != row["excluded"]:
            found.append(f"{name}: {'now excluded' if row['excluded'] else 'back in the list'}")
        if old["by_country"] != row["by_country"] and old["shipped"] == row["shipped"]:
            found.append(f"{name}: units by country changed")
    return found


def signature_meaning(case_ref: str, label: str, lots: int) -> str:
    return (
        f"I confirm this list of {lots} {'lot' if lots == 1 else 'lots'} sharing {label} for case {case_ref}, as "
        "the records show it. MDARIX recommends no field action; any field action is decided in our QMS."
    )
