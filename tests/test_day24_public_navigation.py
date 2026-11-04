from tests.conftest import frontend_app_source
from pathlib import Path


def compact(text: str) -> str:
    """Drop all whitespace so assertions survive formatter line wrapping."""
    return "".join(text.split())


ROOT = Path(__file__).resolve().parents[1]
# The public website: the shell plus its pages, content and motion modules.
SITE = "\n".join(
    path.read_text(encoding="utf-8")
    for path in [
        ROOT / "frontend" / "src" / "PublicMegaSite.tsx",
        *sorted((ROOT / "frontend" / "src" / "site").glob("*.ts*")),
    ]
)
MAIN = frontend_app_source()
STYLES = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")
WORKSPACE = ROOT / "frontend" / "src" / "features" / "workspace"
WORKSPACE_CONTEXT = (WORKSPACE / "workspaceContext.tsx").read_text(encoding="utf-8")
WORKSPACE_OVERVIEW = (WORKSPACE / "sections" / "Dashboard.tsx").read_text(encoding="utf-8")


def test_public_navigation_exposes_required_categories_and_actions():
    for label in (
        "Platform & AI",
        "Solutions",
        "Product Lifecycle",
        "Why MDARIX",
        "Resources",
        "Plans",
        "Sign in",
        "Get started",
    ):
        assert label in SITE


def test_current_and_future_capabilities_are_explicitly_distinguished():
    assert "future?: boolean" in SITE
    assert "Current capabilities" in SITE
    assert "Broader lifecycle intelligence" in SITE
    assert "does not represent available functionality" in SITE
    assert "Available in R1" not in SITE
    assert 'status: "R1"' not in SITE
    assert "R1" not in SITE


def test_public_story_preserves_system_of_record_and_human_authority_boundaries():
    assert "System of Intelligence, not System of Record" in SITE
    assert "Authorized humans make controlled decisions" in SITE
    assert "AI does not create the final regulated decision" in SITE


def test_private_application_routes_require_authenticated_session():
    # The gate asks the server for the session itself (no automatic "expired" redirect for a first visit) and sends
    # anyone without one to sign-in, coming back to the same page afterwards.
    assert compact('requestJson<{ mfa_state?: string | null }>("/api/v1/auth/session"') in compact(MAIN)
    assert "redirectOnUnauthorized: false" in MAIN
    assert "window.location.replace(signInPath(" in MAIN
    assert "Customer application routes require an authenticated session" in MAIN


def test_mega_menu_supports_escape_and_responsive_navigation():
    assert 'event.key === "Escape"' in SITE
    assert "aria-expanded={openMenu === name}" in SITE
    assert 'aria-controls="public-navigation"' in SITE


def test_authenticated_home_tells_and_connects_the_workflow_story():
    # Signed-in business users (and a customer administrator who switched into it) land on the user workspace,
    # which opens on a live Dashboard.
    assert compact(
        'if ((!isPlatformAdmin && !isCustomerAdmin) || (isCustomerAdmin && adminMode === "workspace"))'
    ) in compact(MAIN)
    assert "<UserWorkspace" in MAIN
    # The workflow story is the navigation itself, in order: product -> signal -> case -> evidence -> decision -> trust.
    order = ["Products", "Signals", "Investigations", "Evidence", "Decisions", "Trust & Audit"]
    positions = [WORKSPACE_CONTEXT.index(f'"{name}"') for name in order]
    assert positions == sorted(positions)
    for endpoint in (
        "/api/v1/analytics/command-center",
        "/api/v1/analytics/signals",
        "/api/v1/analytics/investigations",
        "/api/v1/analytics/evidence",
    ):
        assert endpoint in WORKSPACE_OVERVIEW
    for phrase in ("Needs attention", "What to do next", "Open cases", "Latest signals"):
        assert phrase in WORKSPACE_OVERVIEW
    assert 'open("Investigations")' in WORKSPACE_OVERVIEW
    assert 'open("Evidence")' in WORKSPACE_OVERVIEW


def test_semantic_design_tokens_cover_business_meaning():
    # Since 0.10.66 (stage 5) the one token file holds every colour by role (frontend/src/tokens.css; tokens.test.ts
    # checks their contrast); the former per-sheet names (--brand-primary, --ai-advisory, ...) are gone. Each business
    # meaning still has its role: the brand, text, the page, critical, warning, good, information and AI advisory.
    tokens = (ROOT / "frontend" / "src" / "tokens.css").read_text(encoding="utf-8")
    assert '@import "./tokens.css";' in STYLES
    for token in (
        "--ms-teal",
        "--ms-ink",
        "--ms-ground",
        "--ms-crit",
        "--ms-warn",
        "--ms-good",
        "--ms-info",
        "--ms-ai",
    ):
        assert f"  {token}:" in tokens, token
    assert "Red (crit) is only for overdue or critical" in tokens


def test_website_is_consolidated_and_every_former_url_still_resolves():
    for page in ("/platform", "/solutions", "/product-lifecycle", "/trust", "/resources", "/pricing", "/company"):
        assert f'"{page}"' in SITE
    # Former top-level pages redirect to the section that now holds their content.
    for legacy in (
        "/why-mdarix",
        "/ai-trust",
        "/security",
        "/integrations",
        "/plans",
        "/capabilities",
        "/roadmap",
        "/request-demo",
    ):
        assert f'"{legacy}"' in SITE
    # The application is matched by whole path segments (/app, /platform-admin), so the website's /platform page is
    # never mistaken for /platform-admin/..., and every other address is the website (its pages or "not found").
    assert "publicPath.startsWith(`${root}/`)" in MAIN
    assert '["/app", "/platform-admin"]' in MAIN
