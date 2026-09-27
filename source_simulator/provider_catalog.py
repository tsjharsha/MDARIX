"""Deterministic provider entities and one-to-one MDARIX mapping contracts."""

PROVIDER_CATALOG = {
    "TRACKWISE": {
        "Complaint": {
            "complaint_number": "complaint_identifier",
            "opened_date": "reported_at",
            "severity": "severity",
            "status": "lifecycle_status",
        },
        "Investigation": {
            "investigation_number": "investigation_identifier",
            "opened_date": "opened_at",
            "status": "status",
        },
        "CAPA": {
            "capa_number": "capa_identifier",
            "opened_date": "opened_at",
            "status": "status",
        },
    },
    "PLM": {
        "Product": {"product_number": "product_identifier", "name": "name", "status": "lifecycle_status"},
        "ProductVersion": {"product_number": "product_identifier", "version": "version_identifier", "release_date": "release_timestamp"},
        "Component": {"component_number": "component_identifier", "name": "name", "status": "lifecycle_status"},
        "Change": {"change_number": "change_identifier", "effective_date": "effective_at", "status": "status"},
    },
    "ERP": {
        "Supplier": {"supplier_number": "supplier_identifier", "name": "name", "status": "status"},
        "Site": {"site_number": "site_identifier", "name": "name", "status": "status"},
        "Lot": {"lot_number": "lot_identifier", "product_number": "product_identifier", "status": "status"},
    },
    "SUPPLIER": {
        "SupplierPart": {"part_number": "supplier_part_identifier", "description": "description", "status": "status"},
        "Certificate": {"certificate_number": "certificate_identifier", "expiry_date": "expires_at", "status": "status"},
        "SupplierEvent": {"event_number": "event_identifier", "event_date": "occurred_at", "event_type": "event_type"},
    },
    "VEEVA_QMS": {
        "QualityEvent": {"event_number": "event_identifier", "opened_date": "reported_at", "severity": "severity", "status": "status"},
        "Investigation": {"investigation_number": "investigation_identifier", "opened_date": "opened_at", "status": "status"},
        "CAPA": {"capa_number": "capa_identifier", "opened_date": "opened_at", "status": "status"},
    },
    "TEAMCENTER": {
        "Item": {"item_number": "product_identifier", "name": "name", "lifecycle": "lifecycle_status"},
        "ItemRevision": {"item_number": "product_identifier", "revision": "version_identifier", "release_date": "release_timestamp"},
        "ChangeNotice": {"change_number": "change_identifier", "effective_date": "effective_at", "status": "status"},
    },
    "ORACLE_ERP": {
        "Supplier": {"supplier_number": "supplier_identifier", "name": "name", "status": "status"},
        "PurchaseOrder": {"order_number": "purchase_order_identifier", "supplier_number": "supplier_identifier", "status": "status"},
        "Lot": {"lot_number": "lot_identifier", "item_number": "product_identifier", "status": "status"},
    },
    "COUPA": {
        "Supplier": {"supplier_number": "supplier_identifier", "name": "name", "status": "status"},
        "PurchaseOrder": {"order_number": "purchase_order_identifier", "supplier_number": "supplier_identifier", "status": "status"},
        "SupplierRisk": {"risk_number": "supplier_risk_identifier", "supplier_number": "supplier_identifier", "status": "status"},
    },
}

PROVIDER_PORTS = {"TRACKWISE": 8101, "PLM": 8102, "ERP": 8103, "SUPPLIER": 8104, "VEEVA_QMS": 8105, "TEAMCENTER": 8106, "ORACLE_ERP": 8107, "COUPA": 8108}

def schema_for(provider: str, entity: str) -> list[str]:
    return list(PROVIDER_CATALOG.get(provider.upper(), {}).get(entity, {}).keys())
