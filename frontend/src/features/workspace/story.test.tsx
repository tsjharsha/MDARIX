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
