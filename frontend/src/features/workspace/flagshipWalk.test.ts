import { describe, expect, it } from "vitest";
import { NEW_PLACES, placeOf, routeFor, tabParts } from "../../app/linkTable";
import { SCENARIOS } from "./entrance";

/**
 * Quality plan stage 8, the done-when: the flagship story is done without the menu. The server half walks it step by
 * step (tests/test_flagship_walkthrough.py, which lists WALK); this half proves each step's main button is on the
 * screen that shows it, and each server next action opens a place of the new navigation on the complaint's own record
 * (never a list to search, never the menu).
 */
const sources = import.meta.glob(["./sections/*.tsx"], { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;
const source = (name: string) => sources[`./sections/${name}.tsx`] ?? "";

// [the main button, the screen that shows it]: the walk's steps after the entrance and the server's next actions.
const BUTTONS: Array<[string, string]> = [
  ["Save the triage record", "Triage"],
  ["Save and sign", "MarketAssessment"],
  ["Assess India (CDSCO) too", "MarketAssessment"],
  ["Ask for approval", "Reports"],
  ["Approve", "Reports"],
  ["Mark as submitted", "Reports"],
  ["Record the evidence", "Reports"],
  ["Sign", "Dispositions"],
  ["Record review", "CaseEvidence"],
  ["Record outcome", "CaseReviews"],
  ["Compose the brief", "CaseDecisionBrief"],
  ["Submit for quality review", "CaseDecisionBrief"],
  ["Accept", "CaseDecisionBrief"],
  ["Sign decision", "CaseDecision"],
  ["Sign ready to close", "ComplaintPage"],
];

// The server's next actions along the walk (closure.py), each with the record it names.
const NEXT_ACTIONS = [
  { section: "Complaints", tab: "Triage", record: { kind: "complaint", id: "c1" } },
  { section: "Complaints", tab: "Reportability", record: { kind: "complaint", id: "c1" } },
  { section: "Complaints", tab: "Reports", record: { kind: "complaint", id: "c1" } },
  { section: "Complaints", tab: "Dispositions", record: { kind: "disposition", id: "c1" } },
  { section: "Investigations", tab: "Decision", record: { kind: "case", id: "case-1" } },
];

describe("the flagship walk-through, by each screen's main button", () => {
  it("starts on its tile and names each step's button where it is pressed", () => {
    const flagship = SCENARIOS.find((item) => item.key === "reportable")!;
    expect(flagship.title).toBe("Is this reportable, and by when, in the US and India?");
    for (const [label, screen] of BUTTONS) expect(source(screen), `${label} on ${screen}`).toContain(label);
  });

  it("opens every next action on the complaint's own record, on a place of the new navigation", () => {
    for (const target of NEXT_ACTIONS) {
      const classic = placeOf({ section: target.section, target });
      const place = routeFor(classic.section, classic.tab, "mvp", "new");
      const { name, query } = tabParts(place.tab);
      expect(NEW_PLACES[place.section]?.tabs, `${target.section} › ${target.tab}`).toContain(name);
      // A record the screen opens on: never a list to search.
      if (target.record.kind !== "case") expect(query, target.tab).toContain("c1");
    }
    // "Assess the United States (FDA) market" opens the complaint's assessment, not its list of reports (0.10.68
    // opened Reporting on the reports, with no assessment in sight).
    expect(routeFor("Complaints", "Reportability?complaint=c1", "mvp", "new").tab).toBe(
      "Reporting?complaint=c1&part=assess",
    );
    expect(source("ComplaintViews")).toContain('tabParam(carried, "part") === "assess"');
  });
});
