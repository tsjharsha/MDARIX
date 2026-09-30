from pathlib import Path


ROOT = Path(__file__).parents[1]
ROUTER = (ROOT / "backend" / "app" / "access_router.py").read_text(encoding="utf-8")
SCREEN = (ROOT / "frontend" / "src" / "features" / "admin" / "PlatformAdminScreen.tsx").read_text(encoding="utf-8")


def test_operational_admin_endpoints_are_tenant_scoped_and_secret_safe():
    for route in (
        "/admin/integrations/runs",
        "/admin/integrations/reconciliation",
        "/admin/integrations/credentials",
        "/admin/ai-executions",
    ):
        assert f'@router.get("{route}")' in ROUTER
    assert '"secret_value": None' in ROUTER
    assert "secrets_redacted" in ROUTER


def test_operational_admin_frontend_surfaces_are_connected():
    for label in ("Integration runs", "Reconciliation", "Credentials", "AI executions"):
        assert label in SCREEN
    assert "AdminOperationalRecords" in SCREEN
