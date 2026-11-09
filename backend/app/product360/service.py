from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from backend.app.db.session import engine
from backend.app.product_facts import category_label
from backend.app.product360.origin import of_row
from backend.app.product360.schemas import (
    Product360Response,
    ProductSummary,
    TemporalRealityResponse,
    TimelineEvent,
)
from graph.service import RealityGraphService

TENANT_KEY = "ACME_CARE_SYNTHETIC"
EVENT_CATEGORIES = {
    "PRODUCT",
    "DESIGN",
    "COMPONENT",
    "SUPPLIER",
    "MANUFACTURING",
    "FIELD",
    "INVESTIGATION",
    "RISK",
    "EVIDENCE",
}


class Product360Error(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def rowdict(row) -> dict[str, Any]:
    result = dict(row)
    for key, value in list(result.items()):
        if value is not None and not isinstance(value, (str, int, float, bool, dict, list)):
            result[key] = str(value)
    return result


class Product360Service:
    def __init__(self) -> None:
        self.graph = RealityGraphService()

    def tenant_id(self) -> str:
        return self.graph.tenant_id()

    def count_products(self, tenant_id: str, db_engine=None) -> int:
        with (db_engine or engine).connect() as conn:
            return int(
                conn.execute(
                    text("SELECT count(*) FROM products WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id}
                ).scalar()
                or 0
            )

    def list_products(
        self,
        tenant_id: str | None = None,
        db_engine=None,
        *,
        limit: int | None = None,
        offset: int = 0,
        with_counts: bool = False,
    ) -> list[ProductSummary]:
        tenant_id = tenant_id or self.tenant_id()
        with (db_engine or engine).connect() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT p.id, p.business_id, p.product_identifier, p.name, p.product_family, p.lifecycle_status, "
                        "p.source_system, p.source_identifier, p.ingestion_timestamp, p.created_at, "
                        "array_agg(pv.version_identifier ORDER BY pv.version_identifier) AS versions "
                        "FROM products p LEFT JOIN product_versions pv ON pv.tenant_id=p.tenant_id AND pv.product_id=p.id "
                        "WHERE p.tenant_id=:tenant_id GROUP BY p.id, p.business_id, p.product_identifier, p.name, p.product_family, p.lifecycle_status "
                        "ORDER BY p.name, p.id LIMIT :limit OFFSET :offset"
                    ),
                    {"tenant_id": tenant_id, "limit": limit, "offset": offset},
                )
                .mappings()
                .all()
            )
            counts = self.product_counts(conn, tenant_id, [str(row["id"]) for row in rows]) if with_counts else {}
        return [
            ProductSummary(
                id=str(row["id"]),
                business_id=row["business_id"],
                product_identifier=row["product_identifier"],
                name=row["name"],
                product_family=row["product_family"],
                lifecycle_status=row["lifecycle_status"],
                available_versions=[v for v in (row["versions"] or []) if v],
                origin=of_row(row),
                counts=counts.get(str(row["id"])) if with_counts else None,
            )
            for row in rows
        ]

    def product_counts(self, conn, tenant_id: str, product_ids: list[str]) -> dict[str, dict[str, Any]]:
        """For each product of a page, in one statement: its newest version (by release, then name) and, on that
        version, the open complaints, the open investigations holding one of its complaints and the open trends to
        review; and the product's open CAPAs (a CAPA names a product, not a version)."""
        from backend.app.capa_effectiveness.rules import CLOSED_STATUSES, EXCLUDED_STATUSES
        from backend.app.db.models.signals import OPEN_SIGNAL_STATUSES

        if not product_ids:
            return {}
        rows = (
            conn.execute(
                text(
                    "WITH newest AS (SELECT DISTINCT ON (product_id) product_id, id, version_identifier "
                    "FROM product_versions WHERE tenant_id=:t AND product_id = ANY(CAST(:ids AS uuid[])) "
                    "ORDER BY product_id, release_timestamp DESC NULLS LAST, version_identifier DESC) "
                    "SELECT p.id, n.id AS version_id, n.version_identifier, "
                    "(SELECT count(*) FROM complaints c WHERE c.tenant_id=:t AND c.product_id=p.id "
                    " AND c.product_version_id IS NOT DISTINCT FROM n.id AND lower(coalesce(c.status,'')) <> 'closed') "
                    " AS open_complaints, "
                    "(SELECT count(*) FROM investigations i WHERE i.tenant_id=:t AND i.product_id=p.id "
                    " AND lower(coalesce(i.status,'')) <> 'closed' AND EXISTS (SELECT 1 FROM investigation_complaints ic "
                    " JOIN complaints c ON c.tenant_id=ic.tenant_id AND c.id=ic.complaint_id WHERE ic.tenant_id=:t "
                    " AND ic.investigation_id=i.id AND c.product_version_id IS NOT DISTINCT FROM n.id)) "
                    " AS open_investigations, "
                    "(SELECT count(*) FROM signals s WHERE s.tenant_id=:t AND s.product_id=p.id "
                    " AND s.product_version_id IS NOT DISTINCT FROM n.id AND s.status = ANY(:open_signals)) "
                    " AS open_signals, "
                    "(SELECT count(*) FROM capas k WHERE k.tenant_id=:t AND (k.product_id=p.id OR k.investigation_id IN "
                    " (SELECT id FROM investigations WHERE tenant_id=:t AND product_id=p.id)) "
                    " AND NOT (lower(coalesce(k.status,'')) = ANY(:closed_capas))) AS open_capas "
                    "FROM products p LEFT JOIN newest n ON n.product_id=p.id "
                    "WHERE p.tenant_id=:t AND p.id = ANY(CAST(:ids AS uuid[]))"
                ),
                {
                    "t": tenant_id,
                    "ids": product_ids,
                    "open_signals": list(OPEN_SIGNAL_STATUSES),
                    "closed_capas": sorted(CLOSED_STATUSES | EXCLUDED_STATUSES),
                },
            )
            .mappings()
            .all()
        )
        return {
            str(row["id"]): {
                "version_id": str(row["version_id"]) if row["version_id"] else None,
                "version_identifier": row["version_identifier"],
                **{
                    key: int(row[key])
                    for key in ("open_complaints", "open_investigations", "open_signals", "open_capas")
                },
            }
            for row in rows
        }

    def product360(
        self,
        product_id: str,
        version_id: str | None = None,
        as_of: datetime | None = None,
        mode: str = "current",
        tenant_id: str | None = None,
        db_engine=None,
        light: bool = False,
    ) -> Product360Response:
        """The product's page. ``light`` (W1) leaves out the complaint rows, evidence, failure modes, controls and the
        timeline, and gives their counts in ``overview`` instead: the read for the Product 360 page at any size."""
        # API callers must pass the authenticated tenant.  The synthetic default
        # remains only for existing internal/public Product 360 callers.
        tenant_id = tenant_id or self.tenant_id()
        with (db_engine or engine).connect() as conn:
            product = self.resolve_product(conn, tenant_id, product_id)
            if not product:
                raise Product360Error("PRODUCT_NOT_FOUND", "Product not found")
            product_id = str(product["id"])
            versions = (
                conn.execute(
                    text(
                        "SELECT * FROM product_versions WHERE tenant_id=:tenant_id AND product_id=:product_id ORDER BY release_timestamp NULLS LAST, version_identifier"
                    ),
                    {"tenant_id": tenant_id, "product_id": product_id},
                )
                .mappings()
                .all()
            )
            visible_versions = self.filter_rows_by_time(versions, as_of, mode, "release_timestamp")
            selected = self.select_version(versions, version_id, as_of)
            selected_id = str(selected["id"]) if selected else None
            components = self.components(conn, tenant_id, selected_id)
            suppliers = self.suppliers(conn, tenant_id, components)
            changes = self.changes(conn, tenant_id, product_id)
            changes = self.filter_rows_by_time(changes, as_of, mode, "effective_timestamp", "event_timestamp")
            lots = self.lots(conn, tenant_id, selected_id)
            lots = self.filter_rows_by_time(lots, as_of, mode, "manufactured_timestamp")
            investigations = self.investigations(conn, tenant_id, product_id)
            investigations = self.filter_rows_by_time(investigations, as_of, mode, "opened_at")
            light_counts = self.light_counts(conn, tenant_id, product_id, selected_id, investigations) if light else {}
            complaints = [] if light else self.complaints(conn, tenant_id, product_id, selected_id, as_of, mode)
            complaints = self.filter_rows_by_time(complaints, as_of, mode, "ingestion_timestamp", "event_timestamp")
            risks = (
                conn.execute(
                    text(
                        "SELECT id, business_id, risk_identifier, description, status FROM risks WHERE tenant_id=:tenant_id AND product_id=:product_id ORDER BY risk_identifier"
                    ),
                    {"tenant_id": tenant_id, "product_id": product_id},
                )
                .mappings()
                .all()
            )
            failure_modes = (
                []
                if light
                else (
                    conn.execute(
                        text(
                            "SELECT id, business_id, failure_mode_identifier, name FROM failure_modes WHERE tenant_id=:tenant_id ORDER BY failure_mode_identifier"
                        ),
                        {"tenant_id": tenant_id},
                    )
                    .mappings()
                    .all()
                )
            )
            controls = (
                []
                if light
                else (
                    conn.execute(
                        text(
                            "SELECT id, business_id, control_identifier, control_type, description, status FROM controls WHERE tenant_id=:tenant_id ORDER BY control_identifier"
                        ),
                        {"tenant_id": tenant_id},
                    )
                    .mappings()
                    .all()
                )
            )
            evidence = [] if light else self.evidence(conn, tenant_id, investigations, as_of, mode)
            evidence = self.filter_rows_by_time(evidence, as_of, mode, "ingestion_timestamp", "source_timestamp")
            timeline = (
                []
                if light
                else self.timeline(
                    product,
                    versions,
                    components,
                    suppliers,
                    changes,
                    lots,
                    complaints,
                    investigations,
                    evidence,
                    risks,
                    controls,
                )
            )
            timeline = self.filter_as_of(timeline, as_of, mode)
            limitations = self.limitations(
                lots,
                light_counts.get("missing_lot", sum(1 for row in complaints if row["lot_batch_id"] is None)),
                light_counts.get("late_evidence", self.late(evidence)),
            )
            provenance = [] if light else self.provenance(conn, tenant_id, product_id, selected_id)
            lot_details = self.lot_details(conn, tenant_id, lots)
        overview = {
            "version_count": len(versions),
            "component_count": len(components),
            "supplier_count": len(suppliers),
            "lot_count": len(lots),
            "complaint_count": light_counts.get("complaints", len(complaints)),
            "investigation_count": len(investigations),
            "evidence_count": light_counts.get("evidence", len(evidence)),
            "limitation_count": len(limitations),
            "no_root_cause_conclusion": True,
            "light": light,
        }
        return Product360Response(
            product={
                **rowdict(product),
                "device_category_label": category_label(product["device_category"]),
                "origin": of_row(product),
            },
            selected_version=rowdict(selected) if selected else None,
            versions=[rowdict(v) for v in visible_versions],
            overview=overview,
            configuration={
                "components": [{**rowdict(c), "origin": of_row(c)} for c in components],
                "suppliers": [{**rowdict(s), "origin": of_row(s)} for s in suppliers],
            },
            changes=[{**rowdict(c), "origin": of_row(c)} for c in changes],
            manufacturing={
                "lots": [{**rowdict(l), **lot_details.get(str(l["id"]), {}), "origin": of_row(l)} for l in lots],
                "sites": self.sites_for_lots(lots),
            },
            complaints=[rowdict(c) for c in complaints],
            investigations=[rowdict(i) for i in investigations],
            risks=[rowdict(r) for r in risks],
            failure_modes=[rowdict(f) for f in failure_modes],
            controls=[rowdict(c) for c in controls],
            evidence=[rowdict(e) for e in evidence],
            limitations=limitations,
            provenance=provenance,
            timeline=timeline,
            temporal_context={
                "mode": mode,
                "as_of": as_of.isoformat() if as_of else None,
                "event_as_of_distinct_from_known_as_of": True,
            },
            metadata={"tenant_id": tenant_id, "generated_at": utcnow().isoformat(), "ground_truth_used": False},
        )

    def temporal_reality(
        self,
        product_id: str,
        version_id: str | None = None,
        as_of: datetime | None = None,
        mode: str = "event",
        tenant_id: str | None = None,
        db_engine=None,
    ) -> TemporalRealityResponse:
        product = self.product360(
            product_id, version_id, as_of, "known" if mode == "known" else "event", tenant_id, db_engine=db_engine
        )
        events = product.timeline
        return TemporalRealityResponse(
            product_id=product_id,
            product_version_id=version_id,
            mode=mode,
            as_of=as_of,
            events=events,
            event_count=len(events),
            late_arriving_count=sum(1 for event in events if event.late_arriving),
            metadata={"ground_truth_used": False, "generated_at": utcnow().isoformat()},
        )

    def select_version(self, versions, version_id: str | None, as_of: datetime | None):
        if version_id:
            return next(
                (v for v in versions if str(v["id"]) == version_id or v["version_identifier"] == version_id), None
            )
        if as_of:
            eligible = [v for v in versions if v["release_timestamp"] and v["release_timestamp"] <= as_of]
            if eligible:
                return eligible[-1]
        return versions[-1] if versions else None

    def components(self, conn, tenant_id: str, version_id: str | None):
        if not version_id:
            return []
        return (
            conn.execute(
                text(
                    "SELECT DISTINCT c.id, c.business_id, c.component_identifier, c.name, c.revision, c.description, c.status, "
                    "c.source_system, c.source_identifier, c.ingestion_timestamp, c.created_at "
                    "FROM components c JOIN product_components pc ON pc.tenant_id=c.tenant_id AND pc.component_id=c.id "
                    "WHERE c.tenant_id=:tenant_id AND pc.product_version_id=:version_id ORDER BY c.component_identifier"
                ),
                {"tenant_id": tenant_id, "version_id": version_id},
            )
            .mappings()
            .all()
        )

    def suppliers(self, conn, tenant_id: str, components):
        ids = [str(row["id"]) for row in components]
        if not ids:
            return []
        return (
            conn.execute(
                text(
                    "SELECT DISTINCT s.id, s.business_id, s.supplier_identifier, s.name, s.status, c.component_identifier, "
                    "c.business_id AS component_business_id, c.name AS component_name, c.id AS component_id, "
                    "cs.effective_timestamp AS supplied_from, s.source_system, s.source_identifier, "
                    "s.ingestion_timestamp, s.created_at "
                    "FROM suppliers s JOIN component_suppliers cs ON cs.tenant_id=s.tenant_id AND cs.supplier_id=s.id "
                    "JOIN components c ON c.tenant_id=cs.tenant_id AND c.id=cs.component_id "
                    "WHERE s.tenant_id=:tenant_id AND c.id = ANY(:component_ids) ORDER BY s.name"
                ),
                {"tenant_id": tenant_id, "component_ids": ids},
            )
            .mappings()
            .all()
        )

    def resolve_product(self, conn, tenant_id: str, ref: str):
        """The organization's product by its record ID, MDARIX ID or product identifier; None when it has none."""
        return (
            conn.execute(
                text(
                    "SELECT * FROM products WHERE tenant_id=:tenant_id "
                    "AND (id::text=:ref OR business_id=:ref OR product_identifier=:ref) ORDER BY id::text=:ref DESC LIMIT 1"
                ),
                {"tenant_id": tenant_id, "ref": str(ref)},
            )
            .mappings()
            .one_or_none()
        )

    def light_counts(self, conn, tenant_id: str, product_id: str, version_id: str | None, investigations) -> dict:
        """The light read's counts in two queries: the version's complaints (and those without a lot), and the
        evidence of the product's investigations (and the evidence that arrived after its source time)."""
        sql = (
            "SELECT count(*) AS complaints, count(*) FILTER (WHERE lot_batch_id IS NULL) AS missing_lot "
            "FROM complaints WHERE tenant_id=:tenant_id AND product_id=:product_id"
        )
        params: dict[str, Any] = {"tenant_id": tenant_id, "product_id": product_id}
        if version_id:
            sql += " AND product_version_id=:version_id"
            params["version_id"] = version_id
        found = dict(conn.execute(text(sql), params).mappings().one())
        ids = [str(row["id"]) for row in investigations]
        found.update(
            conn.execute(
                text(
                    "SELECT count(*) AS evidence, count(*) FILTER (WHERE source_timestamp IS NOT NULL "
                    "AND ingestion_timestamp > source_timestamp) AS late_evidence "
                    "FROM evidence WHERE tenant_id=:tenant_id AND investigation_id = ANY(CAST(:ids AS uuid[]))"
                ),
                {"tenant_id": tenant_id, "ids": ids},
            )
            .mappings()
            .one()
        )
        return {key: int(value or 0) for key, value in found.items()}

    def changes(self, conn, tenant_id: str, product_id: str) -> list[dict[str, Any]]:
        """The product's changes only (W1, OD-11): those recorded as affecting a component of any of its versions, or
        the product itself, each with the components it affects and the complaints on the affected versions before
        and after it took effect. MDARIX lists what was recorded; it infers no cause."""
        rows = (
            conn.execute(
                text(
                    "WITH parts AS (SELECT DISTINCT pc.component_id, pc.product_version_id FROM product_components pc "
                    "JOIN product_versions pv ON pv.tenant_id=pc.tenant_id AND pv.id=pc.product_version_id "
                    "WHERE pc.tenant_id=:tenant_id AND pv.product_id=:product_id), "
                    "hits AS (SELECT rr.source_entity_id AS change_id, rr.target_entity_type, rr.target_entity_id "
                    "FROM reality_relationships rr WHERE rr.tenant_id=:tenant_id AND rr.source_entity_type='Change' "
                    "AND rr.relationship_type='AFFECTS' AND ((rr.target_entity_type='Component' "
                    "AND rr.target_entity_id IN (SELECT component_id FROM parts)) "
                    "OR (rr.target_entity_type='Product' AND rr.target_entity_id=:product_id))) "
                    "SELECT ch.id, ch.business_id, ch.change_identifier, ch.change_type, ch.description, "
                    "ch.event_timestamp, ch.effective_timestamp, ch.source_system, ch.source_identifier, "
                    "ch.ingestion_timestamp, ch.created_at, "
                    "array_remove(array_agg(DISTINCT c.component_identifier), NULL) AS affects, "
                    "array_remove(array_agg(DISTINCT c.name), NULL) AS affects_names, "
                    "bool_or(h.target_entity_type='Product') AS affects_product, "
                    "array_remove(array_agg(DISTINCT p.product_version_id), NULL) AS versions "
                    "FROM hits h JOIN changes ch ON ch.tenant_id=:tenant_id AND ch.id=h.change_id "
                    "LEFT JOIN components c ON c.tenant_id=:tenant_id AND h.target_entity_type='Component' "
                    "AND c.id=h.target_entity_id "
                    "LEFT JOIN parts p ON h.target_entity_type='Component' AND p.component_id=h.target_entity_id "
                    "GROUP BY ch.id ORDER BY ch.effective_timestamp NULLS LAST, ch.change_identifier"
                ),
                {"tenant_id": tenant_id, "product_id": product_id},
            )
            .mappings()
            .all()
        )
        if not rows:
            return []
        split = self._split(conn, tenant_id, product_id, rows)
        result = []
        for row in rows:
            item = dict(row)
            item["versions"] = sorted(str(v) for v in row["versions"] or [])
            item["complaints_before"], item["complaints_after"] = split.get(str(row["id"]), (0, 0))
            result.append(item)
        return result

    def _split(self, conn, tenant_id: str, product_id: str | None, changes) -> dict[str, tuple[int, int]]:
        """``{change id: (before, after)}`` in one grouped count: the complaints on each change's affected versions
        (every version of the product for a change on the whole product), by whether the event came before the change
        took effect. A complaint with no event date is in neither."""
        pairs = [
            (str(row["id"]), str(version))
            for row in changes
            if not row["affects_product"]
            for version in row["versions"] or []
        ]
        rows = conn.execute(
            text(
                "SELECT ch.id, count(c.id) FILTER (WHERE c.event_timestamp < coalesce(ch.effective_timestamp, "
                "ch.event_timestamp)) AS before, count(c.id) FILTER (WHERE c.event_timestamp >= "
                "coalesce(ch.effective_timestamp, ch.event_timestamp)) AS after "
                "FROM changes ch JOIN complaints c ON c.tenant_id=ch.tenant_id "
                "AND (CAST(:product_id AS uuid) IS NULL OR c.product_id=CAST(:product_id AS uuid)) "
                "WHERE ch.tenant_id=:tenant_id AND ch.id = ANY(CAST(:ids AS uuid[])) AND (ch.id = ANY(CAST(:whole AS uuid[])) "
                "OR (ch.id::text || '/' || c.product_version_id::text) = ANY(CAST(:pairs AS text[]))) GROUP BY ch.id"
            ),
            {
                "tenant_id": tenant_id,
                "product_id": product_id,
                "ids": [str(row["id"]) for row in changes],
                "whole": [str(row["id"]) for row in changes if row["affects_product"]],
                "pairs": [f"{change}/{version}" for change, version in pairs],
            },
        ).mappings()
        return {str(row["id"]): (int(row["before"]), int(row["after"])) for row in rows}

    def lots(self, conn, tenant_id: str, version_id: str | None):
        if not version_id:
            return []
        return (
            conn.execute(
                text(
                    "SELECT l.id, l.business_id, l.lot_identifier, l.status, l.effective_timestamp AS manufactured_timestamp, "
                    "l.expiry_date, l.quantity, l.source_system, l.source_identifier, l.ingestion_timestamp, l.created_at, "
                    "ms.site_identifier, ms.business_id AS site_business_id, ms.name AS site_name, "
                    "CASE WHEN l.source_identifier IN ('LOT-010','LOT-013','LOT-017') THEN 'PARTIAL' ELSE 'COMPLETE' END AS traceability_state "
                    "FROM lot_batches l LEFT JOIN manufacturing_sites ms ON ms.tenant_id=l.tenant_id AND ms.id=l.manufacturing_site_id "
                    "WHERE l.tenant_id=:tenant_id AND l.product_version_id=:version_id ORDER BY l.effective_timestamp NULLS LAST, l.lot_identifier"
                ),
                {"tenant_id": tenant_id, "version_id": version_id},
            )
            .mappings()
            .all()
        )

    def lot_details(self, conn, tenant_id: str, lots) -> dict[str, dict[str, Any]]:
        """Per lot (W1, the Lots tab): its complaints and complaints per 1,000 units released (None when the units are
        not known), the component lots its genealogy names, and whether its distribution is imported."""
        from backend.app.lot_impact.service import per_thousand

        ids = [str(row["id"]) for row in lots]
        if not ids:
            return {}
        rows = conn.execute(
            text(
                "SELECT l.id, (SELECT count(*) FROM complaints c WHERE c.tenant_id=:t AND c.lot_batch_id=l.id) AS complaints, "
                "(SELECT coalesce(array_agg(cm.name || ' lot ' || lc.component_lot_identifier ORDER BY cm.name), '{}') "
                " FROM lot_components lc JOIN components cm ON cm.tenant_id=lc.tenant_id AND cm.id=lc.component_id "
                " WHERE lc.tenant_id=:t AND lc.lot_batch_id=l.id AND lc.component_lot_identifier IS NOT NULL) AS genealogy, "
                "EXISTS (SELECT 1 FROM lot_distributions d WHERE d.tenant_id=:t AND d.lot_batch_id=l.id) AS distribution_imported "
                "FROM lot_batches l WHERE l.tenant_id=:t AND l.id = ANY(CAST(:ids AS uuid[]))"
            ),
            {"t": tenant_id, "ids": ids},
        ).mappings()
        quantity = {str(row["id"]): row.get("quantity") for row in lots}
        return {
            str(row["id"]): {
                "complaints": int(row["complaints"]),
                "per_1000": per_thousand(int(row["complaints"]), quantity.get(str(row["id"]))),
                "genealogy": list(row["genealogy"] or []),
                "distribution_imported": bool(row["distribution_imported"]),
            }
            for row in rows
        }

    def complaints(
        self, conn, tenant_id: str, product_id: str, version_id: str | None, as_of: datetime | None, mode: str
    ):
        sql = "SELECT id, business_id, complaint_identifier, event_timestamp, recorded_timestamp, ingestion_timestamp, description, status, lot_batch_id FROM complaints WHERE tenant_id=:tenant_id AND product_id=:product_id"
        params = {"tenant_id": tenant_id, "product_id": product_id}
        if version_id:
            sql += " AND product_version_id=:version_id"
            params["version_id"] = version_id
        sql += " ORDER BY event_timestamp NULLS LAST, complaint_identifier"
        return conn.execute(text(sql), params).mappings().all()

    def investigations(self, conn, tenant_id: str, product_id: str):
        return (
            conn.execute(
                text(
                    "SELECT id, business_id, investigation_identifier, investigation_question, status, opened_at, closed_at FROM investigations WHERE tenant_id=:tenant_id AND product_id=:product_id ORDER BY opened_at"
                ),
                {"tenant_id": tenant_id, "product_id": product_id},
            )
            .mappings()
            .all()
        )

    def list_product_investigations(
        self, product_id: str, tenant_id: str | None = None, db_engine=None
    ) -> list[dict[str, Any]]:
        """Return all investigations associated with a product for workspace access.

        This intentionally does not apply an as-of filter: association access must not
        reinterpret a historical Product 360 snapshot as absence of an investigation.
        """
        tenant_id = tenant_id or self.tenant_id()
        with (db_engine or engine).connect() as conn:
            product = (
                conn.execute(
                    text("SELECT id FROM products WHERE tenant_id=:tenant_id AND id=:id"),
                    {"tenant_id": tenant_id, "id": product_id},
                )
                .mappings()
                .one_or_none()
            )
            if not product:
                raise Product360Error("PRODUCT_NOT_FOUND", "Product not found")
            rows = self.investigations(conn, tenant_id, product_id)
            workflow = self.investigation_workflow(conn, tenant_id, product_id)
        return [{**rowdict(row), **workflow.get(str(row["id"]), {})} for row in rows]

    def investigation_workflow(self, conn, tenant_id: str, product_id: str) -> dict[str, dict[str, Any]]:
        """Each case's workflow state (with its label), priority, due date and owner, for the product's case list. Read
        apart from ``investigations`` so the Product 360 snapshot stays as it is; empty when the organization database
        has no such columns yet."""
        from backend.app.case_workflow.states import effective_state, state_label

        try:
            rows = (
                conn.execute(
                    text(
                        "SELECT id, status, workflow_state, priority, due_at, owner_ref FROM investigations "
                        "WHERE tenant_id=:tenant_id AND product_id=:product_id"
                    ),
                    {"tenant_id": tenant_id, "product_id": product_id},
                )
                .mappings()
                .all()
            )
        except Exception:
            # Read last, after the case list itself, so a failure here leaves that list intact.
            return {}
        result = {}
        for row in rows:
            state = effective_state(row["workflow_state"], row["status"])
            result[str(row["id"])] = {
                "workflow_state": state,
                "workflow_state_label": state_label(state),
                "priority": row["priority"],
                "due_at": row["due_at"].isoformat() if row["due_at"] is not None else None,
                "owner_ref": row["owner_ref"],
            }
        for investigation_id, version in self.investigation_versions(conn, tenant_id, product_id).items():
            result.setdefault(investigation_id, {})["version_identifier"] = version
        return result

    def investigation_versions(self, conn, tenant_id: str, product_id: str) -> dict[str, str]:
        """Each case's product version: the one most of its complaints carry (0.10.70). The workspace shows a case on its
        own version, never on the version a record opened before it was on."""
        rows = (
            conn.execute(
                text(
                    "SELECT ic.investigation_id, pv.version_identifier, count(*) AS n FROM investigation_complaints ic "
                    "JOIN complaints c ON c.tenant_id=ic.tenant_id AND c.id=ic.complaint_id "
                    "JOIN product_versions pv ON pv.tenant_id=c.tenant_id AND pv.id=c.product_version_id "
                    "WHERE ic.tenant_id=:tenant_id AND c.product_id=:product_id "
                    "GROUP BY ic.investigation_id, pv.version_identifier "
                    "ORDER BY ic.investigation_id, n DESC, pv.version_identifier"
                ),
                {"tenant_id": tenant_id, "product_id": product_id},
            )
            .mappings()
            .all()
        )
        found: dict[str, str] = {}
        for row in rows:
            found.setdefault(str(row["investigation_id"]), row["version_identifier"])
        return found

    def evidence(self, conn, tenant_id: str, investigations, as_of: datetime | None, mode: str):
        ids = [str(row["id"]) for row in investigations]
        if not ids:
            return []
        return (
            conn.execute(
                text(
                    "SELECT e.id, e.business_id, e.evidence_identifier, e.evidence_type, e.title, e.source_reference, e.reliability_status, e.content, "
                    "e.source_timestamp, e.recorded_timestamp, e.ingestion_timestamp "
                    "FROM evidence e JOIN staged_source_records s ON s.tenant_id=e.tenant_id AND s.raw_payload->>'evidence_id'=e.evidence_identifier "
                    "JOIN investigations i ON i.tenant_id=e.tenant_id AND i.source_identifier=s.raw_payload->>'investigation_id' "
                    "WHERE e.tenant_id=:tenant_id AND i.id = ANY(:investigation_ids) ORDER BY e.source_timestamp NULLS LAST, e.evidence_identifier"
                ),
                {"tenant_id": tenant_id, "investigation_ids": ids},
            )
            .mappings()
            .all()
        )

    def timeline(
        self,
        product,
        versions,
        components,
        suppliers,
        changes,
        lots,
        complaints,
        investigations,
        evidence,
        risks,
        controls,
    ) -> list[TimelineEvent]:
        events: list[TimelineEvent] = []
        for version in versions:
            events.append(
                self.event(
                    "PRODUCT_VERSION_EFFECTIVE",
                    "PRODUCT",
                    f"Version {version['version_identifier']} effective",
                    "product_version",
                    version["id"],
                    business_id=version.get("business_id"),
                    effective=version["release_timestamp"],
                    source=version.get("source_system"),
                )
            )
        for change in changes:
            events.append(
                self.event(
                    "CHANGE_EFFECTIVE",
                    "DESIGN",
                    change["description"],
                    "change",
                    change["id"],
                    business_id=change.get("business_id"),
                    event=change["event_timestamp"],
                    effective=change["effective_timestamp"],
                    source=change.get("source_system"),
                )
            )
        for lot in lots:
            events.append(
                self.event(
                    "MANUFACTURING_LOT",
                    "MANUFACTURING",
                    f"Lot {lot['lot_identifier']} manufactured",
                    "lot_batch",
                    lot["id"],
                    business_id=lot.get("business_id"),
                    effective=lot["manufactured_timestamp"],
                    quality=lot["traceability_state"],
                )
            )
        for complaint in complaints:
            events.append(
                self.event(
                    "COMPLAINT_EVENT",
                    "FIELD",
                    complaint["complaint_identifier"],
                    "complaint",
                    complaint["id"],
                    business_id=complaint.get("business_id"),
                    event=complaint["event_timestamp"],
                    recorded=complaint["recorded_timestamp"],
                    knowledge=complaint["ingestion_timestamp"],
                    quality=complaint["status"],
                )
            )
        for investigation in investigations:
            events.append(
                self.event(
                    "INVESTIGATION_OPENED",
                    "INVESTIGATION",
                    investigation["investigation_identifier"],
                    "investigation",
                    investigation["id"],
                    business_id=investigation.get("business_id"),
                    event=investigation["opened_at"],
                )
            )
        for item in evidence:
            late = bool(
                item["source_timestamp"]
                and item["ingestion_timestamp"]
                and item["ingestion_timestamp"] > item["source_timestamp"]
            )
            events.append(
                self.event(
                    "EVIDENCE_RECEIVED",
                    "EVIDENCE",
                    item["title"],
                    "evidence",
                    item["id"],
                    business_id=item.get("business_id"),
                    event=item["source_timestamp"],
                    recorded=item["recorded_timestamp"],
                    knowledge=item["ingestion_timestamp"],
                    source=item["source_reference"],
                    quality=item["reliability_status"],
                    evidence=True,
                    late=late,
                )
            )
        return sorted(
            events,
            key=lambda e: (
                e.event_time
                or e.effective_time
                or e.recorded_time
                or e.knowledge_available_time
                or datetime.max.replace(tzinfo=timezone.utc)
            ),
        )

    def event(
        self,
        event_type: str,
        category: str,
        title: str,
        entity_type: str,
        entity_id: Any,
        business_id: str | None = None,
        event=None,
        effective=None,
        recorded=None,
        knowledge=None,
        source=None,
        quality=None,
        evidence=False,
        late=False,
    ) -> TimelineEvent:
        return TimelineEvent(
            event_id=f"{event_type}:{entity_type}:{entity_id}",
            event_type=event_type,
            category=category,
            title=title,
            related_entity_type=entity_type,
            related_entity_id=str(entity_id),
            related_entity_business_id=business_id,
            event_time=event,
            effective_time=effective,
            recorded_time=recorded,
            knowledge_available_time=knowledge,
            source=source,
            quality_status=quality,
            evidence_available=evidence,
            late_arriving=late,
        )

    def filter_as_of(self, events: list[TimelineEvent], as_of: datetime | None, mode: str) -> list[TimelineEvent]:
        if not as_of:
            return events
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        if mode == "known":
            return [
                e
                for e in events
                if (
                    e.knowledge_available_time
                    or e.recorded_time
                    or e.event_time
                    or e.effective_time
                    or datetime.max.replace(tzinfo=timezone.utc)
                )
                <= as_of
            ]
        return [
            e
            for e in events
            if (e.event_time or e.effective_time or datetime.max.replace(tzinfo=timezone.utc)) <= as_of
        ]

    def filter_rows_by_time(
        self, rows, as_of: datetime | None, mode: str, known_key: str, event_key: str | None = None
    ):
        if not as_of:
            return rows
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        primary_key = known_key if mode == "known" else (event_key or known_key)
        fallback_key = event_key or known_key
        return [
            row
            for row in rows
            if (row[primary_key] or row[fallback_key]) and (row[primary_key] or row[fallback_key]) <= as_of
        ]

    @staticmethod
    def late(evidence) -> int:
        return sum(
            1
            for row in evidence
            if row["source_timestamp"]
            and row["ingestion_timestamp"]
            and row["ingestion_timestamp"] > row["source_timestamp"]
        )

    def limitations(self, lots, missing_lot: int, late: int) -> list[dict[str, Any]]:
        """The data limitations: lots with partial traceability, and the counts of complaints without a lot and of
        evidence that arrived after its source time."""
        items = []
        partial_lots = [row for row in lots if row["traceability_state"] == "PARTIAL"]
        if partial_lots:
            items.append(
                {
                    "code": "INCOMPLETE_TRACEABILITY",
                    "severity": "WARNING",
                    "description": f"{len(partial_lots)} lots have partial traceability.",
                }
            )
        if missing_lot:
            items.append(
                {
                    "code": "MISSING_LOT_REFERENCE",
                    "severity": "WARNING",
                    "description": f"{missing_lot} complaints lack resolved lot context.",
                }
            )
        if late:
            items.append(
                {
                    "code": "LATE_ARRIVING_EVIDENCE",
                    "severity": "INFO",
                    "description": f"{late} evidence records arrived after their event/source time.",
                }
            )
        items.append(
            {
                "code": "NO_CAUSAL_CONCLUSION",
                "severity": "INFO",
                "description": "Product 360 shows lifecycle context only; no root-cause conclusion is generated.",
            }
        )
        return items

    def provenance(self, conn, tenant_id: str, product_id: str, version_id: str | None) -> list[dict[str, Any]]:
        rows = (
            conn.execute(
                text(
                    "SELECT canonical_entity_type, canonical_business_identifier, source_value, resolution_rule, resolution_status, provenance "
                    "FROM source_canonical_links WHERE tenant_id=:tenant_id AND canonical_entity_type IN ('product','product_version','complaint','evidence') "
                    "ORDER BY canonical_entity_type LIMIT 40"
                ),
                {"tenant_id": tenant_id},
            )
            .mappings()
            .all()
        )
        return [rowdict(row) for row in rows]

    def sites_for_lots(self, lots) -> list[dict[str, Any]]:
        seen = {}
        for lot in lots:
            if lot["site_identifier"]:
                seen[lot["site_identifier"]] = {
                    "business_id": lot["site_business_id"],
                    "site_identifier": lot["site_identifier"],
                    "name": lot["site_name"],
                }
        return list(seen.values())
