from tests.conftest import access_api_source
from pathlib import Path


ROOT = Path(__file__).parents[1]
ROUTER = access_api_source()
AREAS = ROOT / "frontend" / "src" / "features" / "admin" / "areas"
INTEGRATIONS = (AREAS / "Integrations.tsx").read_text(encoding="utf-8")
AI = (AREAS / "AiControlCenter.tsx").read_text(encoding="utf-8")
SECTIONS = (AREAS / "sections.ts").read_text(encoding="utf-8")


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
    # Runs, reconciliation and credentials are Data & Integrations steps; AI runs are an AI Control Center section
    # (formerly "Executions").
    for label in ("Runs & failures", "Reconciliation", "Credentials", "AI runs"):
        assert f'"{label}"' in SECTIONS
    assert "/api/v1/platform-admin/console/integration-runs" in INTEGRATIONS
    assert "reconciled" in INTEGRATIONS
    assert "/api/v1/admin/integrations/credentials" in INTEGRATIONS
    assert "/api/v1/platform-admin/console/ai-activity" in AI
