// The Platform Admin trial overview (GET /api/v1/platform-admin/trials, backend/app/trial/story.py): every free trial
// still holding data, its dates and usage, how far into the story it went (chapters it acted in, from records it
// created, never page views) and its feedback. The figures cover every trial; the table is one page of them, filtered
// and sorted by the server. Pure rules for the screen (customers/TrialsOverview.tsx).
import { sortParams, type SortState } from "../../../app/tableSort";
import type { Slice, Tone } from "../console/dashboardModel";

export type TrialState = "ACTIVE" | "ENDING_SOON" | "ENDED";

export type TrialItem = {
  tenant_id: string;
  tenant_business_id?: string | null;
  tenant_key: string;
  name: string;
  owner: { email: string; name: string | null; status: string } | null;
  starts_at: string | null;
  expires_at: string;
  data_deleted_at: string;
  state: TrialState;
  days_left: number;
  users: { used: number; limit: number };
  rows: { used: number; limit: number };
  story: {
    acted: string[];
    acted_count: number;
    total: number;
    next: string | null;
    counts: Record<string, number>;
    last_activity: string | null;
  };
  feedback: { responses: number; overall: number | null; recommend: number | null } | null;
  // The trial's latest one-to-one demo request (booked from Getting started), or null.
  demo_request?: { status: string; created_at: string | null; business_id: string | null } | null;
  /** What the organization said it was cited for (its Getting started), to prepare the demo. */
  cited_for?: string[];
};

export type TrialOverview = {
  summary: {
    trials: number;
    active: number;
    ending_soon: number;
    acted: number;
    engaged: number;
    own_data: number;
    feedback: number;
    demo_requested?: number;
    chapters: Record<string, number>;
  };
  chapters: { code: string; number: number; title: string }[];
  engaged_chapters: number;
  /** One page of the trials matching the filters, in the requested order (attention order by default). */
  items: TrialItem[];
  /** The trials that need a person first, from every trial whatever the table shows. */
  attention?: TrialItem[];
  page?: number;
  page_size?: number;
  total?: number;
  pages?: number;
};

export const TRIALS_PATH = "/api/v1/platform-admin/trials";

/** Columns the server orders every page by (OVERVIEW_SORTS in backend/app/trial/story.py). */
export const TRIAL_SORT_KEYS = ["name", "state", "story", "last_activity", "demo", "feedback"] as const;

export const TRIAL_STATE_FILTERS: [string, string][] = [
  ["", "All trials"],
  ["ACTIVE", "Active"],
  ["ENDING_SOON", "Ending within 7 days"],
  ["ENDED", "Ended"],
];

export type TrialQuery = { page: number; sort: SortState; state: string; q: string };

/** The overview request for one page of the table: its page, order, state filter and search. */
export function trialsPath({ page, sort, state, q }: TrialQuery): string {
  const params = new URLSearchParams({ page: String(page), ...sortParams(sort) });
  if (state) params.set("state", state);
  if (q.trim()) params.set("q", q.trim());
  return `${TRIALS_PATH}?${params}`;
}

/** Who needs attention first: the server's list (every trial), else the first open trials it sent. */
export function attentionList(data: TrialOverview | null | undefined, engagedAt: number): TrialItem[] {
  if (data?.attention) return data.attention;
  return attentionOrder(data?.items ?? [], engagedAt)
    .filter((item) => item.state !== "ENDED")
    .slice(0, 5);
}

export const TRIAL_STATE: Record<TrialState, { label: string; tone: Tone }> = {
  ACTIVE: { label: "Active", tone: "good" },
  ENDING_SOON: { label: "Ends within 7 days", tone: "warning" },
  ENDED: { label: "Ended, data kept 30 days", tone: "neutral" },
};

export const trialStateOf = (state: string | null | undefined) =>
  TRIAL_STATE[(state ?? "") as TrialState] ?? { label: state ?? "—", tone: "neutral" as Tone };

/** How far into the story a trial went, as one phrase and a tone: none, started, engaged (the server's bar), done. */
export function storyStage(item: Pick<TrialItem, "story">, engagedAt: number): { label: string; tone: Tone } {
  const { acted_count: acted, total } = item.story;
  if (!acted) return { label: "Not started", tone: "neutral" };
  if (acted >= total) return { label: "Closed the whole loop", tone: "good" };
  if (acted >= engagedAt) return { label: "Engaged", tone: "good" };
  return { label: "Started", tone: "warning" };
}

/** How many active trials acted in each chapter, in story order: where trials stop. */
export function chapterFunnel(data: TrialOverview | null | undefined): Slice[] {
  if (!data) return [];
  return data.chapters.map((chapter) => ({
    key: chapter.code,
    label: `${chapter.number}. ${chapter.title}`,
    count: data.summary.chapters[chapter.code] ?? 0,
    tone: "neutral" as Tone,
  }));
}

/** The chapter title a trial should try next, or a closing line. */
export function nextChapterTitle(item: Pick<TrialItem, "story">, chapters: TrialOverview["chapters"]): string {
  if (!item.story.next) return "Every chapter tried";
  const chapter = chapters.find((entry) => entry.code === item.story.next);
  return chapter ? `${chapter.number}. ${chapter.title}` : item.story.next;
}

/** Trials that need a person's attention first: ending soon and not engaged, then the least progress. */
export function attentionOrder(items: readonly TrialItem[], engagedAt: number): TrialItem[] {
  const rank = (item: TrialItem) =>
    item.state === "ENDED" ? 3 : item.state === "ENDING_SOON" && item.story.acted_count < engagedAt ? 0 : 1;
  return [...items].sort(
    (left, right) =>
      rank(left) - rank(right) || left.story.acted_count - right.story.acted_count || left.days_left - right.days_left,
  );
}
