import { describe, expect, it } from "vitest";
import table from "./linkTable.json";
import {
  NEW_HOMES,
  NEW_MENU,
  NEW_PLACES,
  NEW_RECORD_PLACES,
  OLD_VIEWS,
  PLACES,
  RECORD_PLACES,
  currentTab,
  placeOf,
  placesFor,
  recordPlace,
  routeFor,
  tabParts,
  type Navigation,
} from "./linkTable";
import { APP_ROUTES, viewFromPath } from "./router";
import { WORKSPACE_VIEWS } from "./navigationPolicy";
import { MVP_RECORDS_TABS, PARKED_SECTIONS } from "./featureSet";
import { NEW_ONLY_SECTIONS, WORKSPACE_SECTIONS } from "../features/workspace/workspaceContext";
import { COMPLAINT_VIEWS } from "../features/workspace/sections/ComplaintViews";
import { TRENDS_TABS } from "../features/workspace/sections/Trends";
import { SETTINGS_TABS } from "../features/workspace/sections/Settings";
import { COMPLAINT_SECTIONS } from "../features/workspace/sections/ComplaintPage";
import { addressFor, locationFromAddress } from "../features/workspace/workspaceAddress";
import { VIEW_TO_SECTION } from "../features/workspace/UserWorkspace";
import { COMPLAINTS_TABS } from "../features/workspace/complaintReview";
import { SIGNALS_TABS } from "../features/workspace/signals";
import { READINESS_TABS, eventTab } from "../features/workspace/oversight";
import { LOOK_AHEAD_TABS } from "../features/workspace/partyPreview";
import { TASK_TABS, OTHER_MY_WORK_TABS, taskDestination } from "../features/workspace/tasks";
import { TRIAL_TABS } from "../features/workspace/sections/GettingStarted";
import { objectTarget, parseTrustTab } from "../features/workspace/caseAudit";
import { SAMPLE_PAINS } from "../features/workspace/sampleStory";
import { GUIDE_PARTS } from "../features/help/userGuide";
import { communicationsTab } from "../features/workspace/communications";
import { reportsTab } from "../features/workspace/authorityReports";
import { recordsTab } from "../features/workspace/effectiveness";
import { signalsTab } from "../features/workspace/signals";
import { decisionTab } from "../features/workspace/decisionTabs";
import { reviewsTab } from "../features/workspace/reviews";
import { trustTab } from "../features/workspace/caseAudit";
import { documentLink } from "../features/workspace/documents";
import { complaintListTab } from "../features/workspace/complaintList";
import { intelligenceTab } from "../features/workspace/intelligence";

/**
 * Quality plan stage 6: every link source resolves to a screen and tab that exist (6.10), and every old address and
 * section name has a place (6.7). A place is a section of linkTable.json "places" and, where named, one of its tabs.
 */
const landsOn = (section: string, tab: string | undefined | null, navigation: Navigation = "classic") => {
  const place = routeFor(section, tab ?? undefined, "mvp", navigation);
  const known = placesFor(navigation)[place.section];
  const name = tabParts(place.tab).name;
  return { ok: !!known && (!name || known.tabs.includes(name)), place };
};

/** A place only the new navigation has (stage 7): its screen, or its tab, is not a classic one. */
const newOnly = (section: string, tab: string | undefined | null) => {
  const name = tabParts(tab).name;
  return (
    !PLACES[section] || (!!name && !PLACES[section].tabs.includes(name) && NEW_PLACES[section]?.tabs.includes(name))
  );
};

/**
 * Every link lands on an existing screen and tab on both navigations (0.10.68): an organization on the classic menu
 * and one on the new menu open the same link. A link to a place only the new navigation has is checked there.
 */
const expectLands = (section: string, tab: string | undefined | null, where: string) => {
  for (const navigation of ["classic", "new"] as const) {
    if (navigation === "classic" && newOnly(section, tab)) continue;
    const { ok, place } = landsOn(section, tab, navigation);
    expect(ok, `${where} (${navigation}): ${section} / ${tab} lands on ${place.section} / ${place.tab}`).toBe(true);
  }
};

describe("the link table's places are the screens", () => {
  it("lists every tab each screen offers, under the MVP feature set every trial and pilot runs", () => {
    expect(PLACES.Complaints.tabs).toEqual([...COMPLAINTS_TABS]);
    expect(PLACES.Signals.tabs).toEqual([...SIGNALS_TABS]);
    expect(PLACES.Readiness.tabs).toEqual([...READINESS_TABS]);
    expect(PLACES.Records.tabs).toEqual([...MVP_RECORDS_TABS]);
    expect(PLACES["Look ahead"].tabs).toEqual([...LOOK_AHEAD_TABS]);
    expect(PLACES["Getting started"].tabs).toEqual([...TRIAL_TABS]);
    expect([...PLACES["My Work"].tabs].sort()).toEqual(
      [...TASK_TABS.map((item) => item.tab), "Approvals", ...OTHER_MY_WORK_TABS].sort(),
    );
    // Every section the MVP shows has a place; the parked ones have none (they redirect). The new navigation's own
    // screens are in newPlaces.
    const shown = WORKSPACE_SECTIONS.filter(
      (section) => !PARKED_SECTIONS.includes(section) && !NEW_ONLY_SECTIONS.includes(section),
    );
    expect(Object.keys(PLACES).sort()).toEqual([...shown].sort());
  });

  it("gives every place its own address, which the browser routes", () => {
    for (const [section, place] of Object.entries({ ...PLACES, ...NEW_PLACES })) {
      if (section === "Complaint") continue; // /app/complaints/<ref>, below
      const view = viewFromPath(place.path);
      expect(APP_ROUTES[view], section).toBe(place.path);
      expect(WORKSPACE_VIEWS, section).toContain(view);
      // The classic and new screens that share a path (/app/my-work) are one section.
      expect(VIEW_TO_SECTION[view]?.[0], section).toBe(section);
    }
  });

  it("opens each kind of record on an existing tab", () => {
    for (const [kind, place] of Object.entries(RECORD_PLACES)) expectLands(place.section, place.tab, kind);
    for (const [kind, place] of Object.entries(NEW_RECORD_PLACES))
      expect(landsOn(place.section, place.tab, "new").ok, `new: ${kind}`).toBe(true);
    expect(Object.keys(table.viewIds).sort()).toEqual([...WORKSPACE_SECTIONS].sort());
  });
});

describe("every old address redirects (6.7)", () => {
  it("opens every former address (/app/<view>) on a place", () => {
    for (const [view, [section, tab]] of Object.entries(OLD_VIEWS)) expectLands(section, tab, `/app/${view}`);
    // ... including the parked ones, which e-mails, guides and videos used.
    for (const view of ["decision", "risk-traceability", "regulatory-copilot", "story", "persona", "ask", "evidence"])
      expect(OLD_VIEWS[view], view).toBeDefined();
  });

  it("opens every former section name, with any of its former tabs, on a place", () => {
    for (const row of table.oldSections) expectLands(row.section, row.tab, `${row.section} › ${row.tab ?? ""}`);
    for (const section of PARKED_SECTIONS) expectLands(section, undefined, section);
    for (const [section, renamed] of Object.entries(table.oldTabs))
      for (const [old, now] of Object.entries(renamed)) {
        expect(currentTab(section, old)).toBe(now);
        // A parked section's old tab lands where its new tab does (Evidence, Trust & Audit).
        expect(routeFor(section, old, "mvp")).toEqual(
          PARKED_SECTIONS.includes(section) ? routeFor(section, now, "mvp") : { section, tab: now },
        );
      }
  });

  it("opens an old Case evidence or Case timeline link (before 0.10.93) on the renamed tab, with what it carries", () => {
    expect(currentTab("Evidence", "Case evidence")).toBe("Investigation evidence");
    expect(currentTab("Evidence", "Case evidence?item=EV000012")).toBe("Investigation evidence?item=EV000012");
    expect(currentTab("Trust & Audit", "Case timeline?case=c1&label=INV000001")).toBe(
      "Investigation timeline?case=c1&label=INV000001",
    );
    expect(parseTrustTab("Case timeline?case=c1&label=INV000001")).toEqual({
      tab: "Investigation timeline",
      caseId: "c1",
      caseLabel: "INV000001",
    });
    expect(currentTab("Evidence", "Requests?request=REQ000001")).toBe("Requests?request=REQ000001");
  });

  it("reads every ?section= address (used until 0.10.67) as its screen, and writes the screen's own path", () => {
    for (const section of WORKSPACE_SECTIONS) {
      const named = locationFromAddress(
        "/app",
        `?section=${encodeURIComponent(section)}`,
        VIEW_TO_SECTION,
        WORKSPACE_SECTIONS,
      );
      expect(named?.section, section).toBe(section);
      if (PLACES[section]) expect(addressFor({ section }), section).toBe(PLACES[section].path);
    }
  });
});

describe("every link source resolves to an existing screen (6.10)", () => {
  it("every task type", () => {
    const types = [
      "SIGNAL_TRIAGE",
      "DECISION_APPROVAL",
      "RISK_REVIEW",
      "REGULATORY_REVIEW",
      "INVESTIGATION",
      "FOLLOW_UP",
      "EVIDENCE_REQUEST",
      "EVIDENCE_REVIEW",
      "EVIDENCE_RESPONSE",
      "IMPACT_ASSESSMENT",
      "QUALITY_REVIEW",
      "REPORTABILITY_DECISION",
      "FIRST_CONTACT_FOLLOW_UP",
      "QMS_COMPLAINT",
      "SERVICE_ONLY_REVIEW",
      "EXTERNAL_REPLY_DUE",
      "EFFECTIVENESS_CHECK",
      "SOMETHING_NEW",
    ];
    const investigation = { id: "c1", business_id: "INV000001" } as never;
    const sources = [
      undefined,
      "DecisionBriefVersion",
      "ReportSnapshot",
      "DecisionGuideVersion",
      "CaseReview",
      "Signal",
    ];
    let checked = 0;
    for (const task_type of types)
      for (const kind of sources)
        for (const withCase of [true, false]) {
          const task = {
            task_type,
            investigation: withCase ? investigation : null,
            source: kind ? { type: kind, id: "REV000001", business_id: "SIG000001" } : undefined,
            details: { complaint_id: "c1", capa_id: "p1", follow_up_id: "FU000001", request_id: "REQ000001" },
          } as never;
          const where = taskDestination(task);
          expectLands(where.section, where.tab, `${task_type} from ${kind ?? "no source"}`);
          checked += 1;
        }
    expect(checked).toBe(types.length * sources.length * 2);
  });

  it("every record a case's audit trail names", () => {
    const kinds = [
      "DECISION",
      "SIGNAL",
      "REVIEW",
      "RISK_REVIEW",
      "CASE_REVIEW",
      "DECISION_BRIEF",
      "BRIEF_VERSION",
      "TASK",
      "FOLLOW_UP",
      "IMPACT_ASSESSMENT",
      "EVIDENCE_REQUEST",
      "EVIDENCE",
      "HYPOTHESIS",
      "UNKNOWN",
      "SCOPE",
      "CASE",
      "INVESTIGATION",
      // New in 0.10.67 (6.5): a complaint, its reports, communications, CAPAs and disposition.
      "COMPLAINT",
      "ReportObligation",
      "CommunicationEntry",
      "Capa",
      "ComplaintDisposition",
    ];
    for (const type of kinds) {
      const target = objectTarget({ type, id: "8f1c2d3e-0000-4000-8000-000000000001", business_id: "X000001" });
      if (type === "DECISION") expect(target?.kind).toBe("decision");
      else {
        expect(target?.kind, type).toBe("section");
        if (target?.kind === "section") expectLands(target.section, target.tab, type);
      }
    }
    expect(objectTarget({ type: "Capa", id: "p1" })).toEqual({
      kind: "section",
      section: "Records",
      tab: "Effectiveness checks?capa=p1",
    });
    expect(objectTarget({ type: "ComplaintDisposition", id: "d1", complaint_id: "c1" } as never)).toEqual({
      kind: "section",
      section: "Complaints",
      tab: "Dispositions?complaint=c1",
    });
  });

  it("every tab a link builds", () => {
    const built: Array<[string, string]> = [
      ["Complaints", communicationsTab("c1")],
      ["Complaints", reportsTab("c1")],
      ["Complaints", complaintListTab({ country: "US", lot: "L7" })],
      ["Records", recordsTab("p1")],
      ["Records", documentLink("MANAGEMENT_REVIEW" as never, "s1")],
      ["Signals", signalsTab({ signal: "SIG000023" })],
      ["Signals", signalsTab({ filters: { priorities: ["HIGH"] } as never })],
      ["Investigations", decisionTab({ followUp: "FU000001" })],
      ["Investigations", reviewsTab("REV000001")],
      ["Investigations", intelligenceTab("Unknowns")],
      ["Trust & Audit", trustTab({ tab: "Investigation timeline", caseId: "c1", caseLabel: "INV000001" })],
      ["Readiness", eventTab("c1")],
      ["Decisions", decisionTab({ caseId: "c1" })],
      ["Evidence", "Requests?request=REQ000001"],
    ];
    for (const [section, tab] of built) expectLands(section, tab, tab);
  });

  it("every literal open() in the workspace's screens", () => {
    const sources = import.meta.glob(["../features/**/*.tsx", "../features/**/*.ts", "!../features/**/*.test.*"], {
      query: "?raw",
      import: "default",
      eager: true,
    }) as Record<string, string>;
    // The workspace's open(section, tab) (WorkspaceApi); the administrator consoles have an open() of their own.
    const workspace = Object.entries(sources).filter(([path]) => !/\/(customer-admin|admin)\//.test(path));
    const call = /(?<![\w.])(?:workspace\??\.)?open\(\s*"([^"]+)"\s*(?:,\s*"([^"]*)"\s*)?\)/g;
    let checked = 0;
    for (const [path, text] of workspace)
      for (const match of text.matchAll(call)) {
        if (/window\.open\($/.test(text.slice(0, match.index + 7))) continue;
        expect(WORKSPACE_SECTIONS as readonly string[], `${path}: open("${match[1]}")`).toContain(match[1]);
        expectLands(match[1], match[2], `${path}: open("${match[1]}", "${match[2] ?? ""}")`);
        checked += 1;
      }
    expect(checked).toBeGreaterThanOrEqual(55);
  });

  it("every chapter of the sample story", () => {
    for (const pain of SAMPLE_PAINS) expectLands(pain.opens.section, pain.opens.tab, pain.key);
  });

  it('every "A › B" path in the user guide names a screen and one of its tabs', () => {
    const text = JSON.stringify(GUIDE_PARTS);
    // Not workspace screens: the Help menu's pages and the Admin console's sections ("In the Admin console open
    // Users › Invite").
    const elsewhere = ["Help", "Users", "Security"];
    const PANELS: Record<string, string[]> = {
      "Getting started": ["Plan your next steps", "Sample data & trial settings"],
    };
    let checked = 0;
    for (const match of text.matchAll(/([A-Z][A-Za-z]*(?: [A-Za-z&]+)?) › /g)) {
      const words = match[1];
      // A path's second level ("Readiness › Oversight › Ready to close"): a part of the tab, not a screen.
      if (text.slice(0, match.index).endsWith("› ")) continue;
      // A screen only the new navigation has (Settings, 0.10.97) is checked against its tabs there.
      const find = (from: typeof PLACES) => Object.keys(from).find((name) => words.endsWith(name));
      const places = find(PLACES) ? PLACES : NEW_PLACES;
      const section = find(places);
      if (!section) {
        expect(
          elsewhere.some((name) => words.endsWith(name)),
          `the guide's "${words} ›" names no screen`,
        ).toBe(true);
        continue;
      }
      const after = text.slice((match.index ?? 0) + match[0].length);
      // A screen without tabs names a part of itself (Import data › Distribution, a template); Getting started has
      // two parts the guide names besides its tabs (0.10.87).
      const parts = places[section].tabs.length ? [...places[section].tabs, ...(PANELS[section] ?? [])] : [after];
      const tab = parts.find((name) => after.startsWith(name));
      expect(tab, `the guide's "${section} › ${after.slice(0, 30)}" names no tab of ${section}`).toBeDefined();
      checked += 1;
    }
    expect(checked).toBeGreaterThanOrEqual(45);
  });
});

describe("the one resolver turns a server's target into a place (6.6)", () => {
  it("reads the structured target, and an older answer's section and tab", () => {
    const complaint = "c1";
    expect(
      placeOf({
        section: "Complaints",
        tab: `Reports?complaint=${complaint}`,
        target: { section: "Complaints", tab: "Reports", record: { kind: "complaint", id: complaint }, panel: null },
      }),
    ).toEqual({ section: "Complaints", tab: "Reports?complaint=c1" });
    expect(
      placeOf({
        section: "x",
        tab: null,
        target: { section: "Readiness", tab: "Oversight", record: { kind: "complaint", id: "c1" } },
      }),
    ).toEqual({ section: "Readiness", tab: "Oversight?event=c1" });
    // An alert raised before 0.10.67 carries only its section and tab.
    expect(placeOf({ section: "Complaints", tab: "Reports?complaint=c1" })).toEqual({
      section: "Complaints",
      tab: "Reports?complaint=c1",
    });
    expect(placeOf({ section: "My Work", tab: null })).toEqual({ section: "My Work", tab: undefined });
    expect(recordPlace("report", "r1")).toEqual(
      placeOf({ section: "", target: { section: "Complaints", tab: "Reports", record: { kind: "report", id: "r1" } } }),
    );
  });
});

describe("the new navigation (stage 7, 0.10.68)", () => {
  it("lists the tabs and views each new screen offers", () => {
    expect(NEW_PLACES.Complaints.tabs).toEqual([...COMPLAINT_VIEWS]);
    expect(NEW_PLACES.Trends.tabs).toEqual([...TRENDS_TABS]);
    expect(NEW_PLACES.Settings.tabs).toEqual([...SETTINGS_TABS]);
    // One complaint's page (0.10.74, C2): Details (address name Summary), Related and Activity, then the former
    // sections' names, which open the section that holds them now.
    expect(NEW_PLACES.Complaint.tabs.slice(0, 3)).toEqual([...COMPLAINT_SECTIONS]);
    expect(NEW_PLACES.Complaint.tabs.slice(3)).toEqual(["Evidence", "Decisions & actions", "History"]);
    expect(NEW_PLACES["My Work"].views?.["Tasks for me"]).toEqual(TASK_TABS.map((item) => item.tab));
    // The tab bar (0.10.73, Release C part C1): eight destinations, My work as Home; each persona shows some of
    // them. Settings and Account are in the avatar's menu (Help is the Help menu).
    expect(NEW_MENU.main).toEqual([
      "My Work",
      "Complaints",
      "Decision trees",
      "Reports",
      "Investigations",
      "Trends",
      "Product 360",
      "Records",
      "Team",
    ]);
    expect(NEW_MENU.top).toEqual(["Settings", "My Account"]);
    expect(NEW_MENU.main.map((name) => NEW_PLACES[name].label ?? name)).toEqual([
      "Home",
      "Complaints",
      "Decision trees",
      "Reports",
      "Investigations",
      "Trends",
      "Products",
      "Records",
      "Team",
    ]);
    // My work has fewer tabs than the classic 10.
    expect(NEW_PLACES["My Work"].tabs.length).toBeLessThan(PLACES["My Work"].tabs.length);
  });

  it("gives every classic screen and tab a home on the new navigation (7.1: every old screen is reachable)", () => {
    let checked = 0;
    for (const [section, place] of Object.entries(PLACES))
      for (const tab of [undefined, ...place.tabs]) {
        const { ok, place: home } = landsOn(section, tab, "new");
        expect(ok, `${section} / ${tab ?? ""} -> ${home.section} / ${home.tab}`).toBe(true);
        checked += 1;
      }
    // 12 screens, 58 tabs (with the nested ones counted under their screen).
    expect(checked).toBeGreaterThanOrEqual(12 + 58);
    for (const [view, [section, tab]] of Object.entries(OLD_VIEWS))
      expect(landsOn(section, tab, "new").ok, `/app/${view}`).toBe(true);
    for (const row of table.oldSections) expect(landsOn(row.section, row.tab, "new").ok, row.section).toBe(true);
    // Every row of the table names a classic place and a new one.
    for (const row of NEW_HOMES) expect(landsOn(row.to.section, row.to.tab, "new").ok, row.section).toBe(true);
  });

  it("keeps what a link carries, and names the view a former tab is now", () => {
    expect(routeFor("Complaints", "Reports?complaint=c1&report=r1", "mvp", "new")).toEqual({
      section: "Complaints",
      tab: "Reporting?complaint=c1&report=r1",
    });
    expect(routeFor("My Work", "Overdue", "mvp", "new")).toEqual({
      section: "My Work",
      tab: "Tasks for me?view=Overdue",
    });
    expect(routeFor("Complaints", "First contact?check=i1", "mvp", "new")).toEqual({
      section: "My Work",
      tab: "Queues?check=i1&view=Calls+to+check",
    });
    expect(routeFor("Complaints", "Review settings", "mvp", "new")).toEqual({
      section: "Settings",
      tab: "Complaint review rules",
    });
    expect(routeFor("Signals", "Signal inbox?signal=SIG000023", "mvp", "new")).toEqual({
      section: "Trends",
      tab: "Trends to review?signal=SIG000023",
    });
    expect(routeFor("Readiness", undefined, "mvp", "new")).toEqual({ section: "Records", tab: "Inspection readiness" });
    expect(routeFor("Getting started", "Team", "mvp", "new")).toEqual({ section: "Team", tab: undefined });
    // A place of the new navigation stays where it is.
    expect(routeFor("Complaints", "To triage", "mvp", "new")).toEqual({ section: "Complaints", tab: "To triage" });
    // Without the MVP feature set (no addresses) nothing moves.
    expect(routeFor("Complaints", "Triage", "full", "new")).toEqual({ section: "Complaints", tab: "Triage" });
  });

  it("opens a complaint on its own page by its reference; the stage-6 id links redirect to it", () => {
    const id = "8f1c2d3e-0000-4000-8000-000000000001";
    expect(routeFor("Readiness", `Oversight?event=${id}`, "mvp", "new")).toEqual({
      section: "Complaint",
      tab: `Summary?ref=${id}`,
    });
    expect(addressFor({ section: "Complaint", tab: "Summary?ref=SAMPLE-RV-06" })).toBe("/app/complaints/SAMPLE-RV-06");
    expect(addressFor({ section: "Complaint", tab: "History?ref=A/B 7" })).toBe(
      "/app/complaints/A%2FB%207?tab=History",
    );
    expect(locationFromAddress("/app/complaints/SAMPLE-RV-06", "", VIEW_TO_SECTION, WORKSPACE_SECTIONS)).toEqual({
      section: "Complaint",
      tab: "Summary?ref=SAMPLE-RV-06",
    });
    expect(
      locationFromAddress("/app/complaints/A%2FB%207", "?tab=History", VIEW_TO_SECTION, WORKSPACE_SECTIONS),
    ).toEqual({ section: "Complaint", tab: "History?ref=A%2FB+7" });
    expect(viewFromPath("/app/complaints/SAMPLE-RV-06")).toBe("complaints");
    // On the classic navigation the same address opens the complaint's Oversight checklist.
    expect(routeFor("Complaint", "Summary?ref=SAMPLE-RV-06", "mvp", "classic")).toEqual({
      section: "Readiness",
      tab: "Oversight?event=SAMPLE-RV-06",
    });
    // Every record the server names opens on the new navigation; a complaint opens its page.
    expect(
      routeFor(
        "Readiness",
        placeOf({ section: "", target: { section: "Readiness", tab: "Oversight", record: { kind: "complaint", id } } })
          .tab,
        "mvp",
        "new",
      ),
    ).toEqual({ section: "Complaint", tab: `Summary?ref=${id}` });
  });

  it("maps every former investigation tab to its section and part (stage 8, 8.1)", () => {
    // The four sections, and the tab's own list of every investigation (0.10.74, C2).
    expect(NEW_PLACES.Investigations.tabs).toEqual([
      "Summary",
      "Evidence",
      "Decisions & actions",
      "History",
      "All investigations",
    ]);
    const homes: Array<[string, string]> = [
      ["Workspace", "Summary"],
      ["Scope", "Summary?part=scope"],
      ["Evidence", "Evidence"],
      ["Intelligence?view=Unknowns", "Evidence?view=Unknowns&part=intelligence"],
      ["Ask MDARIX", "Evidence?part=ask"],
      ["Reviews?review=REV000001", "Decisions & actions?review=REV000001&part=reviews"],
      ["Decision Brief", "Decisions & actions?part=brief"],
      ["Decision?follow_up=FU000001", "Decisions & actions?follow_up=FU000001&part=decision"],
      ["Record", "History"],
    ];
    for (const [tab, home] of homes)
      expect(routeFor("Investigations", tab, "mvp", "new"), tab).toEqual({ section: "Investigations", tab: home });
    // Every classic tab of the case page has a home (none is left on a tab the new screen does not have).
    for (const tab of PLACES.Investigations.tabs) expect(landsOn("Investigations", tab, "new").ok, tab).toBe(true);
    // The classic navigation keeps today's tabs, and opens a section's address on the tab that held it.
    expect(routeFor("Investigations", "Decision", "mvp", "classic").tab).toBe("Decision");
    expect(routeFor("Investigations", "Decisions & actions?part=brief", "mvp", "classic").tab).toBe(
      "Decision?part=brief",
    );
    expect(routeFor("Investigations", "History", "mvp", "classic").tab).toBe("Record");
    expect(recordPlace("case", "INV000002", {}, "new")).toEqual({ section: "Investigations", tab: "Summary" });
  });

  it("opens the new navigation's own addresses on the classic one too", () => {
    for (const section of ["Trends", "Settings", "Team", "Product 360"])
      expect(landsOn(section, undefined, "classic").ok, section).toBe(true);
  });

  it("opens a former Products link on Product 360 on the new navigation, Readiness on the classic (P360-14)", () => {
    expect(routeFor("Products", undefined, "mvp", "new")).toEqual({ section: "Product 360", tab: "Product 360" });
    expect(routeFor("Products", "Configuration", "mvp", "new")).toEqual({ section: "Product 360", tab: "Product 360" });
    expect(OLD_VIEWS.products).toEqual(["Products"]);
    expect(routeFor("Products", undefined, "mvp", "classic").section).toBe("Readiness");
    expect(routeFor("Product 360", "Supplier 360?supplier=SAMPLE-SUP-B", "mvp", "new")).toEqual({
      section: "Product 360",
      tab: "Supplier 360?supplier=SAMPLE-SUP-B",
    });
    expect((NEW_RECORD_PLACES as Record<string, unknown>).product).toEqual({
      section: "Product 360",
      tab: "Product 360",
      param: "product",
    });
  });

  it("puts no setting on a daily screen (7.7)", () => {
    // Work › Products' tabs are Product 360 and Supplier 360 (owner, 10 Nov 2026): no clash with Settings › Products.
    expect(NEW_PLACES["Product 360"].tabs).toEqual(["Product 360", "Supplier 360"]);
    const daily = NEW_MENU.main.flatMap((section) => NEW_PLACES[section].tabs);
    for (const setting of [
      "Review settings",
      "Reporting windows",
      "Decision guides",
      "Detection rules",
      "Working calendar",
      "Import templates",
      ...SETTINGS_TABS,
    ])
      expect(daily, setting).not.toContain(setting);
    // Each classic setting's home is Settings.
    for (const [section, tab] of [
      ["Complaints", "Review settings"],
      ["Complaints", "Reporting windows"],
      ["Complaints", "Decision guides"],
      ["Signals", "Detection rules"],
    ])
      expect(routeFor(section, tab, "mvp", "new").section, tab).toBe("Settings");
    // The components that hold a setting on a daily screen hide it on the new navigation.
    const sources = import.meta.glob(["../features/workspace/sections/*.tsx"], {
      query: "?raw",
      import: "default",
      eager: true,
    }) as Record<string, string>;
    const text = (name: string) => sources[`../features/workspace/sections/${name}.tsx`];
    expect(text("Communications")).toMatch(/workspace\?\.navigation !== "new" && <AttemptsSetting/);
    expect(text("Oversight")).toMatch(/part === "all" && view && <CalendarPanel/);
    expect(text("Reminders")).toMatch(/!fresh && <AwayControl/);
  });
});
