// The Platform Admin trial overview (GET /api/v1/platform-admin/trials, backend/app/trial/story.py): every free trial
// still holding data, its dates and usage, how far into the story it went (chapters it acted in, from records it
// created, never page views) and its feedback. The figures cover every trial; the table is one page of them, filtered
// and sorted by the server. Pure rules for the screen (customers/TrialsOverview.tsx).
import { sortParams, type SortState } from "../../../app/tableSort";
import type { Slice, Tone } from "../console/dashboardModel";

export type TrialState = "ACTIVE" | "ENDING_SOON" | "ENDED";

export type TrialPerson = { id?: string; email: string; name: string | null; status: string };

/** One change the trial's owner made to their team (backend/app/trial/story.py, from the trial's audit trail). */
export type TrialTeamChange = { change: string; person: string | null; at: string | null };

const TEAM_CHANGE: Record<string, string> = {
  REMOVED: "Removed",
  INVITATION_WITHDRAWN: "Invitation withdrawn:",
  MFA_RESET: "MFA reset:",
};

/** "Removed casey@example.com", "MFA reset: casey@example.com": what the owner did, and to whom. */
export const teamChangeText = (item: TrialTeamChange) =>
  `${TEAM_CHANGE[item.change] ?? item.change} ${item.person ?? "a former colleague"}`;

/**
 * When a trial's data is deleted (backend/app/trial/retention.py): 30 days after the trial ends, or later while an open
 * request asks to move the data into the pilot (held until the request closes, at the latest until ``hold_until``).
 */
export type TrialRetention = {
  /** The one projection's date: null under a legal hold (no date is given until the hold is lifted). */
  earliest_deletion?: string | null;
  hold?: "LEGAL_HOLD" | "MVP_REQUEST" | null;
  delete_after: string;
  original_delete_after: string;
  held_for_mvp_request: boolean;
  hold_until: string;
  mvp_request: { id: string; status: string } | null;
};

/** The deletion line for the Platform Administrator: held for the pilot request, or the day the data is deleted. */
export function retentionText(
  retention: TrialRetention | null | undefined,
  format: (value: string) => string,
  deletedAt?: string | null,
): string | null {
  if (retention?.hold === "LEGAL_HOLD") return "Data kept under a legal hold: no deletion date until it is lifted";
  if (retention?.held_for_mvp_request)
    return `Data held for its pilot request (would have been deleted ${format(retention.original_delete_after)}); deleted ${format(retention.hold_until)} at the latest`;
  const day = retention ? (retention.earliest_deletion ?? retention.delete_after) : deletedAt;
  return day ? `Data deleted ${format(day)}` : null;
}

export type TrialItem = {
  tenant_id: string;
  tenant_business_id?: string | null;
  tenant_key: string;
  name: string;
  owner: TrialPerson | null;
  /** The people holding a seat (active or invited), owner first: Platform Admin may reset one's MFA. */
  people?: TrialPerson[];
  /** The owner's latest removals, withdrawn invitations and MFA resets, newest first. */
  team_changes?: TrialTeamChange[];
  starts_at: string | null;
  expires_at: string;
  /** The end of a grace period given on Plans & Licensing; the trial runs (and counts its days) until then. */
  grace_ends_at?: string | null;
  /** The end has passed but the grace period has not: still running. */
  in_grace?: boolean;
  data_deleted_at: string;
  retention?: TrialRetention | null;
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

/** An ended trial whose data an open pilot request holds says so, instead of "data kept 30 days". */
export const trialBadgeOf = (row: Pick<TrialItem, "state" | "retention">) =>
  row.state === "ENDED" && row.retention?.held_for_mvp_request
    ? { label: "Ended, data held for its pilot request", tone: "warning" as Tone }
    : trialStateOf(row.state);

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
