// 0.10.82, round D1 "One story": the record pages and Home, rendered from the server's answers.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ComplaintPage } from "./sections/ComplaintPage";
import { ONE_STORY_PATH, type StoryRun } from "./oneStory";
import { eventPath } from "./oversight";
import { rv11 } from "../../test/rv11";
import { HomeSection } from "./sections/Home";
import { IMPORTED_SOURCE } from "./complaintList";
import { trendPath } from "./signalAi";
import { SERVER_VIEWS } from "./listViews";
import { OVERDUE_PATH, OVERDUE_VIEW } from "./home";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
}));

const api = (overrides: Partial<WorkspaceApi> = {}) =>
  ({
    session: { user_id: "u1", business_permissions: ["records.write", "signal.triage"] },
    work: { products: [], investigations: [] },
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
    persona: "admin",
    ...overrides,
  }) as unknown as WorkspaceApi;

const render = (node: ReactNode, value: WorkspaceApi = api()) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

const LABELS = ["The call", "Triage", "Tree", "Reportable?", "Form", "Fill", "Approval", "Submit", "Records", "Trends"];
const run = (current: number): StoryRun => ({
  run: "sample",
  complaint: {
    id: "c-rv11",
    ref: "SAMPLE-RV-11",
    description: "",
    product_id: "p",
    serious_injury: false,
    death: false,
  },
  market: "US",
  market_label: "United States (FDA)",
  conclusion: null,
  report_id: null,
  report_stage: null,
  needs: [],
  steps: LABELS.map((label, index) => ({ key: label, label, done: index < current, skipped: false })),
  current,
  finished: current >= 10,
});

describe("every record page: one Next step, which is the story's, and one progress indicator (D1.5)", () => {
  it("on the story's complaint shows a slim pill, the story's step as the rail's one button and one status line", () => {
    resources.data[eventPath("SAMPLE-RV-11")] = rv11();
    resources.data[ONE_STORY_PATH] = { sample: run(2), yours: null };
    const html = render(<ComplaintPage tab="Summary?ref=SAMPLE-RV-11" />);
    expect(html).toContain('class="uw-story-pill"');
    expect(html).toContain("Step 3 of 10");
    const rail = html.slice(html.indexOf('aria-label="What to do next"'));
    expect(rail).toContain("Story step 3: the decision tree");
    expect(rail).toContain("Open the tree");
    // One main button on the page, and one progress indicator: the status line, no chevron path.
    expect(html.match(/class="ac-primary"/g)).toHaveLength(1);
    expect(html).toContain("Stage 2 of 6 ·");
    expect(html).not.toContain('class="uw-path"');
  });

  it("on another complaint shows no pill and keeps the record's own next step", () => {
    resources.data[eventPath("SAMPLE-RV-11")] = rv11();
    resources.data[ONE_STORY_PATH] = {
      sample: { ...run(2), complaint: { ...run(2).complaint, ref: "X" } },
      yours: null,
    };
    const html = render(<ComplaintPage tab="Summary?ref=SAMPLE-RV-11" />);
    expect(html).not.toContain("uw-story-pill");
    expect(html.slice(html.indexOf('aria-label="What to do next"'))).toContain(
      "<b>Assess the United States (FDA) market</b>",
    );
  });
});

describe("Home for every persona (D1.6)", () => {
  const home = (persona = "admin", extra: Partial<WorkspaceApi> = {}) =>
    render(<HomeSection heading={{ current: null }} />, api({ persona, ...extra }));

  it("on the sample shows a slim Continue-the-story banner, not a second retelling of the story", () => {
    resources.data[ONE_STORY_PATH] = { sample: run(3), yours: null };
    for (const persona of ["admin", "regulatory", "handler", "executive"]) {
      const html = home(persona);
      expect(html).toContain('class="uw-card uw-home-banner"');
      expect(html).toContain("Step 4 of 10: Reportable?");
      expect(html).toContain("Continue the story");
      expect(html).not.toContain("Review this sample event");
    }
  });

  it("on your data leads with the most urgent complaint and what the file did not say", () => {
    const yours: StoryRun = {
      ...run(1),
      run: "yours",
      market: null,
      market_label: null,
      complaint: { ...run(1).complaint, ref: "FAC-1001", serious_injury: true, description: "It burned her hand." },
      needs: [{ fact: "COUNTRY", label: "Incident country", message: "", rule: "21 CFR 803; EU MDR Art. 87" }],
    };
    resources.data[ONE_STORY_PATH] = { sample: run(10), yours };
    const html = home("admin", { dataSource: IMPORTED_SOURCE });
    expect(html).toContain("FAC-1001 is a serious injury with no incident country.");
    expect(html).toContain("What your file did not say");
    expect(html).toContain("Incident country");
    expect(html).toContain("Asked on the complaint page: 21 CFR 803");
    expect(html).toContain("Walk it through · step 2 of 10");
  });

  it("shows a Story complete card once the ten steps are done", () => {
    resources.data[ONE_STORY_PATH] = { sample: run(10), yours: null };
    expect(home()).toContain("Story complete · SAMPLE-RV-11");
  });

  it("draws the trend card with observed and expected bars, and each tile opens its own list", () => {
    resources.data[ONE_STORY_PATH] = { sample: run(3), yours: null };
    resources.data[trendPath("version").split("?")[0]] = {
      items: [
        {
          key: "o",
          name: "OrbitCare 300 Rev B",
          product: { id: "o" },
          recent: 9,
          expected: 0.97,
          ratio: 9.3,
          result: "SIGNIFICANT",
          lots: [],
        },
      ],
    };
    const html = home();
    expect(html).toContain("OrbitCare 300 Rev B: 9 complaints against 1.0 expected (9.3×)");
    expect(html.match(/class="uw-bar-fill/g)).toHaveLength(2);
    expect(SERVER_VIEWS[OVERDUE_VIEW].code).toBe("overdue");
    expect(OVERDUE_PATH).toContain("view=overdue");
    delete resources.data[trendPath("version").split("?")[0]];
  });
});
