"""Getting started › Automatic insights: the headline numbers, the monthly trend, a compact list of the complaints for
filtering on screen, and the questions to ask next, each answered in place from the workspace's own records.

Every answer is computed by fixed rules, never by a model: it counts, compares or lists what the records hold, names the
records it used (``basis``, ``ids``) and says what the records lack to answer more (``missing``). Where the records
cannot answer, the answer says so instead of guessing. Answers say where complaints come from, what they concern and
what rose; they never say why. A question is asked only when the records hold what its answer needs.

imports.insights() calls build() with the complaints in its scope (the trial's uploads, else the sample) and the
tenant's products, versions and lots; everything read here is filtered to the same tenant.
"""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.db.models.foundation import (
    Change,
    Complaint,
    Component,
    ComponentSupplier,
    Investigation,
    LotBatch,
    ManufacturingSite,
    ProductComponent,
    RealityRelationship,
    Supplier,
    Unknown,
)

# The months compared with the ones before them: the trend highlights them and the rise is measured on them.
RECENT_MONTHS = 3
# Fewer months than this and there is nothing before the recent window to compare it with.
TREND_MIN_MONTHS = RECENT_MONTHS + 1
# A problem code counts as rising with at least this many complaints in the recent window (one complaint is not a rise).
RISING_MIN_RECENT = 2
# Record IDs an answer lists; the count beyond is given as a number.
IDS_MAX = 100
# Rows of an answer's table and bars of its chart.
ROWS_MAX = 12


def month_of(complaint: Complaint) -> str | None:
    """The complaint's month (YYYY-MM): received, else the event, else when the record was made (as by_month counts)."""
    when = complaint.complaint_timestamp or complaint.event_timestamp or complaint.created_at
    return when.strftime("%Y-%m") if when else None


def month_series(months: list[str]) -> list[str]:
    """Every month from the first to the last given, so a month without complaints shows as a zero."""
    if not months:
        return []
    first, last = min(months), max(months)
    year, month = int(first[:4]), int(first[5:7])
    series = []
    while f"{year:04d}-{month:02d}" <= last:
        series.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return series


def windows(series: list[str]) -> tuple[list[str], list[str]] | None:
    """The recent months and the months before them; None when there are too few months to compare."""
    if len(series) < TREND_MIN_MONTHS:
        return None
    return series[-RECENT_MONTHS:], series[:-RECENT_MONTHS]


def month_label(month: str) -> str:
    return datetime.strptime(month, "%Y-%m").strftime("%b %Y")


def _count(n: int, noun: str, plural: str | None = None) -> str:
    return f"{n:,} {noun if n == 1 else (plural or noun + 's')}"


def _rate(value: float) -> str:
    return f"{value:.1f}"


def _day(value) -> str | None:
    return value.strftime("%d %b %Y").lstrip("0") if value else None


def _shorten(text: str | None, length: int = 160) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= length else value[: length - 1].rsplit(" ", 1)[0] + "…"


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _answer(summary, *, basis, table=None, bars=None, facts=(), ids=(), cases=(), missing=()) -> dict:
    ids = list(dict.fromkeys(ids))
    return {
        "summary": summary,
        "table": table,
        "bars": bars,
        "facts": list(facts),
        "ids": ids[:IDS_MAX],
        "ids_total": len(ids),
        "cases": list(cases),
        "basis": basis,
        "missing": list(missing),
    }


class _Records:
    """The complaints in scope with the tenant's products, versions, lots and sites, and the counts answers share."""

    def __init__(self, db: Session, tenant_id, scope: str, complaints, products, versions, lots):
        self.db, self.tenant_id, self.scope = db, tenant_id, scope
        self.complaints: list[Complaint] = complaints
        self.products: dict = products
        self.versions: dict = versions
        self.lots: dict = lots
        self.sites = {
            site.id: site for site in db.query(ManufacturingSite).filter(ManufacturingSite.tenant_id == tenant_id).all()
        }
        self.months = {complaint.id: month_of(complaint) for complaint in complaints}
        self.series = month_series([month for month in self.months.values() if month])
        self.windows = windows(self.series)
        self._components: dict = {}

    def version_label(self, version_id) -> str | None:
        version = self.versions.get(version_id)
        if version is None:
            return None
        product = self.products.get(version.product_id)
        return f"{product.name} {version.version_identifier}" if product else version.version_identifier

    def lot_label(self, lot_id) -> str | None:
        lot = self.lots.get(lot_id)
        return lot.lot_identifier if lot else None

    def tally(self, key, complaints=None) -> list[tuple]:
        counts: dict = {}
        for complaint in self.complaints if complaints is None else complaints:
            value = key(complaint)
            if value is not None:
                counts[value] = counts.get(value, 0) + 1
        return sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))

    def averages(self, complaints) -> tuple[float, float] | None:
        """Complaints per month in the recent months and in the months before, over the whole series."""
        if self.windows is None:
            return None
        recent, earlier = self.windows
        months = [self.months[complaint.id] for complaint in complaints]
        return (
            sum(month in recent for month in months) / len(recent),
            sum(month in earlier for month in months) / len(earlier),
        )

    def components_of(self, version_id) -> list[dict]:
        """The components the version lists (Product 360 bill of materials), each with its suppliers."""
        if version_id not in self._components:
            self._components[version_id] = self._read_components(version_id)
        return self._components[version_id]

    def _read_components(self, version_id) -> list[dict]:
        rows = (
            self.db.query(Component)
            .join(
                ProductComponent,
                (ProductComponent.component_id == Component.id) & (ProductComponent.tenant_id == Component.tenant_id),
            )
            .filter(
                ProductComponent.tenant_id == self.tenant_id,
                ProductComponent.product_version_id == version_id,
                ProductComponent.relationship_status == "active",
            )
            .order_by(Component.name)
            .all()
        )
        suppliers: dict = {}
        if rows:
            for link, supplier in (
                self.db.query(ComponentSupplier, Supplier)
                .join(
                    Supplier,
                    (Supplier.id == ComponentSupplier.supplier_id)
                    & (Supplier.tenant_id == ComponentSupplier.tenant_id),
                )
                .filter(
                    ComponentSupplier.tenant_id == self.tenant_id,
                    ComponentSupplier.component_id.in_([row.id for row in rows]),
                )
                .order_by(Supplier.name)
            ):
                suppliers.setdefault(link.component_id, []).append(
                    {"name": supplier.name, "since": _day(link.effective_timestamp)}
                )
        return [{"id": row.id, "name": row.name, "suppliers": suppliers.get(row.id, [])} for row in rows]


def _component_text(component: dict) -> str:
    if not component["suppliers"]:
        return f"{component['name']}: no supplier recorded"
    suppliers = [
        f"{item['name']} since {item['since']}" if item["since"] else item["name"] for item in component["suppliers"]
    ]
    return f"{component['name']}: {_join(suppliers)}"


# --------------------------------------------------------------------------------------------- what the screen shows


def compact_records(records: _Records) -> tuple[list[dict], dict]:
    """One short row per complaint for filtering on screen, and the readable name of each version it names."""
    rows, labels = [], {}
    for complaint in records.complaints:
        version = records.versions.get(complaint.product_version_id)
        if version is not None and version.business_id not in labels:
            labels[version.business_id] = records.version_label(version.id)
        rows.append(
            {
                "id": complaint.business_id,
                "ref": complaint.complaint_identifier,
                "version": version.business_id if version else None,
                "lot": records.lot_label(complaint.lot_batch_id),
                "code": complaint.problem_code,
                "country": complaint.country,
                "month": records.months[complaint.id],
                "harm": bool(complaint.death or complaint.serious_injury),
                "malfunction": bool(complaint.malfunction),
                "status": complaint.status,
            }
        )
    return rows, labels


def headline(records: _Records) -> dict:
    """The numbers at the top of the panel, for every complaint in scope (the screen recomputes them for a filter)."""
    complaints = records.complaints
    total = len(complaints)
    top = records.tally(lambda c: c.product_version_id)
    top_version = None
    if top and total:
        version_id, n = top[0]
        top_version = {
            "label": records.version_label(version_id),
            "version": records.versions[version_id].version_identifier if version_id in records.versions else None,
            "complaints": n,
            "share": round(100 * n / total),
        }
    averages = records.averages(complaints)
    rate = None
    if averages is not None:
        recent, earlier = averages
        rate = {
            "recent": round(recent, 1),
            "earlier": round(earlier, 1),
            "direction": "up" if recent > earlier else "down" if recent < earlier else "flat",
        }
    return {
        "total": total,
        "harm": sum(1 for c in complaints if c.death or c.serious_injury),
        "malfunction": sum(1 for c in complaints if c.malfunction),
        "top_version": top_version,
        "rate": rate,
    }


def trend(records: _Records) -> dict:
    counts = dict(records.tally(lambda c: records.months[c.id]))
    averages = records.averages(records.complaints)
    return {
        "months": [{"month": month, "complaints": counts.get(month, 0)} for month in records.series],
        "recent_months": RECENT_MONTHS if averages is not None else 0,
        "recent_average": round(averages[0], 1) if averages else None,
        "earlier_average": round(averages[1], 1) if averages else None,
    }


# ------------------------------------------------------------------------------------------ the questions, answered


def _version_question(records: _Records) -> dict | None:
    """What changed in the version with the most complaints: it against the product's other versions, its components
    and suppliers, and the change records linked to the product or its components."""
    top = [item for item in records.tally(lambda c: c.product_version_id) if item[0] in records.versions]
    if not top:
        return None
    version = records.versions[top[0][0]]
    product = records.products.get(version.product_id)
    if product is None:
        return None
    # The version asked about first, then the product's other versions.
    siblings = sorted(
        (item for item in records.versions.values() if item.product_id == product.id),
        key=lambda item: (item.id != version.id, item.version_identifier),
    )
    last = records.series[-1] if records.series else None
    rows, parts, ids = [], [], []
    for sibling in siblings:
        own = [c for c in records.complaints if c.product_version_id == sibling.id]
        ids += [c.business_id for c in own] if sibling.id == version.id else []
        months = sorted(records.months[c.id] for c in own if records.months[c.id])
        first = months[0] if months else None
        span = len(month_series([first, last])) if first and last else 0
        per_month = len(own) / span if span else None
        lots = records.tally(lambda c: records.lot_label(c.lot_batch_id), own)[:2]
        codes = records.tally(lambda c: c.problem_code, own)[:2]
        rows.append(
            [
                sibling.version_identifier,
                _day(sibling.release_timestamp) or "—",
                len(own),
                _rate(per_month) if per_month is not None else "—",
                ", ".join(f"{lot} ({n})" for lot, n in lots) or "—",
                ", ".join(f"{code} ({n})" for code, n in codes) or "—",
            ]
        )
        parts.append(
            f"{sibling.version_identifier} has {_count(len(own), 'complaint')}, {_rate(per_month)} per month since "
            f"its first complaint in {month_label(first)}"
            if own and first
            else f"{sibling.version_identifier} has none"
        )
    summary = f"{product.name}: " + "; ".join(parts) + "."
    facts, missing = [], []
    components = records.components_of(version.id)
    if components:
        facts.append(
            f"{version.version_identifier} lists {_count(len(components), 'component')}: "
            + "; ".join(_component_text(item) for item in components)
            + "."
        )
        for sibling in siblings[1:]:
            theirs = records.components_of(sibling.id)
            if not theirs:
                missing.append(
                    f"{sibling.version_identifier} has no components recorded, so its parts cannot be compared."
                )
                continue
            mine = {item["name"]: item for item in components}
            other = {item["name"]: item for item in theirs}
            only = sorted(set(mine) - set(other))
            differ = sorted(
                name
                for name in set(mine) & set(other)
                if {s["name"] for s in mine[name]["suppliers"]} != {s["name"] for s in other[name]["suppliers"]}
            )
            if only:
                facts.append(
                    f"Listed for {version.version_identifier} but not {sibling.version_identifier}: {_join(only)}."
                )
            if differ:
                facts.append(
                    f"Supplied differently in {version.version_identifier} and {sibling.version_identifier}: "
                    f"{_join(differ)}."
                )
            if not only and not differ:
                facts.append(
                    f"{version.version_identifier} and {sibling.version_identifier} list the same components and "
                    "suppliers."
                )
    else:
        missing.append(f"{version.version_identifier} has no components recorded.")

    component_ids = {item["id"] for item in components}
    for sibling in siblings[1:]:
        component_ids |= {item["id"] for item in records.components_of(sibling.id)}
    # Change records reach a product or a component only through an AFFECTS relationship (business_imports.py); the
    # text of a change is not read for names, so only what the records link is shown.
    targets = (RealityRelationship.target_entity_type == "Product") & (
        RealityRelationship.target_entity_id == product.id
    )
    if component_ids:
        targets = targets | (
            (RealityRelationship.target_entity_type == "Component")
            & RealityRelationship.target_entity_id.in_(component_ids)
        )
    linked = records.db.query(RealityRelationship.source_entity_id).filter(
        RealityRelationship.tenant_id == records.tenant_id,
        RealityRelationship.source_entity_type == "Change",
        targets,
    )
    changes = (
        records.db.query(Change)
        .filter(Change.tenant_id == records.tenant_id, Change.id.in_(linked))
        .order_by(Change.event_timestamp.desc().nullslast(), Change.change_identifier)
        .limit(ROWS_MAX)
        .all()
    )
    for change in changes:
        when = _day(change.event_timestamp or change.effective_timestamp)
        facts.append(
            f"Change {change.change_identifier} ({change.change_type}{', ' + when if when else ''}): "
            f"{_shorten(change.description, 240)}"
        )
    if not changes:
        any_link = records.db.query(RealityRelationship.source_entity_id).filter(
            RealityRelationship.tenant_id == records.tenant_id, RealityRelationship.source_entity_type == "Change"
        )
        unlinked = (
            records.db.query(Change.change_identifier)
            .filter(
                Change.tenant_id == records.tenant_id,
                Change.source_system == records.scope,
                Change.id.not_in(any_link),
            )
            .order_by(Change.change_identifier)
            .all()
        )
        note = f"No change record is linked to {product.name} or its components."
        if unlinked:
            names = [row.change_identifier for row in unlinked[:5]]
            note += (
                f" {_count(len(unlinked), 'change record')} ({_join(names)}{' and more' if len(unlinked) > 5 else ''}) "
                f"{'is' if len(unlinked) == 1 else 'are'} not linked to any product or component, so "
                f"{'it is' if len(unlinked) == 1 else 'they are'} not shown here."
            )
        missing.append(note)
    return {
        "key": "version",
        "question": f"What changed in {product.name} {version.version_identifier}?",
        "answer": _answer(
            summary,
            table={
                "columns": ["Version", "Released", "Complaints", "Per month", "Top lots", "Top problem codes"],
                "rows": rows,
            },
            facts=facts,
            ids=ids,
            basis="Complaints by version and their months, lots and problem codes; the versions' release dates, "
            "components and suppliers; change records linked to the product or its components.",
            missing=missing,
        ),
    }


def _lot_row(records: _Records, lot: LotBatch, complaints: int) -> list:
    site = records.sites.get(lot.manufacturing_site_id)
    return [
        lot.lot_identifier,
        records.version_label(lot.product_version_id) or "—",
        site.name if site else "—",
        f"{lot.quantity:,}" if lot.quantity else "—",
        complaints,
        _rate(100 * complaints / lot.quantity) if lot.quantity else "—",
    ]


def _lots_question(records: _Records) -> dict | None:
    """What the two lots with the most complaints have in common, as far as the records link them."""
    top = [(records.lots[lot_id], n) for lot_id, n in records.tally(lambda c: c.lot_batch_id) if lot_id in records.lots]
    if not top:
        return None
    pair = top[:2]
    lots = [lot for lot, _n in pair]
    names = [lot.lot_identifier for lot in lots]
    together = sum(n for _lot, n in pair)
    total = len(records.complaints)
    facts, missing = [], []
    if len(lots) == 1:
        lot = lots[0]
        question = f"What do the records say about lot {lot.lot_identifier}?"
        label = records.version_label(lot.product_version_id)
        summary = (
            f"Lot {lot.lot_identifier}" + (f" ({label})" if label else "") + f" has {together} of "
            f"{_count(total, 'complaint')}."
        )
    else:
        question = f"What do lots {names[0]} and {names[1]} have in common?"
        first, second = lots
        shared = []
        if first.product_version_id and first.product_version_id == second.product_version_id:
            shared.append(f"{records.version_label(first.product_version_id)} lots")
        site = records.sites.get(first.manufacturing_site_id)
        if site and first.manufacturing_site_id == second.manufacturing_site_id:
            shared.append(f"made at {site.name}")
        if shared:
            opening = f"Lots {names[0]} and {names[1]} are both " + " ".join(shared)
        elif first.product_version_id and second.product_version_id:
            opening = (
                f"Lots {names[0]} and {names[1]} are of different versions "
                f"({records.version_label(first.product_version_id)} and "
                f"{records.version_label(second.product_version_id)})"
            )
        else:
            opening = f"The records name no version or site that lots {names[0]} and {names[1]} share"
        summary = f"{opening}; together they have {together} of {_count(total, 'complaint')}."
    version_ids = list(dict.fromkeys(lot.product_version_id for lot in lots if lot.product_version_id))
    parts = {version_id: records.components_of(version_id) for version_id in version_ids}
    if len(lots) == 2 and len(version_ids) == 1 and parts[version_ids[0]]:
        facts.append(
            f"Both lots are {records.version_label(version_ids[0])}, whose recorded components and suppliers are: "
            + "; ".join(_component_text(item) for item in parts[version_ids[0]])
            + "."
        )
    elif len(lots) == 2 and len(version_ids) == 2 and all(parts.values()):
        first, second = ({_component_text(item) for item in parts[v]} for v in version_ids)
        common = sorted(first & second)
        facts.append(
            "Components and suppliers listed for both versions: " + "; ".join(common) + "."
            if common
            else "The two versions list no component with the same supplier."
        )
    elif len(lots) == 1 and version_ids and parts[version_ids[0]]:
        facts.append(
            f"{records.version_label(version_ids[0])} lists: "
            + "; ".join(_component_text(item) for item in parts[version_ids[0]])
            + "."
        )
    else:
        missing.append("No components are recorded for the versions of these lots.")
    missing.append(
        "The records do not link a lot to the component lots or supplier deliveries that went into it, so which "
        "parts each lot used is not known."
    )
    for lot in lots:
        if lot.product_version_id is None:
            missing.append(f"Lot {lot.lot_identifier} has no product version recorded.")
        if lot.manufacturing_site_id is None:
            missing.append(f"Lot {lot.lot_identifier} has no manufacturing site recorded.")
        if not lot.quantity:
            missing.append(f"Lot {lot.lot_identifier} has no quantity, so complaints per 100 units cannot be shown.")
    ids = [c.business_id for c in records.complaints if c.lot_batch_id in {lot.id for lot in lots}]
    return {
        "key": "lots",
        "question": question,
        "answer": _answer(
            summary,
            table={
                "columns": ["Lot", "Version", "Site", "Quantity", "Complaints", "Per 100 units"],
                "rows": [_lot_row(records, lot, n) for lot, n in pair],
            },
            facts=facts,
            ids=ids,
            basis="The lots' version, manufacturing site and quantity; their complaints; the components and suppliers "
            "the versions list.",
            missing=missing,
        ),
    }


def _rise_question(records: _Records) -> dict | None:
    """Whether the rise holds per unit: complaints per 1,000 units, lot by lot and version by version."""
    averages = records.averages(records.complaints)
    if averages is None or averages[0] <= averages[1]:
        return None
    recent, earlier = averages
    rose = f"Complaints rose from {_rate(earlier)} to {_rate(recent)} per month"
    counts = dict(records.tally(lambda c: c.lot_batch_id))
    with_complaints = [records.lots[lot_id] for lot_id in counts if lot_id in records.lots]
    without_quantity = sorted(lot.lot_identifier for lot in with_complaints if not lot.quantity)
    rows = [
        [
            lot.lot_identifier,
            records.version_label(lot.product_version_id) or "—",
            f"{lot.quantity:,}" if lot.quantity else "—",
            counts[lot.id],
            _rate(1000 * counts[lot.id] / lot.quantity) if lot.quantity else "—",
        ]
        for lot in sorted(with_complaints, key=lambda lot: (-counts[lot.id], lot.lot_identifier))
    ][:ROWS_MAX]
    # A version's rate counts all its lots, those without complaints too: their units are in the field as well.
    rates = []
    version_ids = {lot.product_version_id for lot in with_complaints if lot.product_version_id}
    for version_id in version_ids:
        all_lots = [lot for lot in records.lots.values() if lot.product_version_id == version_id]
        if not all_lots or any(not lot.quantity for lot in all_lots):
            continue
        units = sum(lot.quantity for lot in all_lots)
        n = sum(counts.get(lot.id, 0) for lot in all_lots)
        rates.append((1000 * n / units, records.version_label(version_id), n, units))
    rates.sort(key=lambda item: (-item[0], item[1]))
    missing = []
    if without_quantity:
        missing.append(
            f"{_count(len(without_quantity), 'lot')} with complaints {'has' if len(without_quantity) == 1 else 'have'} "
            f"no quantity ({_join(without_quantity[:5])}{' and more' if len(without_quantity) > 5 else ''})."
        )
    if not rates:
        summary = f"{rose}, but lot quantities are missing, so complaints per unit cannot be shown."
        missing.append("Lot quantities (the quantity column of the lots file) are needed to count per unit.")
    else:
        shown = [
            f"{label} {_rate(rate)} ({_count(n, 'complaint')} from {units:,} units)"
            for rate, label, n, units in rates[:3]
        ]
        summary = f"{rose}. Per 1,000 units released: " + "; ".join(shown) + "."
    no_lot = sum(1 for c in records.complaints if c.lot_batch_id not in records.lots)
    if no_lot:
        missing.append(
            f"{_count(no_lot, 'complaint')} {'names' if no_lot == 1 else 'name'} no lot and cannot be counted per unit."
        )
    return {
        "key": "rise",
        "question": "Is the rise real, or just more devices in use?",
        "answer": _answer(
            summary,
            table={"columns": ["Lot", "Version", "Quantity", "Complaints", "Per 1,000 units"], "rows": rows},
            ids=[],
            basis=f"Complaints per month, the last {RECENT_MONTHS} months against the months before; complaints per "
            "lot; lot quantities as recorded.",
            missing=missing,
        ),
    }


def _harm_question(records: _Records) -> dict | None:
    """The complaints that report a death, a serious injury or a malfunction."""
    recorded = [
        c for c in records.complaints if any(flag is not None for flag in (c.death, c.serious_injury, c.malfunction))
    ]
    if not recorded:
        return None
    deaths = [c for c in records.complaints if c.death]
    injuries = [c for c in records.complaints if c.serious_injury and not c.death]
    harm = [c for c in records.complaints if c.death or c.serious_injury]
    malfunctions = [c for c in records.complaints if c.malfunction]
    if not harm and not malfunctions:
        summary = (
            f"None of the {_count(len(recorded), 'complaint')} that record these fields report harm or a malfunction."
        )
    else:
        kinds = [_count(len(deaths), "death")] if deaths else []
        kinds += [_count(len(injuries), "serious injury", "serious injuries")] if injuries else []
        summary = (
            f"{_count(len(harm), 'complaint')} {'reports' if len(harm) == 1 else 'report'} harm"
            + (f" ({_join(kinds)})" if kinds else "")
            + f" and {_count(len(malfunctions), 'complaint')} {'reports' if len(malfunctions) == 1 else 'report'} "
            "a malfunction."
        )
    flagged = [c for c in records.complaints if c.death or c.serious_injury or c.malfunction]
    rows = [
        [
            c.business_id,
            records.version_label(c.product_version_id) or "—",
            c.problem_code or "—",
            ", ".join(
                label
                for flag, label in (
                    (c.death, "Death"),
                    (c.serious_injury, "Serious injury"),
                    (c.malfunction, "Malfunction"),
                )
                if flag
            ),
        ]
        for c in sorted(flagged, key=lambda c: (not (c.death or c.serious_injury), c.business_id))
    ][:ROWS_MAX]
    empty = len(records.complaints) - len(recorded)
    missing = []
    if empty:
        verb = "leaves" if empty == 1 else "leave"
        missing.append(f"{_count(empty, 'complaint')} {verb} death, serious injury and malfunction empty.")
    return {
        "key": "harm",
        "question": "Which complaints report harm or a malfunction?",
        "answer": _answer(
            summary,
            table={"columns": ["Complaint", "Version", "Problem code", "Reports"], "rows": rows} if rows else None,
            ids=[c.business_id for c in flagged],
            basis="The death, serious injury and malfunction fields of each complaint.",
            missing=missing,
        ),
    }


def _codes_question(records: _Records) -> dict | None:
    """Problem codes with more complaints per month in the recent months than before."""
    coded = [c for c in records.complaints if c.problem_code]
    if not coded or records.windows is None:
        return None
    recent_months, _earlier = records.windows
    rising = []
    for code, _n in records.tally(lambda c: c.problem_code):
        own = [c for c in coded if c.problem_code == code]
        recent, earlier = records.averages(own)
        recent_count = sum(1 for c in own if records.months[c.id] in recent_months)
        if recent > earlier and recent_count >= RISING_MIN_RECENT:
            rising.append((code, recent, earlier, recent_count, own))
    period = f"{month_label(recent_months[0])} to {month_label(recent_months[-1])}"
    window = f"the last {RECENT_MONTHS} months ({period})"
    if rising:
        summary = (
            f"{_count(len(rising), 'problem code')} rose in {window}: "
            + "; ".join(f"{code} from {_rate(e)} to {_rate(r)} per month" for code, r, e, _c, _o in rising[:3])
            + ("; and more" if len(rising) > 3 else "")
            + "."
        )
    else:
        summary = (
            f"No problem code rose in {window}: none has at least {RISING_MIN_RECENT} complaints in those months "
            "and more per month than before."
        )
    missing = []
    uncoded = len(records.complaints) - len(coded)
    if uncoded:
        missing.append(
            f"{_count(uncoded, 'complaint')} {'has' if uncoded == 1 else 'have'} no problem code and "
            f"{'is' if uncoded == 1 else 'are'} not counted here."
        )
    return {
        "key": "codes",
        "question": "Which problem codes are rising?",
        "answer": _answer(
            summary,
            table={
                "columns": ["Problem code", f"Last {RECENT_MONTHS} months", "Per month before", "Per month now"],
                "rows": [[code, c, _rate(e), _rate(r)] for code, r, e, c, _o in rising[:ROWS_MAX]],
            }
            if rising
            else None,
            ids=[c.business_id for *_rest, own in rising for c in own],
            basis=f"Problem codes by month, the last {RECENT_MONTHS} months ({period}) against the months before.",
            missing=missing,
        ),
    }


def _origin_question(records: _Records) -> dict | None:
    """Where complaints come from: country and reporter type, as recorded."""
    countries = records.tally(lambda c: c.country)
    reporters = records.tally(lambda c: c.reporter_type)
    if not countries and not reporters:
        return None
    total = len(records.complaints)
    parts = []
    if countries:
        top, n = countries[0]
        with_country = sum(n for _c, n in countries)
        in_all = _count(len(countries), "country", "countries")
        parts.append(f"{top} has the most complaints ({n} of {with_country} with a country; {in_all} in all)")
    if reporters:
        parts.append("By reporter type: " + ", ".join(f"{kind} {n}" for kind, n in reporters[:4]))
    missing = []
    no_country = total - sum(n for _c, n in countries)
    no_reporter = total - sum(n for _r, n in reporters)
    if no_country:
        missing.append(f"{_count(no_country, 'complaint')} {'has' if no_country == 1 else 'have'} no country.")
    if not reporters:
        missing.append("No complaint records a reporter type.")
    elif no_reporter:
        verb = "has" if no_reporter == 1 else "have"
        missing.append(f"{_count(no_reporter, 'complaint')} {verb} no reporter type.")
    return {
        "key": "origin",
        "question": "Where are complaints coming from?",
        "answer": _answer(
            ". ".join(parts) + ".",
            bars=[{"label": country, "count": n} for country, n in countries[:ROWS_MAX]] or None,
            table={"columns": ["Reporter type", "Complaints"], "rows": [[kind, n] for kind, n in reporters]}
            if reporters
            else None,
            basis="The country and reporter type of each complaint.",
            missing=missing,
        ),
    }


def _evidence_question(records: _Records) -> dict:
    """The evidence open cases on these products still wait for: open evidence requests and open questions."""
    from backend.app.case_workflow.readiness import request_is_open, unknown_is_open
    from backend.app.db.models.stage3 import SupplierEvidenceRequest
    from backend.app.evidence_workflow.rules import case_closed

    product_ids = list({c.product_id for c in records.complaints if c.product_id})
    cases = [
        case
        for case in records.db.query(Investigation)
        .filter(Investigation.tenant_id == records.tenant_id, Investigation.product_id.in_(product_ids))
        .order_by(Investigation.business_id)
        if not case_closed(case.workflow_state, case.status)
    ]
    question = "What evidence is still missing?"
    basis = "Open investigations on these products, their evidence requests and their open questions (unknowns)."
    if not cases:
        return {
            "key": "evidence",
            "question": question,
            "answer": _answer(
                "No investigation is open on these products, so no evidence is being waited for.",
                basis=basis,
                missing=["Open an investigation to record the evidence it needs."],
            ),
        }
    by_id = {case.id: case for case in cases}
    requests = [
        row
        for row in records.db.query(SupplierEvidenceRequest)
        .filter(
            SupplierEvidenceRequest.tenant_id == records.tenant_id,
            SupplierEvidenceRequest.investigation_id.in_(list(by_id)),
        )
        .order_by(SupplierEvidenceRequest.created_at)
        if request_is_open(row.status, row.reviewed_at)
    ]
    unknowns = [
        row
        for row in records.db.query(Unknown)
        .filter(Unknown.tenant_id == records.tenant_id, Unknown.investigation_id.in_(list(by_id)))
        .order_by(Unknown.created_at)
        if unknown_is_open(row.status)
    ]
    case_names = _join([case.business_id for case in cases[:5]]) + (" and more" if len(cases) > 5 else "")
    if requests or unknowns:
        summary = (
            f"{_count(len(cases), 'open investigation')} ({case_names}) {'waits' if len(cases) == 1 else 'wait'} on "
            f"{_count(len(requests), 'evidence request')} and {_count(len(unknowns), 'open question')}."
        )
    else:
        summary = (
            f"No evidence request or open question is recorded on the {_count(len(cases), 'open investigation')} "
            f"({case_names})."
        )
    case_of = {case_id: case.business_id for case_id, case in by_id.items()}
    rows = [
        [case_of[row.investigation_id], "Evidence request", _shorten(row.title, 120), _day(row.due_at) or "—"]
        for row in requests
    ] + [
        [
            case_of[row.investigation_id],
            "Open question",
            _shorten(row.evidence_needed or row.description, 120),
            "—",
        ]
        for row in unknowns
    ]
    return {
        "key": "evidence",
        "question": question,
        "answer": _answer(
            summary,
            table={"columns": ["Investigation", "Kind", "What is needed", "Due"], "rows": rows[:ROWS_MAX]}
            if rows
            else None,
            cases=[
                {"id": str(case.id), "business_id": case.business_id, "product_id": str(case.product_id)}
                for case in cases[:ROWS_MAX]
            ],
            basis=basis,
            # MDARIX knows what a case still needs only from what people record on it.
            missing=[]
            if requests or unknowns
            else ["Evidence a case needs shows here once someone records it as a request or an open question."],
        ),
    }


QUESTIONS = (
    _version_question,
    _lots_question,
    _rise_question,
    _harm_question,
    _codes_question,
    _origin_question,
    _evidence_question,
)


# The words of a question typed into Ask MDARIX that name what one of the questions above answers. Without AI, Ask
# answers such a question with the same fixed-rule answer as Getting started instead of a search for the words.
ASK_TOPICS = (
    ("lots", ("lot", "lots", "batch", "batches")),
    ("version", ("version", "versions", "rev", "revision", "changed", "change", "changes")),
    ("rise", ("rise", "rising", "rose", "increase", "increased", "trend", "more devices")),
    ("harm", ("harm", "injury", "injuries", "malfunction", "malfunctions", "death", "deaths")),
    ("codes", ("problem code", "problem codes", "codes", "failure mode", "failure modes")),
    ("origin", ("country", "countries", "coming from", "region", "regions")),
)
ASK_ANSWERS_MAX = 2


def answers_for(questions: list[dict], text: str) -> list[dict]:
    """The questions above (as ``build`` returns them) that ``text`` asks about, in ``ASK_TOPICS`` order."""
    words = " " + " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower())) + " "
    keys = [key for key, terms in ASK_TOPICS if any(f" {term} " in words for term in terms)]
    by_key = {item["key"]: item for item in questions}
    return [by_key[key] for key in keys if key in by_key][:ASK_ANSWERS_MAX]


def build(db: Session, tenant_id, scope: str, complaints, products, versions, lots) -> dict:
    """The panel's new fields for the complaints in scope; empty when there are none."""
    records = _Records(db, tenant_id, scope, complaints, products, versions, lots)
    rows, labels = compact_records(records)
    questions = [item for item in (ask(records) for ask in QUESTIONS) if item] if complaints else []
    return {
        "headline": headline(records),
        "trend": trend(records),
        "records": rows,
        "version_labels": labels,
        "questions": questions,
    }
