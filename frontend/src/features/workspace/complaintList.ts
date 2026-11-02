// Pure rules for the complaint list (Complaints › Complaint list, Signals › Complaint list): the filters it sends to
// GET /api/v1/complaints (backend/app/complaints_router.py, which filters within the signed-in organization and
// pages), the tab name that carries filters in a link, and the filters Getting started › Automatic insights hands it.
import type { InsightFilters } from "./trialInsights";

export const COMPLAINT_LIST_TAB = "Complaint list";
export const COMPLAINT_LIST_PAGE_SIZE = 50;

export type ComplaintListFilters = {
  q: string;
  productId: string;
  status: string;
  /** A product version's MDARIX ID (or id). */
  version: string;
  /** A lot number, matched whole (any case). */
  lot: string;
  problemCode: string;
  country: string;
  /** The system the complaints came from (Automatic insights reads one: the sample or the imported data). */
  source: string;
};

export const EMPTY_COMPLAINT_FILTERS: ComplaintListFilters = {
  q: "",
  productId: "",
  status: "",
  version: "",
  lot: "",
  problemCode: "",
  country: "",
  source: "",
};

/** Each filter's query parameter, on the server and in a tab name. */
const PARAMS: ReadonlyArray<[keyof ComplaintListFilters, string]> = [
  ["q", "q"],
  ["productId", "product_id"],
  ["status", "status"],
  ["version", "version"],
  ["lot", "lot"],
  ["problemCode", "problem_code"],
  ["country", "country"],
  ["source", "source_system"],
];

function filterParams(filters: Partial<ComplaintListFilters>, params = new URLSearchParams()): URLSearchParams {
  for (const [key, name] of PARAMS) {
    const value = (filters[key] ?? "").trim();
    if (value) params.set(name, value);
  }
  return params;
}

/** Every filter as its tab parameter (an empty one as ""), for the screen's address. */
export const complaintFilterValues = (filters: ComplaintListFilters): Record<string, string> =>
  Object.fromEntries(PARAMS.map(([key, name]) => [name, filters[key] ?? ""]));

/** The list's request: a page, the column sort and every filter set. */
export function complaintListPath(
  filters: ComplaintListFilters,
  page: number,
  sort: Record<string, string> = {},
): string {
  const params = new URLSearchParams({ page: String(page), page_size: String(COMPLAINT_LIST_PAGE_SIZE), ...sort });
  return `/api/v1/complaints?${filterParams(filters, params)}`;
}

/** The tab name that opens the list with these filters ("Complaint list?version=PVR000002&country=US"). */
export function complaintListTab(filters: Partial<ComplaintListFilters> = {}): string {
  const rest = filterParams(filters).toString();
  return rest ? `${COMPLAINT_LIST_TAB}?${rest}` : COMPLAINT_LIST_TAB;
}

/** What a tab name asks for: whether it is the list, and its filters (see complaintListTab). */
export function parseComplaintListTab(value: string | null | undefined): {
  isList: boolean;
  filters: ComplaintListFilters;
} {
  const text = String(value ?? "");
  const mark = text.indexOf("?");
  const name = mark >= 0 ? text.slice(0, mark) : text;
  const params = new URLSearchParams(mark >= 0 ? text.slice(mark + 1) : "");
  const filters = { ...EMPTY_COMPLAINT_FILTERS };
  for (const [key, param] of PARAMS) filters[key] = (params.get(param) ?? "").trim().slice(0, 120);
  return { isList: name === COMPLAINT_LIST_TAB, filters };
}

/** Whether any filter narrows the list. */
export const hasComplaintFilters = (filters: ComplaintListFilters) =>
  PARAMS.some(([key]) => filters[key].trim() !== "");

/** The filters of Automatic insights (version, lot, problem code, country) as the list's, with its data's source. */
export function insightComplaintFilters(
  filters: InsightFilters,
  source?: string | null,
): Partial<ComplaintListFilters> {
  return {
    version: filters.version ?? "",
    lot: filters.lot ?? "",
    problemCode: filters.code ?? "",
    country: filters.country ?? "",
    source: source ?? "",
  };
}

/** The sample data's source and a free trial's imported data's (backend/app/trial: SAMPLE_SOURCE, UPLOAD_SOURCE). */
export const SAMPLE_SOURCE = "MDARIX_SAMPLE";
export const IMPORTED_SOURCE = "TRIAL_UPLOAD";

const SOURCE_NAMES: Record<string, string> = {
  [SAMPLE_SOURCE]: "the sample data",
  [IMPORTED_SOURCE]: "your imported data",
};

/** How a source filter reads: "Only the sample data". */
export const sourceText = (source: string) => `Only ${SOURCE_NAMES[source] ?? source}`;

/**
 * What the list's data filter offers (DEV-017): while the sample data is there (a free trial), "Only your imported
 * data" and "Only the sample data"; a source from a link stays chosen. None otherwise: every complaint is the
 * organization's own.
 */
export function sourceChoices(sources: string[], chosen: string): string[] {
  if (!sources.includes(SAMPLE_SOURCE) && !chosen) return [];
  const choices = [IMPORTED_SOURCE, SAMPLE_SOURCE];
  return chosen && !choices.includes(chosen) ? [...choices, chosen] : choices;
}

export type ComplaintVersionChoice = { id: string; business_id: string | null; product_id: string; label: string };

/** The versions the version filter offers: the chosen product's only, once a product is chosen. */
export function versionChoices(versions: ComplaintVersionChoice[], productId: string): ComplaintVersionChoice[] {
  return productId ? versions.filter((item) => item.product_id === productId) : versions;
}

/** A version choice's value: its MDARIX ID, else its id. */
export const versionValue = (item: ComplaintVersionChoice) => item.business_id || item.id;
