import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { NEW_PLACES, routeFor, tabParts } from "../../app/linkTable";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { FLAGSHIP, SCENARIOS, storyStep } from "./entrance";
import { Entrance, StoryBar } from "./sections/Entrance";

// Quality plan stage 8 (8.4): the five-minute entrance and its story bar.

vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: () => ({ state: "ready", data: { home: [], has_sample: false }, reload: () => undefined }),
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

describe("the five-minute entrance", () => {
  it("offers the three owner-approved stories and your own export, each about five minutes", () => {
    expect(SCENARIOS.map((item) => item.title)).toEqual([
      "A complaint just arrived: what now?",
      "Is a problem rising?",
      "Is this reportable, and by when, in the US and India?",
      "Try it on your own export",
    ]);
    const html = renderToStaticMarkup(
      <WorkspaceContext.Provider value={api()}>
        <Entrance onRestarted={() => undefined} />
      </WorkspaceContext.Provider>,
    );
    // 0.10.71 (A2): your own export is under Help › Try your own data, not a tile.
    expect(html.match(/About 5 minutes/g)).toHaveLength(3);
    expect(html).not.toContain("Upload your export");
    expect(html).toContain("Inspection readiness on the sample");
  });

  it("starts each story on its record, and every step is a place of the new navigation", () => {
    for (const scenario of SCENARIOS) {
      const start = routeFor(scenario.start.section, scenario.start.tab, "mvp", "new");
      expect(NEW_PLACES[start.section], scenario.key).toBeTruthy();
      // The story's first step is where its tile lands.
      expect(storyStep(scenario, start), scenario.key).toBe(0);
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
