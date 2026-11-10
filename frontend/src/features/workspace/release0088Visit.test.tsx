// 0.10.88, P0 of the review of 0.10.87: a story step ticked by its visit (the report, Records, Trends; 0.10.93: no
// longer the call)
// counts only once its own screen has loaded the story's record; a screen that failed to load ticks nothing.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ComplaintPage } from "./sections/ComplaintPage";
import { ReportPage } from "./sections/ReportsTab";
import { FinishedRecord } from "./sections/Records";
import { TrendCheck } from "./sections/TrendCheck";
import { ONE_STORY_PATH, openStep, takeMarkProblem, visited, type StoryRun, type Visit } from "./oneStory";
import { eventPath } from "./oversight";
import { REPORTS, type ReportDetail } from "./authorityReports";
import { rv11 } from "../../test/rv11";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    const value = (path && resources.data[path.split("?")[0]]) ?? null;
    return value instanceof Error
      ? { state: "error", data: null, error: value.message, code: value.name, requestId: "req-1", reload: () => {} }
      : { state: value ? "ready" : "loading", data: value, reload: () => undefined };
  },
}));
// What each screen tells the story: the record it shows, and whether its read succeeded. The hook's effect is the
// real ``visited`` once loaded (renderToStaticMarkup runs no effects).
const hook = vi.hoisted(() => ({ calls: [] as Array<{ visit: Visit; loaded: boolean }> }));
vi.mock("./oneStory", async (original) => ({
  ...(await original<typeof import("./oneStory")>()),
  useVisited: (visit: Visit, loaded: boolean) => void hook.calls.push({ visit, loaded }),
}));

const ORBIT = "SAMPLE-ORBIT-300";
const api = (shownTab?: string) =>
  ({
    session: { user_id: "u1", business_permissions: ["records.write", "signal.triage", "regulatory.review"] },
    work: { products: [{ id: "p-orbit", product_identifier: ORBIT, name: "OrbitCare" }], investigations: [] },
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
    persona: "admin",
    shownTab,
    reportTab: shownTab ? vi.fn() : undefined,
  }) as unknown as WorkspaceApi;
const render = (node: ReactNode, shownTab?: string) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={api(shownTab)}>{node}</WorkspaceContext.Provider>);

const run = (current: number): StoryRun => ({
  run: "sample",
  complaint: {
    id: "c-rv11",
    ref: "SAMPLE-RV-11",
    description: null,
    product_id: "p-orbit",
    serious_injury: false,
    death: false,
  },
  market: "US",
  market_label: "United States (FDA)",
  conclusion: "REPORTABLE",
  report_id: "r-rv11",
  report_stage: "DRAFT",
  needs: [],
  steps: Array.from({ length: 10 }, (_, index) => ({
    key: `s${index}`,
    label: `S${index}`,
    done: index < current,
    skipped: false,
  })),
  current,
  finished: false,
});

const report = {
  id: "r-rv11",
  kind: "INITIAL",
  complaint: {
    id: "c-rv11",
    ref: "SAMPLE-RV-11",
    complaint_identifier: "SAMPLE-RV-11",
    product_name: "OrbitCare",
    version: "Rev B",
    country: "US",
    description: "Reads high",
    aware_date: "2026-10-08",
    sample: true,
  },
  market: "US",
  market_label: "United States (FDA)",
  form: {
    code: "FDA_3500A",
    title: "Form FDA 3500A",
    version: "09/2025",
    authority: "FDA",
    source_document: "",
    clauses: [],
  },
  routes: [],
  state: "DRAFT",
  state_label: "Draft",
  next_step: "Next",
  steps: [{ state: "DRAFT", label: "Draft" }],
  deadline: { due_on: "2026-11-07", provisional: false, days_left: 6, overdue: false },
  assessment: null,
  case: null,
  sections: [],
  counts: {},
  status_labels: {},
  editable: true,
  snapshots: [],
  pending_snapshot: null,
  cannot_approve: [],
  submissions: [],
  request: null,
  parent_id: null,
  responses: [],
  note: null,
  follow_up_due_on: null,
  sample: true,
} as unknown as ReportDetail;

/** Each destination: the step that opens it, and the screen with its read failed or loaded. */
const STEPS: Array<{ name: string; index: number; screen: () => string; read: string; data: () => unknown }> = [
  {
    name: "step 6, the report page",
    index: 5,
    screen: () => render(<ReportPage id="r-rv11" onBack={() => undefined} />),
    read: `${REPORTS}/r-rv11`,
    data: () => report,
  },
  {
    name: "step 9, Records",
    index: 8,
    screen: () => render(<FinishedRecord reference="SAMPLE-RV-11" />),
    read: eventPath("SAMPLE-RV-11"),
    data: rv11,
  },
  {
    name: "step 10, Trends",
    index: 9,
    screen: () => render(<TrendCheck onOpenSignal={vi.fn()} />, `Trend check?product=${ORBIT}`),
    read: "/api/v1/triage/trends",
    data: () => ({ grouping: "version", items: [], summary: { groups: 0, complaints_counted: 0, significant: 0 } }),
  },
];

let fetch: ReturnType<typeof vi.fn>;
/** Render the screen, then run what its effect would: the real ``visited`` for each loaded report of it. */
const show = async (screen: () => string) => {
  hook.calls = [];
  screen();
  for (const call of hook.calls) if (call.loaded) await visited(call.visit);
  return hook.calls;
};
const marks = () =>
  fetch.mock.calls
    .filter(([path]) => String(path).endsWith(`${ONE_STORY_PATH}/marks`))
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)));

beforeEach(() => {
  resources.data = { [ONE_STORY_PATH]: { sample: null, yours: null }, "/api/v1/triage": { items: [] } };
  fetch = vi.fn(async () => Response.json({}));
  vi.stubGlobal("fetch", fetch);
  vi.stubGlobal("window", { setTimeout, clearTimeout, dispatchEvent: () => true });
});
afterEach(() => {
  vi.unstubAllGlobals();
  takeMarkProblem();
});

describe.each(STEPS)("$name ticks only once it has loaded", ({ index, screen, read, data }) => {
  it("posts nothing when opening the step: the screen saves the mark", async () => {
    const open = vi.fn();
    await openStep(run(index), index, open);
    expect(open).toHaveBeenCalledTimes(1);
    expect(marks()).toEqual([]);
  });

  it("posts no mark when its read fails (a server error), keeps the visit, and ticks once on the retry", async () => {
    await openStep(run(index), index, vi.fn());
    resources.data[read] = Object.assign(new Error("The server could not answer"), { name: "INTERNAL_ERROR" });
    const failed = await show(screen);
    expect(failed.length).toBeGreaterThan(0);
    expect(failed.every((call) => !call.loaded)).toBe(true);
    expect(marks()).toEqual([]);
    // Retry: the read now succeeds, and exactly one mark is saved, for the story's complaint.
    resources.data[read] = data();
    await show(screen);
    await show(screen);
    expect(marks()).toEqual([{ run: "sample", step: expect.any(String), complaint_id: "c-rv11" }]);
  });

  it("posts no mark while its read is still loading", async () => {
    await openStep(run(index), index, vi.fn());
    await show(screen);
    expect(marks()).toEqual([]);
  });
});

describe("a loaded screen of another record ticks nothing", () => {
  it("another complaint, another report, another product", async () => {
    for (const visit of [
      { step: "form", reportId: "r-other" },
      { step: "records", complaintId: "c-other" },
      { step: "trends", product: "OTHER-1" },
    ] as Visit[]) {
      const index = { form: 5, records: 8, trends: 9 }[visit.step];
      await openStep(run(index), index, vi.fn());
      await visited(visit);
      // Nor a screen of a different step.
      await visited(
        visit.step === "records" ? { step: "form", reportId: "r-rv11" } : { step: "records", complaintId: "c-rv11" },
      );
    }
    expect(marks()).toEqual([]);
  });

  it("the complaint page marks nothing: steps 1 and 2 read the case's records (0.10.93)", async () => {
    await openStep(run(0), 0, vi.fn());
    resources.data[eventPath("SAMPLE-RV-11")] = rv11();
    expect(await show(() => render(<ComplaintPage tab="Summary?ref=SAMPLE-RV-11" />))).toEqual([]);
    expect(marks()).toEqual([]);
  });

  it("names the step in a refusal, and keeps it for Getting started", async () => {
    fetch.mockImplementation(async () =>
      Response.json({ detail: { code: "STEP_NOT_YET", message: "Finish step 8 first." } }, { status: 409 }),
    );
    await openStep(run(8), 8, vi.fn());
    await visited({ step: "records", complaintId: "c-rv11" });
    expect(marks()).toHaveLength(1);
    expect(takeMarkProblem()).toContain("Finish step 8 first.");
  });
});
