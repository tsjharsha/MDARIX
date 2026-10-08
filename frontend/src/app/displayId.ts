/**
 * The identifiers people see. Every record of the numbered objects (customers, tenants, users, complaints,
 * investigations, decisions, …) carries `business_id` (CUST000001, CMP000012): that is the ID a person reads, quotes
 * and searches for. The UUID `id` stays the technical key for links, routes, API calls and React keys, and is never
 * shown. A record imported from a customer system also keeps that system's own number (complaint_identifier,
 * investigation_identifier, …), shown as its "Source ID".
 */

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** True for a UUID (with or without surrounding spaces), which must never reach a person as text. */
export const isUuid = (value: unknown): boolean => typeof value === "string" && UUID.test(value.trim());

// Any record shape (typed API rows have no index signature); read field by field.
type Fields = object | null | undefined;
const field = (record: Fields, key: string): unknown =>
  record && typeof record === "object" ? (record as Record<string, unknown>)[key] : undefined;

/** The value as display text, or null when it is empty or a UUID. */
export const safeText = (value: unknown): string | null => {
  if (value === null || value === undefined || typeof value === "object") return null;
  const text = String(value).trim();
  return text && !isUuid(text) ? text : null;
};

// The fields a record names itself by, in the order they are preferred when it has no MDARIX ID yet.
const NAME_KEYS = ["name", "display_name", "title", "email"];

/**
 * The customer system's own number for an imported record: `<object>_identifier` (complaint_identifier,
 * investigation_identifier, product_identifier, lot_identifier, …) or `source_reference`. Never a UUID.
 */
export const sourceId = (record: Fields, key?: string): string | null => {
  if (!record || typeof record !== "object") return null;
  if (key) return safeText(field(record, key));
  for (const [name, value] of Object.entries(record)) {
    if (name.endsWith("_identifier")) {
      const text = safeText(value);
      if (text) return text;
    }
  }
  return safeText(field(record, "source_reference"));
};

/**
 * A record's identifier for an ID column: its MDARIX ID (`business_id`), else, when `sourceKey` names it, its number in
 * the customer system it came from (complaint_identifier, tenant_key). Null when it has neither; never the UUID.
 */
export const businessId = (record: Fields, sourceKey?: string): string | null =>
  safeText(field(record, "business_id")) ?? (sourceKey ? sourceId(record, sourceKey) : null);

/**
 * The ID to show for a record in a sentence, heading or option: its business ID (see businessId), else its name, else
 * `fallback` ("—"). Never the UUID, so a screen stays readable while an older API response has no business_id yet.
 */
export const displayId = (record: Fields, sourceKey?: string, fallback = "—"): string => {
  if (!record || typeof record !== "object") return fallback;
  const id = businessId(record, sourceKey);
  if (id) return id;
  for (const key of NAME_KEYS) {
    const text = safeText(field(record, key));
    if (text) return text;
  }
  return fallback;
};

/**
 * The ID to show for a record another record refers to: `<role>_business_id` (investigation_business_id,
 * customer_business_id, …), else the given fallbacks in order (a source number or a name), else "—".
 */
export const referenceId = (record: Fields, role: string, ...fallbacks: unknown[]): string => {
  const own = safeText(field(record, `${role}_business_id`));
  if (own) return own;
  for (const value of fallbacks) {
    const text = safeText(value);
    if (text) return text;
  }
  return "—";
};

/** The text a cell shows for a value that might be a stray UUID: the value itself, or "—" in its place. */
export const hideUuid = (value: unknown, fallback = "—"): string => safeText(value) ?? fallback;
