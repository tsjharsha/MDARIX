"""Product 360's connected records (W1, spec 6.2): ``GET /api/v1/products/{id}/links``.

Without ``kind``: six tiles for the version (complaints, investigations, trends to review, CAPAs with their
effectiveness checks, risks, authority reports), each with its count and newest three, and the complaints per month of
each version over twelve months. With ``kind``: that one list, paged. Every row carries its origin and, where a record
is linked through another one, the basis of the link. Reads only, inside the caller's organization; every query names
the tenant on every table it reads. The change markers of the monthly chart come from the light Product 360 read.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.product360.origin import of_row
from backend.app.product360.service import Product360Error, Product360Service, rowdict

KINDS = ("complaints", "investigations", "signals", "capas", "risks", "reports")
TILE_ITEMS = 3
MONTHS = 12
# Matches no version: "every version" is a NULL version parameter.
_VERSION = "(CAST(:v AS uuid) IS NULL OR {column} = CAST(:v AS uuid))"


def resolve(db: Session, tenant_id: str, product_ref: str, version_ref: str | None):
    """The product (record ID, MDARIX ID or product identifier), its versions oldest first, and the chosen version
    (record ID, MDARIX ID or version identifier; None for every version). Another organization's record is not found."""
    product = Product360Service().resolve_product(db, tenant_id, product_ref)
    if product is None:
        raise Product360Error("PRODUCT_NOT_FOUND", "Product not found")
    versions = (
        db.execute(
            text(
                "SELECT id, business_id, version_identifier, release_timestamp FROM product_versions "
                "WHERE tenant_id=:t AND product_id=:p ORDER BY release_timestamp NULLS LAST, version_identifier"
            ),
            {"t": tenant_id, "p": product["id"]},
        )
        .mappings()
        .all()
    )
    version = None
    if version_ref:
        version = next(
            (v for v in versions if version_ref in (str(v["id"]), v["business_id"], v["version_identifier"])), None
        )
        if version is None:
            raise Product360Error("VERSION_NOT_FOUND", "Version not found")
    return product, versions, version


def _row(row) -> dict[str, Any]:
    item = rowdict(row)
    item.pop("total", None)
    item["origin"] = of_row(row)
    return item


def _paged(db: Session, sql: str, params: dict, limit: int, offset: int) -> tuple[list[dict], int]:
    """The rows of ``sql`` (which selects ``count(*) OVER () AS total``) at ``offset``, and the total."""
    rows = db.execute(text(f"{sql} LIMIT :limit OFFSET :offset"), {**params, "limit": limit, "offset": offset})
    rows = rows.mappings().all()
    if rows:
        return [_row(row) for row in rows], int(rows[0]["total"])
    if offset:
        first = db.execute(text(f"{sql} LIMIT 1"), params).mappings().first()
        return [], int(first["total"]) if first else 0
    return [], 0


def complaints(db, t, product, version, limit, offset):
    sql = (
        "SELECT c.id, c.business_id, c.complaint_identifier, c.event_timestamp, c.status, c.problem_code, "
        "l.lot_identifier, pv.version_identifier, c.source_system, c.source_identifier, c.ingestion_timestamp, "
        "c.created_at, count(*) OVER () AS total FROM complaints c "
        "LEFT JOIN lot_batches l ON l.tenant_id=c.tenant_id AND l.id=c.lot_batch_id "
        "LEFT JOIN product_versions pv ON pv.tenant_id=c.tenant_id AND pv.id=c.product_version_id "
        f"WHERE c.tenant_id=:t AND c.product_id=:p AND {_VERSION.format(column='c.product_version_id')} "
        "ORDER BY c.event_timestamp DESC NULLS LAST, c.complaint_identifier"
    )
    return _paged(db, sql, _params(t, product, version), limit, offset)


def reports(db, t, product, version, limit, offset):
    sql = (
        "SELECT o.id, o.market, o.form_code, o.report_type, o.state, o.due_on, o.created_at, o.source_system, "
        "c.id AS complaint_id, c.complaint_identifier, s.submitted_at, s.authority_reference, "
        "count(*) OVER () AS total FROM report_obligations o "
        "JOIN complaints c ON c.tenant_id=o.tenant_id AND c.id=o.complaint_id "
        "LEFT JOIN LATERAL (SELECT submitted_at, authority_reference FROM report_submissions "
        "WHERE tenant_id=:t AND obligation_id=o.id ORDER BY attempt DESC LIMIT 1) s ON true "
        f"WHERE o.tenant_id=:t AND c.product_id=:p AND {_VERSION.format(column='c.product_version_id')} "
        "ORDER BY o.created_at DESC, o.id"
    )
    rows, total = _paged(db, sql, _params(t, product, version), limit, offset)
    for row in rows:
        row["basis"] = f"Report on complaint {row['complaint_identifier']}"
    return rows, total


def investigations(db, t, product, version) -> list[dict]:
    """The product's investigations, each on its version (the one most of its complaints carry) and with every version
    its complaints are on; on a chosen version (PV-1), those with a complaint on it, so an investigation spanning
    several versions is under each, with those that record no version (``applies_to`` PRODUCT). Newest first."""
    rows = (
        db.execute(
            text(
                "SELECT i.id, i.business_id, i.investigation_identifier, i.investigation_question, i.status, "
                "i.workflow_state, i.opened_at, i.owner_ref, i.source_system, i.source_identifier, "
                "i.ingestion_timestamp, i.created_at, (SELECT count(*) FROM investigation_complaints ic "
                "WHERE ic.tenant_id=:t AND ic.investigation_id=i.id) AS complaints_held "
                "FROM investigations i WHERE i.tenant_id=:t AND i.product_id=:p "
                "ORDER BY i.opened_at DESC NULLS LAST, i.investigation_identifier"
            ),
            {"t": t, "p": product["id"]},
        )
        .mappings()
        .all()
    )
    service = Product360Service()
    on = service.investigation_versions(db, t, str(product["id"]))
    spans = service.investigation_version_sets(db, t, str(product["id"]))
    found = []
    for row in rows:
        item = _row(row)
        item["version_identifier"] = on.get(str(row["id"]))
        item["versions"] = spans.get(str(row["id"]), [])
        item["applies_to"] = "VERSION" if item["versions"] else "PRODUCT"
        if version is None or not item["versions"] or version["version_identifier"] in item["versions"]:
            found.append(item)
    return found


def signals(db, t, product, version) -> list[dict]:
    from backend.app.db.models.signals import OPEN_SIGNAL_STATUSES

    rows = db.execute(
        text(
            "SELECT s.id, s.business_id, s.title, s.problem_key, s.status, s.rule_code, s.rule_version, "
            "s.complaint_count, s.product_version_id, pv.version_identifier, s.created_at FROM signals s "
            "LEFT JOIN product_versions pv ON pv.tenant_id=s.tenant_id AND pv.id=s.product_version_id "
            f"WHERE s.tenant_id=:t AND s.product_id=:p AND s.status = ANY(:open) "
            f"AND {_VERSION.format(column='s.product_version_id')} ORDER BY s.created_at DESC, s.id"
        ),
        {**_params(t, product, version), "open": list(OPEN_SIGNAL_STATUSES)},
    ).mappings()
    return [_row(row) for row in rows]


def check_state(row) -> dict[str, Any]:
    """A CAPA's effectiveness check as people read it: the latest round's result, else planned (by a check round or
    the CAPA's own check date), else none. A planned check is never shown as effective."""
    status = str(row.get("check_status") or "").upper()
    planned_on = row.get("planned_on") or row.get("effectiveness_check_at")
    day = (
        planned_on.date().isoformat() if hasattr(planned_on, "date") else (str(planned_on)[:10] if planned_on else None)
    )
    if status in ("EFFECTIVE", "NOT_EFFECTIVE"):
        label = "Effective" if status == "EFFECTIVE" else "Not effective"
        signed = row.get("signed_by")
        return {
            "state": status,
            "label": label + (f", signed by {signed}" if signed else ""),
            "round": row.get("round"),
            "signed_by": signed,
            "signed_at": str(row["signed_at"]) if row.get("signed_at") else None,
        }
    if status == "PLANNED" or planned_on:
        return {
            "state": "PLANNED",
            "label": f"Effectiveness check planned for {day}; not yet recorded"
            if day
            else "Effectiveness check planned",
            "round": row.get("round"),
            "planned_on": day,
        }
    return {"state": "NONE", "label": "No effectiveness check planned", "round": None}


def capa_rows(db, t, where: str, params: dict) -> list[dict]:
    """CAPAs matching ``where`` (on ``k``), each with its latest effectiveness check round, the investigation it came
    from and its product, open first then by due date."""
    rows = db.execute(
        text(
            "SELECT DISTINCT ON (k.id) k.id, k.business_id, k.capa_identifier, k.title, k.status, k.due_at, "
            "k.effectiveness_check_at, k.qms_reference, k.investigation_id, k.product_id, k.source_system, "
            "k.source_identifier, k.ingestion_timestamp, k.created_at, i.investigation_identifier, "
            "i.business_id AS investigation_business_id, p.name AS product_name, ec.status AS check_status, ec.round, "
            "ec.planned_on, ec.signed_by, ec.signed_at FROM capas k "
            "LEFT JOIN capa_effectiveness_checks ec ON ec.tenant_id=k.tenant_id AND ec.capa_id=k.id "
            "LEFT JOIN investigations i ON i.tenant_id=k.tenant_id AND i.id=k.investigation_id "
            "LEFT JOIN products p ON p.tenant_id=k.tenant_id AND p.id=k.product_id "
            f"WHERE k.tenant_id=:t AND ({where}) ORDER BY k.id, ec.round DESC NULLS LAST"
        ),
        {"t": t, **params},
    ).mappings()
    found = []
    for row in rows:
        item = _row(row)
        item["check"] = check_state(row)
        found.append(item)
    found.sort(key=lambda item: (str(item["status"] or "").lower() == "closed", item["due_at"] or "", item["id"]))
    return found


def capas(db, t, product, version=None) -> list[dict]:
    """The product's CAPAs. On a chosen version (PV-1): those from an investigation listed on it (one with a complaint
    on it, or one recording no version), and those with no investigation (a CAPA names a product, never a version);
    each says whether it is the version's or the product's (``applies_to``)."""
    cases = {row["id"]: row["applies_to"] for row in investigations(db, t, product, version)} if version else None
    where = (
        "k.product_id=:p OR k.investigation_id IN (SELECT id FROM investigations WHERE tenant_id=:t AND product_id=:p)"
        if version is None
        else "(k.investigation_id IS NULL AND k.product_id=:p) OR k.investigation_id = ANY(CAST(:cases AS uuid[]))"
    )
    rows = capa_rows(db, t, where, {"p": product["id"], "cases": list(cases or [])})
    for row in rows:
        case = str(row["investigation_id"]) if row["investigation_id"] else None
        row["applies_to"] = (cases or {}).get(case, "VERSION") if case else "PRODUCT"
        row["basis"] = (
            f"CAPA from {row['investigation_identifier']}"
            if row["investigation_identifier"]
            else f"CAPA on {product['name']} (product level)"
        )
    return rows


def risks(db, t, product, version) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT r.id, r.business_id, r.risk_identifier, r.description, r.status, r.product_version_id, "
            "r.source_system, r.source_identifier, r.ingestion_timestamp, r.created_at, "
            "CASE WHEN r.product_version_id IS NULL THEN 'PRODUCT' ELSE 'VERSION' END AS applies_to FROM risks r "
            "WHERE r.tenant_id=:t AND r.product_id=:p AND (CAST(:v AS uuid) IS NULL OR r.product_version_id IS NULL "
            "OR r.product_version_id = CAST(:v AS uuid)) ORDER BY r.risk_identifier"
        ),
        _params(t, product, version),
    ).mappings()
    return [_row(row) for row in rows]


def monthly(db, t, versions, now: datetime | None = None) -> dict[str, Any]:
    """Complaints per month of each version (``id``, ``version_identifier``, ``release_timestamp``, optionally
    ``product_name``) over the last twelve months (by event date), with each version's release as a marker. Months
    without complaints read 0."""
    now = now or datetime.now(timezone.utc)
    year, month = divmod(now.year * 12 + now.month - 1 - (MONTHS - 1), 12)
    start = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    months = []
    cursor = start
    while cursor <= now:
        months.append(cursor.strftime("%Y-%m"))
        cursor = (cursor + timedelta(days=32)).replace(day=1)
    counts: dict[tuple[str, str], int] = {}
    for row in db.execute(
        text(
            "SELECT product_version_id, to_char(date_trunc('month', event_timestamp AT TIME ZONE 'UTC'), 'YYYY-MM') AS m, "
            "count(*) AS n FROM complaints WHERE tenant_id=:t AND product_version_id = ANY(CAST(:v AS uuid[])) "
            "AND event_timestamp >= :since "
            "GROUP BY 1, 2"
        ),
        {"t": t, "v": [str(v["id"]) for v in versions], "since": start},
    ).mappings():
        counts[(str(row["product_version_id"]), row["m"])] = int(row["n"])
    return {
        "months": months,
        "series": [
            {
                "version_id": str(v["id"]),
                "version_identifier": v["version_identifier"],
                "product_name": v.get("product_name"),
                "counts": [counts.get((str(v["id"]), month), 0) for month in months],
            }
            for v in versions
        ],
        "markers": [
            {
                "kind": "release",
                "label": f"{v['version_identifier']} released",
                "at": v["release_timestamp"].isoformat(),
            }
            for v in versions
            if v["release_timestamp"] is not None and v["release_timestamp"] >= start
        ],
    }


def _params(t, product, version) -> dict:
    return {"t": t, "p": product["id"], "v": str(version["id"]) if version else None}


def _head(product, version) -> dict:
    return {
        "product": {
            key: str(product[key]) if key == "id" else product[key]
            for key in ("id", "business_id", "product_identifier", "name")
        },
        "version": (
            {
                "id": str(version["id"]),
                "business_id": version["business_id"],
                "version_identifier": version["version_identifier"],
            }
            if version
            else None
        ),
    }


def tiles(db: Session, tenant_id: str, product_ref: str, version_ref: str | None) -> dict[str, Any]:
    product, versions, version = resolve(db, tenant_id, product_ref, version_ref)
    found: dict[str, dict] = {}
    for kind, reader in (("complaints", complaints), ("reports", reports)):
        items, total = reader(db, tenant_id, product, version, TILE_ITEMS, 0)
        found[kind] = {"count": total, "items": items}
    for kind, rows in (
        ("investigations", investigations(db, tenant_id, product, version)),
        ("signals", signals(db, tenant_id, product, version)),
        ("capas", capas(db, tenant_id, product, version)),
        ("risks", risks(db, tenant_id, product, version)),
    ):
        found[kind] = {"count": len(rows), "items": rows[:TILE_ITEMS]}
    return {**_head(product, version), "tiles": found, "monthly": monthly(db, tenant_id, versions)}


def one_list(
    db: Session,
    tenant_id: str,
    product_ref: str,
    version_ref: str | None,
    kind: str,
    limit: int,
    offset: int,
    response: Response,
) -> list[dict]:
    """One list, paged, with ``X-Total-Count`` and ``X-Next-Offset`` (backend/app/paging.py)."""
    product, _versions, version = resolve(db, tenant_id, product_ref, version_ref)
    if kind in ("complaints", "reports"):
        rows, total = (complaints if kind == "complaints" else reports)(db, tenant_id, product, version, limit, offset)
    else:
        every = {
            "investigations": lambda: investigations(db, tenant_id, product, version),
            "signals": lambda: signals(db, tenant_id, product, version),
            "capas": lambda: capas(db, tenant_id, product, version),
            "risks": lambda: risks(db, tenant_id, product, version),
        }[kind]()
        rows, total = every[offset : offset + limit], len(every)
    response.headers["X-Total-Count"] = str(total)
    following = offset + limit
    response.headers["X-Next-Offset"] = str(following) if following < total else ""
    return rows
