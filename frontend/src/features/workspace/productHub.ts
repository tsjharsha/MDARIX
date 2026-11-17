// Product 360 and Supplier 360 on the new navigation (0.10.94, W1): the address of each page, where a record row
// opens, the origin chip and the Rev A / Rev B compare. Pure rules the pages use; the reads are the server's
// (backend/app/product360). MDARIX lists what was recorded and why each record is linked; it never infers a cause.
import { tabParts } from "../../app/linkTable";
import { SAMPLE_SOURCE } from "./complaintList";

/** The tabs of Work › Products (linkTable.json newPlaces["Product 360"]). */
export const HUB_TABS = ["Product 360", "Supplier 360"] as const;
export type HubTab = (typeof HUB_TABS)[number];

/** One product's sections; the Records tab holds the full lists. Connected and Sources are a free trial's (W5). */
export const PRODUCT_VIEWS = [
  "Overview",
  "Connected",
  "Configuration",
  "Lots",
  "Changes",
  "Records",
  "Version story",
  "Sources (simulated)",
] as const;
export type ProductView = (typeof PRODUCT_VIEWS)[number];
/** The sections a pilot does not have yet (W5, D1: the twin's reads answer 404 outside a free trial). */
export const TRIAL_VIEWS: readonly ProductView[] = ["Connected", "Sources (simulated)"];
export const productViews = (trial: boolean): readonly ProductView[] =>
  trial ? PRODUCT_VIEWS : PRODUCT_VIEWS.filter((view) => !TRIAL_VIEWS.includes(view));

/** One supplier's sections. Lots is offered in a free trial only (supplier_router.LOTS_TRIAL_ONLY). */
export const SUPPLIER_VIEWS = [
  "Overview",
  "Parts and products",
  "Lots",
  "Complaints and investigations",
  "Changes and evidence",
  "CAPAs",
] as const;
export type SupplierView = (typeof SUPPLIER_VIEWS)[number];

/** The lists of the Records tab, in the tiles' order, with their names. */
export const RECORD_KINDS = [
  ["complaints", "Complaints"],
  ["investigations", "Investigations"],
  ["signals", "Trends to review"],
  ["capas", "CAPAs and effectiveness checks"],
  ["risks", "Risks"],
  ["reports", "Authority reports"],
] as const;
export type RecordKind = (typeof RECORD_KINDS)[number][0];

/** What the page's address names: the tab, and the product (with its version, section, list and compare) or the
 * supplier (with its section). Addresses use the identifiers people read (?product=SAMPLE-ORBIT-300&version=Rev B). */
export type HubPlace = {
  tab: HubTab;
  product: string | null;
  version: string | null;
  supplier: string | null;
  view: string | null;
  list: RecordKind | null;
  compare: string | null;
  /** W5: the change whose impact is open (its id), a previewed change ("<component id>" or "<component id>:<supplier
   * id>") and a field-action scope ("COMPONENT_LOT:<component id or identifier>:<lot>"). */
  change: string | null;
  preview: string | null;
  scope: string | null;
};

export function hubPlace(tab: string | undefined | null): HubPlace {
  const { name, query } = tabParts(tab);
  const params = new URLSearchParams(query);
  const get = (key: string) => params.get(key)?.trim() || null;
  const list = get("list");
  return {
    tab: name === "Supplier 360" ? "Supplier 360" : "Product 360",
    product: get("product"),
    version: get("version"),
    supplier: get("supplier"),
    view: get("view"),
    list: RECORD_KINDS.some(([kind]) => kind === list) ? (list as RecordKind) : null,
    compare: get("compare"),
    change: get("change"),
    preview: get("preview"),
    scope: get("scope"),
  };
}

/** The tab (with what it carries) for a place; empty values are left out. */
export function hubTab(place: Partial<HubPlace> & { tab: HubTab }): string {
  const params = new URLSearchParams();
  for (const key of [
    "product",
    "version",
    "supplier",
    "view",
    "list",
    "compare",
    "change",
    "preview",
    "scope",
  ] as const) {
    const value = place[key];
    if (value) params.set(key, value);
  }
  const rest = params.toString();
  return rest ? `${place.tab}?${rest}` : place.tab;
}

/** A product's page: its tab ("Product 360?product=…&version=…"). */
export const productTab = (product: string, version?: string | null, view?: ProductView | null) =>
  hubTab({ tab: "Product 360", product, version: version ?? null, view: view && view !== "Overview" ? view : null });

/** A supplier's page: its tab ("Supplier 360?supplier=…"). */
export const supplierTab = (supplier: string, view?: SupplierView | null) =>
  hubTab({ tab: "Supplier 360", supplier, view: view && view !== "Overview" ? view : null });

/** A section named in the address, if the page offers it; else its first. */
export const chosenView = <T extends string>(views: readonly T[], named: string | null): T =>
  views.includes(named as T) ? (named as T) : views[0];

/** Where a record row is, as the server sends it (backend/app/product360/origin.py). */
export type Origin = {
  kind: "SAMPLE" | "IMPORTED" | "MDARIX" | "EXTERNAL";
  label: string;
  detail: string;
  system?: string | null;
  external_id?: string | null;
  loaded_at?: string | null;
};

/** Connect mode (operating-modes M1-M6): a record from the customer's own system is corrected there. */
export const correctionNote = (origin: Origin | null | undefined) =>
  origin?.kind === "EXTERNAL" && origin.system
    ? `Correct it in ${origin.system} and import again.`
    : origin?.kind === "IMPORTED"
      ? "Correct it in your export and import it again."
      : null;

/** Whether a record belongs to the data the trial's top bar shows (the sample's or the imported): all without one. */
export const inDataShown = (origin: Origin | null | undefined, dataSource: string | null | undefined) =>
  !dataSource || (dataSource === SAMPLE_SOURCE) === (origin?.kind === "SAMPLE");

/** "12.4 per 1,000 units", or why there is no rate: never a rate from partial units. */
export function rateText(perThousand: number | string | null | undefined, unitsKnown = true): string {
  if (!unitsKnown || perThousand === null || perThousand === undefined || perThousand === "") return "units not known";
  return `${Number(perThousand).toFixed(1)} per 1,000 units`;
}

type Part = { id?: string | null; component_identifier?: string | null; name?: string | null };
type SupplierRow = {
  id?: string | null;
  business_id?: string | null;
  supplier_identifier?: string | null;
  name?: string | null;
  component_identifier?: string | null;
  supplied_from?: string | null;
};
type ChangeRow = {
  change_identifier?: string | null;
  change_type?: string | null;
  description?: string | null;
  effective_timestamp?: string | null;
  event_timestamp?: string | null;
  affects?: string[] | null;
  versions?: string[] | null;
};
export type Configuration = { components: Part[]; suppliers: SupplierRow[] };

export type CompareRow = {
  key: string;
  name: string;
  before: SupplierRow[];
  after: SupplierRow[];
  state: "same" | "added" | "removed" | "changed";
  changes: ChangeRow[];
};

const supplierKey = (row: SupplierRow) => String(row.id ?? row.supplier_identifier ?? row.name ?? "");

/**
 * The earlier version's configuration beside this one's, by part identifier: a part only in this version is added,
 * one only in the earlier is removed, one whose recorded suppliers differ is changed. A change recorded as affecting
 * the part on this version is named beside it (never as a cause).
 */
export function compareConfigurations(
  earlier: Configuration,
  current: Configuration,
  changes: ChangeRow[],
  currentVersionId: string | null,
): CompareRow[] {
  const suppliersOf = (config: Configuration, key: string) =>
    config.suppliers.filter((row) => row.component_identifier === key);
  const names = new Map<string, string>();
  for (const part of [...earlier.components, ...current.components]) {
    const key = String(part.component_identifier ?? part.id ?? "");
    if (key && !names.has(key)) names.set(key, part.name ?? key);
  }
  const has = (config: Configuration, key: string) =>
    config.components.some((part) => String(part.component_identifier ?? part.id ?? "") === key);
  return [...names.entries()]
    .map(([key, name]) => {
      const before = suppliersOf(earlier, key);
      const after = suppliersOf(current, key);
      const same = before.map(supplierKey).sort().join("|") === after.map(supplierKey).sort().join("|");
      const state: CompareRow["state"] = !has(earlier, key)
        ? "added"
        : !has(current, key)
          ? "removed"
          : same
            ? "same"
            : "changed";
      const named = changes.filter(
        (change) =>
          (change.affects ?? []).includes(key) &&
          (!currentVersionId || !change.versions?.length || change.versions.includes(currentVersionId)),
      );
      return { key, name, before, after, state, changes: state === "same" ? [] : named };
    })
    .sort((a, b) => Number(a.state === "same") - Number(b.state === "same") || a.name.localeCompare(b.name));
}

/** The monthly chart's markers by month ("2026-08"): a version's release, a part link, a change. */
export function markersByMonth(markers: ReadonlyArray<{ kind: string; label: string; at: string }>) {
  const found = new Map<string, string[]>();
  for (const marker of markers) {
    const month = String(marker.at ?? "").slice(0, 7);
    if (month) found.set(month, [...(found.get(month) ?? []), marker.label]);
  }
  return found;
}

/** "Aug 26" for "2026-08". */
export const monthLabel = (month: string) => {
  const [year, number] = month.split("-");
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[Number(number) - 1] ?? month} ${year?.slice(2) ?? ""}`.trim();
};
