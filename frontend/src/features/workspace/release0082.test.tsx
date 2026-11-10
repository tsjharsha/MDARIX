// 0.10.82, round D1 "One story" of the approved redesign: what shows on screen.
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { IMPORTED_SOURCE, SAMPLE_SOURCE } from "./complaintList";
import { runOf, shownRun, stepBlocker, stepPlace, type OneStory, type StoryRun } from "./oneStory";
import { StoryView, TrendBars } from "./sections/OneStory";
import { HomeSection } from "./sections/Home";
import { placeOf, recordPlace } from "../../app/linkTable";
import gettingStarted from "./sections/GettingStarted.tsx?raw";
import { TeamView, personaConfirmation } from "./sections/TrialTeam";
import { LoadChecklist, loadedObjects, type ImportTemplate } from "./sections/ImportData";
import type { ImportRun } from "./sections/ImportReports";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import type { TrendItem } from "./signalAi";

const LABELS = ["The case", "Classify", "Triage", "Tree", "Decide", "Form", "Approval", "Submit", "Records", "Trends"];
export const runAt = (run: "sample" | "yours", current: number, extra: Partial<StoryRun> = {}): StoryRun => ({
  run,
  complaint: {
    id: `${run}-id`,
    ref: run === "sample" ? "SAMPLE-RV-11" : "OS-1002",
    description: run === "sample" ? "Its SpO2 read 4 to 6 points high." : "The casing burned the child's hand.",
    product_id: run === "sample" ? "pulse" : "neb",
    serious_injury: run === "yours",
    death: false,
  },
  market: run === "sample" ? "US" : null,
  market_label: run === "sample" ? "United States (FDA)" : null,
  conclusion: null,
  report_id: null,
  report_stage: null,
  needs: [],
  steps: LABELS.map((label, index) => ({ key: label, label, done: index < current, skipped: false })),
  current,
  finished: current >= 10,
  ...extra,
});

export const workspace = (extra: Partial<WorkspaceApi> = {}) =>
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
  });

const trend = (name: string, product: string, recent: number, expected: number, result: string) =>
  ({ key: name, name, product: { id: product }, recent, expected, ratio: recent / expected, result }) as TrendItem;

describe("Getting started: one story of ten steps (D1.1-D1.4)", () => {
  beforeEach(stubWindow);
  afterEach(() => vi.unstubAllGlobals());
  const view = (story: OneStory, extra: Partial<WorkspaceApi> = {}) =>
    renderToStaticMarkup(
      <WorkspaceContext.Provider value={workspace(extra)}>
        <StoryView story={story} />
      </WorkspaceContext.Provider>,
    );

  it("has one title, one ten-step list with its Sample data label and one main button", () => {
    const html = view({ sample: runAt("sample", 3), yours: null });
    expect(html.match(/<h1/g)).toHaveLength(1);
    expect(html).toContain("Getting started</h1>");
    expect(html.match(/class="uw-os-step/g)).toHaveLength(10);
    expect(html).toContain(">Sample data<");
    expect(html).toContain("3 of 10 completed");
    // The step card is the next step from the saved record, and has exactly one main button.
    expect(html).toContain("Step 4 · Tree");
    expect(html.match(/ac-primary/g)).toHaveLength(1);
    expect(html).toContain("Open the decision tree");
    // One-word labels on the rail, so none wraps or is cut.
    for (const label of LABELS) expect(label.split(" ").length <= 2 && html.includes(`>${label}<`)).toBe(true);
  });

  it("after the sample's tenth step offers the same ten steps on your data", () => {
    const html = view({ sample: runAt("sample", 10), yours: runAt("yours", 0) });
    expect(html).toContain("The sample walkthrough is complete");
    expect(html).toContain("Do the same with your data");
    // The data switch on Your data shows that run, its label and its most urgent complaint.
    const yours = view({ sample: runAt("sample", 10), yours: runAt("yours", 0) }, { dataSource: IMPORTED_SOURCE });
    expect(yours).toContain(">Your data<");
    expect(yours).toContain("Your most urgent complaint: OS‑1002");
  });

  it("says which fact the import lacks, and opens the complaint page where it is asked", () => {
    const run = runAt("yours", 3, {
      needs: [{ fact: "COUNTRY", label: "Incident country", message: "", rule: "" }],
    });
    expect(stepBlocker(run, 3)).toContain("no incident country for OS-1002");
    expect(stepPlace(run, 3)).toEqual({ section: "Complaint", tab: "Summary?ref=OS-1002" });
    const html = view({ sample: null, yours: run });
    expect(html).toContain("The complaint page asks for it");
    expect(html).toContain("Open OS-1002");
  });

  it("opens each step's real screen with the record in place", () => {
    const run = runAt("sample", 4, { report_id: "r1" });
    // No story Case (classified in your QMS): steps 1 and 2 open the complaint itself.
    expect(stepPlace(run, 0).tab).toBe("Summary?ref=SAMPLE-RV-11");
    // With the story's Case, steps 1 and 2 open its case check on the Cases view (B2-11); triage opens the complaint.
    const withCase = { ...run, case: { id: "c11", ref: "SAMPLE-CASE-11", classification: null, state: "OPEN" } };
    expect(stepPlace(withCase, 0)).toEqual({ section: "Complaints", tab: "First contact?check=c11" });
    expect(stepPlace(withCase, 1)).toEqual({ section: "Complaints", tab: "First contact?check=c11" });
    expect(stepPlace(withCase, 2).tab).toBe("Summary?ref=SAMPLE-RV-11");
    expect(stepPlace(run, 3)).toEqual({ section: "Decision trees", tab: "?market=US&complaint=sample-id" });
    expect(stepPlace(run, 5)).toEqual({ section: "Reports", tab: "?report=r1" });
    expect(stepPlace(run, 8)).toEqual({ section: "Records", tab: "Decision records?complaint=SAMPLE-RV-11" });
    expect(stepPlace(run, 9).tab).toBe("Trend check?product=SAMPLE-ORBIT-300");
    // Before the report exists, its steps open the tree, where signing "reportable" creates it.
    expect(stepPlace(runAt("sample", 4), 5).section).toBe("Decision trees");
  });

  it("ends the sample on the OrbitCare rise; the trend bars say their verdict in words", () => {
    const html = view({ sample: runAt("sample", 9), yours: null });
    expect(html).toContain("Open the OrbitCare 300 trend");
    const rise = renderToStaticMarkup(
      <TrendBars row={trend("OrbitCare 300 Rev B", "orbit", 9, 0.97, "SIGNIFICANT")} />,
    );
    expect(rise).toContain("OrbitCare 300 Rev B: significant rise");
    // A group too small to assess says so, never "in line" (3 observed against 0.99 expected).
    const few = renderToStaticMarkup(<TrendBars row={trend("PulseWatch 410 Rev A", "pulse", 3, 0.99, "TOO_FEW")} />);
    expect(few).toContain("PulseWatch 410 Rev A: too few to assess");
    expect(few).not.toContain("in line");
  });

  it("finds the story's run by its complaint, and shows the sample unless Your data is chosen", () => {
    const story = { sample: runAt("sample", 1), yours: runAt("yours", 0) };
    expect(runOf(story, "OS-1002")?.run).toBe("yours");
    expect(runOf(story, "SAMPLE-RV-07")).toBeNull();
    expect(shownRun(story, SAMPLE_SOURCE)?.run).toBe("sample");
    expect(shownRun({ sample: null, yours: story.yours }, SAMPLE_SOURCE)?.run).toBe("yours");
  });
});

describe("Home's tiles while they read (D1.6)", () => {
  beforeEach(stubWindow);
  afterEach(() => vi.unstubAllGlobals());

  it("say Reading… on every tile, never an all-clear, before the data arrives", () => {
    const html = renderToStaticMarkup(
      <WorkspaceContext.Provider value={workspace({ isTrial: true } as Partial<WorkspaceApi>)}>
        <HomeSection heading={{ current: null }} />
      </WorkspaceContext.Provider>,
    );
    const stats = html.slice(html.indexOf('aria-label="What needs attention"'), html.indexOf("uw-home-grid"));
    expect(stats.match(/Reading…/g)).toHaveLength(3);
    expect(stats).not.toContain("No product rising");
    expect(stats).not.toContain("Nothing past its time");
  });
});

describe("Team: several personas per invited colleague (D1.9)", () => {
  const personas = [
    { code: "quality", label: "Quality Leader", sub: "Complaints, investigations, CAPA, trends" },
    { code: "regulatory", label: "Regulatory Leader", sub: "Reportability, legal clocks, authority reports" },
    { code: "decision", label: "Decision Maker", sub: "Approvals and signed decisions" },
  ];
  const rahul = {
    id: "u2",
    display_name: "Rahul Iyer",
    email: "rahul@example.test",
    status: "ACTIVE",
    is_owner: false,
    is_you: false,
    persona: "regulatory",
    persona_label: "Regulatory Leader",
    persona_locked: true,
    personas: [
      { code: "regulatory", label: "Regulatory Leader" },
      { code: "decision", label: "Decision Maker" },
    ],
  };
  const team = {
    can_invite: true,
    can_manage: true,
    limit: 50,
    seats_used: 2,
    personas,
    members: [
      {
        ...rahul,
        id: "u1",
        display_name: "Asha Menon",
        is_owner: true,
        is_you: true,
        persona_locked: false,
        personas: [],
      },
      rahul,
    ],
  };

  it("invites with one or more personas ticked, and shows a colleague's personas together", () => {
    const html = renderToStaticMarkup(
      <TeamView
        team={{ state: "ready", data: team, reload: () => undefined }}
        busy={false}
        message={null}
        onInvite={async () => true}
        onResend={() => undefined}
        onConfirm={() => undefined}
        onChanged={() => undefined}
      />,
    );
    expect(html).toContain("Personas: tick one or more");
    expect(html.match(/type="checkbox"/g)!.length).toBeGreaterThanOrEqual(3);
    expect(html).not.toContain("<select");
    expect(html).toContain("Regulatory Leader + Decision Maker");
  });

  it("changes the set with one confirmation naming every persona", () => {
    const confirm = personaConfirmation(rahul, [personas[1], personas[2]], () => undefined);
    expect(confirm.title).toBe("Make Rahul Iyer a Regulatory Leader + Decision Maker?");
    expect(confirm.body).toContain("Nobody approves what they prepared themselves.");
  });
});

describe("Import your data: one drop zone and the loading checklist (D1.10)", () => {
  const entities = [
    "products",
    "lots",
    "distribution",
    "complaints",
    "investigations",
    "capas",
    "risks",
    ...Array.from({ length: 11 }, (_, index) => `extra${index}`),
  ];
  const templates = entities.map((entity) => ({
    entity,
    title: entity,
    required: [],
    optional: [],
    help: {},
    download: "",
  })) as unknown as ImportTemplate[];

  it("lists the 7 core objects in loading order, what each unlocks and whether it is loaded, the 11 others folded", () => {
    const runs = [
      { entity: "complaints", imported_at: "2026-11-02T06:10:00Z", report: { rows_accepted: 4 } },
      { entity: "complaints", imported_at: "2026-11-01T06:10:00Z", report: { rows_accepted: 9 } },
    ] as unknown as ImportRun[];
    const html = renderToStaticMarkup(
      <LoadChecklist core={templates.slice(0, 7)} more={templates.slice(7)} runs={runs} />,
    );
    expect(html.indexOf(">products<")).toBeLessThan(html.indexOf(">lots<"));
    expect(html.indexOf(">lots<")).toBeLessThan(html.indexOf(">complaints<"));
    expect(html).toContain("Per-unit trends and lot impact");
    // The newest import of an object is the one shown.
    expect(html).toContain("4 rows loaded");
    expect(html.match(/is-loaded/g)).toHaveLength(1);
    expect(html).toContain("More objects (11)");
    expect(loadedObjects(runs).complaints.rows).toBe(4);
  });
});

describe("a call's next action opens its own triage card (navigation M5)", () => {
  it("opens the triage list on the call's own card", () => {
    const opens = {
      section: "Complaints",
      tab: "Triage?intake=i1",
      target: { section: "Complaints", tab: "Triage", record: { kind: "intake", id: "i1" }, panel: null },
    };
    expect(placeOf(opens as never)).toEqual({ section: "Complaints", tab: "Triage?intake=i1" });
    expect(recordPlace("intake" as never, "i1", {}, "new")).toEqual({
      section: "Complaints",
      tab: "To triage?intake=i1",
    });
  });
});

describe("Getting started's address on the new navigation", () => {
  it("never writes ?tab=Your+data, which a refresh opened as the Import page", () => {
    expect(gettingStarted).toContain('navigation === "new" ? ((focus ?? "").split("?")[0] as TrialTab) : "Your data"');
  });
});
