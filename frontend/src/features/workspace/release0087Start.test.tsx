// 0.10.87, Getting started v2 (the owner's specification, 5 Nov 2026): one walkthrough card with one count and one
// progress bar, three cards to explore at one's own pace, and one collapsed "Sample data & trial settings".
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StoryView, harmText, pickOn, pickView, practiceLine, summaryOf } from "./sections/OneStory";
import { GettingStartedSection } from "./sections/GettingStarted";
import { ExploreCards, GuideLinks, TrialSettings } from "./sections/GettingStartedMore";
import { openStep, type StoryRun } from "./oneStory";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { IMPORTED_SOURCE, SAMPLE_SOURCE } from "./complaintList";
import { SAMPLE_REMOVAL_PATH } from "./sections/RemoveSample";

const reads = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    const data = (path && reads.data[path.split("?")[0]]) ?? null;
    return { state: data ? "ready" : "loading", data, reload: () => undefined };
  },
}));

const LABELS = [
  "Review the call",
  "Triage",
  "Assess reportability",
  "Sign conclusion",
  "Prepare report",
  "Complete details",
  "Approve report",
  "Record submission",
  "Review records",
  "Explore trends",
];
const runAt = (run: "sample" | "yours", current: number, extra: Partial<StoryRun> = {}): StoryRun => ({
  run,
  complaint: {
    id: `${run}-id`,
    ref: run === "sample" ? "SAMPLE-RV-11" : "OS-1002",
    description:
      run === "sample"
        ? "Biomedical engineering checked a monitor against a reference oximeter: its SpO2 read 4 to 6 points high on two patients. No harm was reported. The monitor is out of use and sent for service."
        : "The pump alarmed during set-up.",
    product_id: "p1",
    product_name: run === "sample" ? "PulseWatch 410" : "Infusion pump",
    serious_injury: false,
    death: false,
    harm: run === "sample" ? "NONE" : null,
    service_status: run === "sample" ? "IN_PROGRESS" : null,
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
  ...extra,
});

const OWNER = { allowed_menu: ["home", "products", "investigations"], business_permissions: ["records.write"] };
const api = (extra: Partial<WorkspaceApi> = {}) =>
  ({
    session: OWNER,
    persona: "admin",
    work: { products: [], setInvestigationId: vi.fn(), refreshProducts: vi.fn() },
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
    dataSource: SAMPLE_SOURCE,
    ...extra,
  }) as unknown as WorkspaceApi;
const render = (node: ReactNode, value: WorkspaceApi = api()) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);
const count = (html: string, text: string) => html.split(text).length - 1;

const STATUS = "/api/v1/trial/status";
const trialStatus = (sample: number, owner = true) => ({
  is_trial: true,
  is_owner: owner,
  expires_at: "2026-12-04T00:00:00Z",
  days_left: 30,
  limits: { users: 5, rows: 5000, file_bytes: 2_000_000 },
  usage: { users: 1, rows: 0 },
  sample: { products: sample ? 3 : 0, complaints: sample },
  own_data: { products: 0, lots: 0, complaints: 0 },
});

beforeEach(() => {
  reads.data = {};
  vi.stubGlobal("window", {
    location: { pathname: "/app/getting-started", search: "", hash: "", origin: "https://mdarix.test" },
    localStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
    sessionStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
    dispatchEvent: () => true,
    setTimeout,
    clearTimeout,
  });
});
afterEach(() => vi.unstubAllGlobals());

describe("the walkthrough card renders the progress the server reports", () => {
  it("has one title, one practice line, one count and one progress bar", () => {
    const html = render(<StoryView story={{ sample: runAt("sample", 3), yours: null }} />);
    expect(count(html, "<h1")).toBe(1);
    expect(html).toContain("Getting started</h1>");
    expect(html).toContain("Follow one sample complaint from first call to reporting.");
    expect(count(html, practiceLine(true))).toBe(1);
    expect(practiceLine(true)).toBe("Fictional data · Trial outputs are practice records · Human sign-off required");
    expect(html).toContain("Your sample walkthrough</h2>");
    expect(count(html, ">Sample data<")).toBe(1);
    expect(count(html, "of 10 completed")).toBe(2); // the count, and the bar's own text for screen readers
    expect(html).toContain("3 of 10 completed</span>");
    expect(count(html, 'role="progressbar"')).toBe(1);
    expect(html).toMatch(/role="progressbar"[^>]*aria-valuenow="3"/);
    // The ten steps in the owner's words, three completed (said in words, not by colour), the fourth next.
    for (const label of LABELS) expect(html).toContain(`</span>${label}</span>`);
    expect(count(html, 'class="uw-os-s">Completed<')).toBe(3);
    expect(count(html, 'aria-current="step"')).toBe(1);
    expect(html).toMatch(/aria-current="step" aria-pressed="true"[^>]*>.*Sign conclusion/);
    // The large hero and the miniature browser window are gone.
    expect(html).not.toContain("uw-os-mini");
    expect(html).not.toContain("One complaint, from the first call to the signed report");
  });

  it("shows the step's label, heading, instruction, complaint summary and one main button", () => {
    const html = render(<StoryView story={{ sample: runAt("sample", 0), yours: null }} />);
    expect(html).toContain("Step 1 · Review the call");
    expect(html).toContain("Start with the hospital&#x27;s report");
    expect(html).toContain("Read the event and check the available facts.");
    expect(count(html, "ac-primary")).toBe(1);
    expect(html).toContain("Open sample complaint");
    // The summary is read from the record: its first sentence only, never the whole narrative.
    expect(html).toContain("SAMPLE-RV-11</b>");
    expect(html).toContain("its SpO2 read 4 to 6 points high on two patients.");
    expect(html).not.toContain("The monitor is out of use");
    expect(html).toContain("<dt>Device</dt><dd>PulseWatch 410</dd>");
    expect(html).toContain("<dt>Reported harm</dt><dd>None reported</dd>");
    expect(html).toContain("<dt>Device status</dt><dd>In service</dd>");
    // A quiet hint names the step after it.
    expect(html).toContain("step 2, Triage");
  });

  it("says skipped steps as not needed, and a finished walkthrough as complete", () => {
    const run = runAt("sample", 10, {
      conclusion: "NOT_REPORTABLE",
      steps: LABELS.map((label, index) => ({
        key: label,
        label,
        done: index < 4 || index >= 8,
        skipped: index >= 4 && index < 8,
      })),
    });
    const html = render(<StoryView story={{ sample: run, yours: null }} />);
    expect(html).toContain("6 of 10 completed · 4 not needed");
    expect(count(html, 'class="uw-os-s">Not needed<')).toBe(4);
    expect(html).toMatch(/aria-valuenow="10"/);
    expect(html).toContain("The sample walkthrough is complete");
    expect(html).toContain("Do the same with your data");
  });
});

describe("picking a step previews it and never completes it", () => {
  it("previews another step, keeps the real next step marked next, and resumes on it", () => {
    const run = runAt("sample", 1);
    expect(pickView(run, null)).toEqual({ finished: false, selected: 1, previewing: false });
    expect(pickView(run, 5)).toEqual({ finished: false, selected: 5, previewing: true });
    // Clicking the next step resumes it; any other step is a preview.
    expect(pickOn(run, 1)).toBeNull();
    expect(pickOn(run, 5)).toBe(5);
    // A finished walkthrough's step picked again is a preview of it, with the finale one click back.
    expect(pickView(runAt("sample", 10), 3)).toEqual({ finished: false, selected: 3, previewing: true });
  });

  it("marks nothing while it shows the walkthrough: a mark is sent only by a step's main button", async () => {
    const fetch = vi.fn(async () => Response.json({}));
    vi.stubGlobal("fetch", fetch);
    render(<StoryView story={{ sample: runAt("sample", 1), yours: null }} />);
    expect(fetch).not.toHaveBeenCalled();
    // The main button of step 1 opens the sample complaint by its reference, in this tenant, and sends its mark.
    const open = vi.fn();
    await openStep(runAt("sample", 0), 0, open);
    expect(open).toHaveBeenCalledWith("Complaint", "Summary?ref=SAMPLE-RV-11");
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

describe("facts the record does not give stay missing", () => {
  it("never turns missing harm into None reported", () => {
    const blank = runAt("yours", 0).complaint;
    expect(harmText(blank)).toBeNull();
    expect(harmText({ ...blank, harm: "NONE" })).toBe("None reported");
    expect(harmText({ ...blank, harm: undefined, serious_injury: true })).toBe("Serious injury reported");
    // An older server without the field: a record without harm is not "None reported" either.
    expect(harmText({ ...blank, harm: undefined })).toBeNull();
    const html = render(
      <StoryView story={{ sample: null, yours: runAt("yours", 0) }} />,
      api({ dataSource: IMPORTED_SOURCE }),
    );
    expect(html).toContain('<dt>Reported harm</dt><dd><span class="ac-muted">Not recorded</span></dd>');
    expect(html).not.toContain("None reported");
    expect(html).not.toContain("Device status");
  });

  it("runs the same card on your own data, without calling it fictional", () => {
    const html = render(
      <StoryView story={{ sample: runAt("sample", 10), yours: runAt("yours", 0) }} />,
      api({ dataSource: IMPORTED_SOURCE }),
    );
    expect(html).toContain("Your data walkthrough</h2>");
    expect(html).toContain(">Your data<");
    expect(html).toContain("Follow your most urgent complaint from first call to reporting.");
    expect(html).toContain("Trial outputs are practice records · Human sign-off required");
    expect(html).not.toContain("Fictional data");
    expect(html).toContain("Open OS-1002");
  });

  it("summarises in one sentence, and cuts a long one at a word", () => {
    expect(summaryOf("One. Two.")).toBe("One.");
    expect(summaryOf(null)).toBeNull();
    const long = summaryOf(`${"word ".repeat(40)}end.`)!;
    expect(long.length).toBeLessThanOrEqual(138);
    expect(long.endsWith("word…")).toBe(true);
  });
});

describe("loading, failure, refusal and a removed sample", () => {
  it("says it is reading, never an empty walkthrough", () => {
    const html = render(<StoryView story={null} state="loading" />);
    expect(html).toContain("Reading your walkthrough…");
    expect(html).toContain('aria-busy="true"');
    expect(html).not.toContain("No complaint to follow yet");
    expect(html).not.toContain("Fictional data");
  });

  it("offers Try again when the read failed, and says a refusal plainly", () => {
    const failed = render(<StoryView story={null} state="error" onRetry={vi.fn()} />);
    expect(failed).toContain("The walkthrough could not be loaded");
    expect(failed).toContain(">Try again</button>");
    const refused = render(<StoryView story={null} state="forbidden" />);
    expect(refused).toContain("Your role cannot read the walkthrough");
  });

  it("invents no complaint once the sample is removed, and repeats no import button", () => {
    const html = render(<StoryView story={{ sample: null, yours: null }} />);
    expect(html).toContain("No complaint to follow yet");
    expect(html).not.toContain("SAMPLE-");
    expect(html).not.toContain("ac-primary");
    reads.data[STATUS] = trialStatus(0);
    const settings = render(
      <TrialSettings
        trial={trialStatus(0) as never}
        startOpen
        allowed={() => true}
        onOpen={vi.fn()}
        onRestarted={vi.fn()}
        onRemoved={vi.fn()}
        onNextSteps={vi.fn()}
      />,
    );
    expect(settings).toContain("The sample data is not in this trial");
    expect(settings).not.toContain("Restart the sample story");
    expect(settings).not.toContain("Remove the sample data");
  });
});

describe("explore at your own pace", () => {
  const cards = (owner: boolean) =>
    render(
      <ExploreCards
        owner={owner}
        onTeam={vi.fn()}
        onWorkflows={vi.fn()}
        onFeedback={vi.fn()}
        onNextSteps={vi.fn()}
        chapters={[]}
      />,
    );

  it("has three cards; inviting is the trial owner's", () => {
    const owner = cards(true);
    expect(owner).toContain("Explore at your own pace</h2>");
    expect(count(owner, 'class="uw-gs-card"')).toBe(3);
    expect(owner).toContain("Try review and approval with colleagues.");
    expect(owner).toContain("Manage team");
    const colleague = cards(false);
    expect(colleague).not.toContain("Manage team");
    expect(colleague).toContain("View team");
    expect(colleague).toContain("The trial owner invites and manages colleagues.");
    // No card is a main button, and the resources show only when asked for.
    expect(owner).not.toContain("ac-primary");
    expect(owner).toContain("Choose a focus");
    expect(owner).toMatch(/aria-expanded="false"[^>]*>Open resources/);
    expect(owner).not.toContain("Free trial user guide");
  });

  it("groups the guides, support, feedback, the pilot page and the demo as quiet links", () => {
    const html = render(
      <GuideLinks support="help@mdarix.test" onFeedback={vi.fn()} onNextSteps={vi.fn()} chapters={[]} />,
    );
    for (const text of [
      'href="/help/trial-guide"',
      'href="/help/user-guide?navigation=new"',
      'href="mailto:help@mdarix.test"',
      "Share feedback",
      "Next steps: from trial to pilot",
      "Book a one-to-one demo",
    ])
      expect(html).toContain(text);
    expect(html).not.toContain("ac-primary");
  });

  it("keeps the library of other workflows one click away, with the chapters and the audit focus", () => {
    reads.data[STATUS] = trialStatus(37);
    reads.data["/api/v1/trial/story"] = {
      acted: 0,
      total: 10,
      next: "ROUTINE_COMPLAINTS",
      chapters: [
        {
          code: "ROUTINE_COMPLAINTS",
          number: 1,
          title: "Routine complaints",
          promise: "Close a routine complaint.",
          pain: "Inspectors cite slow closure.",
          finding: { text: "", state: "NOT_SET" },
          acted: { done: false, count: 0 },
          opens: { section: "Complaints", tab: "All" },
        },
      ],
    };
    const html = render(<GettingStartedSection focus="Other workflows" />);
    expect(html).toContain("Explore other workflows</h1>");
    expect(html).toContain("Routine complaints");
    expect(html).toContain("Close a routine complaint");
    // Restarting and removing the sample are not here: only in Getting started's collapsed settings.
    expect(html).not.toContain("Restart the sample story");
    expect(html).not.toContain("Remove the sample data");
  });
});

describe("one collapsed section holds the sample and trial controls", () => {
  const preview = { sample: { products: 3, complaints: 37 }, work_on_sample: 0, own_records_affected: 0 };

  it("is collapsed by default, and shows nothing destructive on the page until opened", () => {
    reads.data[STATUS] = trialStatus(37);
    reads.data[SAMPLE_REMOVAL_PATH] = { ...preview, has_sample: true, is_owner: true };
    const html = render(<GettingStartedSection />);
    expect(html).toContain("Sample data &amp; trial settings</summary>");
    expect(html).not.toMatch(/<details id="trial-settings"[^>]* open=""/);
    expect(html).not.toContain("Restart the sample story");
    expect(html).not.toContain("Remove the sample data");
    // The countdown and the import action stay in the shell, not in the page body.
    expect(html).not.toContain("days left");
    expect(html).not.toContain("Import your data</button>");
  });

  it("opened from a link, holds the explanation, the trial's dates and each control once, with its confirmation", () => {
    reads.data[STATUS] = trialStatus(37);
    reads.data[SAMPLE_REMOVAL_PATH] = { ...preview, has_sample: true, is_owner: true };
    const html = render(<GettingStartedSection focus="About the sample data" />);
    expect(html).toMatch(/<details id="trial-settings"[^>]* open=""/);
    expect(html).toContain("What your sample data is, and why it looks like this");
    expect(html).toContain("Trial ends");
    // Each control once on the page: the restart's title and its one button; the removal behind its confirmation.
    expect(count(html, "Restart the sample story")).toBe(2);
    expect(count(html, "Remove the sample data<")).toBe(2);
    expect(html).toContain("I understand the sample data cannot be brought back.");
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>.*Remove the sample data/);
  });

  it("tells a colleague who may not restart or remove the sample, instead of hiding it silently", () => {
    reads.data[SAMPLE_REMOVAL_PATH] = { ...preview, has_sample: true, is_owner: false };
    const html = render(
      <TrialSettings
        trial={trialStatus(37, false) as never}
        startOpen
        allowed={() => true}
        onOpen={vi.fn()}
        onRestarted={vi.fn()}
        onRemoved={vi.fn()}
        onNextSteps={vi.fn()}
      />,
    );
    expect(html).toContain("Only the person who started the trial can restart or remove the sample data.");
    expect(html).not.toContain(">Restart the sample story<");
  });
});
