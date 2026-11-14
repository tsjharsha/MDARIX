// Shapes and small rules for Trial organizations (backend/app/access/platform_trials.py). The server decides what
// is allowed; these helpers only word it and keep the drawers from sending what it would refuse anyway.

export const TRIAL_ORGS_PATH = "/api/v1/platform-admin/trial-organizations";
export const EXTENSION_DAYS_MAX = 30;
export const REASON_MIN = 10;

export type TrialCounts = {
  waiting_for_review: number;
  active: number;
  ending_soon: number;
  ended_data_kept: number;
  exit_requests_waiting: number;
  converted_this_month: number;
};

export type TrialState = "ACTIVE" | "ENDING_SOON" | "ENDED" | "ENDED_EARLY" | "DATA_DELETED" | "CONVERTED";

export type ActionState = {
  allowed: boolean;
  reason: string | null;
  days_left?: number;
  pending_request_id?: string | null;
};

export type TrialPersonView = { id: string; email: string; name: string | null; status: string };

export type TrialDetail = {
  tenant_id: string;
  tenant_business_id: string | null;
  tenant_key: string | null;
  name: string;
  status: string | null;
  state: TrialState;
  legal_hold: boolean;
  plan: string | null;
  dates: {
    starts_at: string | null;
    ends_at: string | null;
    ends_words: string | null;
    days_left: number;
    original_ends_at?: string;
    latest_end?: string;
    extension_used?: number;
    extension_left?: number;
    extension_max?: number;
    deletion?: { earliest_deletion: string | null; hold_reason: string | null } | null;
  };
  people: { used: number; owner: TrialPersonView | null; people: TrialPersonView[]; request_email: string | null };
  sample: {
    status: "LOADED" | "REMOVED" | "RESTARTED";
    at: string | null;
    sample_only: boolean;
    sample_counts: Record<string, number>;
    own_counts: Record<string, number>;
    uploaded_rows: number;
  };
  activity: {
    story: { acted_count: number; total: number; last_activity: string | null };
    feedback: unknown;
    demo_request: { status: string; created_at: string } | null;
  };
  exit_request: { id: string; status: string; reason_label: string | null; reason: string | null } | null;
  conversion: { kind: string | null; plan_code: string | null; at: string | null } | null;
  next_step: string;
  actions: { extend: ActionState; end: ActionState; convert: ActionState; delete_data: ActionState };
  ai: { enabled: boolean; line: string };
};

export const STATE_LABELS: Record<TrialState, string> = {
  ACTIVE: "Active",
  ENDING_SOON: "Ending soon",
  ENDED: "Ended, data kept",
  ENDED_EARLY: "Ended early",
  DATA_DELETED: "Data deleted",
  CONVERTED: "Converted",
};

export const stateTone = (state: TrialState): "good" | "warning" | "neutral" | "critical" =>
  state === "ACTIVE" ? "good" : state === "ENDING_SOON" ? "warning" : state === "CONVERTED" ? "good" : "neutral";

export const SAMPLE_LABELS = { LOADED: "Loaded", REMOVED: "Removed by the owner", RESTARTED: "Restarted" } as const;

/** The header strip: five counts, each opening the place where it is handled. */
export const STRIP = [
  { key: "waiting_for_review", label: "Waiting for review", section: "Requests", state: "" },
  { key: "active", label: "Active", section: "Trials", state: "ACTIVE" },
  { key: "ending_soon", label: "Ending within 7 days", section: "Trials", state: "ENDING_SOON" },
  { key: "ended_data_kept", label: "Ended, data kept", section: "Trials", state: "ENDED" },
  { key: "exit_requests_waiting", label: "Requests to end early waiting", section: "Ending and deletion", state: "" },
] as const;

const DAY_MS = 86_400_000;

/** The extension drawer's sentence: the new end and how much of the 30 days it uses. */
export function extensionSentence(
  endsAt: string | null | undefined,
  used: number,
  days: number,
  format: (d: Date) => string,
) {
  if (!endsAt) return "";
  const base = new Date(endsAt).getTime();
  const end = new Date(base + days * DAY_MS);
  return `The trial will end on ${format(end)}. ${used + days} of ${EXTENSION_DAYS_MAX} extension days used.`;
}

/** Whole days 1..left, or why not. */
export function extensionError(days: number, left: number): string | null {
  if (!Number.isInteger(days) || days < 1) return "Extend by at least 1 day.";
  if (days > left) return `This trial can be extended by ${left} more days at most (${EXTENSION_DAYS_MAX} in total).`;
  return null;
}

export const reasonError = (reason: string) =>
  reason.trim().replace(/\s+/g, " ").length < REASON_MIN ? `Give a reason of ${REASON_MIN} characters or more.` : null;

/** The organization's name, typed to confirm a deletion (spacing and capitals do not matter, as on the server). */
export const nameMatches = (typed: string, name: string) =>
  typed.trim().replace(/\s+/g, " ").toLowerCase() === name.trim().replace(/\s+/g, " ").toLowerCase() &&
  typed.trim() !== "";

/** Plans a trial can be converted to: any active plan except the Free Trial. */
export const convertiblePlans = <P extends { code: string; status?: string | null }>(plans: P[]) =>
  plans.filter((plan) => plan.code !== "FREE_TRIAL" && String(plan.status ?? "ACTIVE").toUpperCase() === "ACTIVE");
