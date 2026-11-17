// W1: the flagship story, OrbitCare 300 Rev B (SAMPLE-INV-001) in seven steps, on Getting started and in its bar.
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FlagshipView, OneStory, flagshipCopy } from "./sections/OneStory";
import { FlagshipBar, flagshipBarParts } from "./sections/FlagshipBar";
import { AtAGlance } from "./sections/caseIntelligence/RootCause";
import {
  ONE_STORY_PATH,
  branchPlace,
  flagshipPlace,
  openFlagshipStep,
  visited,
  type FlagshipRun,
  type OneStory as OneStoryData,
  type StoryRun,
} from "./oneStory";
import { evidenceStates, versionWords, type IntelHypothesis } from "./intelligence";
import { RECORDED_LABEL, RecordedChip } from "../shared/AiReview";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { SAMPLE_SOURCE } from "./complaintList";

const reads = vi.hoisted(() => ({
  data: {} as Record<string, unknown>,
  sent: [] as unknown[],
  ai: null as boolean | null,
}));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    const data = (path && reads.data[path.split("?")[0]]) ?? null;
    return { state: data ? "ready" : "loading", data, reload: () => undefined };
  },
  send: async (path: string, method: string, body: unknown) => {
    reads.sent.push({ path, method, body });
    return {};
  },
}));
vi.mock("./useAiStatus", () => ({ useAiReady: () => reads.ai, useAiBanner: () => null }));

const LABELS = [
  "Signal: pressure alarms are rising",
  "Product reality",
  "What is known and what is not",
  "AI investigation",
  "Investigation Brief",
  "Human decision",
  "Action and impact",
];
const flagship = (current = 0, extra: Partial<FlagshipRun> = {}): FlagshipRun => ({
  run: "flagship",
  product: {
    id: "p-orbit",
    ref: "SAMPLE-ORBIT-300",
    name: "OrbitCare 300 Infusion Pump (Sample)",
    label: "OrbitCare 300",
    version: "Rev B",
    version_state: "KNOWN",
    unverified: 0,
  },
  investigation: {
    id: "inv-1",
    ref: "SAMPLE-INV-001",
    question: "Why did pressure-alarm complaints rise after OrbitCare 300 Rev B?",
  },
  change: { ref: "SAMPLE-CHG-014", description: "Sensor supplier changed; inspection cut from 32 to 13 units." },
  capa: {
    id: "capa-2",
    ref: "SAMPLE-CAPA-02",
    title: "Restore incoming inspection",
    check_planned: false,
    check_status: null,
  },
  branch: { complaint_id: "rv06", ref: "SAMPLE-RV-06" },
  ai_proposals: 1,
  mfa_verified: null,
  steps: LABELS.map((label, index) => ({ key: `k${index}`, label, done: index < current, skipped: false })),
  current,
  finished: current >= 7,
  ...extra,
});
const sampleRun = (current: number) =>
  ({
    run: "sample",
    complaint: {
      id: "rv11",
      ref: "SAMPLE-RV-11",
      description: null,
      product_id: null,
      serious_injury: false,
      death: false,
    },
    market: "US",
    market_label: "United States (FDA)",
    conclusion: null,
    report_id: null,
    report_stage: null,
    needs: [],
    steps: Array.from({ length: 10 }, (_, index) => ({
      key: `s${index}`,
      label: `S${index}`,
      done: index < current,
      skipped: false,
    })),
    current,
    finished: false,
  }) as StoryRun;
const story = (run: FlagshipRun, sample = 0): OneStoryData => ({
  sample: sampleRun(sample),
  yours: null,
  flagship: run,
});

const api = (extra: Partial<WorkspaceApi> = {}) =>
  ({
    session: { allowed_menu: ["home"], business_permissions: [] },
    work: { products: [], setInvestigationId: vi.fn(), refreshProducts: vi.fn() },
    open: vi.fn(),
    notify: vi.fn(),
    startStory: vi.fn(),
    navigation: "new",
    isTrial: true,
    dataSource: SAMPLE_SOURCE,
    ...extra,
  }) as unknown as WorkspaceApi;
const render = (node: ReactNode, value: WorkspaceApi = api()) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);
const primaries = (html: string) => html.match(/class="ac-primary[^"]*"/g) ?? [];

beforeEach(() => {
  reads.data = {};
  reads.sent = [];
  reads.ai = null;
});

describe("Getting started leads with the flagship", () => {
  it("has one main button, Start the sample investigation, no Coming next, and OrbitCare 300 · Rev B", () => {
    reads.data[ONE_STORY_PATH] = story(flagship());
    const html = render(<OneStory more={<button className="ac-primary">Explore</button>} />);
    expect(primaries(html)).toHaveLength(1);
    expect(html).toContain("Start the sample investigation");
    expect(html).not.toContain("Coming next");
    expect(html).toContain("OrbitCare 300 · Rev B · SAMPLE-INV-001 · Step 1 of 7");
  });

  it("explains the trend's lot 005 on the first two step cards", () => {
    const html = render(<FlagshipView story={story(flagship(1))} run={flagship(1)} />);
    expect(html).toContain("Lot 005 was built with the next sensor lot (NS-SL-2533)");
  });

  it("W2: before the first step, one calm screen: the button in the band, the steps folded", () => {
    reads.data[ONE_STORY_PATH] = story(flagship());
    const html = render(<OneStory />);
    expect(primaries(html)).toHaveLength(1);
    expect(html).toMatch(/uw-gs-head.*Start the sample investigation/s);
    expect(html).toContain("<summary>See the seven steps</summary>");
    expect(html).not.toContain("uw-os-rail");
    expect(html).not.toContain("<dt>Why</dt>");
  });

  it("keeps the PulseWatch story inside the closed fold, with a line to continue it", () => {
    const html = render(<FlagshipView story={story(flagship(), 4)} run={flagship()} more={<p>Explore cards</p>} />);
    expect(html).toContain("<summary>More sample stories (optional)</summary>");
    // Closed: neither the ten-step walkthrough nor the explore cards are on the page until it is opened.
    expect(html).not.toContain("Your sample walkthrough");
    expect(html).not.toContain("Explore cards");
    expect(html).not.toContain("PulseWatch 410, 10 steps");
    expect(html).toContain("You started the PulseWatch 410 story (Step 5 of 10).");
    expect(html).toContain("Continue it");
  });

  it("finishes with the investigation complete and Do the same with your data", () => {
    const html = render(<FlagshipView story={story(flagship(7))} run={flagship(7)} />);
    expect(html).toContain("The sample investigation is complete");
    expect(primaries(html)).toHaveLength(1);
    expect(html).toContain("Do the same with your data");
    expect(html).not.toMatch(/it worked/i);
  });

  it("says the brief came before the AI proposal, and step 7's three honest lines", () => {
    const brief = render(<FlagshipView story={story(flagship(4))} run={flagship(4)} />);
    expect(brief).toContain(
      "Written by the sample author before the AI proposal; your accepted proposal is on the case.",
    );
    expect(brief).toContain("Review the brief");
    const action = render(<FlagshipView story={story(flagship(6))} run={flagship(6)} />);
    expect(action).toContain("CAPA SAMPLE-CAPA-02: Restore incoming inspection");
    expect(action).toContain("Did it work? Too early");
    expect(action).toContain("SAMPLE-RSK-01 and SAMPLE-RSK-02");
    expect(action).toContain("Plan the effectiveness check");
    expect(action).toContain("Optional: is SAMPLE-RV-06 reportable in each market?");
  });
});

describe("each step opens its real screen", () => {
  it("places all seven steps and the optional branch", () => {
    const run = flagship();
    expect(flagshipPlace(run, 0)).toEqual({ section: "Trends", tab: "Trend check?product=SAMPLE-ORBIT-300" });
    expect(flagshipPlace(run, 1)).toEqual({
      section: "Product 360",
      tab: "Product 360?product=SAMPLE-ORBIT-300&view=Configuration&compare=Rev+A&version=Rev+B",
    });
    const inCase = { section: "Investigations", caseId: "inv-1", productId: "p-orbit" };
    expect(flagshipPlace(run, 2)).toEqual({ ...inCase, tab: "Evidence?view=Overview&part=intelligence" });
    expect(flagshipPlace(run, 3)).toEqual({ ...inCase, tab: "Evidence" });
    expect(flagshipPlace(run, 4)).toEqual({ ...inCase, tab: "Decisions & actions?part=brief" });
    expect(flagshipPlace(run, 5)).toEqual({ ...inCase, tab: "Decisions & actions?part=decision" });
    expect(flagshipPlace(run, 6)).toEqual({ section: "Records", tab: "Effectiveness checks?capa=capa-2" });
    expect(branchPlace(run)?.section).toBeTruthy();
  });

  it("opens the case first and saves a mark only once the right screen loads", async () => {
    const run = flagship(1);
    const open = vi.fn();
    const setCase = vi.fn();
    openFlagshipStep(run, 1, open, setCase);
    expect(setCase).not.toHaveBeenCalled();
    await visited({ step: "product", product: "SAMPLE-ORBIT-300", version: "Rev A" });
    expect(reads.sent).toEqual([]);
    await visited({ step: "product", product: "SAMPLE-ORBIT-300", version: "Rev B" });
    expect(reads.sent).toEqual([
      {
        path: `${ONE_STORY_PATH}/marks`,
        method: "POST",
        body: { run: "flagship", step: "product", complaint_id: "inv-1" },
      },
    ]);
    openFlagshipStep(flagship(2), 2, open, setCase);
    expect(setCase).toHaveBeenCalledWith("inv-1", "p-orbit");
    await visited({ step: "evidence", investigationId: "inv-1" });
    // The signal is the trend check's load.
    openFlagshipStep(flagship(0), 0, open, setCase);
    await visited({ step: "trends", product: "SAMPLE-ORBIT-300" });
    expect(reads.sent.map((item) => (item as { body: { step: string } }).body.step)).toEqual([
      "product",
      "evidence",
      "signal",
    ]);
  });
});

describe("step 4: the AI", () => {
  it("asks AI when AI answers, else reviews the recorded proposals with their chip", () => {
    reads.ai = false;
    const off = render(<FlagshipView story={story(flagship(3))} run={flagship(3)} />);
    expect(off).toContain("Review the AI proposals");
    expect(off).toContain("AI is off: no model is called.");
    expect(off).toContain(RECORDED_LABEL);
    reads.ai = true;
    const on = render(<FlagshipView story={story(flagship(3))} run={flagship(3)} />);
    expect(on).toContain("Ask AI for competing explanations");
    expect(on).not.toContain(RECORDED_LABEL);
    expect(flagshipCopy(flagship(3), 3, null).b).toBe("Review the AI proposals");
  });

  it("puts the chip on recorded proposals only", () => {
    expect(renderToStaticMarkup(<RecordedChip recorded />)).toContain("Recorded with the sample · no model was called");
    expect(renderToStaticMarkup(<RecordedChip recorded={false} />)).toBe("");
    expect(renderToStaticMarkup(<RecordedChip />)).toBe("");
  });
});

describe("step 3: at a glance", () => {
  const link = (business_id: string, relation: string, by = "person") => ({
    id: `${business_id}-${relation}`,
    relation,
    evidence: { business_id, title: `${business_id} title` },
    created_by_type: by,
  });
  const hypotheses = [
    {
      id: "h1",
      statement: "The NovaSense sensors read high.",
      origin: "HUMAN",
      evidence: [link("EV-001", "SUPPORTING"), link("EV-002", "SUPPORTING")],
    },
    {
      id: "h2",
      statement: "Ward settings set off the alarms.",
      origin: "HUMAN",
      evidence: [link("EV-002", "CONTRADICTING"), link("EV-003", "CONTRADICTING")],
    },
    {
      id: "h3",
      statement: "The inspection cut let the sensors through.",
      origin: "AI",
      evidence: [link("EV-001", "SUPPORTING", "ai"), link("EV-002", "CONTRADICTING", "ai")],
    },
  ] as IntelHypothesis[];

  it("groups known, unknown, contradicted and missing, and keeps the time order", () => {
    const states = evidenceStates({
      hypotheses,
      unknowns: [
        { id: "u1", business_id: "UNK-1", description: "Bench test of returned pumps", status: "open" },
        { id: "u2", business_id: "UNK-2", description: "Ward alarm limits", status: "in_progress" },
        { id: "u3", business_id: "UNK-3", description: "Resolved one", status: "resolved" },
      ],
      chains: [
        {
          id: "c1",
          business_id: "FC-1",
          links: [
            { id: "l1", from_label: "Sensors high", to_label: "Pump reads high", state: "UNKNOWN" },
            { id: "l2", from_label: "Change", to_label: "Inspection cut", state: "SUPPORTED" },
          ],
        },
      ],
      versions: [
        { anchor_date: "2026-10-20T00:00:00Z", lot: { identifier: "LOT-004" } },
        { anchor_date: "2026-09-15T00:00:00Z", lot: { identifier: "LOT-003" } },
      ],
      product: {
        changes: [
          {
            change_identifier: "SAMPLE-CHG-014",
            description: "Supplier change",
            event_timestamp: "2026-08-29T00:00:00Z",
          },
        ],
        versions: [
          { version_identifier: "Rev B", release_timestamp: "2026-09-03T00:00:00Z" },
          { version_identifier: "Rev A", release_timestamp: "2025-11-22T00:00:00Z" },
        ],
        lots: [
          { lot_identifier: "LOT-003", manufactured_timestamp: "2026-09-03T00:00:00Z" },
          { lot_identifier: "LOT-004", manufactured_timestamp: "2026-09-10T00:00:00Z" },
          { lot_identifier: "LOT-006", manufactured_timestamp: "2026-09-20T00:00:00Z" },
        ],
        evidence: [{ business_id: "EV-002", title: "Incoming inspection", source_timestamp: "2026-11-05T00:00:00Z" }],
      },
    });
    expect(states.known.map((item) => item.sources[0])).toEqual(["EV-001", "EV-002"]);
    expect(states.unknown.map((item) => item.sources[0])).toEqual(["UNK-1", "UNK-2"]);
    expect(states.contradicted).toEqual([
      { label: "Ward settings set off the alarms.", sources: ["EV-002", "EV-003"] },
      { label: "AI proposal: The inspection cut let the sensors through.", sources: ["EV-002"] },
    ]);
    expect(states.missing).toEqual([{ label: "Sensors high → Pump reads high", sources: ["FC-1"] }]);
    const dates = states.timeline.map((event) => event.date);
    expect(dates).toEqual([...dates].sort((a, b) => Date.parse(a) - Date.parse(b)));
    expect(states.timeline.map((event) => event.source)).toEqual([
      "Rev A",
      "SAMPLE-CHG-014",
      "Rev B",
      "Lot LOT-003",
      "Lot LOT-004",
      "Complaints",
      "Complaints",
      "EV-002",
    ]);
    const html = renderToStaticMarkup(<AtAGlance caseLabel="SAMPLE-INV-001" states={states} />);
    for (const word of ["Known", "Unknown", "Contradicted", "Missing", "In time order"]) expect(html).toContain(word);
  });

  it("says where a version comes from and never fills in an unknown one", () => {
    expect(versionWords({ version: { version_identifier: "Rev B" }, version_source: "COMPLAINT" }).source).toBe(
      "From the complaint",
    );
    expect(versionWords({ version: { version_identifier: "Rev B" }, version_source: "LOT" }).source).toBe(
      "From the lot",
    );
    const unknown = versionWords({
      version: null,
      version_source: null,
      candidate_versions: [{ version_identifier: "Rev A" }, { version_identifier: "Rev B" }],
    });
    expect(unknown).toEqual({
      version: "Version not known (unverified)",
      source: "Neither the complaint nor its lot names a version",
      candidates: ["Rev A", "Rev B"],
    });
  });
});

describe("the flagship bar", () => {
  it("reads product · version · case · step, the unverified version and the optional branch", () => {
    expect(flagshipBarParts(flagship())).toEqual(["OrbitCare 300", "Rev B", "SAMPLE-INV-001", "Step 1 of 7"]);
    const unverified = flagship(2, {
      product: { ...flagship().product, version: null, version_state: "UNVERIFIED", unverified: 3 },
    });
    expect(flagshipBarParts(unverified)[1]).toBe("Version not verified");
    expect(flagshipBarParts(flagship(), true)).toEqual(["Optional branch", "SAMPLE-RV-06"]);
    expect(flagshipBarParts(flagship(7))[3]).toBe("All seven steps done");
  });

  it("shows on the step's screens with Next and Back, never on Getting started", () => {
    reads.data[ONE_STORY_PATH] = story(flagship(1));
    const html = render(<FlagshipBar section="Product 360" />);
    expect(html).toContain("OrbitCare 300");
    expect(html).toContain("Step 2 of 7");
    expect(html).toContain("Next: Product reality");
    expect(html).toContain("Back to Getting started");
    expect(render(<FlagshipBar section="Getting started" />)).toBe("");
    const branch = render(<FlagshipBar section="Decision trees" branch />);
    expect(branch).toContain("Optional branch");
    expect(branch).not.toContain("Next:");
  });
});
