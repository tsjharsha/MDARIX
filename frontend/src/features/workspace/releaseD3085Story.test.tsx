// 0.10.85, first of round D3 (the owner's report on live 0.10.84): Getting started's story always works.
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StoryView } from "./sections/OneStory";
import { NavRail } from "./HybridShell";
import { ONE_STORY_PATH, openStep, takeMarkProblem, visited, type StoryRun } from "./oneStory";
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
      <StoryView story={{ sample: run, yours: null }} />
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
    expect(html).toContain("1 of 10 completed");
    expect(html).toMatch(/class="uw-os-step is-earlier"[^>]*title="Done earlier by your team"/);
    expect(html.match(/class="uw-os-s">Completed</g)).toHaveLength(1);
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
    const run = runAt("sample", 8);
    await openStep(run, 8, vi.fn());
    // 0.10.88: the mark is saved once Records has loaded that complaint's record.
    await visited({ step: "records", complaintId: run.complaint.id });
    const body = JSON.parse(String((fetch.mock.calls[0] as unknown as [string, RequestInit])[1].body));
    expect(body).toEqual({ run: "sample", step: "records", complaint_id: run.complaint.id });
    expect(takeMarkProblem()).toContain("The story now follows OS-1002.");
    expect(takeMarkProblem()).toBeNull();
  });

  it("shows the open screen as a tab of its own when the persona's tabs do not list it", () => {
    const bar = renderToStaticMarkup(
      <NavRail
        tabs={["start", "home", "trends", "records"]}
        current="complaints"
        open={vi.fn()}
        personaLabel="Executive"
      />,
    );
    expect(bar).toMatch(
      /class="uw-tab is-extra" aria-current="page" title="Opened from Getting started or a link: not one of Executive&#x27;s tabs">.*?<span class="uw-tab-label">Complaints</,
    );
    const listed = renderToStaticMarkup(<NavRail tabs={["start", "home"]} current="home" open={vi.fn()} />);
    expect(listed).not.toContain("is-extra");
  });
});

describe("Getting started is the walkthrough first (owner, 5 Nov 2026)", () => {
  it("renders the walkthrough, then the three cards and the collapsed settings (0.10.87)", () => {
    const page = gettingStarted.slice(gettingStarted.lastIndexOf('<div className="uw-gs">'));
    expect(page.indexOf("<OneStory heading={heading} />")).toBeLessThan(page.indexOf("<ExploreCards"));
    expect(page.indexOf("<ExploreCards")).toBeLessThan(page.indexOf("<TrialSettings"));
    expect(gettingStarted).not.toContain("More ways to explore");
  });
});

describe("the step list tells a screen reader which steps are not needed (0.10.88, DEV-10)", () => {
  beforeEach(stubWindow);
  afterEach(() => vi.unstubAllGlobals());

  it("names a step skipped by a not-reportable conclusion as not needed, not as a step still to do", () => {
    const run = { ...runAt("sample", 8), conclusion: "NOT_REPORTABLE" } as StoryRun;
    run.steps = run.steps.map((step, index) =>
      index >= 4 && index <= 7 ? { ...step, done: false, skipped: true } : step,
    );
    // 0.10.87's walkthrough says each step's state in words inside its button.
    const rail = view({}, run).match(/aria-label="Walkthrough steps">(.*?)<\/ol>/)?.[1] ?? "";
    const form = rail.split("<button").find((item) => item.includes(">Form<")) ?? "";
    expect(form).toMatch(/>Not needed</);
  });
});

describe("a triage not needed (0.10.88, DEV-10)", () => {
  beforeEach(stubWindow);
  afterEach(() => vi.unstubAllGlobals());

  it("says the complaint was not flagged for triage, not that a conclusion was signed", () => {
    // The card of step 3 (0.10.93), as shown when it is selected; the server says why it is not needed.
    const run = { ...runAt("yours", 2), current: 2 };
    run.steps = run.steps.map((step, index) =>
      index === 2 ? { ...step, done: false, skipped: true, note: "Not needed: not flagged for triage" } : step,
    );
    const html = renderToStaticMarkup(
      <WorkspaceContext.Provider value={workspace()}>
        <StoryView story={{ sample: null, yours: run }} />
      </WorkspaceContext.Provider>,
    );
    expect(html).toContain("Not needed: not flagged for triage");
    expect(html).not.toContain("the signed conclusion is");
  });
});
