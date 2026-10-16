from tests.conftest import access_api_source
from pathlib import Path


ROOT = Path(__file__).parents[1]
FEATURE = ROOT / "frontend" / "src" / "features" / "customer-admin"
UI = "\n".join(path.read_text(encoding="utf-8") for path in sorted(FEATURE.rglob("*.ts*")) if ".test." not in path.name)
USERS_UI = (FEATURE / "sections" / "Users.tsx").read_text(encoding="utf-8")
ROUTER = access_api_source()


def test_customer_admin_uses_server_scoped_mutation_contracts():
    for endpoint in (
        "/api/v1/admin/identity/users",
        "/api/v1/admin/identity/roles",
        "/api/v1/admin/configuration/connectors",
        "/api/v1/admin/configuration/mappings",
        "/api/v1/admin/audit-history/export",
    ):
        assert endpoint in UI
    # Every call goes through the shared same-origin client; no hand-rolled fetch with other credentials.
    assert "requestJson" in UI
    assert "fetch(" not in UI
    assert '@router.post("/admin/identity/users")' in ROUTER
    assert '@router.post("/admin/configuration/connectors")' in ROUTER
    assert '@router.post("/admin/configuration/mappings")' in ROUTER


def test_customer_admin_does_not_accept_browser_tenant_as_authority():
    start = USERS_UI.index("const submitInvite")
    invite_block = USERS_UI[start : USERS_UI.index("return (", start)]
    assert "tenant_id" not in invite_block
    assert "Tenant context is server-derived" in USERS_UI
    assert "target_tenant_id" not in UI


def test_customer_admin_has_auditable_export_and_mfa_entry_points():
    assert "/api/v1/admin/audit-history/export?output_format=CSV" in UI
    assert "/api/v1/admin/audit-history/evidence-package" in UI
    # The administrator's own MFA panel is the shared one (features/shared/TwoFactorSettings.tsx), as in My Account.
    assert "<TwoFactorPanel" in UI
    shared = (ROOT / "frontend" / "src" / "features" / "shared" / "TwoFactorSettings.tsx").read_text(encoding="utf-8")
    assert "/mfa?setup=1" in shared and "/api/v1/auth/mfa/recovery-codes" in shared


def test_customer_admin_never_offers_platform_roles():
    roles = UI[
        UI.index("export const ASSIGNABLE_ROLES") : UI.index("] as const;", UI.index("export const ASSIGNABLE_ROLES"))
    ]
    for platform_role in ("PLATFORM_ADMIN", '"ADMINISTRATOR"', '"ADMIN"', "MDARIX"):
        assert platform_role not in roles


def test_customer_admin_risky_actions_are_confirmed():
    # Suspend, offboard, retire, sync and release run only through the confirmation dialog.
    assert 'role="alertdialog"' in UI
    for action in ('"SUSPENDED"', '"OFFBOARDED"', "/execute", "/release-action", "/identity-provider"):
        assert action in UI
    assert "useIdleSignOut()" in UI
    assert "IDLE_SIGN_OUT_MS" in (ROOT / "frontend" / "src" / "features" / "shared" / "session.ts").read_text(
        encoding="utf-8"
    )
