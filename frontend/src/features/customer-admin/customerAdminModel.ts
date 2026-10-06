// Pure aggregation for the Customer Administrator overview. Figures come only from tenant-scoped API responses.
import { titleCase, type Slice, type Tone } from "../admin/console/dashboardModel";
import type { Section } from "./context";

export type TenantUser = { id: string; email?: string; display_name?: string; role?: string; status?: string };

const USER_STATUS: Record<string, { label: string; tone: Tone; order: number }> = {
  ACTIVE: { label: "Active", tone: "good", order: 0 },
  INVITED: { label: "Invited", tone: "neutral", order: 1 },
  PENDING_ACTIVATION: { label: "Pending activation", tone: "neutral", order: 2 },
  SUSPENDED: { label: "Suspended", tone: "serious", order: 3 },
  LOCKED: { label: "Locked", tone: "critical", order: 4 },
  OFFBOARDED: { label: "Offboarded", tone: "neutral", order: 5 },
};

const code = (value: unknown) =>
  String(value ?? "")
    .trim()
    .toUpperCase();

export function userStatusSlices(users: TenantUser[]): Slice[] {
  const counts = new Map<string, number>();
  for (const user of users) {
    const key = code(user.status) || "UNKNOWN";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([key, count]) => ({ key, count, meta: USER_STATUS[key] }))
    .sort((a, b) => (a.meta?.order ?? 99) - (b.meta?.order ?? 99) || b.count - a.count)
    .map(({ key, count, meta }) => ({
      key,
      count,
      label: meta?.label ?? titleCase(key),
      tone: meta?.tone ?? "neutral",
    }));
}

export function userTone(status: unknown): Tone {
  return USER_STATUS[code(status)]?.tone ?? "neutral";
}

export function roleMix(users: TenantUser[]): Slice[] {
  const counts = new Map<string, number>();
  for (const user of users) {
    if (code(user.status) === "OFFBOARDED") continue;
    const label = user.role ? titleCase(user.role) : "No role";
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([label, count]) => ({ key: label, label, count, tone: "neutral" as Tone }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

/** Seat usage against the plan limit; null limit means the plan does not declare one. */
export function seatUsage(used: number, limit: number | null | undefined) {
  if (!limit || limit <= 0) return { used, limit: null, share: null, tone: "neutral" as Tone };
  const share = used / limit;
  const tone: Tone = share > 1 ? "critical" : share >= 0.9 ? "serious" : share >= 0.75 ? "warning" : "good";
  return { used, limit, share, tone };
}

export type CustomerAttention = { key: string; tone: Tone; title: string; detail: string; section: Section };

export function customerAttention(input: {
  alerts: Array<{ code?: string; label?: string; count?: number; severity?: string }>;
  users: TenantUser[];
  failedRuns: number;
  seats: ReturnType<typeof seatUsage>;
  daysToExpiry: number | null;
}): CustomerAttention[] {
  const items: CustomerAttention[] = input.alerts.map((alert) => ({
    key: `alert-${alert.code}`,
    tone: code(alert.severity) === "HIGH" ? "critical" : "warning",
    title: alert.label ?? titleCase(alert.code ?? "Alert"),
    detail: `${alert.count ?? 0} open`,
    section: code(alert.code).includes("SECURITY")
      ? "Security"
      : code(alert.code).includes("CONNECTOR")
        ? "Integrations"
        : code(alert.code).includes("MAPPING")
          ? "Data Mapping"
          : code(alert.code).includes("INVIT")
            ? "Users"
            : "Audit",
  }));
  const locked = input.users.filter((user) => ["LOCKED", "SUSPENDED"].includes(code(user.status))).length;
  if (locked)
    items.push({
      key: "users-blocked",
      tone: "serious",
      title: `${locked} ${locked === 1 ? "user is" : "users are"} suspended or locked`,
      detail: "Review whether access should be restored or removed",
      section: "Users",
    });
  if (input.failedRuns)
    items.push({
      key: "runs-failed",
      tone: "critical",
      title: `${input.failedRuns} integration ${input.failedRuns === 1 ? "run" : "runs"} failed`,
      detail: "Check the connection and re-run the sync",
      section: "Integrations",
    });
  if (input.seats.limit !== null && input.seats.tone !== "good")
    items.push({
      key: "seats",
      tone: input.seats.tone,
      title: `${input.seats.used} of ${input.seats.limit} licensed seats in use`,
      detail: "Offboard unused accounts or request more seats",
      section: "Plan & Subscription",
    });
  if (input.daysToExpiry !== null && input.daysToExpiry <= 60)
    items.push({
      key: "expiry",
      tone: input.daysToExpiry < 0 ? "critical" : input.daysToExpiry <= 14 ? "serious" : "warning",
      title: input.daysToExpiry < 0 ? "Subscription has expired" : `Subscription ends in ${input.daysToExpiry} days`,
      detail: "Request a renewal before access is restricted",
      section: "Plan & Subscription",
    });
  const rank: Record<Tone, number> = { critical: 4, serious: 3, warning: 2, neutral: 1, good: 0 };
  return items.sort((a, b) => rank[b.tone] - rank[a.tone]);
}

/**
 * When the organization's subscription ends, and how many whole days are left: from the lifecycle answer
 * (`subscription.expires_at`, or `expires_at`) or, during a free trial, the trial status. Null when the subscription
 * has no end date the console can read.
 */
export function subscriptionEnd(
  lifecycle: { expires_at?: string | null; subscription?: { expires_at?: string | null } | null } | null,
  trial: { is_trial?: boolean; expires_at?: string | null; days_left?: number } | null,
  now = new Date(),
): { endsAt: string; daysLeft: number; trial: boolean } | null {
  const fromLifecycle = lifecycle?.subscription?.expires_at ?? lifecycle?.expires_at ?? null;
  const fromTrial = trial?.is_trial ? (trial.expires_at ?? null) : null;
  const endsAt = fromLifecycle ?? fromTrial;
  const time = endsAt ? Date.parse(endsAt) : Number.NaN;
  if (!endsAt || Number.isNaN(time)) return null;
  const daysLeft =
    !fromLifecycle && typeof trial?.days_left === "number"
      ? trial.days_left
      : Math.max(0, Math.ceil((time - now.getTime()) / 86_400_000));
  return { endsAt, daysLeft, trial: !fromLifecycle && !!fromTrial };
}
