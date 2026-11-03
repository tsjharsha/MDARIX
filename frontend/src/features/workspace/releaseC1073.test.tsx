// Release C part C1 (0.10.73): the shell, personas and team. The tab bar shows only the persona's destinations; the
// trial owner switches "Viewing as", a colleague sees their persona locked; Home answers what needs attention; the
// team invites with a persona. The classic navigation is untouched.
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NEW_MENU, routeFor } from "../../app/linkTable";
import { UserWorkspace } from "./UserWorkspace";
import { PERSONA_TABS, PersonaSwitch, tabOfSection, visibleTabs } from "./HybridShell";
import { homeCounts, laneShare, legalClocks, nextActions, personaItems } from "./home";
import { TeamView, personaConfirmation, type Team, type TeamMember } from "./sections/TrialTeam";
import type { OversightItem } from "./oversight";
import type { SessionContext } from "./workspaceContext";

// The approved design's PERSONAS (mdarix-hybrid-mockup.html), as the server sends them (access_control/personas.py).
const OPTIONS = [
  ["admin", "Admin", ["home", "complaints", "trees", "reports", "investigations", "trends", "records", "team"]],
  ["quality", "Quality Leader", ["home", "complaints", "reports", "investigations", "trends", "records"]],
  ["regulatory", "Regulatory Leader", ["home", "complaints", "trees", "reports", "records"]],
  ["handler", "Complaint Handler", ["home", "complaints"]],
  ["investigator", "Investigator", ["home", "investigations", "trends"]],
  ["risk", "Risk Reviewer", ["home", "investigations", "records"]],
  ["decision", "Decision Maker", ["home", "complaints", "reports", "records"]],
  ["executive", "Executive", ["home", "trends", "records"]],
].map(([code, label, tabs]) => ({
  code: code as string,
  label: label as string,
  sub: `${label} line`,
  tabs: tabs as string[],
}));

const ALL_SECTIONS = Object.values(PERSONA_TABS).map((tab) => tab.section as string);

const session = (persona: string, locked: boolean, navigation = "new") =>
  ({
    display_name: "Asha Quality",
    feature_set: "mvp",
    navigation,
    allowed_menu: ["home", "products", "investigations", "evidence", "decision-center", "assurance", "audit"],
    business_permissions: ["records.write", "quality.review", "decision.sign", "regulatory.approve"],
    current_tenant: { tenant_name: "Medisynth Devices (Sample)" },
    persona,
    persona_locked: locked,
    persona_options: OPTIONS,
  }) as unknown as SessionContext;

const tabLabels = (markup: string) =>
  [...markup.matchAll(/<button type="button" class="uw-tab"[^>]*>([^<]*)<\/button>/g)].map((match) => match[1]);

describe("the shell and its tab bar", () => {
  beforeEach(() => {
    vi.stubGlobal("window", {
      location: { pathname: "/app/my-work", search: "", hash: "", origin: "https://mdarix.test" },
      localStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
      sessionStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("maps each tab onto a place of the link table, Home being My work", () => {
    // 0.10.80: a trial's Getting started comes first, outside the personas' tabs (release0080.test.tsx).
    expect(Object.values(PERSONA_TABS).map((tab) => tab.section)).toEqual(["Getting started", ...NEW_MENU.main]);
    expect(PERSONA_TABS.home.section).toBe("My Work");
    expect(tabOfSection("Complaint")).toBe("complaints");
    expect(tabOfSection("Settings")).toBeNull();
  });

  it("shows each persona only its destinations, and never a tab the server does not grant", () => {
    const labels = (tabs: string[]) => tabs.map((key) => PERSONA_TABS[key].label);
    for (const option of OPTIONS) expect(visibleTabs(option.tabs, ALL_SECTIONS)).toEqual(option.tabs);
    expect(labels(visibleTabs(OPTIONS[3].tabs, ALL_SECTIONS))).toEqual(["Home", "Complaints"]);
    // A section the server's menu does not grant is left out, whatever the persona.
    expect(visibleTabs(OPTIONS[0].tabs, ["My Work", "Records"])).toEqual(["home", "records"]);
  });

  it("gives the trial owner the top bar, Viewing as and Admin's eight tabs, with Home first", () => {
    const markup = renderToStaticMarkup(<UserWorkspace session={session("admin", false)} initialView="my-work" />);
    expect(tabLabels(markup)).toEqual([
      "Home",
      "Complaints",
      "Decision trees",
      "Reports",
      "Investigations",
      "Trends",
      "Records",
      "Team",
    ]);
    expect(markup).toContain("Viewing as");
    expect(markup).toContain('aria-haspopup="menu"');
    expect(markup).toContain("Search complaints, products, reports");
    expect(markup).toMatch(/<h1[^>]*>Good (morning|afternoon|evening), Asha<\/h1>/);
    expect(markup).toContain("Your next actions");
    // The classic menu is not drawn on the new navigation.
    expect(markup).not.toContain('aria-label="Workspace navigation"');
  });

  it("shows a colleague their persona locked, with only its tabs", () => {
    const markup = renderToStaticMarkup(<UserWorkspace session={session("regulatory", true)} initialView="my-work" />);
    expect(tabLabels(markup)).toEqual(["Home", "Complaints", "Decision trees", "Reports", "Records"]);
    expect(markup).toContain("· set by the trial owner");
    expect(markup).not.toContain('aria-controls="uw-persona-menu"');
    expect(markup).toContain("Legal clocks");
  });

  it("leaves the classic navigation as it was", () => {
    const markup = renderToStaticMarkup(
      <UserWorkspace session={session("admin", false, "classic")} initialView="my-work" />,
    );
    expect(markup).toContain('aria-label="Workspace navigation"');
    expect(markup).not.toContain("uw-tabs");
    expect(markup).not.toContain("Viewing as");
  });

  it("lands a fresh trial on Home: the new navigation no longer sends it to Getting started first", () => {
    const source = Object.values(
      import.meta.glob("./UserWorkspace.tsx", { query: "?raw", import: "default", eager: true }),
    )[0] as string;
    expect(source).toContain('(initialView ?? "home") === "home" && !addressed && !fresh)');
    expect(source).toContain('fresh && (initialView ?? "home") === "home"');
  });
});

describe("old addresses on the new shell", () => {
  it("opens the new tabs on the new navigation and their classic places on the classic one", () => {
    expect(routeFor("Decision trees", undefined, "mvp", "new")).toEqual({ section: "Decision trees", tab: undefined });
    expect(routeFor("Reports", undefined, "mvp", "new")).toEqual({ section: "Reports", tab: undefined });
    expect(routeFor("Decision trees", undefined, "mvp", "classic")).toEqual({
      section: "Complaints",
      tab: "Decision guides",
    });
    expect(routeFor("Reports", undefined, "mvp", "classic")).toEqual({ section: "Complaints", tab: "Reports" });
    // Every classic screen still lands on a tab of the bar or a screen of the avatar's menu.
    for (const section of ["Readiness", "Dashboard", "Signals", "Evidence", "Decisions", "Trust & Audit"]) {
      const place = routeFor(section, undefined, "mvp", "new");
      expect([...NEW_MENU.main, ...NEW_MENU.top]).toContain(place.section);
    }
  });
});

describe("the persona switch", () => {
  it("offers the trial owner every persona, and says it changes the view, not the signature", () => {
    const markup = renderToStaticMarkup(
      <PersonaSwitch persona="quality" options={OPTIONS} locked={false} onChoose={() => undefined} />,
    );
    expect(markup).toContain("Viewing as");
    expect(markup).toContain("Quality Leader");
    expect(markup).toContain('aria-haspopup="menu"');
  });

  it("shows anyone else their persona with a lock and no menu", () => {
    const markup = renderToStaticMarkup(
      <PersonaSwitch persona="decision" options={OPTIONS} locked onChoose={() => undefined} />,
    );
    expect(markup).toContain("Decision Maker");
    expect(markup).toContain("set by the trial owner");
    expect(markup).not.toContain("<button");
  });
});

const item = (overrides: Partial<OversightItem>): OversightItem =>
  ({
    key: overrides.title ?? "k",
    category: "TASK",
    category_label: "Other tasks",
    title: "A task",
    ref: null,
    complaint_id: null,
    market: null,
    product: null,
    owner: "Asha Quality",
    queue: null,
    away: null,
    due_at: "2026-11-05T18:29:00Z",
    state: "LATER",
    state_label: "Later",
    hours_left: 48,
    escalated_to: [],
    alerts: true,
    opens: null,
    ...overrides,
  }) as OversightItem;

describe("Home's rules", () => {
  const now = new Date("2026-11-03T10:00:00Z");
  const items = [
    item({ title: "Report", category: "REPORTING", market: "US", due_at: "2026-11-08T18:29:00Z", hours_left: 128 }),
    item({ title: "Triage", category: "TRIAGE", state: "OVERDUE", due_at: "2026-11-03T08:00:00Z", hours_left: -2 }),
    item({ title: "Later", category: "CAPA", due_at: "2026-12-20T00:00:00Z", hours_left: 1100 }),
    item({ title: "Obligation", category: "OBLIGATION", market: "IN", due_at: "2026-11-04T18:29:00Z", hours_left: 32 }),
  ];

  it("counts overdue and due this week from the items the persona is about", () => {
    expect(homeCounts(items, now)).toEqual({ overdue: 1, week: 2 });
    expect(personaItems(items, "regulatory").map((row) => row.title)).toEqual(["Report", "Obligation"]);
    expect(personaItems(items, "handler").map((row) => row.title)).toEqual(["Triage"]);
    expect(personaItems(items, "executive")).toHaveLength(4);
  });

  it("lists the next actions most urgent first, and the legal clocks by market", () => {
    expect(nextActions(items).map((row) => row.title)).toEqual(["Triage", "Obligation", "Report", "Later"]);
    expect(legalClocks(items).map((row) => row.market)).toEqual(["IN", "US"]);
    expect(laneShare({ state: "OVERDUE", hours_left: -3 })).toBe(100);
    expect(laneShare({ state: "LATER", hours_left: 720 })).toBe(4);
    expect(laneShare({ state: "LATER", hours_left: 360 })).toBe(50);
  });
});

describe("the team: a persona per invitation", () => {
  const member = (overrides: Partial<TeamMember>): TeamMember => ({
    id: "u2",
    display_name: "Rahul Colleague",
    email: "rahul@example.invalid",
    status: "ACTIVE",
    is_owner: false,
    is_you: false,
    persona: "regulatory",
    persona_label: "Regulatory Leader",
    persona_locked: true,
    ...overrides,
  });
  const team: Team = {
    can_invite: true,
    can_manage: true,
    limit: 50,
    seats_used: 2,
    members: [
      member({
        id: "u1",
        display_name: "Asha Quality",
        is_owner: true,
        is_you: true,
        persona: "admin",
        persona_label: "Admin",
        persona_locked: false,
      }),
      member({}),
    ],
    personas: OPTIONS.slice(1).map(({ code, label, sub }) => ({ code, label, sub })),
  };
  const markup = renderToStaticMarkup(
    <TeamView
      team={{ state: "ready", data: team, reload: () => undefined }}
      busy={false}
      message={null}
      onInvite={async () => true}
      onResend={() => undefined}
      onConfirm={() => undefined}
      onChanged={() => undefined}
    />,
  );

  it("invites with a name, a work e-mail and a persona, up to the safety cap", () => {
    expect(markup).toContain("2 people · up to 50");
    expect(markup).toContain("Persona");
    expect(markup).toContain("Send the invitation");
    expect(markup).not.toContain('value="admin"'); // Admin is the trial owner's own
    expect(markup).toContain("They see this persona&#x27;s screens and sign as its role");
  });

  it("lists each person's persona, with a lock for a colleague, and lets the owner change it", () => {
    expect(markup).toContain("Regulatory Leader");
    expect(markup).toContain("Set by you: they cannot change it");
    // A colleague viewing the team sees the persona with its lock, and nothing to change.
    const seen = renderToStaticMarkup(
      <TeamView
        team={{ state: "ready", data: { ...team, can_invite: false, can_manage: false }, reload: () => undefined }}
        busy={false}
        message={null}
        onInvite={async () => true}
        onResend={() => undefined}
        onConfirm={() => undefined}
        onChanged={() => undefined}
      />,
    );
    expect(seen).toContain('aria-label="set by the trial owner"');
    expect(seen).not.toContain("Persona of Rahul Colleague");
    expect(markup).toContain("Persona of Rahul Colleague");
    const confirm = personaConfirmation(team.members[1], team.personas![5], () => undefined);
    expect(confirm.title).toBe("Make Rahul Colleague a Decision Maker?");
    expect(confirm.body).toContain("signs as its role");
  });
});
