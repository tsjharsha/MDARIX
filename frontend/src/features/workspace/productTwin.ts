// The Product Lifecycle Twin (W5, a free trial's): the addresses of its reads and the pure rules its screens use. The
// reads are the server's (backend/app/product360/twin.py, data_import_router /sources). MDARIX lists; it recommends no
// recall and decides no notification. The sources are simulated: generic system names only, never a vendor's.
import { hubTab, type HubPlace } from "./productHub";

type Row = Record<string, any>;

/** What every simulated source and every node caption says. */
export const SIMULATED_LABEL = "Simulated, not a live connection";
export const PREVIEW_BANNER = "Preview: no change record. Nothing is saved.";
export const NOT_IMPORTED = "Distribution not imported";
export const SOURCES_PATH = "/api/v1/data/import/sources";
/** The sample's sensor lot, the flagship's field-action scope (step 7). */
export const SAMPLE_SENSOR = "SAMPLE-ORBIT-300-C1";
export const SAMPLE_SENSOR_LOT = "NS-SL-2417 (Sample)";

export const twinPath = (product: string, version: string | null) =>
  `/api/v1/products/${encodeURIComponent(product)}/twin${version ? `?${new URLSearchParams({ version })}` : ""}`;

/** The impact read of the change in the address, or of the previewed component (and supplier). */
export function impactPath(product: string, place: Pick<HubPlace, "change" | "preview">): string | null {
  const base = `/api/v1/products/${encodeURIComponent(product)}/change-impact`;
  if (place.change) return `${base}?${new URLSearchParams({ change: place.change })}`;
  const preview = previewOf(place.preview);
  if (!preview) return null;
  const query = new URLSearchParams({ component: preview.component });
  if (preview.supplier) query.set("supplier", preview.supplier);
  return `${base}?${query}`;
}

/** "<component id>" or "<component id>:<supplier id>" (ids never hold a colon). */
export function previewOf(value: string | null | undefined): { component: string; supplier: string | null } | null {
  const [component, supplier] = String(value ?? "").split(":");
  return component ? { component, supplier: supplier || null } : null;
}
export const previewParam = (component: string, supplier?: string | null) =>
  supplier ? `${component}:${supplier}` : component;

/** The scope in the address: "COMPONENT_LOT:<component>:<lot>" (a lot may hold colons; it is everything after). */
export function scopeOf(value: string | null | undefined): { kind: string; ref: string; lot: string } | null {
  const [kind, ref, ...lot] = String(value ?? "").split(":");
  if (!kind || !ref || !lot.length) return null;
  return { kind, ref, lot: lot.join(":") };
}
export const scopeParam = (component: string, lot: string) => `COMPONENT_LOT:${component}:${lot}`;
export const scopeQuery = (scope: { kind: string; ref: string; lot: string }) => new URLSearchParams(scope).toString();
export const scopePath = (scope: { kind: string; ref: string; lot: string }, csv = false) =>
  `/api/v1/field-scope${csv ? ".csv" : ""}?${scopeQuery(scope)}`;

/** "Trace NS-SL-2417 (Sample)": the component lot with the most lots with complaints. */
export const traceText = (trace: Row | null | undefined) => (trace ? `Trace ${trace.lot}` : null);

export type ChainNode = {
  key: string;
  label: string;
  value: string;
  caption: string;
  target: Partial<HubPlace> | "risk-file" | "suppliers";
};

const count = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/**
 * The connected chain, in the story's order: Version → Parts → Suppliers → Component lots → Finished lots → Markets →
 * Complaints (open of total) → Investigations → Risk rows → CAPAs and checks → Changes. Each node opens its own screen
 * and carries where its records came from. With no version (PV-1) only the product-level nodes.
 */
export function chainNodes(twin: Row): ChainNode[] {
  const captions: Record<string, string> = twin.sources?.captions ?? {};
  const version = twin.version?.version_identifier ?? null;
  const markets: Row = twin.markets ?? {};
  const checks = (twin.capas ?? []).filter((row: Row) => row.check?.state && row.check.state !== "NONE").length;
  const nodes: ChainNode[] = version
    ? [
        { key: "version", label: "Version", value: version, caption: "", target: { view: "Version story" } },
        {
          key: "parts",
          label: "Parts",
          value: count(twin.components?.length ?? 0, "part"),
          caption: "",
          target: { view: "Configuration" },
        },
        {
          key: "suppliers",
          label: "Suppliers",
          value: count(twin.suppliers?.length ? new Set(twin.suppliers.map((s: Row) => s.id)).size : 0, "supplier"),
          caption: "",
          target: "suppliers",
        },
        {
          key: "component_lots",
          label: "Component lots",
          value: count(twin.component_lots?.length ?? 0, "component lot"),
          caption: "",
          target: twin.trace ? { view: "Lots", scope: twin.trace.scope } : { view: "Lots" },
        },
        {
          key: "lots",
          label: "Finished lots",
          value: count(twin.lots?.length ?? 0, "lot"),
          caption: "",
          target: { view: "Lots" },
        },
        {
          key: "markets",
          label: "Markets",
          value:
            count(markets.by_country?.length ?? 0, "country", "countries") +
            (markets.not_imported ? ` · ${count(markets.not_imported, "lot")}: not imported` : ""),
          caption: "",
          target: twin.trace ? { view: "Lots", scope: twin.trace.scope } : { view: "Lots" },
        },
      ]
    : [];
  nodes.push(
    {
      key: "complaints",
      label: "Complaints",
      value: `${twin.complaints?.open ?? 0} open of ${twin.complaints?.total ?? 0}`,
      caption: "",
      target: { view: "Records", list: "complaints" },
    },
    {
      key: "investigations",
      label: "Investigations",
      value: count(twin.investigations?.length ?? 0, "investigation"),
      caption: "",
      target: { view: "Records", list: "investigations" },
    },
    {
      key: "risks",
      label: "Risk rows",
      value: count(twin.risks?.length ?? 0, "risk row"),
      caption: "",
      target: "risk-file",
    },
    {
      key: "capas",
      label: "CAPAs and checks",
      value: `${count(twin.capas?.length ?? 0, "CAPA")} · ${count(checks, "check")}`,
      caption: "",
      target: { view: "Records", list: "capas" },
    },
    {
      key: "changes",
      label: "Changes",
      value: count(twin.changes?.length ?? 0, "change"),
      caption: "",
      target: { view: "Changes" },
    },
  );
  return nodes.map((node) => ({ ...node, caption: captions[node.key] ?? "" }));
}

/** The scope's lots in three groups: with complaints, without complaints yet (shipped), and without complaints whose
 * distribution is not imported (never read as 0 units). */
export function scopeGroups<T extends { complaints: number; distribution_imported: boolean }>(lots: readonly T[]) {
  return {
    withComplaints: lots.filter((lot) => lot.complaints > 0),
    withoutComplaints: lots.filter((lot) => lot.complaints === 0 && lot.distribution_imported),
    notImported: lots.filter((lot) => lot.complaints === 0 && !lot.distribution_imported),
  };
}

/** Units shipped, or "Distribution not imported": never 0 for a lot whose shipments are not loaded. */
export const shippedText = (lot: { distribution_imported?: boolean; shipped?: number | null }) =>
  lot.distribution_imported && lot.shipped != null ? lot.shipped.toLocaleString("en-US") : NOT_IMPORTED;

/** One run's five steps, from its data-quality report: fields found, mapped, checked, written or set aside, loaded. */
export function runSteps(run: Row): { label: string; detail: string; ok: boolean }[] {
  const report: Row = run.report ?? {};
  const mapped = run.columns?.length ?? 0;
  const unused = run.not_used?.length ?? 0;
  const duplicates = report.rows_duplicate ?? 0;
  return [
    { label: "Fields found", detail: count(mapped + unused, "column"), ok: true },
    {
      label: "Mapped",
      detail: `${mapped} mapped${unused ? `, ${unused} not used` : ""}`,
      ok: true,
    },
    { label: "Checked", detail: count(report.rows_read ?? 0, "row"), ok: true },
    {
      label: "Written / set aside",
      detail: `${report.rows_accepted ?? 0} written · ${report.rows_quarantined ?? 0} set aside${duplicates ? ` (${count(duplicates, "duplicate")})` : ""}`,
      ok: !report.rows_quarantined,
    },
    {
      label: "Reconciled and loaded",
      detail: run.reconciled ? `Balanced · ${run.lineage_rows ?? 0} with lineage` : "Does not balance: ask us",
      ok: !!run.reconciled,
    },
  ];
}

/** The address of Product 360's Connected view of a product version (the flagship's step 2 link). */
export const connectedTab = (product: string, version: string | null) =>
  hubTab({ tab: "Product 360", product, version, view: "Connected" });

/** The address of the sample sensor lot's field-action scope (the flagship's step 7 line). */
export const sampleScopeTab = (product: string, version: string | null) =>
  hubTab({ tab: "Product 360", product, version, view: "Lots", scope: scopeParam(SAMPLE_SENSOR, SAMPLE_SENSOR_LOT) });

const when = (row: Row) => String(row.effective_timestamp ?? row.event_timestamp ?? "");
const closed = (status: unknown) => /^(closed|cancel)/i.test(String(status ?? ""));
const shortLot = (lot: string) => lot.replace(/^.*-(LOT-)/, "$1");

export type TwinSummary = {
  change: Row | null;
  changes: number;
  versions: string[];
  lots: { total: number; withComplaints: string[] };
  complaints: { open: number; total: number };
  investigations: Row[];
  capas: Row[];
};

/**
 * W1e: the twin read as a quality lead reads it, from the connected view's own rows (nothing computed beyond counts):
 * the latest recorded change, the versions it is recorded on (all of them when it names the product), the version's
 * lots with complaints, the complaints, and the open investigations and the CAPAs with no effective check yet.
 */
export function twinSummary(twin: Row): TwinSummary {
  const changes: Row[] = twin.changes ?? [];
  const change = [...changes].sort((a, b) => when(b).localeCompare(when(a)))[0] ?? null;
  const names = new Map<string, string>(
    (twin.versions ?? []).map((row: Row) => [String(row.id), row.version_identifier]),
  );
  const versions = !change
    ? []
    : change.affects_product
      ? [...names.values()]
      : (change.versions ?? []).map((id: string) => names.get(String(id))).filter(Boolean);
  const lots: Row[] = twin.lots ?? [];
  return {
    change,
    changes: changes.length,
    versions,
    lots: {
      total: lots.length,
      withComplaints: lots.filter((lot) => lot.complaints > 0).map((lot) => shortLot(lot.lot_identifier)),
    },
    complaints: { open: twin.complaints?.open ?? 0, total: twin.complaints?.total ?? 0 },
    investigations: (twin.investigations ?? []).filter((row: Row) => !closed(row.status)),
    capas: (twin.capas ?? []).filter((row: Row) => row.check?.state !== "EFFECTIVE"),
  };
}
