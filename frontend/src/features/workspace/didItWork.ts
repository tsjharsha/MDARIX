// B5b: "Did it work?" (backend/app/closed_loop/service.py): what happened after an investigation's signed decision,
// counted from the records. The server owns every rule and every word; the screen shows its words, its denominators
// (or "units unknown") and its limits, and never says an action worked: only a signed effectiveness check does.
import type { Tone } from "../admin/console/dashboardModel";

export type LoopRef = { id: string; ref: string };
export type LoopGroup = {
  name: string;
  before: number;
  after: number;
  basis: "SHIPPED" | "RELEASED" | "UNKNOWN";
  counts_only: boolean;
  unknown_lots?: number;
  lots_in_group?: number;
  lots_with_units_unknown?: number;
  result: string;
  word: string;
  rate_before?: number | null;
  rate_after?: number | null;
  per_30_days_before?: number | null;
  per_30_days_after?: number | null;
  upper_bound_after?: number | null;
  before_complaints?: LoopRef[];
  after_complaints?: LoopRef[];
  lot_unknown?: number;
};
export type LoopLot = {
  id: string;
  ref: string;
  version: string;
  released: string | null;
  cohort: "before" | "after";
  after: number;
  units: number | null;
};
export type LoopAction = {
  kind: "CAPA" | "FIELD_ACTION" | "PRODUCT_CHANGE";
  on: string;
  ref: string;
  follow_up?: string;
  measured_from?: "check" | "decision";
  window: { before: [string, string]; after: [string, string]; after_days: number; days: number };
  by_version: LoopGroup[];
  lot_cohorts?: LoopGroup;
  lots?: LoopLot[];
  new_vs_old?: LoopGroup;
};
export type LoopLater = LoopRef & { version?: string | null; event_on?: string | null; harm?: boolean };
export type DidItWork = {
  rule_version: number;
  notice: string;
  limits: string[];
  superseded: Array<{ id: string; ref: string; decided_at: string | null }>;
  decision: { id: string; ref: string; decided_at: string; outcome: string | null } | null;
  scope?: {
    versions: LoopRef[];
    new_versions: LoopRef[];
    problems: string[];
    complaints: number;
  };
  later?: { count: number; complaints: LoopLater[]; version_unknown: { count: number; complaints: LoopLater[] } };
  capas?: Array<{
    id: string;
    ref: string;
    title: string;
    status: string;
    checks: Array<{ round: number; status: string; planned_on: string | null; signed_at: string | null }>;
  }>;
  field_actions?: Array<{
    follow_up: string;
    reference: string | null;
    kind: string | null;
    effective_on: string | null;
    lot_ids: string[];
    version_ids: string[];
  }>;
  actions?: LoopAction[];
};

export const didItWorkPath = (investigationId: string) =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/did-it-work`;

const KINDS: Record<LoopAction["kind"], string> = {
  CAPA: "CAPA",
  FIELD_ACTION: "Field action",
  PRODUCT_CHANGE: "New version",
};

/** "CAPA SAMPLE-CAPA-02 · measured from the decision": which action date the comparison is about. */
export function actionHeading(action: LoopAction): string {
  const from = action.measured_from === "decision" ? " · measured from the decision (no check planned yet)" : "";
  return `${KINDS[action.kind] ?? action.kind} ${action.ref}${from}`;
}

/** Words, never verdicts: "More" asks for a look; nothing is shown as good or bad. */
export const resultTone = (result: string): Tone => (result === "MORE" ? "warning" : "neutral");

const rate = (value: number | null | undefined) => (value === null || value === undefined ? "–" : String(value));

/** The counts with their rate, or by calendar days when units are unknown (never a rate from partial units). */
export function countsLine(group: LoopGroup): string {
  if (group.counts_only)
    return (
      `${group.before} before · ${group.after} after, by calendar days ` +
      `(${rate(group.per_30_days_before)} vs ${rate(group.per_30_days_after)} per 30 days)`
    );
  const zero =
    group.after === 0 && group.upper_bound_after
      ? `; 0 complaints, but with this exposure the rate could still be up to ${group.upper_bound_after}`
      : "";
  return (
    `${group.before} before (${rate(group.rate_before)}) · ${group.after} after (${rate(group.rate_after)}) ` +
    `per 1,000 unit-months${zero}`
  );
}

/** Where the denominator came from, or "units unknown for X of Y lots". */
export function denominatorLine(group: LoopGroup): string {
  if (group.basis === "SHIPPED") return "Units shipped, with ship dates";
  if (group.basis === "RELEASED") return "Units released, with release dates";
  const unknown = group.lots_with_units_unknown ?? group.unknown_lots ?? 0;
  const lots = group.lots_in_group;
  return unknown && lots ? `Units unknown for ${unknown} of ${lots} lots` : "Units unknown";
}

/** The comparison windows: "before 1 Feb–1 May · after 2 May–today (45 days)". */
export function windowLine(action: LoopAction, day: (value: string) => string): string {
  const { before, after, after_days } = action.window;
  return `Before ${day(before[0])} – ${day(before[1])} · after ${day(after[0])} – ${day(after[1])} (${after_days} days)`;
}

/** The actions for one CAPA only (the block on its effectiveness check). */
export const actionsFor = (view: DidItWork, capaRef: string | null | undefined) =>
  (view.actions ?? []).filter((action) => !capaRef || (action.kind === "CAPA" && action.ref === capaRef));
