import { formatDateTime, formatDay } from "../../app/dates";

// Choosing which fields a list shows: the fields a list can offer, how a raw value is shown, and the saved choice.

// Secrets, and the flags screens use to decide which buttons to offer, are never offered as fields.
const HIDDEN = /(password|secret|token|hash|credential_value|^can_|^is_last_|^lock_version$|^actions$)/i;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$/;

const isPlain = (value: unknown) => value === null || ["string", "number", "boolean"].includes(typeof value);

/**
 * Field keys the rows carry that can be shown as a column: plain values or lists of plain values (never nested
 * objects, never anything that looks like a secret, never internal "_" keys). Looks at the first rows only.
 */
export const availableFieldKeys = (rows: unknown[], exclude: Iterable<string> = [], sample = 25): string[] => {
  const skip = new Set(exclude);
  const order: string[] = [];
  const unusable = new Set<string>();
  const withValue = new Set<string>();
  for (const row of rows.slice(0, sample)) {
    if (!row || typeof row !== "object") continue;
    for (const [key, value] of Object.entries(row as Record<string, unknown>)) {
      if (skip.has(key) || key.startsWith("_") || HIDDEN.test(key)) continue;
      if (!order.includes(key)) order.push(key);
      if (!(isPlain(value) || (Array.isArray(value) && value.every(isPlain)))) unusable.add(key);
      else if (value !== null && value !== undefined && value !== "") withValue.add(key);
    }
  }
  // A field is offered when no row holds a nested record in it and at least one row has a value.
  return order.filter((key) => !unusable.has(key) && withValue.has(key));
};

/** "customer_identifier" -> "Customer identifier", "created_at" -> "Created", "tenant_id" -> "Tenant ID". */
export const fieldLabel = (key: string) => {
  const words = key
    .replace(/_at$/, "")
    .replace(/_/g, " ")
    .replace(/\bid\b/g, "ID")
    .replace(/\burl\b/g, "URL")
    .replace(/\bip\b/g, "IP")
    .trim();
  return words.replace(/^\w/, (letter) => letter.toUpperCase()) || key;
};

/** A raw value as a reader would want to see it. */
export const formatFieldValue = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.length ? value.map((item) => formatFieldValue(item)).join(", ") : "—";
  if (typeof value === "string" && ISO_DATE.test(value)) {
    const date = new Date(value);
    if (!Number.isNaN(date.getTime())) return value.length > 10 ? formatDateTime(date) : formatDay(date);
  }
  if (typeof value === "string" && /^[A-Z][A-Z0-9_]+$/.test(value) && value.includes("_"))
    return value.charAt(0) + value.slice(1).toLowerCase().replace(/_/g, " ");
  return String(value);
};

/** The fields to show, in order: the saved choice (only fields still available), or the defaults. */
export const resolveSelection = (defaults: string[], available: string[], saved: string[] | null): string[] => {
  if (!saved) return defaults.filter((key) => available.includes(key));
  const kept = saved.filter((key) => available.includes(key));
  return kept.length ? kept : defaults.filter((key) => available.includes(key));
};

/** Move one field up or down in the shown list. */
export const moveField = (selection: string[], key: string, direction: -1 | 1): string[] => {
  const from = selection.indexOf(key);
  const to = from + direction;
  if (from < 0 || to < 0 || to >= selection.length) return selection;
  const next = [...selection];
  [next[from], next[to]] = [next[to], next[from]];
  return next;
};

const STORAGE_PREFIX = "mdarix.columns.";

/** The saved choice for a list in this browser (a convenience; it may be missing). */
export const loadSelection = (id: string): string[] | null => {
  try {
    const raw = window.localStorage.getItem(STORAGE_PREFIX + id);
    const parsed = raw ? JSON.parse(raw) : null;
    return Array.isArray(parsed) && parsed.every((item) => typeof item === "string") ? parsed : null;
  } catch {
    return null;
  }
};

export const saveSelection = (id: string, selection: string[] | null) => {
  try {
    if (selection) window.localStorage.setItem(STORAGE_PREFIX + id, JSON.stringify(selection));
    else window.localStorage.removeItem(STORAGE_PREFIX + id);
  } catch {
    // Storage can be unavailable (private window, blocked site data); the choice then lasts for this visit.
  }
};
