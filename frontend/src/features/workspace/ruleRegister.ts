// B4: the rule register, read-only (backend/app/rule_register/router.py). Every rule MDARIX applies, its source,
// version and the dates it is in force; on a market conclusion, the rules used at the event, today and when decided.
import { formatDay } from "../../app/dates";

export type RuleState = "IN_FORCE" | "SCHEDULED" | "RETIRED" | "REPLACED";

export type RuleView = {
  code: string;
  rule: string;
  version: number;
  version_words: string;
  kind: string;
  kind_label: string;
  market: string | null;
  market_label: string;
  title: string;
  plain: string;
  source: Array<{ id: string; short: string; title: string; clause: string }>;
  effective_from: string | null;
  effective_to: string | null;
  state: RuleState;
  law_in_force_from: string | null;
  change: { kind: string; reason?: string; corrects?: string };
  approved_by: string | null;
  approved_on: string | null;
  held_as: "DATA" | "CODE";
  pinned: boolean;
  fingerprint: string | null;
  starter_mark: string;
};

export type RuleList = {
  summary: { rules: number; markets: number; held_as_data: number; starter_mark: string };
  kinds: Array<{ code: string; label: string }>;
  as_at: string | null;
  items: RuleView[];
};

export type RuleDetail = RuleView & {
  implementation_held: string;
  logic: {
    defined: string[];
    reportable: string[];
    report_type: string[];
    not_asked: string[];
    report_types: Array<{ code: string; label: string; days: number | null; basis: string }>;
    counting: { authority_zone: string | null; awareness_is_day_one: boolean; words?: string };
    questions: Array<{ id: string; text: string; clause: string }>;
  } | null;
  history: RuleView[];
};

export type RulesApplied = { rules: Array<{ id: string; state: "APPLIES" | "COULD_APPLY" }>; type_row: string | null };

/** The "Rules used" panel of a market conclusion (C4): three lines kept apart. Null while the register is off. */
export type RulesUsed = {
  at_event: { code: string; title: string; day: string | null; rules_applied: RulesApplied | null };
  today: { code: string; same: boolean };
  decided: {
    floor_code: string | null;
    before_register: boolean;
    rules_applied: RulesApplied | null;
    date_calc: {
      due_date?: string | null;
      days?: number;
      day_basis?: string;
      window?: string;
      source?: string | null;
    } | null;
    fingerprint: string | null;
  } | null;
};

export const STATE_LABELS: Record<RuleState, string> = {
  IN_FORCE: "In force",
  SCHEDULED: "Scheduled",
  RETIRED: "Retired",
  REPLACED: "Replaced",
};

/** "From the start", "From 1 Mar 2027", "From the start to 28 Feb 2027". */
export function inForceText(rule: Pick<RuleView, "effective_from" | "effective_to">): string {
  const from = rule.effective_from ? `From ${formatDay(rule.effective_from)}` : "From the start";
  return rule.effective_to ? `${from} to ${formatDay(rule.effective_to)}` : from;
}

/** The register's address with its filters (empty ones left out). */
export function registerPath(filters: { market?: string; kind?: string; asAt?: string }): string {
  const query = new URLSearchParams();
  if (filters.market) query.set("market", filters.market);
  if (filters.kind) query.set("kind", filters.kind);
  if (filters.asAt) query.set("as_at", filters.asAt);
  const text = query.toString();
  return `/api/v1/rule-register${text ? `?${text}` : ""}`;
}

/** The rules that decided, in words: "F-US-1 applies; F-US-2 could apply". */
export function appliedText(applied: RulesApplied | null | undefined): string {
  if (!applied) return "Rules applied: not recorded";
  if (!applied.rules.length) return "No floor rule applies to these answers";
  return applied.rules
    .map((rule) => `${rule.id} ${rule.state === "APPLIES" ? "applies" : "could apply (an answer is Unknown)"}`)
    .join("; ");
}

/** The three lines of the panel, as plain sentences (null: the register is off; nothing to show). */
export function rulesUsedLines(used: RulesUsed | null | undefined) {
  if (!used) return null;
  const day = used.at_event.day ? formatDay(used.at_event.day) : null;
  const decided = used.decided;
  return {
    atEvent: `${used.at_event.code}${day ? `, in force on the awareness day (${day})` : ""}. ${appliedText(
      used.at_event.rules_applied,
    )}.`,
    today: used.today.same
      ? `${used.today.code}: the same.`
      : `${used.today.code}: differs; not applied to this event${day ? ` (aware on ${day})` : ""}.`,
    decided: !decided
      ? "Not signed yet."
      : decided.before_register
        ? "Signed before the rule register: it keeps what it signed."
        : `Signed under ${decided.floor_code}. ${appliedText(decided.rules_applied)}.${
            decided.date_calc?.due_date
              ? ` Due ${formatDay(decided.date_calc.due_date)} (${decided.date_calc.window ?? "the regulation"}).`
              : ""
          }`,
  };
}
