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
      { press: "Log a call", in: "MyWork" },
      { press: "Save the call", in: "FirstContact" },
      { press: "Save the answers", in: "FirstContact" },
      { press: "Sign the check", in: "FirstContact" },
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
];

describe("the click paths a–m on the new navigation (stages 7 and 8)", () => {
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
    expect(NEW_MENU.main).toContain("Trends");
    // Team is a tab of the bar since 0.10.73 (Admin's only); Settings and Account are in the avatar's menu.
    expect(NEW_MENU.main).toContain("Team");
  });

  it("opens a reportability task on the complaint's market assessment (path b)", () => {
    const task = { task_type: "REPORTABILITY_DECISION", investigation: null, details: { complaint_id: "c1" } } as never;
    expect(routeFor(taskDestination(task).section, taskDestination(task).tab, "mvp", "new")).toEqual({
      section: "Complaints",
      tab: "Reporting?complaint=c1&part=assess",
    });
  });
});
