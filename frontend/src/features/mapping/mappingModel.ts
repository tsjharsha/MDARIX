// The connector mapping format the import reads (backend/app/access/connector_mapping.py), and helpers to build it.

export type FieldRule = { source: string; column: string; transform: string };
export type MappingCheck = {
  status: "READY" | "NEEDS_CHANGES";
  problems: string[];
  missing_required: string[];
  rule_count: number;
};

/** {source_field: {"target_field": "<Entity>.<column>", "transform": …}} — what the import maps records with. */
export const buildRules = (entity: string, rules: FieldRule[]) =>
  Object.fromEntries(
    rules
      .filter((rule) => rule.source && rule.column)
      .map((rule) => [rule.source, { target_field: `${entity}.${rule.column}`, transform: rule.transform }]),
  );

/** "received_date" -> "Received date". */
export const columnLabel = (column: string) =>
  column
    .replace(/_/g, " ")
    .replace(/\bid\b/, "ID")
    .replace(/^\w/, (letter) => letter.toUpperCase());

/** Dates are read as dates; everything else is carried over with spaces at the ends removed. */
export const defaultTransform = (column: string) => (/_date$/.test(column) ? "date" : "trim");

// Customer field names that usually carry an MDARIX field (TrackWise, Veeva and similar QMS exports).
const SYNONYMS: Record<string, string[]> = {
  complaint_id: ["complaint_id", "complaint_number", "record_id", "id"],
  product_id: ["product_id", "product_code", "product_number", "item_number", "part_number"],
  product_name: ["product_name", "product_description", "item_name", "name"],
  description: ["description", "problem_description", "event_description", "complaint_description", "summary"],
  version: ["version", "product_revision", "revision", "product_version"],
  lot_id: ["lot_id", "lot_number", "batch_number", "lot"],
  event_date: ["event_date", "occurrence_date", "incident_date"],
  received_date: ["received_date", "receipt_date", "awareness_date", "opened_date"],
  status: ["status", "state", "complaint_status"],
  manufacture_date: ["manufacture_date", "manufacturing_date", "production_date"],
  product_family: ["product_family", "family", "product_line"],
  version_release_date: ["version_release_date", "release_date"],
};

const normalize = (value: string) => value.toLowerCase().replace(/[^a-z0-9]/g, "");

/** The customer field that most likely fills an MDARIX column, or "" when none is a clear match. */
export const suggestSource = (column: string, sources: Array<{ name: string }>, taken: Set<string> = new Set()) => {
  const candidates = (SYNONYMS[column] ?? [column]).map(normalize);
  for (const candidate of candidates) {
    const found = sources.find((source) => normalize(source.name) === candidate && !taken.has(source.name));
    if (found) return found.name;
  }
  return "";
};

/** Add a rule for every required column not yet filled, pre-choosing the customer field that matches by name. */
export const autoMatch = (rules: FieldRule[], required: string[], sources: Array<{ name: string }>): FieldRule[] => {
  const filled = new Set(rules.map((rule) => rule.column));
  const taken = new Set(rules.map((rule) => rule.source).filter(Boolean));
  const added: FieldRule[] = [];
  for (const column of required) {
    if (filled.has(column)) continue;
    const source = suggestSource(column, sources, taken);
    if (source) taken.add(source);
    added.push({ source, column, transform: defaultTransform(column) });
  }
  return [...rules, ...added];
};

/**
 * Keep only the source records whose field holds one of the listed values (compared without case), for example a
 * Teamcenter item list's "item_type" = Product. Saved as the mapping's "_filter" setting; empty values keep all.
 */
export const withFilter = (rules: Record<string, unknown>, field: string, values: string) => {
  const accepted = values
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  return field && accepted.length ? { ...rules, _filter: { field, in: accepted } } : rules;
};
