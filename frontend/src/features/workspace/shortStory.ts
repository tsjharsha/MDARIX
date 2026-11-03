import type { ServiceWork } from "./oversight";

/**
 * The short story on SAMPLE-RV-11 (0.10.71, A4), as the server reads it (backend/app/trial/short_story.py): four steps,
 * each done when its record exists (the call read, the triage record and the service work with owners, the question
 * to the hospital, the summary seen), never because a screen is open. Kept per person and organization on the server,
 * so a refresh, another device and "Resume SAMPLE-RV-11" all return to the same step.
 */
export const SHORT_STORY_PATH = "/api/v1/trial/short-story";
/** Said on the window when a step is saved, so the story bar and the resume line read the progress again. */
export const SHORT_STORY_SAVED = "mdarix:short-story";

export type ShortStoryStep = { key: "read" | "route" | "question" | "summary"; label: string; done: boolean };

export type ShortStory = {
  available: boolean;
  complaint?: { id: string; ref: string };
  steps: ShortStoryStep[];
  /** The step to do now (0 to 3), or 4 once the summary is seen. */
  current: number;
  started: boolean;
  finished: boolean;
  call: {
    words: string;
    phrases: Array<{ text: string; why: string }>;
    facts: Array<{ label: string; value: string }>;
  };
  route: {
    decision: string;
    source_quote: string | null;
    source_fact: string;
    owner_name: string | null;
    recorded_by: string | null;
    immediate_action: string | null;
  };
  question: {
    suggested: string;
    why: string;
    asked: {
      id: string;
      subject: string;
      owner_name: string | null;
      due_on: string;
      status: string;
      logged_by: string;
    } | null;
    /** From the bound question's state (0.10.72, F2): unknown while open, the answer and its date once answered. */
    consequence: string;
    consequence_state?: "UNKNOWN" | "ANSWERED" | "CLOSED";
    answer?: string | null;
    answered_on?: string | null;
  };
  service: ServiceWork | null;
  /** The full evaluation's steps, each done from SAMPLE-RV-11's own checklist and records (0.10.72). */
  full_evaluation?: { steps: Array<{ key: string; done: boolean }>; current: number };
  markets: Array<{
    market: string;
    label: string;
    state: string;
    open: boolean;
    deadline: string | null;
    deadline_title: string | null;
    why: string | null;
  }>;
  next: { action: string | null; who: string | null };
  people: {
    prepared_by: string[];
    may_approve: string[];
    approved_by: string[];
    practice: boolean;
    practice_note: string | null;
  };
  practice_label: string | null;
};

/** "Step 2 of 4: Decide the route"; once the summary is seen, "Step 4 of 4: The intake decision summary · done". */
export function stepText(story: Pick<ShortStory, "steps" | "current">): string {
  const step = story.steps[story.current];
  if (step) return `Step ${story.current + 1} of ${story.steps.length}: ${step.label}`;
  const last = story.steps[story.steps.length - 1];
  return `Step ${story.steps.length} of ${story.steps.length}: ${last?.label ?? "done"} · done`;
}

/** "Resume SAMPLE-RV-11 · step 2 of 4", for a person whose story is started and not finished; null otherwise. */
export function resumeText(story: ShortStory | null | undefined): string | null {
  if (!story?.available || !story.started || story.finished || !story.complaint) return null;
  return `Resume ${story.complaint.ref} · step ${story.current + 1} of ${story.steps.length}`;
}

/** Tell the story bar and the resume line to read the progress again. */
export const storySaved = () => window.dispatchEvent(new Event(SHORT_STORY_SAVED));
