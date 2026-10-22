import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { newlyTried, pageHidden } from "./sections/ChapterDone";
import { ChapterRow, QuickRating, TRIAL_TABS, quickRatingShown } from "./sections/GettingStarted";
import { TRIAL_PROGRESS_PATH, TRIAL_STORY_PATH, type StoryChapter, type TrialStory } from "./trialStory";

const chapter = (code: string, number: number, done: boolean): StoryChapter => ({
  code,
  number,
  title: `Chapter ${code}`,
  promise: `What MDARIX does for ${code}`,
  pain: `Why ${code} matters`,
  opens: { section: "Complaints", tab: "Second look" },
  finding: { value: 2, text: `2 findings in ${code}`, state: "ATTENTION" },
  acted: { done, count: done ? 1 : 0 },
});

const story = (done: string[]): TrialStory =>
  ({
    as_of: "2026-10-13",
    acted: done.length,
    total: 3,
    next: ["A", "B", "C"].find((code) => !done.includes(code)) ?? null,
    chapters: ["A", "B", "C"].map((code, index) => chapter(code, index + 1, done.includes(code))),
  }) as TrialStory;

describe("Getting started, simplified", () => {
  it("notices a chapter newly tried, but says nothing on first load", () => {
    expect(newlyTried(null, story(["A"]))).toEqual([]);
    expect(newlyTried(["A"], story(["A"]))).toEqual([]);
    expect(newlyTried(["A"], story(["A", "B"])).map((item) => item.code)).toEqual(["B"]);
  });

  it("reads which chapters were tried only, not the findings, every half minute (0.10.43)", () => {
    // The notice needs the chapters, which were tried and the next one: the story without its findings, a fraction
    // of the full read that Getting started makes.
    expect(TRIAL_PROGRESS_PATH).toBe(`${TRIAL_STORY_PATH}?findings=false`);
    // Without a page (the test run, prerendering) nothing counts as hidden.
    expect(pageHidden()).toBe(false);
  });

  it("shows a chapter in one line, with what MDARIX does and why it matters one click away", () => {
    const html = renderToStaticMarkup(
      <ChapterRow chapter={chapter("A", 1, false)} isNext allowed onOpen={() => undefined} />,
    );
    expect(html).toContain("1. Chapter A");
    expect(html).toContain("2 findings in A");
    expect(html).toContain("<details");
    expect(html).toContain("What MDARIX does here, and why it matters");
    expect(html).toContain("Why A matters");
  });

  it("asks one private question, with the full feedback one click away", () => {
    const html = renderToStaticMarkup(<QuickRating onSent={() => undefined} onMore={() => undefined} />);
    expect(html).toContain("How useful is MDARIX so far?");
    expect(html.match(/aria-label="\d of 5"/g)).toHaveLength(5);
    expect(html).toContain("Private to the MDARIX team.");
  });

  it("offers the rating after three chapters and keeps its thank-you in view once rated", () => {
    const state = { acted: 3, feedbackLoaded: true, feedbackSent: false, ratedNow: false };
    expect(quickRatingShown(state)).toBe(true);
    expect(quickRatingShown({ ...state, acted: 2 })).toBe(false);
    expect(quickRatingShown({ ...state, feedbackLoaded: false })).toBe(false);
    expect(quickRatingShown({ ...state, feedbackSent: true })).toBe(false);
    // Rated now: the feedback reloads (loading, then sent) and the thank-you with "tell us more" stays.
    expect(quickRatingShown({ ...state, feedbackLoaded: false, ratedNow: true })).toBe(true);
    expect(quickRatingShown({ ...state, feedbackSent: true, ratedNow: true })).toBe(true);
  });

  it("keeps everything but the story in four tabs", () => {
    expect(TRIAL_TABS).toEqual(["Your data", "Team", "About the sample data", "Your trial"]);
  });
});
