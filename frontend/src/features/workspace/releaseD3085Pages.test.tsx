// 0.10.85, round D3 "Polish to 9.5": the record pages, rendered from the server's answers.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ComplaintPage } from "./sections/ComplaintPage";
import { ONE_STORY_PATH, type StoryRun } from "./oneStory";
import { eventPath } from "./oversight";
import { rv11 } from "../../test/rv11";
import { NewRecordsSection } from "./sections/Records";
import { TrendHeroes } from "./sections/TrendCheck";
import { SignalInbox } from "./sections/SignalInbox";
import { DEFAULT_SIGNAL_FILTERS } from "./signals";
import type { TrendBoard, TrendItem } from "./signalAi";
import { IMPORTED_SOURCE, SAMPLE_SOURCE } from "./complaintList";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    const value = (path && resources.data[path.split("?")[0]]) ?? null;
    return { state: "ready", data: value, reload: () => undefined };
  },
}));

beforeEach(() => {
  resources.data = {};
});

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

const LABELS = ["The call", "Triage", "Tree", "Decide", "Form", "Fill", "Approval", "Submit", "Records", "Trends"];
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

describe("D3.3 the complaint page is a record with a hero", () => {
  it("leads with the reporter's words, the harm, one clock line and one Next step; the rest folds", () => {
    resources.data[eventPath("SAMPLE-RV-11")] = rv11();
    const html = render(<ComplaintPage tab="Summary?ref=SAMPLE-RV-11" />);
    const hero = html.slice(html.indexOf('class="uw-card uw-highlights"'), html.indexOf("</header>"));
    expect(hero).toMatch(/<blockquote>“Biomedical engineering/);
    expect(hero).toContain("No harm reported");
    expect(hero.match(/ms-chip-deadline/g)).toHaveLength(1);
    expect(hero).toContain('aria-label="Next step"');
    // One main button on the page, in the hero.
    expect(html.match(/class="ac-primary"/g)).toHaveLength(1);
    expect(hero).toContain('class="ac-primary"');
    // The checklist, who signs and the service work fold; the words are not said twice.
    expect(html).toMatch(/<details class="uw-rec-part uw-cp-fold"><summary><h2>Each step, and who signs it/);
    expect(html).toMatch(/<details class="uw-card uw-card-pad uw-rail-signs uw-cp-fold"/);
    expect(html).not.toContain("<dt>What happened</dt>");
    expect(html).not.toContain("Also known as");
  });

  it("folds the triage form while the story is on another step", () => {
    const view = rv11();
    // Triage is the record's next step.
    view.summary.next_action = {
      label: "Complete the triage record",
      detail: "",
      opens: {
        label: "",
        target: { section: "Complaints", tab: "Triage", record: { type: "complaint", id: view.event.complaint_id } },
      },
    } as any;
    resources.data[eventPath("SAMPLE-RV-11")] = view;
    resources.data[ONE_STORY_PATH] = { sample: run(0), yours: null };
    const folded = render(<ComplaintPage tab="Summary?ref=SAMPLE-RV-11" />);
    expect(folded).toContain("<summary>Triage record: not complete yet</summary>");
    resources.data[ONE_STORY_PATH] = { sample: run(1), yours: null };
    expect(render(<ComplaintPage tab="Summary?ref=SAMPLE-RV-11" />)).not.toContain("Triage record: not complete yet");
  });
});

describe("D3.4 Records opens on your latest record", () => {
  it("leads with the record, who signed, when and what it means; inspection readiness sits under it", () => {
    resources.data["/api/v1/oversight/latest-signed"] = {
      record: {
        what: "United States (FDA) conclusion: reportable",
        signed_at: "2026-11-02",
        signed_at_time: "2026-11-02T09:02:00Z",
        signed_by: "Asha Menon",
        meaning: "SIGNED_REPORTABLE",
        meaning_label: "signed reportable",
        complaint: { id: "c-rv11", ref: "SAMPLE-RV-11" },
        investigation: null,
      },
    };
    const html = render(
      <NewRecordsSection />,
      api({ session: { user_id: "u1", business_permissions: ["data.export"] } as WorkspaceApi["session"] }),
    );
    expect(html.indexOf("Your latest record")).toBeLessThan(html.indexOf("Inspection readiness"));
    expect(html).toContain("Asha Menon");
    expect(html).toContain("signed reportable");
    expect(html).toContain("Download the decision record (PDF)");
    // Not folded behind "All records: ...".
    expect(html).not.toMatch(/<details[^>]*><summary>All records/);
  });

  it("with nothing signed yet still opens on the latest record's place, never on the readiness dial", () => {
    resources.data["/api/v1/oversight/latest-signed"] = { record: null };
    const html = render(<NewRecordsSection />);
    expect(html).toContain("No signed record yet");
    expect(html.indexOf("No signed record yet")).toBeLessThan(html.indexOf("Inspection readiness"));
  });
});

describe("D3.5 Trends in plain words, with a hero", () => {
  const item = (extra: Partial<TrendItem>): TrendItem =>
    ({
      key: "k",
      product: { id: "p", business_id: null, identifier: "SAMPLE-ORBIT-300", name: "OrbitCare 300" },
      product_version: { id: "v", business_id: null, version_identifier: "Rev B" },
      problem: null,
      name: "OrbitCare 300 Rev B",
      recent: 9,
      recent_days: 30,
      history: 6,
      history_days: 180,
      expected: 0.97,
      p_value: 0.0001,
      p_adjusted: 0.0004,
      groups_tested: 2,
      ratio: 9.3,
      result: "SIGNIFICANT",
      label: "",
      sentence: "",
      recent_complaints: [{ id: "c", business_id: null }],
      open_signals: [],
      basis: "UNITS",
      baseline: "PREVIOUS_VERSION",
      baseline_name: "OrbitCare 300 Rev A",
      ...extra,
    }) as TrendItem;
  const board = (items: TrendItem[]) =>
    ({
      grouping: "version",
      recent_days: 30,
      history_days: 180,
      min_complaints: 3,
      summary: {
        groups: items.length,
        complaints_counted: 13,
        significant: 1,
        elevated: 0,
        steady: 0,
        too_few: 1,
        short_history: 0,
      },
      items,
    }) as unknown as TrendBoard;
  const yours = item({
    key: "y",
    product: { id: "b", business_id: null, identifier: "BREEZE-50", name: "BreezeMist 50" },
    name: "BreezeMist 50 Rev B",
    recent: 4,
    result: "TOO_FEW",
    p_value: null,
    ratio: null,
  });

  it("answers per rising group with observed, expected and the version before, the method folded", () => {
    const html = render(<TrendHeroes board={board([item({}), yours])} action={() => null} source={SAMPLE_SOURCE} />);
    for (const bar of ["Observed", "Expected", "Version before"]) expect(html).toContain(`<span>${bar}</span>`);
    expect(html).toMatch(/<details class="uw-more uw-trend-how"><summary>How we compared<\/summary>/);
    expect(html).not.toContain("BreezeMist");
  });

  it("on your data never shows the sample's rise, and says what a short history can show", () => {
    const html = render(<TrendHeroes board={board([item({}), yours])} action={() => null} source={IMPORTED_SOURCE} />);
    expect(html).not.toContain("OrbitCare");
    expect(html).toContain("Too early to compare");
    expect(html).toContain("never called a rise");
    expect(html).toContain("BreezeMist 50 Rev B: 4");
  });

  it("names Trends to review and Raise a trend, puts the title before SIG0…, and offers no AI filter in a trial", () => {
    resources.data["/api/v1/triage/signals"] = {
      items: [
        {
          id: "s1",
          business_id: "SIG000001",
          title: "OrbitCare 300 Rev B: pressure alarms",
          origin: "THRESHOLD_RULE",
          status: "NEW",
        },
      ],
      total: 1,
      page: 1,
      page_size: 25,
    };
    const html = render(
      <SignalInbox initialFilters={DEFAULT_SIGNAL_FILTERS} initialSignal={null} />,
      api({ session: { user_id: "u1", business_permissions: ["signal.triage"] } as WorkspaceApi["session"] }),
    );
    expect(html).toContain("Trends to review");
    expect(html).toContain("Raise a trend");
    expect(html).not.toContain("Signal inbox");
    expect(html).not.toContain("Suggested by AI");
    expect(html.indexOf("OrbitCare 300 Rev B: pressure alarms")).toBeLessThan(html.indexOf("SIG000001"));
  });
});
