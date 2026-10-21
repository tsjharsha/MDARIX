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
  /** The chapter answers what the organization was cited for (Getting started, "What were you cited for?"). */
  cited?: boolean;
};

export type TrialStory = {
  as_of: string;
  /** An import's signals are still being found: the trend chapter says so, and the story is read again. */
  signals_pending?: boolean;
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

/** A chapter not tried yet is simply still to do: said neutrally, never as a failure. A tried chapter says "Tried",
 * as the progress ring counts it: "Done N times" counted the records it made, so one import of 6 rows read "Done 6
 * times" and a chapter whose sample was removed read "Done 0 times" (UX-28). */
export function chapterStatus(chapter: StoryChapter): string {
  return chapter.acted.done ? "Tried" : "To do";
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

/** What the headline says when the story could not be read (a failed or timed-out request). */
export const STORY_FAILED = {
  title: "Your trial's story could not be loaded",
  detail:
    "Your records are safe; the connection or the server did not answer in time. Try again, or carry on in Investigations, where the sample case is.",
};

/** The story's headline: the next chapter to try, or the loop closed; ``failed`` when the story could not be read. */
export function storyHeadline(story: TrialStory | null | undefined, failed = false): { title: string; detail: string } {
  if (!story) return failed ? STORY_FAILED : { title: "Reading your trial's records…", detail: "" };
  const next = story.chapters.find((chapter) => chapter.code === story.next);
  if (!next)
    return {
      title: "You closed the whole loop",
      detail: "Every chapter has been tried on your records. Talk to us about becoming a design partner.",
    };
  return {
    title: `Chapter ${next.number} of ${story.total}: ${next.title}`,
    detail: next.finding.text ? `${next.finding.text.replace(/[.…\s]+$/, "")}. ${next.promise}` : next.promise,
  };
}
