from pathlib import Path

ROOT = Path(__file__).parents[1]
ROUTER = (ROOT / "backend" / "app" / "access_router.py").read_text(encoding="utf-8")
UI = (ROOT / "frontend" / "src" / "features" / "stage2" / "Stage2AdminControlPlane.tsx").read_text(encoding="utf-8")


def test_stage2_platform_endpoints_exist_and_are_platform_scoped():
    for route in ("/platform-admin/plans", "/platform-admin/customers/{tenant_id}/subscription", "/platform-admin/customers/{tenant_id}/usage", "/platform-admin/canonical-model", "/platform-admin/mapping-impact"):
        assert f'"{route}"' in ROUTER
    assert "_require_platform_admin" in ROUTER


def test_stage2_ui_covers_catalog_subscription_model_and_mapping_governance():
    for endpoint in ("plans", "customers", "canonical-model", "mapping-impact"):
        assert endpoint in UI
    assert "released versions are immutable" in UI


def test_stage2_documentation_deliverables_exist():
    for name in ("architecture/admin/ADMIN_PLANS_SUBSCRIPTIONS.md", "architecture/admin/ADMIN_IDENTITY_ACCESS.md", "architecture/admin/ADMIN_CONNECTOR_CATALOG.md", "architecture/admin/ADMIN_CANONICAL_DATA_MODEL.md", "architecture/admin/ADMIN_MASTER_MAPPING.md", "architecture/admin/ADMIN_MAPPING_IMPACT.md", "history/stage-reports/ADMIN_STAGE2_IMPLEMENTATION_REPORT.md"):
        assert (ROOT / "docs" / name).exists()
