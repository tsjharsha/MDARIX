"""Static contract for the non-admin user workspace: tenant-safe by construction."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "frontend" / "src" / "features" / "workspace"
SOURCE = "\n".join(
    path.read_text(encoding="utf-8") for path in sorted(WORKSPACE.rglob("*.ts*")) if ".test." not in path.name
)
CONTEXT = (WORKSPACE / "workspaceContext.tsx").read_text(encoding="utf-8")
SHELL = (WORKSPACE / "UserWorkspace.tsx").read_text(encoding="utf-8")


def test_workspace_never_names_a_tenant_in_a_request():
    # The server derives the tenant from the session; the workspace must not send one or switch it.
    for forbidden in ("X-Tenant-ID", "tenant_id=", '"tenant_id":', "/me/tenant-context", "fetch("):
        assert forbidden not in SOURCE, forbidden


def test_sections_come_from_the_server_menu_and_fail_closed():
    assert "allowed_menu" in SHELL and "sectionAllowed" in SHELL
    assert "Fail closed" in CONTEXT
    # Every section is mapped to server menu keys; only My Account is always available.
    assert '"My Account": []' in CONTEXT


def test_workspace_signs_out_when_idle_and_offers_sign_out():
    assert "useIdleSignOut()" in SHELL
    assert "signOut()" in SHELL


def test_overview_is_a_live_dashboard_and_every_section_exists():
    for section in (
        "Overview",
        "My Work",
        "Products",
        "Signals",
        "Investigations",
        "Evidence",
        "Decisions",
        "Intelligence",
        "Trust & Audit",
        "My Account",
    ):
        assert f'"{section}"' in CONTEXT
        assert f'section === "{section}"' in SHELL
