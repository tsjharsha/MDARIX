// The free trial's story (/api/v1/trial/story, backend/app/trial/story.py): the quality loop chapter by chapter, each
// with what the trial's records show and whether the organization acted on it (a record it created, never a page
// view). Getting started reads it; the Platform Admin trial overview reads the same progress.
import type { Tone } from "../admin/console/dashboardModel";
import { checkStateOf } from "./readiness";
import type { LoopStation } from "./qualityLoop";

export type StoryChapter = {
  code: string;
  number: number;
  title: string;
  promise: string;
  pain: string;
  opens: { section: string; tab?: string | null };
  finding: { value: number | null; text: string | null; state: string };
  acted: { done: boolean; count: number };
  /** The case the chapter is about (the guided investigation), opened with it; null when there is none. */
  case?: { id: string; product_id: string | null } | null;
};

export type TrialStory = {
  as_of: string;
  acted: number;
  total: number;
  next: string | null;
  chapters: StoryChapter[];
};

export const TRIAL_STORY_PATH = "/api/v1/trial/story";

/** Short names for the loop picture (the titles are sentences). */
export const CHAPTER_SHORT: Record<string, string> = {
  HIDDEN_COMPLAINTS: "Hidden complaints",
  REPORTING_CLOCKS: "Reporting clocks",
  TRENDS_TO_CASES: "Trend to case",
  INVESTIGATE_WITH_AI: "Investigation",
  DECIDE_AND_SIGN: "Signed decision",
  CAPA_EFFECTIVE: "CAPA proven",
  RISK_FILE: "Risk file",
  SHOW_THE_INSPECTOR: "Inspector summary",
  YOUR_DATA: "Your own data",
};

/** What each chapter's button says. */
export const CHAPTER_ACTION: Record<string, string> = {
  HIDDEN_COMPLAINTS: "Review hidden complaints",
  REPORTING_CLOCKS: "Check reporting clocks",
  TRENDS_TO_CASES: "Open the signal inbox",
  INVESTIGATE_WITH_AI: "Open the guided investigation",
  DECIDE_AND_SIGN: "Review and sign the sample decision",
  CAPA_EFFECTIVE: "Check CAPA effectiveness",
  RISK_FILE: "Open risk file input",
  SHOW_THE_INSPECTOR: "Open Readiness",
  YOUR_DATA: "Upload your data",
};

/** The tone a chapter shows: done when acted on, else what its finding says. */
export function chapterTone(chapter: StoryChapter): Tone {
  if (chapter.acted.done) return "good";
  return chapter.finding.state === "NOT_SET" ? "neutral" : checkStateOf(chapter.finding.state).tone;
}

export function chapterStatus(chapter: StoryChapter): string {
  if (chapter.acted.done) return chapter.acted.count === 1 ? "Done once" : `Done ${chapter.acted.count} times`;
  return "Your turn";
}

/** The chapters as stations on the loop picture. */
export function loopFromStory(story: TrialStory | null | undefined): LoopStation[] {
  return (story?.chapters ?? []).map((chapter) => ({
    key: chapter.code,
    number: chapter.number,
    label: CHAPTER_SHORT[chapter.code] ?? chapter.title,
    caption: chapter.finding.text ?? chapter.promise,
    value: chapter.finding.value,
    tone: chapterTone(chapter),
    stateLabel: chapterStatus(chapter),
    done: chapter.acted.done,
    opens: chapter.opens,
  }));
}

/** The story's headline: the next chapter to try, or the loop closed. */
export function storyHeadline(story: TrialStory | null | undefined): { title: string; detail: string } {
  if (!story) return { title: "Reading your trial's records…", detail: "" };
  const next = story.chapters.find((chapter) => chapter.code === story.next);
  if (!next)
    return {
      title: "You closed the whole loop",
      detail: "Every chapter has been tried on your records. Talk to us about becoming a design partner.",
    };
  return {
    title: `Chapter ${next.number} of ${story.total}: ${next.title}`,
    detail: next.finding.text ? `${next.finding.text.replace(/[.\s]+$/, "")}. ${next.promise}` : next.promise,
  };
}
