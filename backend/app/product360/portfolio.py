"""The executive's portfolio (Persona Blueprint wave D): exposure per product, read from existing records only.

``GET /api/v1/portfolio``: for each product of the organization, over every version: its lots, the units those lots
released and shipped (null when no lot or shipment records them), its open complaints, the complaints with a signed
"reportable" conclusion in at least one market, its open investigations and how many of those still wait for a signed
decision, and its signed decisions. Each figure carries its definition beside it (``definitions``), so the screen says
what it counts. Read-only, open to every signed-in member (as Product 360 is); the tenant is the request's.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.db.data_plane import get_data_plane_db
from backend.app.product360.origin import of_row
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1", tags=["Portfolio"])

# What each figure counts, said once and shown beside it.
DEFINITIONS = {
    "lots": "Lots recorded for any version of the product.",
    "units_released": "Devices those lots released, where a lot records it.",
    "units_shipped": "Devices shipped from those lots, where a shipment is recorded.",
    "open_complaints": "Complaints on the product not closed, every version.",
    "reportable": "Complaints with a signed 'reportable' conclusion in at least one market (current version only).",
    "open_investigations": "Investigations on the product not closed.",
    "awaiting_decision": "Open investigations with no signed decision yet.",
    "signed_decisions": "Decisions signed on the product's investigations.",
}

_PRODUCT_INVESTIGATIONS = "SELECT i.id FROM investigations i WHERE i.tenant_id=:t AND i.product_id=p.id"
_SIGNED = "d.tenant_id=:t AND d.investigation_id=i.id AND d.decided_at IS NOT NULL"
_LOTS = (
    "FROM lot_batches l JOIN product_versions v ON v.tenant_id=l.tenant_id AND v.id=l.product_version_id "
    "WHERE l.tenant_id=:t AND v.product_id=p.id"
)

PORTFOLIO = text(
    "SELECT p.id, p.product_identifier, p.name, p.source_system, p.source_identifier, "
    f"(SELECT count(*) {_LOTS}) AS lots, "
    f"(SELECT sum(l.quantity) {_LOTS}) AS units_released, "
    "(SELECT sum(dist.quantity) FROM lot_distributions dist JOIN lot_batches l ON l.tenant_id=dist.tenant_id "
    " AND l.id=dist.lot_batch_id JOIN product_versions v ON v.tenant_id=l.tenant_id AND v.id=l.product_version_id "
    " WHERE dist.tenant_id=:t AND v.product_id=p.id) AS units_shipped, "
    "(SELECT count(*) FROM complaints c WHERE c.tenant_id=:t AND c.product_id=p.id "
    " AND lower(coalesce(c.status,'')) <> 'closed') AS open_complaints, "
    "(SELECT count(DISTINCT a.complaint_id) FROM complaint_market_assessments a JOIN complaints c "
    " ON c.tenant_id=a.tenant_id AND c.id=a.complaint_id WHERE a.tenant_id=:t AND c.product_id=p.id "
    " AND a.conclusion='REPORTABLE' AND a.signed_at IS NOT NULL AND a.superseded_by IS NULL) AS reportable, "
    "(SELECT count(*) FROM investigations i WHERE i.tenant_id=:t AND i.product_id=p.id "
    " AND lower(coalesce(i.status,'')) <> 'closed') AS open_investigations, "
    "(SELECT count(*) FROM investigations i WHERE i.tenant_id=:t AND i.product_id=p.id "
    " AND lower(coalesce(i.status,'')) <> 'closed' "
    f" AND NOT EXISTS (SELECT 1 FROM decisions d WHERE {_SIGNED})) AS awaiting_decision, "
    "(SELECT count(*) FROM decisions d WHERE d.tenant_id=:t AND d.decided_at IS NOT NULL "
    f" AND d.investigation_id IN ({_PRODUCT_INVESTIGATIONS})) AS signed_decisions "
    "FROM products p WHERE p.tenant_id=:t ORDER BY p.name, p.id LIMIT 200"
)

_COUNTS = ("lots", "open_complaints", "reportable", "open_investigations", "awaiting_decision", "signed_decisions")


@router.get("/portfolio")
def portfolio(
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_data_plane_db),
) -> dict:
    rows = db.execute(PORTFOLIO, {"t": str(ctx.tenant_id)}).mappings().all()
    return {
        "definitions": DEFINITIONS,
        "products": [
            {
                "id": str(row["id"]),
                "product_identifier": row["product_identifier"],
                "name": row["name"],
                "origin": of_row(row),
                **{key: int(row[key] or 0) for key in _COUNTS},
                "units_released": None if row["units_released"] is None else int(row["units_released"]),
                "units_shipped": None if row["units_shipped"] is None else int(row["units_shipped"]),
            }
            for row in rows
        ],
    }
