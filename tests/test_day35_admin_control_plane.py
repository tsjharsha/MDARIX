"""Static contract checks between the live administration UI and the admin API.

These assertions only inspect source text, so they must target screens a user
can actually reach. The previous version checked strings inside an
unreferenced ``AdministratorControlPlane`` component (plus its create/edit
forms), which was removed as dead code. Known UI gaps, kept visible here:
no reachable screen reads governance policies or creates roles, permission
sets, personas, connectors, approval authorities or SoD policies; the backend
routes for those exist and are still asserted below.
"""

from pathlib import Path


ROOT = Path(__file__).parents[1]
FRONTEND = ROOT / "frontend" / "src"
UI = (FRONTEND / "main.tsx").read_text(encoding="utf-8")
PLATFORM_ADMIN_UI = (FRONTEND / "features" / "admin" / "PlatformAdminScreen.tsx").read_text(encoding="utf-8")
CUSTOMER_ADMIN_UI = (FRONTEND / "features" / "customer-admin" / "CustomerAdminControlPlane.tsx").read_text(
    encoding="utf-8"
)
SIMPLIFIED_ADMIN_UI = (FRONTEND / "features" / "admin" / "SimplifiedPlatformAdminScreen.tsx").read_text(
    encoding="utf-8"
)
LIVE_ADMIN_UI = "\n".join((UI, PLATFORM_ADMIN_UI, CUSTOMER_ADMIN_UI, SIMPLIFIED_ADMIN_UI))
ROUTER = (ROOT / "backend" / "app" / "access_router.py").read_text(encoding="utf-8")


def test_admin_dashboard_loads_all_control_plane_domains():
    live_reads = [
        "/api/v1/admin/identity/users",
        "/api/v1/admin/identity/roles",
        "/api/v1/admin/identity/permission-sets",
        "/api/v1/admin/identity/memberships",
        "/api/v1/admin/identity/persona-assignments",
        "/api/v1/admin/governance/entitlements",
        "/api/v1/admin/configuration/connectors",
        "/api/v1/admin/configuration/mappings",
        "/api/v1/admin/audit-history",
    ]
    for endpoint in live_reads:
        assert endpoint in LIVE_ADMIN_UI
        assert endpoint.removeprefix("/api/v1") in ROUTER
    # Backend-only today (no reachable UI reads it yet).
    assert "/admin/governance/policies" in ROUTER


def test_admin_create_endpoints_exist_and_user_invitation_is_wired():
    required_create_routes = [
        "/admin/identity/users",
        "/admin/identity/roles",
        "/admin/identity/permission-sets",
        "/admin/identity/persona-assignments",
        "/admin/configuration/connectors",
        "/admin/configuration/mappings",
        "/admin/governance/approval-authorities",
        "/admin/governance/sod-policies",
    ]
    for route in required_create_routes:
        assert f'@router.post("{route}")' in ROUTER
    # The live Customer Administration screen invites users through the API.
    assert '"/api/v1/admin/identity/users"' in CUSTOMER_ADMIN_UI
    assert 'method: "POST"' in CUSTOMER_ADMIN_UI


def test_admin_edit_workflow_covers_every_editable_resource():
    resources = [
        "users",
        "roles",
        "permission-sets",
        "persona-assignments",
        "connectors",
        "mappings",
        "approval-authorities",
        "sod-policies",
    ]
    for resource in resources:
        assert f'"{resource}"' in ROUTER
    assert '@router.patch("/admin/control-plane/{resource}/{resource_id}")' in ROUTER
    # The live Customer Administrator management screen edits users through it.
    assert "/api/v1/admin/control-plane/users/" in UI


def test_admin_route_renders_the_simplified_platform_admin_shell():
    assert "<SimplifiedPlatformAdminScreen" in UI
    assert '["admin", "platform-tenants"].includes(activeView) && <SimplifiedPlatformAdminScreen' in UI
    assert "Administrator control plane" in SIMPLIFIED_ADMIN_UI


def test_platform_admin_data_mapping_exposes_external_to_internal_fields():
    endpoint = "/api/v1/admin/configuration/data-mappings"
    assert endpoint in PLATFORM_ADMIN_UI
    assert '@router.get("/admin/configuration/data-mappings")' in ROUTER
    for label in (
        "External database",
        "External table",
        "External field",
        "MDARIX table",
        "MDARIX field",
        "Transform",
        "Required",
    ):
        assert label in PLATFORM_ADMIN_UI
    for field in ("source_database", "source_schema", "source_table", "target_schema", "target_table"):
        assert field in ROUTER
