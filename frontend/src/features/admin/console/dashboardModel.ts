// Pure aggregation for the Platform Administrator overview dashboard.
// Every figure is derived from an administrator API response; nothing is estimated or invented.

export type Tone = "good" | "warning" | "serious" | "critical" | "neutral";

export type CustomerRow = {
  id?: string;
  name?: string;
  tenant_key?: string;
  status?: string | null;
  plan_code?: string | null;
  plan_name?: string | null;
  seat_usage?: number | null;
  seat_cap?: number | null;
  expires_at?: string | null;
  data_region?: string | null;
  health_status?: string | null;
  last_activity?: string | null;
};

export type ExpiringSubscription = { tenant_id: string; status: string; days_remaining: number };
export type IntegrationRun = { status?: string | null; started_at?: string | null; records_rejected?: number | null };
export type AuditRow = { action?: string; entity_type?: string | null; actor_ref?: string | null; created_at?: string };

export type Slice = { key: string; label: string; count: number; tone: Tone };
export type DayCount = { date: string; label: string; count: number };

const upper = (value: unknown) =>
  String(value ?? "")
    .trim()
    .toUpperCase();

const TENANT_STATUS: Record<string, { label: string; tone: Tone; order: number }> = {
  ACTIVE: { label: "Active", tone: "good", order: 0 },
  PROVISIONED: { label: "Provisioned", tone: "good", order: 1 },
  PROVISIONING: { label: "Provisioning", tone: "neutral", order: 2 },
  PENDING: { label: "Pending", tone: "neutral", order: 3 },
  TRIAL: { label: "Trial", tone: "neutral", order: 4 },
  SUSPENDED: { label: "Suspended", tone: "serious", order: 5 },
  EXPIRED: { label: "Expired", tone: "critical", order: 6 },
  ARCHIVED: { label: "Archived", tone: "neutral", order: 7 },
};

export function titleCase(value: string) {
  return value
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function tenantStatusSlices(customers: CustomerRow[]): Slice[] {
  const counts = new Map<string, number>();
  for (const customer of customers) {
    const key = upper(customer.status) || "UNKNOWN";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([key, count]) => ({
      key,
      count,
      label: TENANT_STATUS[key]?.label ?? titleCase(key),
      tone: TENANT_STATUS[key]?.tone ?? ("neutral" as Tone),
      order: TENANT_STATUS[key]?.order ?? 99,
    }))
    .sort((a, b) => a.order - b.order || b.count - a.count)
    .map(({ order: _order, ...slice }) => slice);
}

export function isActiveTenant(customer: CustomerRow) {
  return ["ACTIVE", "PROVISIONED"].includes(upper(customer.status));
}

/** Ordered expiry windows for subscriptions; an item lands in the first window it fits. */
export function expiryBuckets(subscriptions: ExpiringSubscription[]): Slice[] {
  const buckets: Slice[] = [
    { key: "expired", label: "Expired or in grace", count: 0, tone: "critical" },
    { key: "7", label: "Within 7 days", count: 0, tone: "serious" },
    { key: "30", label: "Within 30 days", count: 0, tone: "warning" },
    { key: "90", label: "Within 90 days", count: 0, tone: "neutral" },
    { key: "later", label: "Later than 90 days", count: 0, tone: "good" },
  ];
  for (const subscription of subscriptions) {
    const days = Number(subscription.days_remaining);
    const status = upper(subscription.status);
    const index =
      status === "EXPIRED" || status === "GRACE" || days < 0 ? 0 : days <= 7 ? 1 : days <= 30 ? 2 : days <= 90 ? 3 : 4;
    buckets[index].count += 1;
  }
  return buckets;
}

export function planMix(customers: CustomerRow[]): Slice[] {
  const counts = new Map<string, number>();
  for (const customer of customers) {
    const label = customer.plan_name || customer.plan_code || "No active plan";
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([label, count]) => ({ key: label, label, count, tone: "neutral" as Tone }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

const dayKey = (date: Date) => date.toISOString().slice(0, 10);

/** Counts per calendar day (UTC) for the `days` days ending on `today`, oldest first; empty days are zero. */
/** The day a daily chart should end on: today, or the latest event when nothing happened in the window
 * (an older data set would otherwise show an empty chart). Without valid dates it is today. */
export function chartWindowEnd(
  timestamps: Array<string | null | undefined>,
  days: number,
  today = new Date(),
): { end: Date; shifted: boolean } {
  const times = timestamps
    .map((value) => (value ? new Date(value).getTime() : Number.NaN))
    .filter((value) => !Number.isNaN(value));
  if (!times.length) return { end: today, shifted: false };
  const latest = Math.max(...times);
  const windowStart = today.getTime() - days * 86_400_000;
  return latest < windowStart ? { end: new Date(latest), shifted: true } : { end: today, shifted: false };
}

export function dailyCounts(
  timestamps: Array<string | null | undefined>,
  days: number,
  today = new Date(),
): DayCount[] {
  const end = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate()));
  const series: DayCount[] = [];
  const index = new Map<string, DayCount>();
  for (let offset = days - 1; offset >= 0; offset -= 1) {
    const date = new Date(end.getTime() - offset * 86_400_000);
    const entry = {
      date: dayKey(date),
      label: date.toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" }),
      count: 0,
    };
    series.push(entry);
    index.set(entry.date, entry);
  }
  for (const timestamp of timestamps) {
    if (!timestamp) continue;
    const parsed = new Date(timestamp);
    if (Number.isNaN(parsed.getTime())) continue;
    const entry = index.get(dayKey(parsed));
    if (entry) entry.count += 1;
  }
  return series;
}

const FAILED_RUN = ["FAILED", "FAILURE", "ERROR", "DEAD_LETTERED", "TIMED_OUT"];
const SUCCEEDED_RUN = ["SUCCEEDED", "SUCCESS", "COMPLETED", "RECONCILED"];

export function runOutcomes(runs: IntegrationRun[]) {
  let succeeded = 0;
  let failed = 0;
  for (const run of runs) {
    const status = upper(run.status);
    if (SUCCEEDED_RUN.includes(status)) succeeded += 1;
    else if (FAILED_RUN.includes(status)) failed += 1;
  }
  const finished = succeeded + failed;
  return {
    total: runs.length,
    succeeded,
    failed,
    inProgress: runs.length - finished,
    successRate: finished ? Math.round((succeeded / finished) * 100) : null,
  };
}

export type Signal = { key: string; label: string; value: number | string | null; tone: Tone; detail: string };

/** Health signals from the summary endpoints. A missing source yields a null value, never a pass. */
export function healthSignals(sources: {
  health?: { metrics?: Record<string, number> } | null;
  operations?: { metrics?: Record<string, number>; worker?: { heartbeat?: string } } | null;
  security?: { metrics?: Record<string, number> } | null;
  ai?: { configured?: boolean; provider?: string | null } | null;
  retention?: { status?: string; expired?: number } | null;
  smtp?: { configured?: boolean } | null;
}): Signal[] {
  const h = sources.health?.metrics;
  const o = sources.operations?.metrics;
  const s = sources.security?.metrics;
  const count = (value: number | undefined, label: string, key: string, badTone: Tone, detail: string): Signal => ({
    key,
    label,
    value: value ?? null,
    tone: value === undefined ? "neutral" : value > 0 ? badTone : "good",
    detail: value === undefined ? "Source unavailable" : detail,
  });
  const worker = sources.operations?.worker?.heartbeat;
  return [
    count(h?.connector_failures, "Connector failures", "connectors", "critical", "Failed or degraded connector events"),
    count(
      o?.outbox_dead_lettered,
      "Dead-lettered jobs",
      "deadLetter",
      "critical",
      "Outbox events that exhausted retries",
    ),
    count(o?.outbox_pending, "Queued jobs", "queue", "warning", "Outbox events waiting to publish"),
    count(
      s?.security_events ?? h?.security_events,
      "Security events",
      "security",
      "serious",
      "Denied or unauthorized access",
    ),
    count(h?.invitation_failures, "Invitation failures", "invites", "serious", "Invitation or activation failures"),
    count(h?.mapping_issues, "Mappings to review", "mappings", "warning", "Draft, blocked or failed mappings"),
    {
      key: "ai",
      label: "AI provider",
      value: sources.ai ? (sources.ai.configured ? "Configured" : "Not configured") : null,
      tone: !sources.ai ? "neutral" : sources.ai.configured ? "good" : "warning",
      detail: sources.ai ? (sources.ai.provider ?? "Provider not reported") : "Source unavailable",
    },
    {
      key: "retention",
      label: "Audit retention",
      value: sources.retention ? titleCase(sources.retention.status ?? "UNKNOWN") : null,
      tone: !sources.retention ? "neutral" : upper(sources.retention.status) === "HEALTHY" ? "good" : "serious",
      detail: sources.retention ? `${sources.retention.expired ?? 0} events past retention` : "Source unavailable",
    },
    {
      key: "smtp",
      label: "Email delivery",
      value: sources.smtp ? (sources.smtp.configured ? "Configured" : "Not configured") : null,
      tone: !sources.smtp ? "neutral" : sources.smtp.configured ? "good" : "warning",
      detail: sources.smtp ? "SMTP settings for invitations and reminders" : "Source unavailable",
    },
    {
      key: "worker",
      label: "Worker heartbeat",
      value: worker ? titleCase(worker) : null,
      tone: "neutral",
      detail: worker ? "Background worker health is not reported yet" : "Source unavailable",
    },
  ];
}

const TONE_RANK: Record<Tone, number> = { critical: 4, serious: 3, warning: 2, neutral: 1, good: 0 };

export function worstTone(tones: Tone[]): Tone {
  return tones.reduce<Tone>((worst, tone) => (TONE_RANK[tone] > TONE_RANK[worst] ? tone : worst), "good");
}

export type AttentionItem = { key: string; tone: Tone; title: string; detail: string };

export function attentionItems(
  customers: CustomerRow[],
  subscriptions: ExpiringSubscription[],
  alerts: Array<{ code?: string; label?: string; count?: number; severity?: string }>,
): AttentionItem[] {
  const items: AttentionItem[] = [];
  for (const alert of alerts) {
    items.push({
      key: `alert-${alert.code}`,
      tone: upper(alert.severity) === "HIGH" ? "critical" : "warning",
      title: alert.label ?? titleCase(alert.code ?? "Alert"),
      detail: `${alert.count ?? 0} open`,
    });
  }
  for (const customer of customers) {
    const status = upper(customer.status);
    if (status === "SUSPENDED" || status === "EXPIRED")
      items.push({
        key: `tenant-${customer.id}`,
        tone: status === "EXPIRED" ? "critical" : "serious",
        title: `${customer.name ?? customer.tenant_key ?? "Tenant"} is ${status.toLowerCase()}`,
        detail: customer.tenant_key ?? "Tenant lifecycle",
      });
    if (customer.seat_cap && (customer.seat_usage ?? 0) > customer.seat_cap)
      items.push({
        key: `seats-${customer.id}`,
        tone: "warning",
        title: `${customer.name ?? "Tenant"} is over its seat cap`,
        detail: `${customer.seat_usage} of ${customer.seat_cap} seats`,
      });
  }
  const names = new Map(customers.map((customer) => [customer.id, customer.name ?? customer.tenant_key]));
  for (const subscription of subscriptions) {
    const days = Number(subscription.days_remaining);
    if (days > 30) continue;
    const name = names.get(subscription.tenant_id) ?? "A tenant";
    items.push({
      key: `sub-${subscription.tenant_id}-${days}`,
      tone: days < 0 || upper(subscription.status) !== "ACTIVE" ? "critical" : days <= 7 ? "serious" : "warning",
      title: days < 0 ? `${name}: subscription expired` : `${name}: subscription ends in ${days} days`,
      detail: `Subscription ${titleCase(subscription.status)}`,
    });
  }
  return items.sort((a, b) => TONE_RANK[b.tone] - TONE_RANK[a.tone]);
}

export function compactNumber(value: number) {
  return new Intl.NumberFormat(undefined, { notation: value >= 10_000 ? "compact" : "standard" }).format(value);
}
