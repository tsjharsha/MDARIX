from tests.conftest import access_api_source
from pathlib import Path


ROOT = Path(__file__).parents[1]
UI = (ROOT / "frontend" / "src" / "features" / "customer-admin" / "CustomerAdminControlPlane.tsx").read_text(
    encoding="utf-8"
)
ROUTER = access_api_source()


def test_customer_admin_uses_server_scoped_mutation_contracts():
    for endpoint in (
        "/api/v1/admin/identity/users",
        "/api/v1/admin/identity/roles",
        "/api/v1/admin/configuration/connectors",
        "/api/v1/admin/configuration/mappings",
        "/api/v1/admin/audit-history/export",
    ):
        assert endpoint in UI or endpoint.replace("/export", "") in UI
    assert 'credentials: "include"' in UI
    assert '@router.post("/admin/identity/users")' in ROUTER
    assert '@router.post("/admin/configuration/connectors")' in ROUTER
    assert '@router.post("/admin/configuration/mappings")' in ROUTER


def test_customer_admin_does_not_accept_browser_tenant_as_authority():
    invite_block = UI[UI.index("const submitInvite") : UI.index("const currentNav")]
    assert "tenant_id" not in invite_block
    assert "Tenant context is server-derived" in UI or "server-derived tenant scope" in UI


def test_customer_admin_has_auditable_export_and_mfa_entry_points():
    assert "/api/v1/admin/audit-history/export?output_format=CSV" in UI
    assert "/api/v1/admin/audit-history/evidence-package" in UI
    assert "/mfa?setup=1" in UI
