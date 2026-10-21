// Pure rules for Readiness (the home of the lightweight MVP): how each inspection check reads, what the headline
// says, and where each check opens. The server (/api/v1/readiness, backend/app/readiness_home) reads the records.
import type { Tone } from "../admin/console/dashboardModel";

export type CheckState = "CLEAR" | "ATTENTION" | "CRITICAL" | "NOT_SET";

export type ReadinessCheck = {
  code: string;
  title: string;
  value: number | null;
  state: CheckState;
  detail: string;
  why: string;
  /** The regulatory basis of the check, from the catalog (backend/app/standards.py). */
  basis?: Array<{ id: string; short: string; title: string }>;
  opens: { section: string; tab?: string } | null;
  items: Array<{ id: string; ref: string | null; label?: string | null }>;
};

export type Readiness = {
  as_of: string;
  home: ReadinessCheck[];
  checks: ReadinessCheck[];
  summary: { checks: number; clear: number; attention: number; critical: number; not_set: number };
  note: string;
  /** The disclaimer the screen carries once under the checks' basis. */
  basis_note?: string;
  /** Signals from an import that answered moments ago are still being found: the trend check waits for them. */
  detection_pending?: boolean;
};

/** The catalog ids of a check's basis, for the chips. */
export const basisIds = (check: Pick<ReadinessCheck, "basis">) => (check.basis ?? []).map((item) => item.id);

export const READINESS_PATH = "/api/v1/readiness";
export const SUMMARY_PERIODS = [
  { days: 90, label: "Last 90 days" },
  { days: 180, label: "Last 6 months" },
  { days: 365, label: "Last 12 months" },
] as const;

export const summaryPdfPath = (days: number) => `/api/v1/readiness/summary.pdf?period_days=${days}`;

/** The inspection pack: the summary PDF, every check and every record behind it as CSV, and SHA-256 fingerprints. */
export const inspectionPackPath = (days: number) => `/api/v1/readiness/inspection-pack.zip?period_days=${days}`;

export const CHECK_STATE: Record<CheckState, { label: string; tone: Tone }> = {
  CLEAR: { label: "Clear", tone: "good" },
  ATTENTION: { label: "Needs attention", tone: "warning" },
  CRITICAL: { label: "Critical", tone: "critical" },
  NOT_SET: { label: "Not set up", tone: "serious" },
};

export const checkStateOf = (state: string | null | undefined) =>
  CHECK_STATE[(state ?? "") as CheckState] ?? { label: "—", tone: "neutral" as Tone };

/** The overall readiness in one line, with the tone of the worst check. */
export function readinessHeadline(data: Readiness | null | undefined): { title: string; detail: string; tone: Tone } {
  if (!data) return { title: "Reading your records…", detail: "", tone: "neutral" };
  const { checks, clear, critical, attention, not_set } = data.summary;
  const tone: Tone = critical ? "critical" : attention || not_set ? "warning" : "good";
  if (clear === checks)
    return {
      title: "Ready: every inspection check is clear",
      detail: "Nothing an investigator would find in your complaints, reports, trends or CAPAs today.",
      tone,
    };
  const parts = [
    critical ? `${critical} critical` : "",
    attention ? `${attention} needing attention` : "",
    not_set ? `${not_set} not set up` : "",
  ].filter(Boolean);
  return {
    title: `${clear} of ${checks} inspection checks clear`,
    detail: `${parts.join(", ")}. Each one opens the records behind it.`,
    tone,
  };
}

/** The number a check shows ("—" when it could not be read). */
export const checkValue = (check: Pick<ReadinessCheck, "value">) =>
  check.value === null || check.value === undefined ? "—" : check.value.toLocaleString();

/** The records a check names, as short references ("CMP000031, CMP000032 and 3 more"). */
export function itemsText(check: Pick<ReadinessCheck, "items" | "value">): string {
  const refs = check.items.map((item) => item.ref || item.label).filter((ref): ref is string => !!ref);
  if (!refs.length) return "";
  const shown = refs.slice(0, 3).join(", ");
  const more = Math.max(0, (check.value ?? refs.length) - Math.min(3, refs.length));
  return more ? `${shown} and ${more} more` : shown;
}
