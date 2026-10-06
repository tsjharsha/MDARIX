// Pure aggregation for the user workspace overview. Every figure comes from tenant-scoped API responses.
import { titleCase, type Slice, type Tone } from "../admin/console/dashboardModel";

const code = (value: unknown) =>
  String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/ /g, "_");

const CLOSED = ["CLOSED", "RESOLVED", "COMPLETED", "CANCELLED", "ARCHIVED"];

/** Today's calendar date where the person is (YYYY-MM-DD), not in UTC: late in the evening west of Greenwich, or
 * early in the morning east of it, the UTC date is already another day. */
export function localDay(date = new Date()): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** The workspace opens on the current state of the records, with today's date ready for point-in-time views. */
export function defaultTimeContext(today = new Date()): { asOf: string; mode: "current" } {
  return { asOf: localDay(today), mode: "current" };
}

export type DashboardStatus = "loading" | "error" | "empty" | "attention" | "clear";

/**
 * What the dashboard's headline may say. "Nothing needs your attention" is said only when the data was actually
 * read and the organization has records; a failed source or an empty organization is said as such.
 */
export function dashboardStatus(input: {
  states: Array<"loading" | "ready" | "error" | "forbidden">;
  counts: Record<string, number | undefined> | null;
  attention: number;
}): DashboardStatus {
  if (input.states.includes("loading")) return "loading";
  if (input.states.includes("error")) return "error";
  const counts = input.counts ?? {};
  const records = ["products", "complaints", "investigations", "evidence"].reduce(
    (total, key) => total + (Number(counts[key]) || 0),
    0,
  );
  if (input.counts && records === 0) return "empty";
  return input.attention ? "attention" : "clear";
}

/** Keep the current selection when it is still listed; otherwise the first open case, else the first case. */
export function preferredInvestigationId(items: Array<{ id?: unknown; status?: unknown }>, selected: string): string {
  if (items.some((item) => String(item.id) === selected)) return selected;
  const open = items.find((item) => isOpenInvestigation(item.status));
  return String((open ?? items[0])?.id ?? "");
}

export function isOpenInvestigation(status: unknown) {
  return !CLOSED.includes(code(status));
}

/** Count records by one field, keeping the label readable and a stable most-first order. */
export function countBy(rows: Array<Record<string, unknown>>, field: string, missing = "Not recorded"): Slice[] {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const label = row[field] ? titleCase(String(row[field])) : missing;
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([label, count]) => ({ key: label, label, count, tone: "neutral" as Tone }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

const INVESTIGATION_TONE: Record<string, Tone> = {
  OPEN: "warning",
  IN_PROGRESS: "warning",
  UNDER_REVIEW: "neutral",
  CLOSED: "good",
  RESOLVED: "good",
};

export function investigationStatusSlices(rows: Array<Record<string, unknown>>): Slice[] {
  return countBy(rows, "status", "Unknown").map((slice) => ({
    ...slice,
    tone: INVESTIGATION_TONE[code(slice.label)] ?? "neutral",
  }));
}

export type WorkspaceAttention = {
  key: string;
  tone: Tone;
  title: string;
  detail: string;
  section: string;
  tab?: string;
};

export function workspaceAttention(input: {
  openInvestigations: number;
  unreliableEvidence: number;
  limitations: Array<{ code: string; severity: string }>;
  highSeveritySignals: number;
}): WorkspaceAttention[] {
  const items: WorkspaceAttention[] = [];
  if (input.highSeveritySignals)
    items.push({
      key: "signals",
      tone: "serious",
      title: `${input.highSeveritySignals} high-severity ${input.highSeveritySignals === 1 ? "signal" : "signals"}`,
      detail: "Review recent complaints",
      section: "Signals",
      tab: "All signals",
    });
  if (input.openInvestigations)
    items.push({
      key: "investigations",
      tone: "warning",
      title: `${input.openInvestigations} open ${input.openInvestigations === 1 ? "investigation" : "investigations"}`,
      detail: "Continue the case work",
      section: "Investigations",
    });
  if (input.unreliableEvidence)
    items.push({
      key: "evidence",
      tone: "warning",
      title: `${input.unreliableEvidence} evidence ${input.unreliableEvidence === 1 ? "record needs" : "records need"} verification`,
      detail: "Reliability is not yet confirmed",
      section: "Evidence",
    });
  const serious = input.limitations.filter((item) => ["HIGH", "CRITICAL"].includes(code(item.severity))).length;
  if (serious)
    items.push({
      key: "limitations",
      tone: "serious",
      title: `${serious} significant data ${serious === 1 ? "limitation" : "limitations"}`,
      detail: "Read these before drawing conclusions",
      section: "Trust & Audit",
      tab: "Data limitations",
    });
  const rank: Record<Tone, number> = { critical: 4, serious: 3, warning: 2, neutral: 1, good: 0 };
  return items.sort((a, b) => rank[b.tone] - rank[a.tone]);
}

export const VERIFIED_RELIABILITY = ["VERIFIED", "CONFIRMED", "RELIABLE", "VALIDATED", "REVIEWED", "HIGH"];
export const HIGH_SEVERITY = ["HIGH", "CRITICAL", "SERIOUS", "MAJOR", "SEVERE"];
export const isVerified = (value: unknown) => VERIFIED_RELIABILITY.includes(code(value));
export const isHighSeverity = (value: unknown) => HIGH_SEVERITY.includes(code(value));
