// 0.10.82, round D1 "One story": the record pages and Home, rendered from the server's answers.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ComplaintPage } from "./sections/ComplaintPage";
import { ONE_STORY_PATH, type StoryRun } from "./oneStory";
import { eventPath } from "./oversight";
import { rv11 } from "../../test/rv11";

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
