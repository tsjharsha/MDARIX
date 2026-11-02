import { describe, expect, it } from "vitest";
import table from "./linkTable.json";
import { OLD_VIEWS, PLACES, RECORD_PLACES, placeOf, recordPlace, routeFor, tabParts } from "./linkTable";
import { APP_ROUTES, viewFromPath } from "./router";
import { WORKSPACE_VIEWS } from "./navigationPolicy";
import { MVP_RECORDS_TABS, PARKED_SECTIONS } from "./featureSet";
import { WORKSPACE_SECTIONS } from "../features/workspace/workspaceContext";
import { addressFor, locationFromAddress } from "../features/workspace/workspaceAddress";
import { VIEW_TO_SECTION } from "../features/workspace/UserWorkspace";
import { COMPLAINTS_TABS } from "../features/workspace/complaintReview";
import { SIGNALS_TABS } from "../features/workspace/signals";
import { READINESS_TABS, eventTab } from "../features/workspace/oversight";
import { LOOK_AHEAD_TABS } from "../features/workspace/partyPreview";
import { TASK_TABS, OTHER_MY_WORK_TABS, taskDestination } from "../features/workspace/tasks";
import { TRIAL_TABS } from "../features/workspace/sections/GettingStarted";
import { objectTarget } from "../features/workspace/caseAudit";
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
const landsOn = (section: string, tab: string | undefined | null) => {
  const place = routeFor(section, tab ?? undefined, "mvp");
  const known = PLACES[place.section];
  const name = tabParts(place.tab).name;
  return { ok: !!known && (!name || known.tabs.includes(name)), place };
};

const expectLands = (section: string, tab: string | undefined | null, where: string) => {
  const { ok, place } = landsOn(section, tab);
  expect(ok, `${where}: ${section} / ${tab} lands on ${place.section} / ${place.tab}`).toBe(true);
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
    // Every section the MVP shows has a place; the parked ones have none (they redirect).
    const shown = WORKSPACE_SECTIONS.filter((section) => !PARKED_SECTIONS.includes(section));
    expect(Object.keys(PLACES).sort()).toEqual([...shown].sort());
  });

  it("gives every place its own address, which the browser routes", () => {
    for (const [section, place] of Object.entries(PLACES)) {
      const view = viewFromPath(place.path);
      expect(APP_ROUTES[view], section).toBe(place.path);
      expect(WORKSPACE_VIEWS, section).toContain(view);
      expect(VIEW_TO_SECTION[view]?.[0], section).toBe(section);
    }
  });

  it("opens each kind of record on an existing tab", () => {
    for (const [kind, place] of Object.entries(RECORD_PLACES)) expectLands(place.section, place.tab, kind);
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
      for (const [old, now] of Object.entries(renamed))
        expect(routeFor(section, old, "mvp")).toEqual({ section, tab: now });
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
      ["Trust & Audit", trustTab({ tab: "Case timeline", caseId: "c1", caseLabel: "INV000001" })],
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
    const PANELS: Record<string, string[]> = { "Getting started": ["See it on your own records, one to one"] };
    let checked = 0;
    for (const match of text.matchAll(/([A-Z][A-Za-z]*(?: [A-Za-z&]+)?) › /g)) {
      const words = match[1];
      // A path's second level ("Readiness › Oversight › Ready to close"): a part of the tab, not a screen.
      if (text.slice(0, match.index).endsWith("› ")) continue;
      const section = Object.keys(PLACES).find((name) => words.endsWith(name));
      if (!section) {
        expect(
          elsewhere.some((name) => words.endsWith(name)),
          `the guide's "${words} ›" names no screen`,
        ).toBe(true);
        continue;
      }
      const after = text.slice((match.index ?? 0) + match[0].length);
      // A screen without tabs names a part of itself (Import data › Distribution, a template); Getting started has
      // one panel the guide names besides its tabs.
      const parts = PLACES[section].tabs.length ? [...PLACES[section].tabs, ...(PANELS[section] ?? [])] : [after];
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
