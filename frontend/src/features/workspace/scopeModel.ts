// Pure rules for a case's scope (Phase 3): the versioned statement of what an investigation covers (its question,
// product versions, complaints in and out, lots, markets, failure modes, period and objectives). The server keeps
// every version and decides every save; these shape the form, check it before it is sent, and compare versions.
import { safeText } from "../../app/displayId";
import type { Product360 } from "../../app/types";

export type ScopeVersionRef = { id: string; business_id?: string | null; version_identifier?: string | null };
export type ScopeComplaint = {
  id: string;
  business_id?: string | null;
  complaint_identifier?: string | null;
  description?: string | null;
  severity?: string | null;
  product_version?: { business_id?: string | null; version_identifier?: string | null } | null;
  reason?: string | null;
};
export type ScopeLot = { id: string; business_id?: string | null; lot_identifier?: string | null };
export type ScopeFailureMode = { id: string; business_id?: string | null; name?: string | null };

export type ScopeVersion = {
  version: number;
  question?: string | null;
  product_versions?: ScopeVersionRef[] | null;
  included_complaints?: ScopeComplaint[] | null;
  excluded_complaints?: ScopeComplaint[] | null;
  lots?: ScopeLot[] | null;
  /** Lots a person left out of the case, with the reason (the lot impact list, a free trial). */
  excluded_lots?: (ScopeLot & { reason?: string | null })[] | null;
  markets?: string[] | null;
  failure_modes?: ScopeFailureMode[] | null;
  date_from?: string | null;
  date_to?: string | null;
  objectives?: string | null;
  change_reason?: string | null;
  reviews_must_restart?: boolean | null;
  conclusions_invalidated?: boolean | null;
  created_at?: string | null;
  created_by_name?: string | null;
};

export type ScopeVersionSummary = {
  version: number;
  created_at?: string | null;
  created_by_name?: string | null;
  created_role?: string | null;
  change_reason?: string | null;
  reviews_must_restart?: boolean | null;
  conclusions_invalidated?: boolean | null;
};

export type CaseScope = {
  investigation?: { id: string; business_id?: string | null; workflow_state?: string | null } | null;
  current?: ScopeVersion | null;
  versions?: ScopeVersionSummary[] | null;
};

/** One entry of a save's diff: a business ID, or the record it names. */
export type ScopeDiffEntry =
  | string
  | {
      id?: string | null;
      business_id?: string | null;
      complaint_identifier?: string | null;
      version_identifier?: string | null;
    };

export type ScopeDiff = {
  added_complaints?: ScopeDiffEntry[] | null;
  removed_complaints?: ScopeDiffEntry[] | null;
  newly_excluded?: ScopeDiffEntry[] | null;
  versions_added?: ScopeDiffEntry[] | null;
  versions_removed?: ScopeDiffEntry[] | null;
  question_changed?: boolean | null;
};

export type ScopeSaveResult = { scope: ScopeVersion; diff?: ScopeDiff | null; warnings?: string[] | null };

export type ScopeForm = {
  question: string;
  versionIds: string[];
  included: string[];
  excluded: Array<{ id: string; reason: string }>;
  lotIds: string[];
  markets: string[];
  failureModeIds: string[];
  dateFrom: string;
  dateTo: string;
  objectives: string;
  changeReason: string;
  reviewsMustRestart: boolean;
  conclusionsInvalidated: boolean;
};

export const QUESTION_MIN = 10;
export const QUESTION_MAX = 2000;
export const EXCLUSION_REASON_MIN = 5;
export const EXCLUSION_REASON_MAX = 500;
export const CHANGE_REASON_MIN = 10;
export const CHANGE_REASON_MAX = 2000;

/** The hint under the question: a neutral question keeps the case open to every explanation. */
export const QUESTION_HINT =
  "Phrase it neutrally: ask what happened and why, without naming a cause in advance (“Why did occlusion alarms rise after release B?”, not “How did the new seal cause the alarms?”).";

const ids = <T extends { id?: unknown }>(rows: T[] | null | undefined) =>
  (rows ?? []).map((row) => String(row.id ?? "")).filter(Boolean);
const day = (value: unknown) => (typeof value === "string" ? value.trim().slice(0, 10) : "");

/** The form for the next version: the current scope as it stands, or an empty scope with the case's question. */
export function scopeFormFrom(current: ScopeVersion | null | undefined, fallbackQuestion = ""): ScopeForm {
  return {
    question: String(current?.question ?? fallbackQuestion ?? ""),
    versionIds: ids(current?.product_versions),
    included: ids(current?.included_complaints),
    excluded: (current?.excluded_complaints ?? [])
      .filter((row) => row?.id)
      .map((row) => ({ id: String(row.id), reason: String(row.reason ?? "") })),
    lotIds: ids(current?.lots),
    markets: [...(current?.markets ?? [])],
    failureModeIds: ids(current?.failure_modes),
    dateFrom: day(current?.date_from),
    dateTo: day(current?.date_to),
    objectives: String(current?.objectives ?? ""),
    changeReason: "",
    reviewsMustRestart: false,
    conclusionsInvalidated: false,
  };
}

export type ComplaintChoice = "none" | "included" | "excluded";

/** Whether a complaint is in the scope, kept out of it (with a reason), or not part of it. */
export function complaintChoice(form: Pick<ScopeForm, "included" | "excluded">, id: string): ComplaintChoice {
  if (form.included.includes(id)) return "included";
  if (form.excluded.some((row) => row.id === id)) return "excluded";
  return "none";
}

/** The form with one complaint put in, kept out, or taken off the scope; a kept-out complaint keeps its reason. */
export function chooseComplaint(form: ScopeForm, id: string, choice: ComplaintChoice): ScopeForm {
  const included = form.included.filter((item) => item !== id);
  const previous = form.excluded.find((row) => row.id === id);
  const excluded = form.excluded.filter((row) => row.id !== id);
  if (choice === "included") included.push(id);
  if (choice === "excluded") excluded.push({ id, reason: previous?.reason ?? "" });
  return { ...form, included, excluded };
}

export function setExclusionReason(form: ScopeForm, id: string, reason: string): ScopeForm {
  return { ...form, excluded: form.excluded.map((row) => (row.id === id ? { ...row, reason } : row)) };
}

/** Markets typed as a list ("DE, FR; US"): trimmed, without repeats (ignoring case), in the order given. */
export function parseMarkets(text: string): string[] {
  const seen = new Set<string>();
  return text
    .split(/[,;\n]/)
    .map((item) => item.trim())
    .filter((item) => {
      const key = item.toLowerCase();
      if (!item || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Everything that stops the scope from being saved (the server checks the same rules), or an empty list. */
export function scopeProblems(form: ScopeForm, hasVersion: boolean): string[] {
  const problems: string[] = [];
  const question = form.question.trim();
  if (question.length < QUESTION_MIN) problems.push(`Write the question in at least ${QUESTION_MIN} characters.`);
  if (question.length > QUESTION_MAX) problems.push(`Keep the question to ${QUESTION_MAX} characters.`);
  const both = form.excluded.filter((row) => form.included.includes(row.id));
  if (both.length) problems.push("A complaint cannot be both in the scope and kept out of it.");
  const unexplained = form.excluded.filter((row) => row.reason.trim().length < EXCLUSION_REASON_MIN);
  if (unexplained.length)
    problems.push(
      `Give each complaint kept out of the scope a reason of at least ${EXCLUSION_REASON_MIN} characters (${unexplained.length} missing).`,
    );
  if (form.excluded.some((row) => row.reason.trim().length > EXCLUSION_REASON_MAX))
    problems.push(`Keep each exclusion reason to ${EXCLUSION_REASON_MAX} characters.`);
  if (form.dateFrom && !DAY.test(form.dateFrom)) problems.push("Enter the start of the period as a date.");
  if (form.dateTo && !DAY.test(form.dateTo)) problems.push("Enter the end of the period as a date.");
  if (DAY.test(form.dateFrom) && DAY.test(form.dateTo) && form.dateFrom > form.dateTo)
    problems.push("The period must start before it ends.");
  const reason = form.changeReason.trim();
  if (hasVersion && reason.length < CHANGE_REASON_MIN)
    problems.push(`Say why the scope changes, in at least ${CHANGE_REASON_MIN} characters.`);
  if (reason.length > CHANGE_REASON_MAX)
    problems.push(`Keep the reason for the change to ${CHANGE_REASON_MAX} characters.`);
  return problems;
}

/** The body of PUT /api/v1/investigations/{id}/scope; empty optional fields are left out. */
export function scopeBody(form: ScopeForm, hasVersion: boolean) {
  const objectives = form.objectives.trim();
  const reason = form.changeReason.trim();
  return {
    question: form.question.trim(),
    product_version_ids: [...form.versionIds],
    included_complaint_ids: [...form.included],
    excluded_complaints: form.excluded.map((row) => ({ complaint_id: row.id, reason: row.reason.trim() })),
    lot_ids: [...form.lotIds],
    markets: [...form.markets],
    failure_mode_ids: [...form.failureModeIds],
    ...(form.dateFrom ? { date_from: form.dateFrom } : {}),
    ...(form.dateTo ? { date_to: form.dateTo } : {}),
    ...(objectives ? { objectives } : {}),
    ...(hasVersion || reason ? { change_reason: reason } : {}),
    reviews_must_restart: form.reviewsMustRestart,
    conclusions_invalidated: form.conclusionsInvalidated,
  };
}

export const scopePath = (investigationId: string, version?: number) =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/scope${
    version === undefined ? "" : `/versions/${encodeURIComponent(String(version))}`
  }`;

// ---------------------------------------------------------------------------------------------------------------
// Picker options: what the scope can hold, from the product context and the scope itself

export type ScopeOption = { id: string; label: string; detail: string | null };

type Row = Record<string, unknown>;
const text = (value: unknown) => safeText(value);

function merged(options: ScopeOption[]): ScopeOption[] {
  const seen = new Set<string>();
  return options.filter((option) => {
    if (!option.id || seen.has(option.id)) return false;
    seen.add(option.id);
    return true;
  });
}

const versionLabel = (row: Row) => text(row.version_identifier) ?? text(row.business_id) ?? "Version";
// The customer's own reference first (0.10.72): "SAMPLE-ORBIT-300-CMP-007", never only the MDARIX ID.
const complaintLabel = (row: Row) => text(row.complaint_identifier) ?? text(row.business_id) ?? "Complaint";
const lotLabel = (row: Row) => text(row.lot_identifier) ?? text(row.business_id) ?? "Lot";
const failureModeLabel = (row: Row) =>
  text(row.business_id) ?? text(row.failure_mode_identifier) ?? text(row.name) ?? "";

export type ScopeOptions = {
  versions: ScopeOption[];
  complaints: ScopeOption[];
  lots: ScopeOption[];
  failureModes: ScopeOption[];
  markets: string[];
};

/**
 * What the pickers offer: the product's versions, the selected version's complaints and lots and the failure modes
 * (Product 360), plus everything the current scope already holds, so a scope that spans versions keeps its items in
 * view. Markets come from the complaints' countries (when recorded) and the scope's own markets.
 */
export function scopeOptions(
  view: Product360 | null | undefined,
  current: ScopeVersion | null | undefined,
): ScopeOptions {
  const versions = merged([
    ...((view?.versions ?? []) as Row[]).map((row) => ({
      id: String(row.id ?? ""),
      label: versionLabel(row),
      detail: text(row.business_id) && text(row.version_identifier) ? text(row.business_id) : null,
    })),
    ...((current?.product_versions ?? []) as Row[]).map((row) => ({
      id: String(row.id ?? ""),
      label: versionLabel(row),
      detail: text(row.business_id) && text(row.version_identifier) ? text(row.business_id) : null,
    })),
  ]);
  const complaintOption = (row: Row) => ({
    id: String(row.id ?? ""),
    label: complaintLabel(row),
    detail: text(row.description),
  });
  const complaints = merged([
    ...((current?.included_complaints ?? []) as Row[]).map(complaintOption),
    ...((current?.excluded_complaints ?? []) as Row[]).map(complaintOption),
    ...((view?.complaints ?? []) as Row[]).map(complaintOption),
  ]);
  const lots = merged([
    ...((current?.lots ?? []) as Row[]).map((row) => ({
      id: String(row.id ?? ""),
      label: lotLabel(row),
      detail: null,
    })),
    ...((view?.manufacturing?.lots ?? []) as Row[]).map((row) => ({
      id: String(row.id ?? ""),
      label: lotLabel(row),
      detail: text(row.site_name),
    })),
  ]);
  const failureModes = merged([
    ...((current?.failure_modes ?? []) as Row[]).map((row) => ({
      id: String(row.id ?? ""),
      label: failureModeLabel(row) || "Failure mode",
      detail: text(row.name),
    })),
    ...((view?.failure_modes ?? []) as Row[]).map((row) => ({
      id: String(row.id ?? ""),
      label: failureModeLabel(row) || "Failure mode",
      detail: text(row.name),
    })),
  ]);
  const countries = ((view?.complaints ?? []) as Row[])
    .map((row) => text(row.country) ?? text(row.market) ?? text(row.country_code))
    .filter((value): value is string => !!value);
  const markets = parseMarkets([...(current?.markets ?? []), ...countries].join(","));
  return { versions, complaints, lots, failureModes, markets };
}

// ---------------------------------------------------------------------------------------------------------------
// What changed: the diff after a save, and a side-by-side comparison of two versions

const entryText = (entry: ScopeDiffEntry): string =>
  typeof entry === "string"
    ? (safeText(entry) ?? "—")
    : (safeText(entry?.business_id) ??
      safeText(entry?.complaint_identifier) ??
      safeText(entry?.version_identifier) ??
      "—");

/** The lines that say what a save changed ("Complaints added: CMP000012, CMP000013"); empty when nothing did. */
export function diffLines(diff: ScopeDiff | null | undefined): string[] {
  if (!diff) return [];
  const lines: string[] = [];
  if (diff.question_changed) lines.push("The question changed.");
  const list = (label: string, entries: ScopeDiffEntry[] | null | undefined) => {
    if (entries?.length) lines.push(`${label}: ${entries.map(entryText).join(", ")}`);
  };
  list("Complaints added", diff.added_complaints);
  list("Complaints removed", diff.removed_complaints);
  list("Complaints newly kept out", diff.newly_excluded);
  list("Versions added", diff.versions_added);
  list("Versions removed", diff.versions_removed);
  return lines;
}

export type ScopeCompareRow = {
  key: string;
  label: string;
  left: string[];
  right: string[];
  added: string[];
  removed: string[];
  same: boolean;
};

/** Each part of a scope as the comparison lists it: business IDs (never UUIDs), the period, the flags. */
export function scopeParts(
  scope: ScopeVersion | null | undefined,
): Array<{ key: string; label: string; items: string[] }> {
  const list = <T>(rows: T[] | null | undefined, label: (row: T) => string) => (rows ?? []).map(label).filter(Boolean);
  const period =
    scope?.date_from || scope?.date_to
      ? [`${day(scope?.date_from) || "open"} to ${day(scope?.date_to) || "open"}`]
      : [];
  return [
    { key: "question", label: "Question", items: safeText(scope?.question) ? [String(scope?.question).trim()] : [] },
    {
      key: "versions",
      label: "Product versions",
      items: list(scope?.product_versions, (row) => versionLabel(row as Row)),
    },
    {
      key: "included",
      label: "Complaints in scope",
      items: list(scope?.included_complaints, (row) => complaintLabel(row as Row)),
    },
    {
      key: "excluded",
      label: "Complaints kept out",
      items: list(scope?.excluded_complaints, (row) => {
        const reason = safeText(row.reason);
        return reason ? `${complaintLabel(row as Row)} (${reason})` : complaintLabel(row as Row);
      }),
    },
    { key: "lots", label: "Lots", items: list(scope?.lots, (row) => lotLabel(row as Row)) },
    {
      key: "lots_left_out",
      label: "Lots left out",
      items: list(scope?.excluded_lots, (row) => {
        const reason = safeText(row.reason);
        return reason ? `${lotLabel(row as Row)} (${reason})` : lotLabel(row as Row);
      }),
    },
    { key: "markets", label: "Markets", items: list(scope?.markets, (row) => String(row).trim()) },
    {
      key: "failure_modes",
      label: "Failure modes",
      items: list(scope?.failure_modes, (row) => {
        const id = safeText(row.business_id);
        const name = safeText(row.name);
        return id && name ? `${id} ${name}` : (id ?? name ?? "");
      }),
    },
    { key: "period", label: "Period", items: period },
    {
      key: "objectives",
      label: "Objectives",
      items: safeText(scope?.objectives) ? [String(scope?.objectives).trim()] : [],
    },
  ];
}

/** Two versions side by side: each part's items on the left and right, and what the right one added or removed. */
export function compareScopes(
  left: ScopeVersion | null | undefined,
  right: ScopeVersion | null | undefined,
): ScopeCompareRow[] {
  const before = scopeParts(left);
  const after = scopeParts(right);
  return before
    .map((part, index) => {
      const next = after[index]?.items ?? [];
      const added = next.filter((item) => !part.items.includes(item));
      const removed = part.items.filter((item) => !next.includes(item));
      return {
        key: part.key,
        label: part.label,
        left: part.items,
        right: next,
        added,
        removed,
        same: !added.length && !removed.length,
      };
    })
    .filter((row) => row.key !== "lots_left_out" || row.left.length > 0 || row.right.length > 0);
}

/** The options a long picker shows: those matching the search (ID or detail), at most `limit`, chosen ones always kept. */
export function visibleOptions(
  options: ScopeOption[],
  query: string,
  chosen: string[],
  limit = 50,
): { shown: ScopeOption[]; total: number } {
  const search = query.trim().toLowerCase();
  const matches = search
    ? options.filter((option) => `${option.label} ${option.detail ?? ""}`.toLowerCase().includes(search))
    : options;
  const page = matches.slice(0, limit);
  const kept = options.filter((option) => chosen.includes(option.id) && !page.includes(option));
  return { shown: [...kept, ...page], total: matches.length };
}
