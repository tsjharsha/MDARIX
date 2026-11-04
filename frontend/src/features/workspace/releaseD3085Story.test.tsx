// 0.10.85, first of round D3 (the owner's report on live 0.10.84): Getting started's story always works.
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StoryView } from "./sections/OneStory";
import { TabBar } from "./HybridShell";
import { ONE_STORY_PATH, openStep, takeMarkProblem, type StoryRun } from "./oneStory";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import gettingStarted from "./sections/GettingStarted.tsx?raw";
import { SAMPLE_SOURCE } from "./complaintList";

const LABELS = ["The call", "Triage", "Tree", "Decide", "Form", "Fill", "Approval", "Submit", "Records", "Trends"];
const runAt = (run: "sample" | "yours", current: number): StoryRun => ({
  run,
  complaint: {
    id: `${run}-id`,
    ref: "SAMPLE-RV-11",
    description: "Its SpO2 read 4 to 6 points high.",
    product_id: "pulse",
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

const workspace = (extra: Partial<WorkspaceApi> = {}) =>
  ({
    session: { business_permissions: [], persona: "admin", current_tenant: { tenant_name: "Test" } },
    persona: "admin",
    open: vi.fn(),
    notify: vi.fn(),
    work: {},
    dataSource: SAMPLE_SOURCE,
    ...extra,
  }) as unknown as WorkspaceApi;

const stubWindow = () =>
  vi.stubGlobal("window", {
    location: { pathname: "/app/getting-started", search: "", hash: "", origin: "https://mdarix.test" },
    localStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
    sessionStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
    dispatchEvent: () => true,
  });

const view = (extra: Partial<WorkspaceApi>, run = runAt("sample", 1)) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider value={workspace(extra)}>
      <StoryView story={{ sample: run, yours: null }} trends={[]} />
    </WorkspaceContext.Provider>,
  );

describe("The story always works (owner report on 0.10.84)", () => {
  beforeEach(stubWindow);
  afterEach(() => vi.unstubAllGlobals());

  it("flags a step the team did out of order, unticked, and counts only the ticks", () => {
    // The owner's screen: step 1 current, step 2 not done, step 3 "Tree" signed earlier by the team.
    const run = runAt("sample", 1);
    run.steps[2] = { ...run.steps[2], done: false, earlier: true };
    const html = view({}, run);
    expect(html).toContain("1 of 10 done");
    expect(html).toMatch(/class="uw-os-step is-earlier"[^>]*title="Done earlier by your team"/);
    expect(html.match(/aria-label="done"/g)).toHaveLength(1);
  });

  it("says who takes a step this person's role cannot open, with the main button disabled and its reason", () => {
    const html = view({ canOpen: (section: string) => section !== "Complaint" });
    expect(html).toContain("does this step: your role cannot open its screen");
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*aria-describedby="uw-os-closed"/);
    // Where the role may open it, the button works.
    expect(view({ canOpen: () => true })).not.toContain("your role cannot open");
  });

  it("opens the step's screen at once, without waiting for the mark to be saved", async () => {
    // The mark's request never answers (a busy server): the screen still opens.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => undefined)),
    );
    const open = vi.fn();
    void openStep(runAt("sample", 0), 0, open);
    await Promise.resolve();
    expect(open).toHaveBeenCalledWith("Complaint", expect.stringContaining("SAMPLE-RV-11"));
    expect(ONE_STORY_PATH).toBe("/api/v1/trial/one-story");
  });

  it("names the complaint the screen showed in the mark, and keeps a refusal for Getting started", async () => {
    const fetch = vi.fn(async () =>
      Response.json({ detail: { code: "STORY_MOVED", message: "The story now follows OS-1002." } }, { status: 409 }),
    );
    vi.stubGlobal("fetch", fetch);
    vi.stubGlobal("window", { setTimeout, clearTimeout });
    const run = runAt("sample", 0);
    await openStep(run, 0, vi.fn());
    const body = JSON.parse(String((fetch.mock.calls[0] as unknown as [string, RequestInit])[1].body));
    expect(body).toEqual({ run: "sample", step: "call", complaint_id: run.complaint.id });
    expect(takeMarkProblem()).toContain("The story now follows OS-1002.");
    expect(takeMarkProblem()).toBeNull();
  });

  it("shows the open screen as a tab of its own when the persona's tabs do not list it", () => {
    const bar = renderToStaticMarkup(
      <TabBar
        tabs={["start", "home", "trends", "records"]}
        current="complaints"
        open={vi.fn()}
        personaLabel="Executive"
      />,
    );
    expect(bar).toMatch(
      /class="uw-tab is-extra" aria-current="page" title="Opened from Getting started or a link: not one of Executive&#x27;s tabs">Complaints/,
    );
    const listed = renderToStaticMarkup(<TabBar tabs={["start", "home"]} current="home" open={vi.fn()} />);
    expect(listed).not.toContain("is-extra");
  });
});

describe("More ways to explore: one compact card (the approved design)", () => {
  it("offers the three parts and one quiet line, not the chapters' wall of main buttons", () => {
    const more = gettingStarted.slice(gettingStarted.indexOf("<summary>More ways to explore</summary>"));
    const card = more.slice(0, more.indexOf("</details>"));
    expect(card).toContain("uw-os-parts");
    expect(card).not.toContain("<Entrance");
    expect(card).not.toContain("{body}");
    expect(card).toContain("The ten chapters, your trial");
    for (const part of ["A new urgent call", "A rising problem", "Approve as a colleague"])
      expect(gettingStarted).toContain(part);
  });
});
