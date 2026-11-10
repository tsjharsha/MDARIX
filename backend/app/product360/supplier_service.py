"""Supplier 360 (W1, spec 4 and 6.3): one supplier's parts, the products and versions that use them, their lots,
complaints, investigations, changes, evidence and CAPAs, and the "pattern to review" box (rule P-1).

A complaint is linked to a supplier only through the records: it is on a version that contains one of its parts, or,
more strongly, on a lot whose genealogy names one of its part lots. Every link says which. Nothing here decides or
writes; the pattern box never calls anything a confirmed signal. Every query names the tenant on every table it reads.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.lot_impact.service import per_thousand
from backend.app.product360 import links
from backend.app.product360.origin import of_row
from backend.app.product360.service import Product360Service, rowdict

RULE, RULE_VERSION = "P-1", 1
WINDOW_DAYS, MIN_COMPLAINTS, MIN_VERSIONS = 90, 2, 2
NOT_A_SIGNAL = (
    "This is a pattern to review, not a confirmed signal. Exposure, period and data completeness need a person's "
    "assessment."
)
SCAR_NOTE = "Supplier corrective action requests (SCAR): planned for a later release."
NEWEST = 5


class SupplierNotFound(LookupError):
    pass


def problem_words(code: str) -> str:
    return " ".join(str(code or "").replace("_", " ").replace("-", " ").lower().split()) or "no problem code"


def _plural(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one if count == 1 else (many or one + 's')}"


def _units_text(item: dict) -> str:
    """ "450 units released (31.1 per 1,000)", or the reason there is no rate. Never a rate from partial units."""
    if item["units_unknown_lots"]:
        return f"units not known for {item['units_unknown_lots']} of {item['lots']} lots"
    if not item["units"]:
        return "no units released recorded"
    return f"{item['units']} units released ({item['per_1000']} per 1,000)"


def pattern(
    supplier: str,
    has_parts: bool,
    versions: list[dict],
    problems: list[dict],
    units: dict[str, dict],
    investigations: list[dict],
    signals: dict[str, int],
) -> dict[str, Any]:
    """Rule P-1, version 1 (OD-5): over the last 90 days, a pattern to review is shown when the same problem code has
    at least 2 complaints on each of at least 2 versions that contain the supplier's parts.

    ``versions``: ``[{version_id, version_identifier, product_id, product_name}]`` containing its parts; ``problems``:
    ``[{version_id, problem, recent}]`` (complaints in the window per version and problem code); ``units``:
    ``{version_id: {units, lots, unknown}}``; ``investigations``: ``[{ref, open, recent: {(version_id, problem): n}}]``,
    the complaints each holds on those versions in the window; the box offers the open ones that hold any of the
    complaints it speaks of, with how many (``held``); ``signals``: open trends to review per version. A pure function: the same input always
    gives the same box."""
    box: dict[str, Any] = {
        "rule": RULE,
        "rule_version": RULE_VERSION,
        "window_days": WINDOW_DAYS,
        "thresholds": {"complaints_per_version": MIN_COMPLAINTS, "versions": MIN_VERSIONS},
        "found": False,
        "case": "NO_PARTS",
        "problem": None,
        "versions": [],
        "investigations": [],
    }
    if not has_parts:
        return {**box, "text": "No parts are recorded for this supplier, so nothing can be linked to it."}
    named = {item["version_id"]: item for item in versions}
    if not named:
        return {
            **box,
            "case": "NO_VERSIONS",
            "text": f"No product version is recorded as containing {supplier} parts, so no complaint can be linked to it.",
        }

    def line(version_id: str, recent: int, problem: str | None) -> dict:
        info = units.get(version_id) or {"units": None, "lots": 0, "unknown": 0}
        known = not info["unknown"] and info["units"]
        return {
            "version_id": version_id,
            "product": named[version_id]["product_name"],
            "version": named[version_id]["version_identifier"],
            "problem": problem,
            "recent": recent,
            "units": info["units"],
            "lots": info["lots"],
            "units_unknown_lots": info["unknown"],
            "per_1000": per_thousand(recent, info["units"]) if known else None,
            "open_signals": signals.get(version_id, 0),
        }

    def covering(counted) -> list[dict]:
        """The open investigations holding any of the complaints ``counted((version_id, problem))`` selects."""
        found = []
        for item in investigations:
            held = sum(n for key, n in item["recent"].items() if counted(key))
            if item.get("open", True) and held:
                found.append({"ref": item["ref"], "held": held, **({"id": item["id"]} if "id" in item else {})})
        return sorted(found, key=lambda item: (-item["held"], item["ref"]))

    box["investigations"] = covering(lambda key: key[0] in named)
    by_problem: dict[str, dict[str, int]] = defaultdict(dict)
    for row in problems:
        if row["version_id"] in named and str(row["problem"] or "").strip() and row["recent"] >= MIN_COMPLAINTS:
            by_problem[row["problem"]][row["version_id"]] = row["recent"]
    qualifying = {problem: found for problem, found in by_problem.items() if len(found) >= MIN_VERSIONS}
    if qualifying:
        problem, found = min(qualifying.items(), key=lambda item: (-len(item[1]), -sum(item[1].values()), item[0]))
        rows = sorted((line(v, n, problem) for v, n in found.items()), key=lambda r: (-r["recent"], r["product"]))
        products = {named[v]["product_id"] for v in found}
        lines = " ".join(
            f"{r['product']} {r['version']}: {_plural(r['recent'], 'complaint')}, {_units_text(r)}." for r in rows
        )
        text_ = (
            f"Pattern to review: {problem_words(problem)} on {_plural(len(rows), 'version')} of "
            f"{_plural(len(products), 'product')} that contain {supplier} parts. {lines} {NOT_A_SIGNAL}"
        )
        cases = covering(lambda key: key[0] in found and key[1] == problem)
        return {
            **box,
            "found": True,
            "case": "PATTERN",
            "problem": problem,
            "versions": rows,
            "investigations": cases,
            "text": text_,
        }
    recent_by_version: dict[str, int] = defaultdict(int)
    for row in problems:
        if row["version_id"] in named:
            recent_by_version[row["version_id"]] += row["recent"]
    rows = sorted(
        (line(v, recent_by_version.get(v, 0), None) for v in named),
        key=lambda r: (-r["recent"], r["product"], r["version"]),
    )
    if len(rows) == 1:
        (only,) = rows
        parts = [
            f"{supplier} parts are in 1 product version: {only['product']} {only['version']}.",
            f"Complaints on it in the last {WINDOW_DAYS} days: {only['recent']}, of {_units_text(only)}.",
        ]
        if only["open_signals"]:
            parts.append(f"Trends: {_plural(only['open_signals'], 'trend')} to review on this version.")
        parts += [f"{case['ref']} is open on {case['held']} of these complaints." for case in box["investigations"]]
        parts.append("No other product or version uses these parts, so a cross-product pattern cannot be seen.")
        return {**box, "case": "ONE_VERSION", "versions": rows, "text": " ".join(parts)}
    return {
        **box,
        "case": "BELOW_RULE",
        "versions": rows,
        "text": (
            f"No problem repeats on more than one version that contains these parts in the last {WINDOW_DAYS} days."
        ),
    }


# --------------------------------------------------------------------------------------------- reading


def resolve(db: Session, t: str, ref: str):
    row = (
        db.execute(
            text(
                "SELECT id, business_id, supplier_identifier, name, status, source_system, source_identifier, "
                "ingestion_timestamp, created_at FROM suppliers WHERE tenant_id=:t "
                "AND (id::text=:ref OR business_id=:ref OR supplier_identifier=:ref) ORDER BY id::text=:ref DESC LIMIT 1"
            ),
            {"t": t, "ref": str(ref)},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise SupplierNotFound("Supplier not found")
    return row


def _parts(db: Session, t: str, supplier_id) -> list[dict]:
    """Query 2: each part with the versions and products that contain it (one row per part and version)."""
    return (
        db.execute(
            text(
                "SELECT c.id, c.business_id, c.component_identifier, c.name, c.revision, c.source_system, "
                "c.source_identifier, c.ingestion_timestamp, c.created_at, cs.effective_timestamp AS supplied_from, "
                "pv.id AS version_id, pv.version_identifier, pv.release_timestamp, p.id AS product_id, "
                "p.name AS product_name, p.product_identifier, "
                "(SELECT coalesce(array_agg(o2.name ORDER BY o2.name), '{}') FROM component_suppliers o "
                " JOIN suppliers o2 ON o2.tenant_id=o.tenant_id AND o2.id=o.supplier_id "
                " WHERE o.tenant_id=:t AND o.component_id=c.id AND o.supplier_id<>:s) AS other_suppliers "
                "FROM component_suppliers cs JOIN components c ON c.tenant_id=cs.tenant_id AND c.id=cs.component_id "
                "LEFT JOIN product_components pc ON pc.tenant_id=c.tenant_id AND pc.component_id=c.id "
                "LEFT JOIN product_versions pv ON pv.tenant_id=pc.tenant_id AND pv.id=pc.product_version_id "
                "LEFT JOIN products p ON p.tenant_id=pv.tenant_id AND p.id=pv.product_id "
                "WHERE cs.tenant_id=:t AND cs.supplier_id=:s "
                "ORDER BY c.component_identifier, c.revision, p.name, pv.release_timestamp NULLS LAST"
            ),
            {"t": t, "s": supplier_id},
        )
        .mappings()
        .all()
    )


def _shape_parts(rows) -> tuple[list[dict], list[dict], dict[str, list[str]]]:
    """The parts (each with the versions using it), the versions containing them, and each version's part names."""
    parts: dict[str, dict] = {}
    versions: dict[str, dict] = {}
    names: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        key = str(row["id"])
        part = parts.get(key)
        if part is None:
            plain = rowdict(row)
            part = parts[key] = {
                **{k: plain[k] for k in ("id", "business_id", "component_identifier", "name", "revision")},
                "supplied_from": plain["supplied_from"],
                "other_suppliers": list(row["other_suppliers"] or []),
                "origin": of_row(row),
                "used_in": [],
            }
        if row["version_id"] is None:
            continue
        version_id = str(row["version_id"])
        if not any(item["version_id"] == version_id for item in part["used_in"]):
            part["used_in"].append(
                {
                    "product_id": str(row["product_id"]),
                    "product_identifier": row["product_identifier"],
                    "product_name": row["product_name"],
                    "version_id": version_id,
                    "version_identifier": row["version_identifier"],
                }
            )
        versions.setdefault(
            version_id,
            {
                "id": version_id,
                "version_id": version_id,
                "version_identifier": row["version_identifier"],
                "release_timestamp": row["release_timestamp"],
                "product_id": str(row["product_id"]),
                "product_name": row["product_name"],
                "product_identifier": row["product_identifier"],
            },
        )
        if row["name"] not in names[version_id]:
            names[version_id].append(row["name"])
    return list(parts.values()), list(versions.values()), dict(names)


def _since(now: datetime) -> datetime:
    return now - timedelta(days=WINDOW_DAYS)


def _problems(db, t, version_ids, since) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT product_version_id, coalesce(problem_code, '') AS problem, count(*) AS n, "
            "count(*) FILTER (WHERE event_timestamp >= :since) AS recent FROM complaints "
            "WHERE tenant_id=:t AND product_version_id = ANY(CAST(:v AS uuid[])) GROUP BY 1, 2"
        ),
        {"t": t, "v": version_ids, "since": since},
    ).mappings()
    return [
        {
            "version_id": str(r["product_version_id"]),
            "problem": r["problem"],
            "n": int(r["n"]),
            "recent": int(r["recent"]),
        }
        for r in rows
    ]


# The open-case form takes at most 200 complaints (investigation_open_router.OpenInvestigationRequest).
PATTERN_COMPLAINTS_MAX = 200


def _pattern_complaints(db, t, box: dict, since) -> list[dict]:
    """The complaints a found pattern speaks of (its problem code, on its versions, in the window), newest first, each
    with its product: "Open an investigation" ticks those of one product, as a case links its own product's only."""
    rows = db.execute(
        text(
            "SELECT id, business_id, complaint_identifier, description, product_id, product_version_id FROM complaints "
            "WHERE tenant_id=:t AND product_version_id = ANY(CAST(:v AS uuid[])) AND problem_code=:p "
            "AND event_timestamp >= :since ORDER BY event_timestamp DESC, complaint_identifier LIMIT :n"
        ),
        {
            "t": t,
            "v": [row["version_id"] for row in box["versions"]],
            "p": box["problem"],
            "since": since,
            "n": PATTERN_COMPLAINTS_MAX,
        },
    ).mappings()
    return [
        {
            "id": str(r["id"]),
            "business_id": r["business_id"],
            "complaint_identifier": r["complaint_identifier"],
            "description": r["description"],
            "product_id": str(r["product_id"]),
            "version_id": str(r["product_version_id"]),
        }
        for r in rows
    ]


def _units(db, t, version_ids) -> dict[str, dict]:
    rows = db.execute(
        text(
            "SELECT product_version_id, sum(quantity) AS units, count(*) AS lots, "
            "count(*) FILTER (WHERE quantity IS NULL) AS unknown FROM lot_batches "
            "WHERE tenant_id=:t AND product_version_id = ANY(CAST(:v AS uuid[])) GROUP BY 1"
        ),
        {"t": t, "v": version_ids},
    ).mappings()
    return {
        str(r["product_version_id"]): {
            "units": int(r["units"]) if r["units"] is not None else None,
            "lots": int(r["lots"]),
            "unknown": int(r["unknown"]),
        }
        for r in rows
    }


def complaints(db, t, part_ids, version_ids, names, limit, offset) -> tuple[list[dict], int]:
    """Complaints on versions containing its parts, newest first, each with the basis of its link: a lot whose
    genealogy names one of its part lots, else the version that contains its part."""
    sql = (
        "SELECT c.id, c.business_id, c.complaint_identifier, c.event_timestamp, c.status, c.problem_code, "
        "c.product_version_id, pv.version_identifier, p.id AS product_id, p.name AS product_name, l.lot_identifier, "
        "c.source_system, c.source_identifier, c.ingestion_timestamp, c.created_at, g.component_lot_identifier, "
        "g.component_name, count(*) OVER () AS total FROM complaints c "
        "JOIN product_versions pv ON pv.tenant_id=c.tenant_id AND pv.id=c.product_version_id "
        "JOIN products p ON p.tenant_id=pv.tenant_id AND p.id=pv.product_id "
        "LEFT JOIN lot_batches l ON l.tenant_id=c.tenant_id AND l.id=c.lot_batch_id "
        "LEFT JOIN LATERAL (SELECT lc.component_lot_identifier, cm.name AS component_name FROM lot_components lc "
        "JOIN components cm ON cm.tenant_id=lc.tenant_id AND cm.id=lc.component_id WHERE lc.tenant_id=:t "
        "AND lc.lot_batch_id=c.lot_batch_id AND lc.component_id = ANY(CAST(:c AS uuid[])) "
        "AND lc.component_lot_identifier IS NOT NULL ORDER BY lc.component_lot_identifier LIMIT 1) g ON true "
        "WHERE c.tenant_id=:t AND c.product_version_id = ANY(CAST(:v AS uuid[])) "
        "ORDER BY c.event_timestamp DESC NULLS LAST, c.complaint_identifier"
    )
    if not version_ids:
        return [], 0
    rows, total = links._paged(db, sql, {"t": t, "c": part_ids, "v": version_ids}, limit, offset)
    for row in rows:
        if row["component_lot_identifier"]:
            row["basis_kind"] = "GENEALOGY"
            row["basis"] = (
                f"On a lot whose genealogy names its {row['component_name']} lot {row['component_lot_identifier']}"
            )
        else:
            row["basis_kind"] = "VERSION"
            row["basis"] = "On a version that contains its " + ", ".join(names.get(str(row["product_version_id"]), []))
    return rows, total


def _investigations(db, t, version_ids, since) -> tuple[list[dict], dict[str, dict[tuple[str, str], int]]]:
    """The investigations holding complaints on those versions (query 7), and per investigation the complaints it
    holds in the window by version and problem code (for the pattern box)."""
    rows = db.execute(
        text(
            "SELECT i.id, i.business_id, i.investigation_identifier, i.status, i.workflow_state, i.opened_at, "
            "i.owner_ref, i.product_id, i.source_system, i.source_identifier, i.ingestion_timestamp, i.created_at, "
            "count(*) AS held, count(*) FILTER (WHERE c.event_timestamp >= :since) AS held_recent "
            "FROM investigations i JOIN investigation_complaints ic ON ic.tenant_id=i.tenant_id AND ic.investigation_id=i.id "
            "JOIN complaints c ON c.tenant_id=ic.tenant_id AND c.id=ic.complaint_id "
            "WHERE i.tenant_id=:t AND c.product_version_id = ANY(CAST(:v AS uuid[])) GROUP BY i.id "
            "ORDER BY held DESC, i.investigation_identifier"
        ),
        {"t": t, "v": version_ids, "since": since},
    ).mappings()
    found = []
    for row in rows:
        item = links._row(row)
        item["open"] = str(row["status"] or "").strip().lower() != "closed"
        item["basis"] = f"Holds {_plural(int(row['held']), 'complaint')} on versions containing its parts"
        found.append(item)
    held: dict[str, dict[tuple[str, str], int]] = defaultdict(dict)
    for row in db.execute(
        text(
            "SELECT ic.investigation_id, c.product_version_id, coalesce(c.problem_code, '') AS problem, count(*) AS n "
            "FROM investigation_complaints ic JOIN complaints c ON c.tenant_id=ic.tenant_id AND c.id=ic.complaint_id "
            "WHERE ic.tenant_id=:t AND c.product_version_id = ANY(CAST(:v AS uuid[])) AND c.event_timestamp >= :since "
            "GROUP BY 1, 2, 3"
        ),
        {"t": t, "v": version_ids, "since": since},
    ).mappings():
        held[str(row["investigation_id"])][(str(row["product_version_id"]), row["problem"])] = int(row["n"])
    return found, dict(held)


def _changes(db, t, part_ids, versions_by_part) -> list[dict]:
    if not part_ids:
        return []
    rows = (
        db.execute(
            text(
                "SELECT ch.id, ch.business_id, ch.change_identifier, ch.change_type, ch.description, ch.event_timestamp, "
                "ch.effective_timestamp, ch.source_system, ch.source_identifier, ch.ingestion_timestamp, ch.created_at, "
                "array_agg(DISTINCT c.component_identifier) AS affects, array_agg(DISTINCT c.name) AS affects_names, "
                "array_agg(DISTINCT c.id::text) AS component_ids FROM reality_relationships rr "
                "JOIN changes ch ON ch.tenant_id=rr.tenant_id AND ch.id=rr.source_entity_id "
                "JOIN components c ON c.tenant_id=rr.tenant_id AND c.id=rr.target_entity_id "
                "WHERE rr.tenant_id=:t AND rr.source_entity_type='Change' AND rr.relationship_type='AFFECTS' "
                "AND rr.target_entity_type='Component' AND rr.target_entity_id = ANY(CAST(:c AS uuid[])) "
                "GROUP BY ch.id ORDER BY ch.effective_timestamp NULLS LAST, ch.change_identifier"
            ),
            {"t": t, "c": part_ids},
        )
        .mappings()
        .all()
    )
    shaped = [
        {
            **dict(row),
            "affects_product": False,
            "versions": sorted({v for c in row["component_ids"] for v in versions_by_part.get(c, [])}),
        }
        for row in rows
    ]
    split = Product360Service()._split(db, t, None, shaped) if shaped else {}
    result = []
    for row in shaped:
        item = links._row(row)
        item.pop("component_ids", None)
        item["complaints_before"], item["complaints_after"] = split.get(str(row["id"]), (0, 0))
        result.append(item)
    return result


def _evidence(db, t, supplier_id, part_ids) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT e.id, e.business_id, e.evidence_identifier, e.title, e.evidence_type, e.reliability_status, "
            "e.source_reference, e.investigation_id, i.investigation_identifier, e.source_system, e.source_identifier, "
            "e.ingestion_timestamp, e.created_at, l.entity_type FROM evidence_entity_links l "
            "JOIN evidence e ON e.tenant_id=l.tenant_id AND e.id=l.evidence_id "
            "LEFT JOIN investigations i ON i.tenant_id=e.tenant_id AND i.id=e.investigation_id "
            "WHERE l.tenant_id=:t AND ((l.entity_type='Supplier' AND l.entity_id=:s) "
            "OR (l.entity_type='Component' AND l.entity_id = ANY(CAST(:c AS uuid[])))) "
            "ORDER BY e.evidence_identifier, l.entity_type DESC"  # the supplier before its part
        ),
        {"t": t, "s": supplier_id, "c": part_ids},
    ).mappings()
    found: dict[str, dict] = {}
    for row in rows:
        item = found.get(str(row["id"]))
        if item is None:
            item = found[str(row["id"])] = {**links._row(row), "linked_to": []}
            item.pop("entity_type", None)
        kind = "the supplier" if row["entity_type"] == "Supplier" else "its part"
        if kind not in item["linked_to"]:
            item["linked_to"].append(kind)
    for item in found.values():
        item["basis"] = "Linked to " + " and ".join(item["linked_to"])
    return list(found.values())


def _requests(db, t, supplier_id) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT r.id, r.business_id, r.title, r.status, r.created_at, r.due_at, r.responded_at, r.response_note, "
            "r.investigation_id, i.investigation_identifier FROM supplier_evidence_requests r "
            "LEFT JOIN investigations i ON i.tenant_id=r.tenant_id AND i.id=r.investigation_id "
            "WHERE r.tenant_id=:t AND r.supplier_id=:s ORDER BY r.created_at DESC LIMIT 20"
        ),
        {"t": t, "s": supplier_id},
    ).mappings()
    return [rowdict(row) for row in rows]


def _signals(db, t, version_ids) -> dict[str, int]:
    from backend.app.db.models.signals import OPEN_SIGNAL_STATUSES

    rows = db.execute(
        text(
            "SELECT product_version_id, count(*) AS n FROM signals WHERE tenant_id=:t "
            "AND product_version_id = ANY(CAST(:v AS uuid[])) AND status = ANY(:open) GROUP BY 1"
        ),
        {"t": t, "v": version_ids, "open": list(OPEN_SIGNAL_STATUSES)},
    ).mappings()
    return {str(r["product_version_id"]): int(r["n"]) for r in rows}


def page(db: Session, t: str, ref: str, now: datetime | None = None) -> dict[str, Any]:
    """One supplier's page (spec 4.2): head, parts and products, counts, the pattern box, the trend, changes,
    evidence, evidence requests, CAPAs, investigations and the newest complaints."""
    now = now or datetime.now(timezone.utc)
    since = _since(now)
    supplier = resolve(db, t, ref)
    part_rows = _parts(db, t, supplier["id"])
    parts, versions, names = _shape_parts(part_rows)
    part_ids = [part["id"] for part in parts]
    version_ids = [v["id"] for v in versions]
    versions_by_part: dict[str, list[str]] = defaultdict(list)
    for part in parts:
        versions_by_part[part["id"]] = [use["version_id"] for use in part["used_in"]]
    problems = _problems(db, t, version_ids, since) if version_ids else []
    units = _units(db, t, version_ids) if version_ids else {}
    signals = _signals(db, t, version_ids) if version_ids else {}
    newest, complaint_total = complaints(db, t, part_ids, version_ids, names, NEWEST, 0)
    cases, held = _investigations(db, t, version_ids, since) if version_ids else ([], {})
    changes = _changes(db, t, part_ids, versions_by_part)
    evidence = _evidence(db, t, supplier["id"], part_ids)
    requests = _requests(db, t, supplier["id"])
    product_ids = sorted({v["product_id"] for v in versions})
    case_ids = [case["id"] for case in cases]
    capas = links.capa_rows(
        db,
        t,
        "k.investigation_id = ANY(CAST(:cases AS uuid[])) OR k.product_id = ANY(CAST(:products AS uuid[]))",
        {"cases": case_ids, "products": product_ids},
    )
    for capa in capas:
        capa["basis"] = (
            f"CAPA from {capa['investigation_identifier']}"
            if capa["investigation_id"] in case_ids
            else f"CAPA on {capa['product_name']}"
        )
    name = supplier["name"]
    box = pattern(
        name,
        bool(parts),
        versions,
        problems,
        units,
        [
            {"id": c["id"], "ref": c["investigation_identifier"], "open": c["open"], "recent": held.get(c["id"], {})}
            for c in cases
        ],
        signals,
    )
    if box["found"]:
        box["complaints"] = _pattern_complaints(db, t, box, since)
    trend = links.monthly(db, t, versions, now)
    start = trend["months"][0] if trend["months"] else None
    for part in parts:
        if part["supplied_from"] and (start is None or part["supplied_from"][:7] >= start):
            trend["markers"].append(
                {"kind": "supplier_link", "label": f"{part['name']} supplied from", "at": part["supplied_from"]}
            )
    for change in changes:
        at = change["effective_timestamp"] or change["event_timestamp"]
        if at and (start is None or at[:7] >= start):
            trend["markers"].append({"kind": "change", "label": change["change_identifier"], "at": at})
    supplied = [part["supplied_from"] for part in parts if part["supplied_from"]]
    return {
        "supplier": {
            **{k: rowdict(supplier)[k] for k in ("id", "business_id", "supplier_identifier", "name", "status")},
            "origin": of_row(supplier),
            "since": min(supplied) if supplied else None,
        },
        "parts": parts,
        "versions": [
            {k: v[k] for k in ("version_id", "version_identifier", "product_id", "product_name", "product_identifier")}
            | {
                "complaints_90d": sum(p["recent"] for p in problems if p["version_id"] == v["version_id"]),
                "units": (units.get(v["version_id"]) or {}).get("units"),
                "open_signals": signals.get(v["version_id"], 0),
            }
            for v in versions
        ],
        "counts": {
            "parts": len(parts),
            "products": len(product_ids),
            "versions": len(versions),
            "lots_on_versions": sum((units.get(v) or {}).get("lots", 0) for v in version_ids),
            "complaints": complaint_total,
            "complaints_90d": sum(p["recent"] for p in problems),
            "investigations": len(cases),
            "changes": len(changes),
            "evidence": len(evidence),
            "evidence_requests": len(requests),
            "capas": len(capas),
        },
        "pattern": box,
        "trend": trend,
        "complaints": {"count": complaint_total, "items": newest},
        "investigations": cases,
        "changes": changes,
        "evidence": evidence,
        "evidence_requests": requests,
        "capas": capas,
        "scar_note": SCAR_NOTE,
        "never_decides": "MDARIX lists what was recorded and why each record is linked; it does not infer a cause.",
    }


def complaint_page(db: Session, t: str, ref: str, limit: int, offset: int) -> tuple[list[dict], int]:
    supplier = resolve(db, t, ref)
    parts, versions, names = _shape_parts(_parts(db, t, supplier["id"]))
    return complaints(db, t, [p["id"] for p in parts], [v["id"] for v in versions], names, limit, offset)


def lots(db: Session, t: str, ref: str) -> dict[str, Any]:
    """Every lot whose genealogy names one of its parts (``lot_impact.build`` with the supplier as the factor); when
    no genealogy names them, the lots of the versions that contain its parts, said plainly."""
    from backend.app.lot_impact.service import SUPPLIER, build

    supplier = resolve(db, t, ref)
    tenant = uuid.UUID(str(t))
    built = build(db, tenant, {"kind": SUPPLIER, "id": str(supplier["id"]), "lot": None, "label": supplier["name"]}, [])
    if built["lots"]:
        return {"basis": "GENEALOGY", "note": None, "lots": built["lots"], "totals": built["totals"]}
    _parts_, versions, _names = _shape_parts(_parts(db, t, supplier["id"]))
    rows = (
        db.execute(
            text(
                "SELECT l.id, l.business_id, l.lot_identifier, l.quantity, l.effective_timestamp, pv.version_identifier, "
                "p.name AS product_name, (SELECT count(*) FROM complaints c WHERE c.tenant_id=:t AND c.lot_batch_id=l.id) "
                "AS complaints FROM lot_batches l JOIN product_versions pv ON pv.tenant_id=l.tenant_id "
                "AND pv.id=l.product_version_id JOIN products p ON p.tenant_id=pv.tenant_id AND p.id=pv.product_id "
                "WHERE l.tenant_id=:t AND l.product_version_id = ANY(CAST(:v AS uuid[])) ORDER BY l.lot_identifier"
            ),
            {"t": t, "v": [v["id"] for v in versions]},
        )
        .mappings()
        .all()
        if versions
        else []
    )
    found = [
        {
            "id": str(row["id"]),
            "business_id": row["business_id"],
            "lot_identifier": row["lot_identifier"],
            "product": row["product_name"],
            "version": row["version_identifier"],
            "made_on": row["effective_timestamp"].date().isoformat() if row["effective_timestamp"] else None,
            "released": row["quantity"],
            "complaints": int(row["complaints"]),
            "per_1000": per_thousand(int(row["complaints"]), row["quantity"]),
            "evidence": ["The lot's version contains this supplier's part."],
        }
        for row in rows
    ]
    found.sort(key=lambda row: (row["complaints"] == 0, -row["complaints"], row["lot_identifier"]))
    return {
        "basis": "VERSION",
        "note": "Lot genealogy not imported. Lots are shown by version instead.",
        "lots": found,
        "totals": {
            "lots": len(found),
            "complaints": sum(row["complaints"] for row in found),
            "released": sum(row["released"] or 0 for row in found),
            "released_unknown": sum(1 for row in found if row["released"] is None),
        },
    }


def supplier_list(db: Session, t: str, limit: int, offset: int, now: datetime | None = None) -> tuple[list[dict], int]:
    """The organization's suppliers, by name, each with its parts, the products and versions using them, complaints
    on those versions in the last 90 days and the open investigations holding any of them. Three queries."""
    now = now or datetime.now(timezone.utc)
    total = int(db.execute(text("SELECT count(*) FROM suppliers WHERE tenant_id=:t"), {"t": t}).scalar() or 0)
    rows = (
        db.execute(
            text(
                "SELECT id, business_id, supplier_identifier, name, status, source_system, source_identifier, "
                "ingestion_timestamp, created_at FROM suppliers WHERE tenant_id=:t ORDER BY name, id "
                "LIMIT :limit OFFSET :offset"
            ),
            {"t": t, "limit": limit, "offset": offset},
        )
        .mappings()
        .all()
    )
    ids = [str(row["id"]) for row in rows]
    counts = {}
    if ids:
        counts = {
            str(r["supplier_id"]): r
            for r in db.execute(
                text(
                    "WITH sv AS (SELECT DISTINCT cs.supplier_id, cs.component_id, pc.product_version_id, pv.product_id "
                    "FROM component_suppliers cs LEFT JOIN product_components pc ON pc.tenant_id=cs.tenant_id "
                    "AND pc.component_id=cs.component_id LEFT JOIN product_versions pv ON pv.tenant_id=pc.tenant_id "
                    "AND pv.id=pc.product_version_id WHERE cs.tenant_id=:t AND cs.supplier_id = ANY(CAST(:ids AS uuid[]))), "
                    "vs AS (SELECT DISTINCT supplier_id, product_version_id FROM sv WHERE product_version_id IS NOT NULL) "
                    "SELECT a.supplier_id, a.parts, a.products, a.versions, coalesce(r.recent, 0) AS complaints_90d, "
                    "coalesce(o.open_investigations, 0) AS open_investigations FROM "
                    "(SELECT supplier_id, count(DISTINCT component_id) AS parts, count(DISTINCT product_id) AS products, "
                    "count(DISTINCT product_version_id) AS versions FROM sv GROUP BY 1) a "
                    "LEFT JOIN (SELECT vs.supplier_id, count(*) AS recent FROM vs JOIN complaints c ON c.tenant_id=:t "
                    "AND c.product_version_id=vs.product_version_id AND c.event_timestamp >= :since GROUP BY 1) r "
                    "ON r.supplier_id=a.supplier_id "
                    "LEFT JOIN (SELECT vs.supplier_id, count(DISTINCT i.id) AS open_investigations FROM vs "
                    "JOIN complaints c ON c.tenant_id=:t AND c.product_version_id=vs.product_version_id "
                    "JOIN investigation_complaints ic ON ic.tenant_id=:t AND ic.complaint_id=c.id "
                    "JOIN investigations i ON i.tenant_id=:t AND i.id=ic.investigation_id "
                    "AND lower(coalesce(i.status, '')) <> 'closed' GROUP BY 1) o ON o.supplier_id=a.supplier_id"
                ),
                {"t": t, "ids": ids, "since": _since(now)},
            ).mappings()
        }
    found = []
    for row in rows:
        c = counts.get(str(row["id"])) or {}
        found.append(
            {
                **{k: rowdict(row)[k] for k in ("id", "business_id", "supplier_identifier", "name", "status")},
                "origin": of_row(row),
                **{
                    key: int(c.get(key) or 0)
                    for key in ("parts", "products", "versions", "complaints_90d", "open_investigations")
                },
            }
        )
    return found, total
