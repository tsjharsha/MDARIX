import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { NEW_PLACES, routeFor, tabParts } from "../../app/linkTable";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { FLAGSHIP, SCENARIOS, storyStep } from "./entrance";
import { Entrance, StoryBar } from "./sections/Entrance";

// Quality plan stage 8 (8.4): the five-minute entrance and its story bar.

vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data:
      path && path.includes("/oversight/events/")
        ? {
            event: {
              description:
                "Biomedical engineering checked a monitor against a reference oximeter: its SpO2 read 4 to 6 points high on two patients. No harm was reported. The monitor is out of use and sent for service.",
            },
          }
        : { home: [], has_sample: false },
    reload: () => undefined,
  }),
}));

const api = (story: string | null = null) =>
  ({
    session: null,
    work: {},
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    story,
    startStory: vi.fn(),
  }) as unknown as WorkspaceApi;

describe("the entrance", () => {
  it("leads with one sample event in the reporter's words; the other stories and the restart under More", () => {
    expect(SCENARIOS.map((item) => item.title)).toEqual([
      "A hospital sent a monitor for service. Should Quality review this too?",
      "A complaint just arrived: what now?",
      "Is a problem rising?",
      "Is this reportable, and by when, in the US and India?",
    ]);
    const html = renderToStaticMarkup(
      <WorkspaceContext.Provider value={api()}>
        <Entrance onRestarted={() => undefined} />
      </WorkspaceContext.Provider>,
    );
    expect(html).toContain("A hospital sent a monitor for service. Should Quality review this too?");
    expect(html).toContain("its SpO2 read 4 to 6 points high on two patients. No harm was reported.");
    expect(html).toContain("Review this sample event");
    expect(html).toContain("Fictional manufacturer · Sample data only");
    expect(html).toContain("Sample event · SAMPLE-RV-11 · 4 steps");
    // The event comes first, then More stories, then More (with the restart).
    expect(html.indexOf("Review this sample event")).toBeLessThan(html.indexOf("More stories"));
    expect(html.indexOf("More stories")).toBeLessThan(html.indexOf("<summary>More</summary>"));
    // 0.10.71 (A2): your own export is under Help › Try your own data, not a tile.
    expect(html).not.toContain("Upload your export");
    // No time claims; step counts only. The readiness numbers are on the manager's My work.
    expect(html).not.toMatch(/minute/i);
    expect(html).toContain("3 steps");
    expect(html).toContain("7 steps");
    expect(html).not.toContain("Inspection readiness");
  });

  it("starts each story on its record, and every step is a place of the new navigation", () => {
    for (const scenario of SCENARIOS) {
      const start = routeFor(scenario.start.section, scenario.start.tab, "mvp", "new");
      expect(NEW_PLACES[start.section], scenario.key).toBeTruthy();
      // The story's first step is where its tile lands, on a named record (never a queue).
      // (The short story's step is what was saved on its record, not the place: shortStory.test.)
      if (scenario.key !== "short") expect(storyStep(scenario, start), scenario.key).toBe(0);
      expect(scenario.start.tab ?? "", scenario.key).toMatch(/\?(ref|product)=SAMPLE-/);
      for (const step of scenario.steps) {
        const place = NEW_PLACES[step.section];
        expect(place, step.label).toBeTruthy();
        for (const tab of [step.tab ?? []].flat()) expect(place.tabs, step.label).toContain(tab);
      }
    }
    // The flagship opens on its own complaint page.
    const flagship = SCENARIOS.find((item) => item.key === "reportable")!;
    expect(routeFor(flagship.start.section, flagship.start.tab, "mvp", "new")).toEqual({
      section: "Complaint",
      tab: `Summary?ref=${FLAGSHIP}`,
    });
  });

  it("reads the step from the place on screen, the report apart from the market assessment", () => {
    const flagship = SCENARIOS.find((item) => item.key === "reportable")!;
    const at = (section: string, tab?: string) => storyStep(flagship, { section, tab });
    expect(at("Complaints", "Reporting?complaint=c1")).toBe(2);
    expect(at("Complaints", "Reporting?complaint=c1&report=r1")).toBe(3);
    expect(at("Complaint", "Decisions & actions?ref=SAMPLE-RV-11")).toBe(6);
    expect(at("Records", "Exports")).toBe(-1);
    expect(tabParts("Summary?ref=x").name).toBe("Summary");
  });

  it("shows the story bar with the step and the way back", () => {
    const html = renderToStaticMarkup(
      <WorkspaceContext.Provider value={api("reportable")}>
        <StoryBar section="Complaints" tab="Reporting?complaint=c1" />
      </WorkspaceContext.Provider>,
    );
    expect(html).toContain("Step 3 of 7: Assess the US, then India");
    expect(html).toContain("Back to the stories");
  });
});
