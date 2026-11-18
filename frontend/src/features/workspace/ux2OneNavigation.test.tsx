// UX2 (Persona Blueprint wave D, 18 Nov 2026): one navigation for every organization. The rail is five work areas,
// each persona only the areas holding its work; Records & trust, Team and Administration are in the avatar menu;
// customer administration opens in the same shell, in five groups; the Executive's Today is the product portfolio;
// every former address opens its new home. Authorization stays on the server (tests/test_portfolio_api.py and the
// Playwright persona journeys check the refusals).
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { routeFor } from "../../app/linkTable";
import { adminInWorkspace } from "../../app/consoleChoice";
import { AREAS, areaEntry, areaOf, areaSections } from "./areas";
import { AreaNav } from "./AreaNav";
import { AvatarMenu, PERSONA_TABS, visibleTabs } from "./HybridShell";
import { UserWorkspace } from "./UserWorkspace";
import { ADMIN_GROUPS, adminGroups, customerAdminSections } from "../customer-admin/CustomerAdminControlPlane";
import { decisionText, unitsText } from "./sections/Portfolio";
import { sectionAllowed, type SessionContext, type WorkspaceSection } from "./workspaceContext";

// The personas as the server sends them (access_control/personas.py WORKSPACE_PERSONAS, UX2).
const PERSONAS: Record<string, string[]> = {
  admin: ["home", "complaints", "investigations", "products", "decisions"],
  quality: ["home", "complaints", "investigations", "products", "decisions"],
  regulatory: ["home", "complaints", "decisions"],
  servicedesk: ["home", "complaints"],
  handler: ["home", "complaints"],
  investigator: ["home", "complaints", "investigations", "products"],
  risk: ["home", "investigations", "products"],
  decision: ["home", "complaints", "investigations", "decisions"],
  executive: ["home", "investigations", "products", "decisions"],
};
const MENU = ["home", "products", "investigations", "evidence", "decision-center", "assurance", "audit"];
const allowed = (permissions: string[], menu = MENU) =>
  (Object.keys(AREAS).flatMap((key) => AREAS[key].sections) as WorkspaceSection[])
    .concat(["Records", "Team", "Settings", "Administration", "Import data"])
    .filter((section) => sectionAllowed(section, menu, permissions));

describe("the five work areas", () => {
  it("are the rail's destinations, in the order the work runs", () => {
    expect(Object.keys(PERSONA_TABS)).toEqual([
      "start",
      "home",
      "complaints",
      "investigations",
      "products",
      "decisions",
    ]);
    expect(Object.values(AREAS).map((area) => area.label)).toEqual([
      "Today",
      "Cases",
      "Investigations",
      "Products",
      "Decisions & Reports",
    ]);
    // Records, Team, Settings and Administration are no area: the avatar menu holds them.
    for (const section of ["Records", "Team", "Settings", "Administration", "My Account"])
      expect(areaOf(section)).toBeNull();
    expect(areaOf("Trends")).toBe("products");
    expect(areaOf("Look ahead")).toBe("home");
    expect(areaOf("Complaint")).toBe("complaints");
  });

  it("show each persona only the areas holding its work", () => {
    const signer = allowed(["decision.sign", "records.write"]);
    for (const [persona, tabs] of Object.entries(PERSONAS)) expect(visibleTabs(tabs, signer), persona).toEqual(tabs);
    // The view-only Executive sees Decisions & Reports for reading: its decision trees and reports, no Approvals.
    const viewer = allowed([]);
    expect(visibleTabs(PERSONAS.executive, viewer)).toEqual(PERSONAS.executive);
    expect(areaSections("decisions", viewer)).toEqual(["Decision trees", "Reports"]);
    expect(areaEntry("Approvals", viewer)).toBe("Decision trees");
    // A signer's Decisions & Reports opens on Approvals.
    expect(areaEntry("Approvals", signer)).toBe("Approvals");
    // Approvals needs a signature right; a report approver has one too.
    expect(sectionAllowed("Approvals", MENU, ["regulatory.approve"])).toBe(true);
    expect(sectionAllowed("Approvals", MENU, ["records.write"])).toBe(false);
    // Administration is the customer administrator's only (the server lists customer-admin for them alone).
    expect(sectionAllowed("Administration", MENU, [])).toBe(false);
    expect(sectionAllowed("Administration", [...MENU, "customer-admin"], [])).toBe(true);
  });

  it("name an area's screens in a labelled navigation, never a hidden tab list", () => {
    const visible = allowed(["decision.sign"]);
    const html = renderToStaticMarkup(<AreaNav section="Reports" visible={visible} open={vi.fn()} />);
    expect(html).toMatch(/^<nav class="uw-areanav" aria-label="Decisions &amp; Reports pages">/);
    expect(html).not.toContain('role="tab');
    expect([...html.matchAll(/<span>([^<]*)<\/span>/g)].map((match) => match[1])).toEqual([
      "Approvals",
      "Decision trees",
      "Authority reports",
    ]);
    expect(html).toMatch(/aria-current="page"[^>]*>.*?<span>Authority reports<\/span>/);
    // An area with one screen the person may open shows no menu at all.
    expect(renderToStaticMarkup(<AreaNav section="Investigations" visible={visible} open={vi.fn()} />)).toBe("");
    expect(renderToStaticMarkup(<AreaNav section="Records" visible={visible} open={vi.fn()} />)).toBe("");
  });
});

describe("the avatar menu", () => {
  it("holds Records & trust, Team and Administration for whoever may open them", () => {
    const menu = (canOpen: (section: WorkspaceSection) => boolean) =>
      renderToStaticMarkup(
        <AvatarMenu session={null} current="My Work" open={vi.fn()} showSettings canOpen={canOpen} defaultOpen />,
      );
    const admin = menu(() => true);
    for (const label of ["Records &amp; trust", "Team", "Administration", "Settings", "Account"])
      expect(admin).toContain(`<span>${label}</span>`);
    // The separate console's switch is not offered once Administration opens in the shell.
    expect(admin).not.toContain("Admin console");
    const viewer = menu((section) => section === "Records");
    expect(viewer).toContain("Records &amp; trust");
    expect(viewer).not.toContain("<span>Administration</span>");
  });
});

describe("every former address opens its new home", () => {
  it.each([
    [["My Work", "Approvals"], { section: "Approvals", tab: undefined }],
    [["Decisions", undefined], { section: "Approvals", tab: undefined }],
    [["Decisions", "Decision center"], { section: "Approvals", tab: undefined }],
    [["Decisions", "Verify a signature"], { section: "Records", tab: "Verify a signature" }],
    [["Complaints", "Reporting?complaint=c1"], { section: "Reports", tab: "?complaint=c1" }],
    [["Complaints", "Authority reports?report=r1"], { section: "Reports", tab: "?report=r1" }],
    [["Complaints", "Investigations"], { section: "Investigations", tab: "All investigations" }],
    [["Complaints", "Reportability?complaint=c1"], { section: "Reports", tab: "?complaint=c1&part=assess" }],
    // Screens that stay keep their own address.
    [["Trends", "Trend check"], { section: "Trends", tab: "Trend check" }],
    [["Records", "Audit trail"], { section: "Records", tab: "Audit trail" }],
    [["Look ahead", undefined], { section: "Look ahead", tab: undefined }],
    [["Complaints", "Calls to check"], { section: "Complaints", tab: "Calls to check" }],
  ] as const)("%j", ([section, tab], home) => {
    expect(routeFor(section, tab, "mvp", "new")).toEqual(home);
  });

  it("keeps the classic fallback's places for an organization a platform administrator set back to classic", () => {
    expect(routeFor("Approvals", undefined, "mvp", "classic")).toEqual({ section: "My Work", tab: "Approvals" });
  });
});

describe("customer administration in five groups, in the same shell", () => {
  it("groups the eleven sections into five, each section in exactly one", () => {
    expect(ADMIN_GROUPS.map((group) => group.label)).toEqual([
      "Organization",
      "People & access",
      "Data & connections",
      "AI & security",
      "Audit",
    ]);
    const all = ADMIN_GROUPS.flatMap((group) => group.sections);
    expect([...all].sort()).toEqual([...customerAdminSections("full")].sort());
    expect(new Set(all).size).toBe(all.length);
    // Under the MVP the connections and mapping are parked: that group is left out rather than shown empty.
    expect(adminGroups(customerAdminSections("mvp")).map((group) => group.label)).not.toContain("Data & connections");
  });

  it("opens inside the workspace on the new navigation; the classic fallback keeps the separate console", () => {
    expect(adminInWorkspace("mvp", "new")).toBe(true);
    expect(adminInWorkspace("mvp", "classic")).toBe(false);
    expect(adminInWorkspace("full", "new")).toBe(false);
  });
});

describe("the shell per persona", () => {
  beforeEach(() => {
    vi.stubGlobal("window", {
      location: { pathname: "/app/my-work", search: "", hash: "", origin: "https://mdarix.test" },
      localStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
      sessionStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  const session = (persona: string, extra: Partial<SessionContext> = {}) =>
    ({
      display_name: "Ravi Exec",
      feature_set: "mvp",
      navigation: "new",
      allowed_menu: MENU,
      business_permissions: [],
      current_tenant: { tenant_name: "AcmeCare (Sample)" },
      persona,
      persona_locked: true,
      persona_options: [{ code: persona, label: persona, sub: "", tabs: PERSONAS[persona] }],
      ...extra,
    }) as unknown as SessionContext;
  const rail = (markup: string) =>
    [
      ...(markup.match(/<nav class="uw-navrail"[\s\S]*?<\/nav>/)?.[0] ?? "").matchAll(
        /<span class="uw-tab-label">([^<]*)<\/span>/g,
      ),
    ].map((match) => match[1]);

  it("gives the Executive the portfolio as Today, read-only, with no story button", () => {
    const markup = renderToStaticMarkup(<UserWorkspace session={session("executive")} initialView="my-work" />);
    expect(rail(markup)).toEqual(["Today", "Investigations", "Products", "Decisions &amp; Reports"]);
    expect(markup).toContain("Product exposure");
    expect(markup).not.toContain("Continue the story");
    expect(markup).not.toContain("Your next actions");
  });

  it("opens customer administration for a customer administrator inside the shell, on /app/customer-admin", () => {
    const markup = renderToStaticMarkup(
      <UserWorkspace
        session={session("admin", { allowed_menu: [...MENU, "customer-admin"], active_role: "CUSTOMER_ADMIN" })}
        initialView="customer-admin"
      />,
    );
    expect(markup).toContain('data-workspace-section="Administration"');
    expect(markup).toContain('aria-label="Administration areas"');
    expect(markup).toContain("How is your organization set up?");
    // The rail stays: no separate application.
    expect(rail(markup)[0]).toBe("Today");
  });

  it("never draws Administration for anyone else, even from its address (the workspace then opens their first screen)", () => {
    const markup = renderToStaticMarkup(<UserWorkspace session={session("quality")} initialView="customer-admin" />);
    expect(markup).not.toContain('aria-label="Administration areas"');
    expect(markup).not.toContain("customer-admin-console");
  });
});

describe("the portfolio's words", () => {
  it("never guesses units, and says the decision status in words", () => {
    expect(unitsText(null)).toBe("Not recorded");
    expect(unitsText(1240)).toBe("1,240");
    expect(decisionText({ open_investigations: 1, awaiting_decision: 1, signed_decisions: 0 })).toBe(
      "1 awaiting a signed decision",
    );
    expect(decisionText({ open_investigations: 1, awaiting_decision: 0, signed_decisions: 1 })).toBe(
      "Open, decision signed",
    );
    expect(decisionText({ open_investigations: 0, awaiting_decision: 0, signed_decisions: 0 })).toBe(
      "No investigation",
    );
  });
});
