import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { QualityLoop } from "./sections/QualityLoop";
import { ChapterRow } from "./sections/GettingStarted";
import { LOOP_ORDER, loopDone, loopFromReadiness, stationPoint, weakestLink } from "./qualityLoop";
import {
  CHAPTER_ACTION,
  CHAPTER_SHORT,
  chapterStatus,
  chapterTone,
  loopFromStory,
  storyHeadline,
  type StoryChapter,
  type TrialStory,
} from "./trialStory";
import type { Readiness, ReadinessCheck } from "./readiness";
import {
  attentionOrder,
  chapterFunnel,
  nextChapterTitle,
  storyStage,
  trialStateOf,
  type TrialItem,
  type TrialOverview,
} from "../admin/customers/trials";

const check = (code: string, state: ReadinessCheck["state"], value: number | null): ReadinessCheck => ({
  code,
  title: code,
  value,
  state,
  detail: `${code} detail`,
  why: "",
  opens: { section: "Complaints", tab: "Second look" },
  items: [],
});

// The server lists the four home numbers first; the loop puts them in the order a complaint travels.
const readiness: Readiness = {
  as_of: "2026-10-13",
  home: [],
  checks: [
    check("COMPLAINTS_TO_RECHECK", "CRITICAL", 5),
    check("COMPLAINTS_PAST_TARGET", "ATTENTION", 2),
    check("REPORTING_CLOCKS", "ATTENTION", 3),
    check("TRENDS_WITHOUT_ACTION", "CLEAR", 0),
    check("RISK_FILE_INPUT", "CRITICAL", 3),
    check("HARM_CLOSED_WITHOUT_CASE", "CRITICAL", 1),
    check("CAPA_EFFECTIVENESS", "CRITICAL", 1),
    check("TRIAGE_OVERDUE", "CLEAR", 0),
    check("SOMETHING_NEW", "NOT_SET", null),
  ],
  summary: { checks: 9, clear: 2, attention: 2, critical: 4, not_set: 1 },
  note: "",
};

describe("the quality loop", () => {
  it("puts the inspection checks in the order a complaint travels, unknown ones last", () => {
    const stations = loopFromReadiness(readiness);
    expect(stations.map((station) => station.key)).toEqual([...LOOP_ORDER.map((step) => step.code), "SOMETHING_NEW"]);
    expect(stations.map((station) => station.number)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
    expect(stations[0]).toMatchObject({ label: "Hidden complaints found", tone: "critical", value: 5, done: false });
    expect(stations[4]).toMatchObject({ key: "TRIAGE_OVERDUE", tone: "good", stateLabel: "Clear", done: true });
    expect(loopDone(stations)).toBe(2);
    expect(loopFromReadiness(null)).toEqual([]);
  });

  it("names the weakest link: the first station in the worst state", () => {
    const stations = loopFromReadiness(readiness);
    expect(weakestLink(stations)?.key).toBe("COMPLAINTS_TO_RECHECK");
    expect(weakestLink(stations.map((station) => ({ ...station, done: true })))).toBeNull();
    const calmer = stations.map((station) =>
      station.tone === "critical" ? { ...station, tone: "warning" as const } : station,
    );
    // With nothing critical, a check that is not set up (serious) outranks those needing attention.
    expect(weakestLink(calmer)?.key).toBe("SOMETHING_NEW");
  });

  it("places the first station at the top and the rest clockwise", () => {
    expect(stationPoint(0, 8, 100, 160, 160)).toEqual({ x: 160, y: 60 });
    expect(stationPoint(2, 8, 100, 160, 160)).toEqual({ x: 260, y: 160 });
    expect(stationPoint(4, 8, 100, 160, 160)).toEqual({ x: 160, y: 260 });
  });

  it("draws the loop with every station, says it in words and opens each station", () => {
    const markup = renderToStaticMarkup(
      <QualityLoop
        stations={loopFromReadiness(readiness)}
        eyebrow="Inspection readiness"
        title="2 of 9 inspection checks clear"
        doneLabel="clear"
        onOpen={vi.fn()}
      >
        <button type="button">Download PDF</button>
      </QualityLoop>,
    );
    expect(markup).toContain('role="img"');
    expect(markup).toContain("The quality loop. 2 of 9 clear. Weakest link: Hidden complaints found, critical.");
    expect(markup).toContain("Hidden complaints found");
    expect(markup).toContain("Risk file fed");
    expect(markup).toContain("Download PDF");
    expect(markup).toContain("is-alarm");
    expect((markup.match(/class="ql-station /g) ?? []).length).toBe(9);
    expect((markup.match(/class="ql-step /g) ?? []).length).toBe(9);
    // Two loops on one page keep their own glow.
    const twice = renderToStaticMarkup(
      <>
        <QualityLoop stations={[]} eyebrow="A" title="A" doneLabel="clear" />
        <QualityLoop stations={[]} eyebrow="B" title="B" doneLabel="clear" />
      </>,
    );
    const ids = [...twice.matchAll(/radialGradient id="([^"]+)"/g)].map((match) => match[1]);
    expect(new Set(ids).size).toBe(2);
  });
});

const chapter = (code: string, overrides: Partial<StoryChapter> = {}): StoryChapter => ({
  code,
  number: 1,
  title: "Recover complaints hidden as cancellations or inquiries",
  promise: "The second look finds records cancelled or logged as inquiries that carry signs of a complaint.",
  pain: "FDA warning letters in 2026 cite complaints cancelled or logged as inquiries.",
  opens: { section: "Complaints", tab: "Second look" },
  finding: { value: 5, text: "5 records may be hidden complaints.", state: "CRITICAL" },
  acted: { done: false, count: 0 },
  ...overrides,
});

describe("the trial's story", () => {
  it("has a short name and an action for every chapter the server tells", () => {
    const codes = [
      "HIDDEN_COMPLAINTS",
      "REPORTING_CLOCKS",
      "TRENDS_TO_CASES",
      "INVESTIGATE_WITH_AI",
      "DECIDE_AND_SIGN",
      "CAPA_EFFECTIVE",
      "RISK_FILE",
      "SHOW_THE_INSPECTOR",
      "YOUR_DATA",
    ];
    expect(Object.keys(CHAPTER_SHORT)).toEqual(codes);
    expect(Object.keys(CHAPTER_ACTION)).toEqual(codes);
  });

  it("reads a chapter as done when the trial acted in it, else by its finding", () => {
    expect(chapterTone(chapter("HIDDEN_COMPLAINTS"))).toBe("critical");
    expect(chapterStatus(chapter("HIDDEN_COMPLAINTS"))).toBe("Your turn");
    const done = chapter("HIDDEN_COMPLAINTS", { acted: { done: true, count: 3 } });
    expect(chapterTone(done)).toBe("good");
    expect(chapterStatus(done)).toBe("Done 3 times");
    expect(chapterTone(chapter("YOUR_DATA", { finding: { value: null, text: null, state: "NOT_SET" } }))).toBe(
      "neutral",
    );
  });

  it("leads with the next chapter, and closes the loop when every chapter was tried", () => {
    const story: TrialStory = {
      as_of: "2026-10-13",
      acted: 0,
      total: 1,
      next: "HIDDEN_COMPLAINTS",
      chapters: [chapter("HIDDEN_COMPLAINTS")],
    };
    expect(storyHeadline(story)).toEqual({
      title: "Chapter 1 of 1: Recover complaints hidden as cancellations or inquiries",
      detail:
        "5 records may be hidden complaints. The second look finds records cancelled or logged as inquiries that carry signs of a complaint.",
    });
    expect(storyHeadline({ ...story, next: null }).title).toBe("You closed the whole loop");
    expect(storyHeadline(null).title).toBe("Reading your trial's records…");
    expect(loopFromStory(story)[0]).toMatchObject({ label: "Hidden complaints", tone: "critical", value: 5 });
  });

  it("shows a chapter with its finding, why it matters and its action", () => {
    const markup = renderToStaticMarkup(
      <ol>
        <ChapterRow chapter={chapter("HIDDEN_COMPLAINTS")} isNext allowed onOpen={vi.fn()} />
      </ol>,
    );
    expect(markup).toContain("is-next");
    expect(markup).toContain("5 records may be hidden complaints.");
    expect(markup).toContain("Why it matters:");
    expect(markup).toContain("Review hidden complaints");
    const done = renderToStaticMarkup(
      <ol>
        <ChapterRow
          chapter={chapter("HIDDEN_COMPLAINTS", { acted: { done: true, count: 1 } })}
          isNext={false}
          allowed={false}
          onOpen={vi.fn()}
        />
      </ol>,
    );
    expect(done).toContain("Open again");
    expect(done).toContain("Done once");
    expect(done).toContain("disabled");
    expect(done).toContain("Your role does not include this screen");
  });
});

const trial = (overrides: Partial<TrialItem> = {}): TrialItem => ({
  tenant_id: "t1",
  tenant_key: "TRIAL_ACME_1",
  name: "Acme Devices",
  owner: { email: "q@acme.invalid", name: "Quinn", status: "ACTIVE" },
  starts_at: "2026-10-01T00:00:00+00:00",
  expires_at: "2026-10-31T00:00:00+00:00",
  data_deleted_at: "2026-11-30T00:00:00+00:00",
  state: "ACTIVE",
  days_left: 18,
  users: { used: 1, limit: 3 },
  rows: { used: 0, limit: 5000 },
  story: { acted: [], acted_count: 0, total: 9, next: "HIDDEN_COMPLAINTS", counts: {}, last_activity: null },
  feedback: null,
  ...overrides,
});

describe("the Platform Admin trial overview", () => {
  it("reads each trial's stage and next chapter", () => {
    expect(storyStage(trial(), 4)).toEqual({ label: "Not started", tone: "neutral" });
    expect(storyStage(trial({ story: { ...trial().story, acted_count: 2 } }), 4).label).toBe("Started");
    expect(storyStage(trial({ story: { ...trial().story, acted_count: 4 } }), 4).label).toBe("Engaged");
    expect(storyStage(trial({ story: { ...trial().story, acted_count: 9 } }), 4).label).toBe("Closed the whole loop");
    const chapters = [{ code: "HIDDEN_COMPLAINTS", number: 1, title: "Recover hidden complaints" }];
    expect(nextChapterTitle(trial(), chapters)).toBe("1. Recover hidden complaints");
    expect(nextChapterTitle(trial({ story: { ...trial().story, next: null } }), chapters)).toBe("Every chapter tried");
    expect(trialStateOf("ENDING_SOON")).toEqual({ label: "Ends within 7 days", tone: "warning" });
  });

  it("puts trials ending soon without engagement first, ended ones last", () => {
    const ending = trial({ tenant_id: "ending", state: "ENDING_SOON", days_left: 3 });
    const engaged = trial({ tenant_id: "engaged", story: { ...trial().story, acted_count: 5 } });
    const fresh = trial({ tenant_id: "fresh" });
    const ended = trial({ tenant_id: "ended", state: "ENDED", days_left: 0 });
    expect(attentionOrder([ended, engaged, fresh, ending], 4).map((item) => item.tenant_id)).toEqual([
      "ending",
      "fresh",
      "engaged",
      "ended",
    ]);
  });

  it("shows where trials stop, chapter by chapter", () => {
    const overview: TrialOverview = {
      summary: {
        trials: 2,
        active: 2,
        ending_soon: 0,
        acted: 1,
        engaged: 0,
        own_data: 0,
        feedback: 0,
        chapters: { HIDDEN_COMPLAINTS: 1 },
      },
      chapters: [
        { code: "HIDDEN_COMPLAINTS", number: 1, title: "Recover hidden complaints" },
        { code: "REPORTING_CLOCKS", number: 2, title: "Decide every report" },
      ],
      engaged_chapters: 4,
      items: [],
    };
    expect(chapterFunnel(overview).map((slice) => [slice.label, slice.count])).toEqual([
      ["1. Recover hidden complaints", 1],
      ["2. Decide every report", 0],
    ]);
    expect(chapterFunnel(null)).toEqual([]);
  });
});

describe("the trend check per unit and against the previous version", () => {
  it("says what a group was compared with and how it was counted", async () => {
    const { trendBaselineText, trendBasisText, trendResultLabel } = await import("./signalAi");
    const young = {
      baseline: "PREVIOUS_VERSION" as const,
      baseline_name: "OrbitCare 300 Rev A",
      history: 6,
      history_days: 180,
      basis: "UNITS" as const,
    };
    expect(trendBaselineText(young)).toBe("OrbitCare 300 Rev A: 6 in the 180 days before this version's release");
    expect(trendBasisText(young)).toBe("Per unit in the field");
    expect(trendResultLabel({ result: "STEADY", baseline: "PREVIOUS_VERSION" })).toBe(
      "In line with the previous version",
    );
    expect(trendResultLabel({ result: "SIGNIFICANT", baseline: "PREVIOUS_VERSION" })).toBe("Significant rise");
    // Older data without the new fields reads as before.
    expect(trendBaselineText({ history: 4, history_days: 90 })).toBe("Own history: 4 in 90 days");
    expect(trendBasisText({})).toBe("Per calendar day");
    expect(trendResultLabel({ result: "STEADY" })).toBe("In line with history");
  });
});

describe("the guide to per-unit trends", () => {
  it("says when groups are counted per calendar day and how to count per unit", async () => {
    const { perUnitHint } = await import("./signalAi");
    expect(perUnitHint({ basis: { units: 3, time: 0 } })).toBeNull();
    expect(perUnitHint(null)).toBeNull();
    expect(perUnitHint({ basis: { units: 2, time: 3 } })).toMatch(/^3 of 5 groups are counted per calendar day/);
    expect(perUnitHint({ basis: { units: 0, time: 4 } })).toMatch(/^Every group is counted per calendar day/);
    expect(perUnitHint({ basis: { units: 0, time: 4 } })).toContain("Add each lot's quantity and manufacture date");
  });

  it("explains the key columns beside the template, with a per-unit callout for lots", async () => {
    const { ColumnGuide } = await import("./sections/ImportData");
    const lots = {
      entity: "lots",
      title: "Lots and batches",
      required: ["lot_id", "product_id", "version"],
      optional: ["manufacture_date", "site_id", "quantity"],
      help: { quantity: "How many devices the lot released.", manufacture_date: "The day the lot was released." },
      download: "/api/v1/data/import/templates/lots.csv",
    };
    const markup = renderToStaticMarkup(<ColumnGuide template={lots} />);
    expect(markup).toContain("Per-unit trends from day one:");
    expect(markup).toContain("How many devices the lot released.");
    expect(markup).toContain("<details open");
    const complaints = { ...lots, entity: "complaints", help: { awareness_date: "Reporting clocks start here." } };
    const plain = renderToStaticMarkup(<ColumnGuide template={complaints} />);
    expect(plain).not.toContain("Per-unit trends");
    expect(plain).toContain("Reporting clocks start here.");
    expect(renderToStaticMarkup(<ColumnGuide template={{ ...lots, help: undefined }} />)).toBe("");
  });
});

describe("booking a one-to-one demo from the trial", () => {
  it("offers the demo, and says when it was asked for", async () => {
    const { BookDemo, demoRequestText } = await import("./sections/BookDemo");
    expect(renderToStaticMarkup(<BookDemo chapters={[]} />)).toContain("Book a one-to-one demo");
    expect(demoRequestText(null)).toBeNull();
    expect(
      demoRequestText({
        id: "d1",
        business_id: "DEMO000001",
        status: "NEW",
        created_at: "2026-10-13T10:00:00+00:00",
        preferred_time: null,
      }),
    ).toMatch(/^You asked for a one-to-one demo on .+\. The MDARIX team will contact you to agree a time\.$/);
    expect(
      demoRequestText({ id: "d1", business_id: null, status: "CLOSED", created_at: null, preferred_time: null }),
    ).toBeNull();
  });

  it("shows MDARIX staff where a request came from and how far the trial got", async () => {
    const { demoContextLines, demoSourceText } = await import("../admin/DemoRequestsWorkspace");
    expect(demoSourceText({ source: "WEBSITE" })).toBe("Website");
    expect(demoSourceText({ source: "TRIAL", organization: "Acme Devices" })).toBe("Free trial: Acme Devices");
    expect(
      demoContextLines({
        source: "TRIAL",
        preferred_time: "Tuesday afternoon, IST",
        note: "Audit in March.",
        context: {
          chapters_tried: 3,
          chapters_total: 9,
          days_left: 12,
          own_data: true,
          focus: ["Feed post-market data into the risk file"],
        },
      }),
    ).toEqual([
      "Suits: Tuesday afternoon, IST",
      "3 of 9 story chapters tried, 12 days left, own data uploaded",
      "Focus: Feed post-market data into the risk file",
      "Note: Audit in March.",
    ]);
    expect(demoContextLines({ source: "WEBSITE", note: null, preferred_time: null, context: null })).toEqual([]);
  });

  it("lets a person switch the weekly readiness email off for themselves", async () => {
    const { EmailChoices } = await import("./sections/Account");
    expect(renderToStaticMarkup(<EmailChoices />)).toContain("Weekly readiness email");
  });

  it("explains the sample data: its size, the pain each part re-creates, the requirement and where to see it", async () => {
    const { SampleDataPanel } = await import("./sections/SampleData");
    const { SAMPLE_PAINS, sampleFacts } = await import("./sampleStory");
    const counts = { products: 3, lots: 15, complaints: 37, investigations: 1, capas: 2, risks: 3 };
    expect(sampleFacts(counts)).toEqual([
      "3 devices",
      "15 lots",
      "37 complaints",
      "1 investigation",
      "2 CAPAs",
      "3 risks",
    ]);
    expect(sampleFacts({ products: 3, capas: 0 })).toEqual(["3 devices"]);
    expect(sampleFacts(null)).toEqual([]);
    // Every pain opens a screen the MVP keeps, and names its requirement.
    const kept = ["Readiness", "Complaints", "Signals", "Investigations", "Records"];
    for (const pain of SAMPLE_PAINS) {
      expect(kept).toContain(pain.opens.section);
      expect(pain.requirement.length).toBeGreaterThan(20);
    }
    const html = renderToStaticMarkup(
      <SampleDataPanel counts={counts} allowed={(section) => section !== "Records"} onOpen={() => undefined} />,
    );
    expect(html).toContain("What your sample data is, and why it looks like this");
    expect(html).toContain("37 complaints");
    for (const pain of SAMPLE_PAINS) expect(html).toContain(pain.title);
    expect(html).toContain("ISO 13485 clause 8.2.2");
    expect(html).toContain("How the sample data was made");
    expect(html).toContain("No real company, device, patient or person");
    // A screen the role does not hold is not offered.
    expect(html).toContain('title="Your role does not include this screen"');
    // A workspace without the sample shows nothing.
    expect(
      renderToStaticMarkup(<SampleDataPanel counts={{ products: 0 }} allowed={() => true} onOpen={() => undefined} />),
    ).toBe("");
  });
});
