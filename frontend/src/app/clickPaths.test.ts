import { describe, expect, it } from "vitest";
import { NEW_MENU, NEW_PLACES, routeFor, tabParts } from "./linkTable";
import { taskDestination } from "../features/workspace/tasks";

/**
 * Quality plan stage 7: the register's click paths a–m on the new navigation, counted step by step. A step either
 * opens a place (it must exist on the new navigation: linkTable.json newPlaces) or presses a button (its words must
 * be on the screen that shows it: the component's source). The count starts on My work, the first screen after
 * sign-in (a trial on the new navigation starts on the entrance the first time: stage 8).
 */
type Step = { go: [string, string?] } | { press: string; in: string };

const sources = import.meta.glob(["../features/**/*.tsx"], { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;
const sourceOf = (name: string) => Object.entries(sources).find(([path]) => path.endsWith(`/${name}.tsx`))?.[1] ?? "";

const lands = ([section, tab]: [string, string?]) => {
  const place = routeFor(section, tab, "mvp", "new");
  const known = NEW_PLACES[place.section];
  const name = tabParts(place.tab).name;
  return !!known && (!name || known.tabs.includes(name));
};

const MENU = (name: string): Step => ({ go: [name] });

/** The register's counts today (findings register, IA, 1 Nov) and proposed; each path's steps on the new navigation. */
export const PATHS: Array<{
  key: string;
  task: string;
  today: number;
  proposed: number;
  steps: Step[];
  note?: string;
}> = [
  {
    key: "a",
    task: "Log a call that may be a complaint",
    today: 6,
    proposed: 4,
    steps: [
      { press: "Log a case", in: "MyWork" },
      { press: "Save the case", in: "FirstContact" },
      { press: "Save the answers", in: "FirstContact" },
      { press: "Sign the case check", in: "FirstContact" },
    ],
  },
  {
    key: "b",
    task: "Reportable for the US and India?",
    today: 6,
    proposed: 4,
    steps: [
      // The reportability task opens the complaint's market assessment at once (tasks.ts).
      { go: ["Complaints", "Reportability?complaint=c1"] },
      { press: "Save and sign", in: "MarketAssessment" },
      { press: "<Tabs", in: "MarketAssessment" },
      { press: "Save and sign", in: "MarketAssessment" },
    ],
  },
  {
    key: "c",
    task: "Draft, approve and record a US report (two people)",
    today: 14,
    proposed: 9,
    steps: [
      { go: ["Complaints", "Reports?complaint=c1"] },
      { press: "Start the worksheet", in: "Reports" },
      { press: "Save", in: "Reports" },
      { press: "Ask for approval", in: "Reports" },
      // The approver's task in My work (stage 3) opens the snapshot.
      { go: ["Complaints", "Reports?complaint=c1"] },
      { press: "Approve", in: "Reports" },
      { go: ["Complaints", "Reports?complaint=c1"] },
      { press: "Mark as submitted", in: "Reports" },
      { press: "receipt", in: "Reports" },
    ],
  },
  {
    key: "d",
    task: "Find complaints hidden as service requests or cancellations",
    today: 2,
    proposed: 2,
    steps: [MENU("Complaints"), { go: ["Complaints", "Second look"] }],
  },
  {
    key: "e",
    task: "Is a product problem rising?",
    today: 2,
    proposed: 1,
    steps: [MENU("Trends")],
    note: "Trends opens on the trend check",
  },
  {
    key: "f",
    task: "Open an investigation from a trend and reach its decision (2-3 people)",
    today: 15,
    proposed: 11,
    steps: [
      MENU("Trends"),
      { go: ["Trends", "Trends to review?signal=SIG000001"] },
      { press: "Open an investigation", in: "SignalDetail" },
      // The brief, the reviews and the decision are one section of the investigation (stage 8), not three tabs.
      { go: ["Investigations", "Decisions & actions"] },
      { press: "Compose", in: "CaseDecisionBrief" },
      { press: "Submit", in: "CaseDecisionBrief" },
      // The reviewer's task opens the same section, on the brief (a former tab's address: linkTable.json newHomes).
      { go: ["Investigations", "Decision Brief"] },
      { press: "Accept", in: "CaseDecisionBrief" },
      // The decision is below the brief in the same section: no tab to open.
      { press: "Sign", in: "CaseDecision" },
      { press: "Sign", in: "CaseDecision" },
    ],
    note: "10 since stage 8 (11 + 1 in stage 7, with the Decision Brief and Decision tabs)",
  },
  {
    key: "g",
    task: "Sign a decision",
    today: 5,
    proposed: 3,
    steps: [
      { go: ["Investigations", "Decision"] },
      { press: "Sign", in: "CaseDecision" },
      { press: "Sign", in: "CaseDecision" },
    ],
  },
  {
    key: "h",
    task: "What is overdue and who owns it",
    today: 2,
    proposed: 1,
    steps: [{ go: ["My Work", "Team overview"] }],
    note: "managers see the overdue count on My work at 0 clicks; the list is 1",
  },
  {
    key: "i",
    task: "Prepare for an inspection, find every export",
    today: 2,
    proposed: 2,
    steps: [MENU("Records"), { go: ["Records", "Exports"] }],
  },
  {
    key: "j",
    task: "Invite a colleague (trial)",
    today: 2,
    proposed: 3,
    steps: [MENU("Team"), { press: "Invite", in: "TrialTeam" }],
    note: "a pilot invites in the admin console, as today (4)",
  },
  {
    key: "k",
    task: "Upload own data",
    today: 5,
    proposed: 5,
    steps: [
      MENU("Complaints"),
      { press: "Import your data", in: "ComplaintViews" },
      { press: "Choose a file", in: "ImportData" },
      { press: "Check file", in: "ImportData" },
      { press: "Import", in: "ImportData" },
    ],
    note: "the register: 4 from Getting started, 5 from the Import data menu; a trial keeps Getting started's 4",
  },
  {
    key: "l",
    task: "Chase an unanswered request to a hospital",
    today: 4,
    proposed: 3,
    steps: [
      // The reminder on My work opens the request itself (oversight/service.py: record communication).
      { go: ["Complaints", "Communications?communication=e1"] },
      { press: "Record another attempt", in: "Communications" },
      { press: "Save", in: "Communications" },
    ],
  },
  {
    key: "m",
    task: "Check a CAPA's effectiveness",
    today: 3,
    proposed: 2,
    steps: [{ go: ["Records", "Effectiveness checks?capa=p1"] }, { press: "Sign", in: "Records" }],
  },
  // B6a Part D (navigation review, D4): the new screens on the same count.
  {
    key: "n",
    task: "Trace a report value to its record, import row and snapshot",
    today: 2,
    proposed: 2,
    steps: [{ go: ["Complaints", "Reports?complaint=c1"] }, { press: "Trace", in: "TraceValue" }],
  },
  {
    key: "o",
    task: "See the outcome numbers against the baseline",
    today: 1,
    proposed: 1,
    steps: [{ go: ["My Work", "Team overview"] }],
    note: "the Value Centre panel is on Team overview (Readiness › Oversight on the classic navigation)",
  },
  // B6a navigation polish (D4 backlog items 2, 4, 5, 10, 14, 15 and the audit trail review).
  {
    key: "p",
    task: "Open a possible duplicate's record before linking or dismissing it",
    today: 4,
    proposed: 2,
    steps: [{ go: ["My Work", "Queues?view=Possible duplicates"] }, { press: "opens in a new tab", in: "BackEntry" }],
    note: "today: the menu, a list and a search for the reference; the late-entry form shows the same link",
  },
  {
    key: "q",
    task: "From a traced value to its record and its import's data-quality report",
    today: 5,
    proposed: 3,
    steps: [
      { go: ["Complaints", "Reports?complaint=c1"] },
      { press: "Trace", in: "TraceValue" },
      { press: "Data-quality report", in: "TraceValue" },
    ],
    note: "the record's reference in the same panel opens its page (originPlace); today: the menu and a search",
  },
  {
    key: "r",
    task: "From a CAPA follow-up to its effectiveness check",
    today: 4,
    proposed: 3,
    steps: [
      { go: ["Investigations", "Decisions & actions?part=decision"] },
      { press: "Details", in: "AfterDecision" },
      { press: "Open its effectiveness check", in: "AfterDecision" },
    ],
    note: "today: Records › Effectiveness checks and a search for the CAPA",
  },
  {
    key: "s",
    task: "A check signed not effective: plan the further action on the decision",
    today: 4,
    proposed: 3,
    steps: [
      { go: ["Records", "Effectiveness checks?capa=p1"] },
      { press: "Go to the investigation's decision", in: "Records" },
      { go: ["Investigations", "Decision"] },
    ],
    note: "today the button opened the Summary (Workspace) and the person chose Decisions & actions",
  },
  {
    key: "t",
    task: "After linking duplicates, confirm the awareness conflict on the triage list",
    today: 3,
    proposed: 3,
    steps: [
      { go: ["My Work", "Queues?view=Possible duplicates"] },
      { press: "Open the triage list", in: "FirstContact" },
      { go: ["Complaints", "Triage"] },
    ],
    note: "today: the menu, Complaints, To triage; now one link from the hint itself",
  },
  {
    key: "u",
    task: "Sign the audit trail review on the new navigation",
    today: 3,
    proposed: 2,
    steps: [{ go: ["My Work", "Team overview"] }, { press: "Sign the audit trail review", in: "Reviews" }],
    note: "today only on the classic Readiness › Oversight (reached on the new navigation by an old address)",
  },
];

describe("the click paths a–u on the new navigation (stages 7 and 8, B6a, navigation polish)", () => {
  it.each(PATHS.map((path) => [path.key, path] as const))("path %s: every step exists, within the count", (_, path) => {
    for (const step of path.steps)
      if ("go" in step) expect(lands(step.go), `${path.key}: ${step.go.join(" › ")}`).toBe(true);
      else expect(sourceOf(step.in), `${path.key}: "${step.press}" on ${step.in}`).toContain(step.press);
    expect(path.steps.length, `${path.key}: ${path.task}`).toBeLessThanOrEqual(path.proposed);
    expect(path.steps.length, `${path.key} is no longer than today`).toBeLessThanOrEqual(path.today);
  });

  it("counts path f in 10 steps: the investigation's sections hold the brief and the decision (stage 8)", () => {
    expect(PATHS.find((path) => path.key === "f")!.steps).toHaveLength(10);
    expect(routeFor("Investigations", "Decision Brief", "mvp", "new")).toEqual({
      section: "Investigations",
      tab: "Decisions & actions?part=brief",
    });
  });

  it("starts on the menu's own screens", () => {
    // UX2: Trends is a screen of the Products area, not a menu line of its own.
    expect(NEW_MENU.main).toContain("Product 360");
    // Team is a tab of the bar since 0.10.73 (Admin's only); Settings and Account are in the avatar's menu.
    // UX2: Team is in the avatar menu for everyone.
    expect(NEW_MENU.top).toContain("Team");
  });

  it("opens a reportability task on the complaint's market assessment (path b)", () => {
    const task = { task_type: "REPORTABILITY_DECISION", investigation: null, details: { complaint_id: "c1" } } as never;
    // UX2: reportability lives in Decisions & Reports › Reports, with the complaint's assessment open.
    expect(routeFor(taskDestination(task).section, taskDestination(task).tab, "mvp", "new")).toEqual({
      section: "Reports",
      tab: "?complaint=c1&part=assess",
    });
  });
});
