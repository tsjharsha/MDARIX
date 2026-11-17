// W5: the Product Lifecycle Twin in a free trial: the Connected view, a change's impact (and a preview of one), the
// field-action scope, the simulated sources and the flagship's links to them; generic system names only.
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { hubPlace, hubTab, productViews } from "./productHub";
import {
  NOT_IMPORTED,
  PREVIEW_BANNER,
  SIMULATED_LABEL,
  SOURCES_PATH,
  chainNodes,
  connectedTab,
  impactPath,
  previewOf,
  previewParam,
  sampleScopeTab,
  scopeGroups,
  scopeOf,
  scopePath,
  shippedText,
  twinPath,
} from "./productTwin";
import { ProductHubSection } from "./sections/ProductHub";
import { ChangeImpactPanel, FieldScopePanel, SourcesView } from "./sections/ProductTwin";
import { FlagshipView } from "./sections/OneStory";
import type { FlagshipRun, OneStory as OneStoryData } from "./oneStory";
import { evidenceStates } from "./intelligence";
import { SAMPLE_SOURCE } from "./complaintList";

const reads = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    const data = (path && (reads.data[path] ?? reads.data[path.split("?")[0]])) ?? null;
    return { state: data ? "ready" : "loading", data, reload: () => undefined };
  },
}));
vi.mock("./useAiStatus", () => ({ useAiReady: () => null, useAiBanner: () => null }));

const PRODUCT = "SAMPLE-ORBIT-300";
const SCOPE = "COMPONENT_LOT:c1:NS-SL-2417 (Sample)";
const CAPTION = `From ERP · ${SIMULATED_LABEL}`;
const captions = Object.fromEntries(
  ["version", "parts", "suppliers", "component_lots", "lots", "markets", "complaints", "investigations", "risks"]
    .concat(["capas", "changes"])
    .map((key) => [
      key,
      key === "investigations" || key === "risks" ? `Kept in MDARIX (sample) · ${SIMULATED_LABEL}` : CAPTION,
    ]),
);
const lot = (n: number, complaints: number, shipped: number | null) => ({
  id: `l${n}`,
  lot_identifier: `${PRODUCT}-LOT-00${n}`,
  product: "OrbitCare 300",
  version: "Rev B",
  quantity: 60,
  released: 60,
  complaints,
  open_complaints: complaints,
  per_1000: complaints ? 50 : 0,
  distribution_imported: shipped !== null,
  shipped,
  in_stock: shipped === null ? null : 60 - shipped,
  by_country: shipped === null ? [] : [{ country: "US", units: shipped }],
  shipments: [],
  evidence: ["Lot genealogy: built with Pressure Sensor (Sample) lot NS-SL-2417 (Sample)"],
  excluded: false,
  basis: "Builds Rev B (lot record)",
});
const TRACE = {
  scope: SCOPE,
  lot: "NS-SL-2417 (Sample)",
  component_name: "Pressure Sensor (Sample)",
  lots: ["LOT-003", "LOT-004", "LOT-006", "LOT-007", "LOT-008"],
  lots_with_complaints: 2,
  complaints: 9,
};
const TWIN = {
  product: { id: "p1", name: "OrbitCare 300" },
  version: { id: "v2", version_identifier: "Rev B" },
  components: [{ id: "c1" }, { id: "c2" }, { id: "c3" }],
  suppliers: [{ id: "s1" }, { id: "s2" }],
  lots: [lot(3, 9, 150), lot(8, 0, null)],
  component_lots: [TRACE],
  trace: TRACE,
  markets: { by_country: [{ country: "US", units: 100 }], sites: [], not_imported: 1 },
  complaints: { total: 20, open: 4 },
  investigations: [{ id: "i1" }],
  risks: [{ id: "r1" }, { id: "r2" }],
  capas: [{ id: "k1", check: { state: "PLANNED" } }],
  changes: [{ id: "ch1" }],
  sources: { simulated: true, label: SIMULATED_LABEL, captions },
  limits: ["A complaint is on a lot only when it names that lot."],
};
const IMPACT = {
  change: { id: "ch1", change_identifier: "SAMPLE-CHG-014", description: "Sensor supplier changed." },
  preview: false,
  versions: [{ id: "v2", version_identifier: "Rev B", basis: "The change record names Pressure Sensor (Sample)" }],
  lots: [lot(3, 9, 150), lot(8, 0, null)],
  markets: { by_country: [{ country: "US", units: 150 }], not_imported: 1 },
  open_complaints: {
    count: 1,
    items: [{ id: "c", complaint_identifier: "SAMPLE-RV-01", basis: "Open complaint on Rev B" }],
  },
  before_after: {
    before: 1,
    after: 9,
    since: "2026-08-29",
    basis: "Complaints on the affected versions, by event date",
  },
  investigations: [{ id: "i1", investigation_identifier: "SAMPLE-INV-001", basis: "Holds complaints on Rev B" }],
  risks: [{ id: "r1", risk_identifier: "SAMPLE-RSK-01", basis: "Risk row on OrbitCare 300 (no version recorded)" }],
  capas: [
    {
      id: "k1",
      capa_identifier: "SAMPLE-CAPA-02",
      check: { label: "Effectiveness check planned for 2027-01-31; not yet recorded" },
      basis: "CAPA from SAMPLE-INV-001",
    },
  ],
  scope: TRACE,
};
const SCOPE_READ = {
  factor: {
    kind: "COMPONENT_LOT",
    id: "c1",
    lot: "NS-SL-2417 (Sample)",
    label: "Pressure Sensor (Sample) lot NS-SL-2417 (Sample)",
  },
  lots: [lot(3, 9, 150), lot(6, 0, 20), lot(8, 0, null)],
  totals: {
    lots: 3,
    with_complaints: 1,
    without_complaints: 2,
    excluded: 0,
    complaints: 9,
    released: 180,
    released_unknown: 0,
    shipped: 170,
    in_stock: 10,
    not_imported: 1,
    by_country: [{ country: "US", units: 170 }],
  },
  fingerprint: "f",
  truncated: false,
  by_market: [{ country: "US", units: 170, sites: 2, lots: ["LOT-003", "LOT-006"] }],
  by_site: [
    {
      consignee: "Cedar Plains Medical Center (Sample)",
      consignee_type: "Hospital",
      country: "US",
      units: 170,
      lots: ["LOT-003"],
    },
  ],
  investigations: [{ id: "i1", business_id: "INV-1", investigation_identifier: "SAMPLE-INV-001" }],
  changes: [{ id: "ch1", change_identifier: "SAMPLE-CHG-014" }],
  never_decides: "MDARIX lists the lots. It recommends no recall and no other field action.",
  cannot_tell: Array.from({ length: 8 }, (_, i) => `Limit ${i + 1}`),
};
const RUN = (file: string, simulated: boolean, aside = 0) => ({
  import_ref: file,
  entity: "lots",
  file_name: file,
  imported_at: "2026-11-17T10:00:00Z",
  imported_by: "MDARIX sample author",
  mapping_version: "lots-template:abc",
  masked_values: 0,
  sample: true,
  simulated,
  report: {
    rows_read: 9,
    rows_accepted: 9 - aside,
    rows_quarantined: aside,
    rows_changed: 0,
    rows_new: 9 - aside,
    balanced: true,
  },
  columns: [{ header: "Batch", column: "lot_id", help: null }],
  not_used: ["Storage Location"],
  lineage_rows: 9 - aside,
  reconciled: true,
});
const SOURCES = (after: boolean | null) => ({
  label: SIMULATED_LABEL,
  added_after_start: after,
  systems: [
    {
      key: "PLM",
      name: "PLM (product lifecycle)",
      objects: ["Items and revisions"],
      runs: after === null ? [] : [RUN("bill of materials (Simulated).csv", true, 1)],
    },
    {
      key: "ERP",
      name: "ERP (manufacturing and shipping)",
      objects: ["Batches"],
      runs: [RUN("Sample distribution export.csv", false)],
    },
    {
      key: "eQMS",
      name: "eQMS (quality system)",
      objects: ["CAPAs"],
      runs: [RUN("Sample complaints export.xlsx", false)],
    },
  ],
});

const api = (shownTab = "", extra: Partial<WorkspaceApi> = {}) =>
  ({
    session: { user_id: "u1", allowed_menu: ["home"] },
    work: { products: [], investigations: [], setInvestigationId: vi.fn() },
    open: vi.fn(),
    notify: vi.fn(),
    reportTab: vi.fn(),
    startStory: vi.fn(),
    shownTab,
    navigation: "new",
    isTrial: true,
    dataSource: SAMPLE_SOURCE,
    ...extra,
  }) as unknown as WorkspaceApi;
const render = (node: ReactNode, value: WorkspaceApi = api()) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);
const primaries = (html: string) => html.match(/class="ac-primary[^"]*"/g) ?? [];
const text = (html: string) =>
  html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&");
const at = vi.fn();
const LIGHT = {
  product: { id: "p1", name: "OrbitCare 300 Infusion Pump (Sample)", product_identifier: PRODUCT },
  versions: [
    { id: "v1", version_identifier: "Rev A" },
    { id: "v2", version_identifier: "Rev B" },
  ],
  selected_version: { id: "v2", version_identifier: "Rev B" },
  changes: [{ id: "ch1", change_identifier: "SAMPLE-CHG-014", complaints_before: 1, complaints_after: 9 }],
  configuration: { components: [], suppliers: [] },
};
const page = (view: string, more = "") =>
  render(<ProductHubSection />, api(`Product 360?product=${PRODUCT}&version=Rev+B&view=${view}${more}`));

beforeEach(() => {
  reads.data = { [`/api/v1/products/${PRODUCT}/product-360`]: LIGHT };
  at.mockReset();
});

describe("the Connected view (U1)", () => {
  it("shows the chain in order with every caption labelled simulated, and one main button: Trace", () => {
    reads.data[twinPath(PRODUCT, "Rev B")] = TWIN;
    const html = page("Connected");
    expect(primaries(html)).toHaveLength(1);
    expect(html).toContain("Trace NS-SL-2417 (Sample)");
    const labels = chainNodes(TWIN).map((node) => node.label);
    expect(labels).toEqual([
      "Version",
      "Parts",
      "Suppliers",
      "Component lots",
      "Finished lots",
      "Markets",
      "Complaints",
      "Investigations",
      "Risk rows",
      "CAPAs and checks",
      "Changes",
    ]);
    expect(chainNodes(TWIN).every((node) => node.caption.endsWith(SIMULATED_LABEL))).toBe(true);
    expect(text(html).split(SIMULATED_LABEL).length - 1).toBeGreaterThanOrEqual(11);
    expect(html).toContain("4 open of 20");
    // PV-1: with no version, only the product's own nodes.
    expect(chainNodes({ ...TWIN, version: null }).map((node) => node.key)).toEqual([
      "complaints",
      "investigations",
      "risks",
      "capas",
      "changes",
    ]);
  });
});

describe("the address carries the change, the preview and the scope", () => {
  it("round-trips through hubTab and hubPlace, and builds the reads from it", () => {
    const tab = hubTab({ tab: "Product 360", product: PRODUCT, version: "Rev B", view: "Lots", scope: SCOPE });
    expect(hubPlace(tab)).toMatchObject({ view: "Lots", scope: SCOPE, change: null, preview: null });
    expect(scopeOf(hubPlace(tab).scope)).toEqual({ kind: "COMPONENT_LOT", ref: "c1", lot: "NS-SL-2417 (Sample)" });
    expect(scopeOf("COMPONENT_LOT:c1:A:B")?.lot).toBe("A:B");
    expect(scopeOf("nonsense")).toBeNull();
    expect(scopePath(scopeOf(SCOPE)!, true)).toBe(
      "/api/v1/field-scope.csv?kind=COMPONENT_LOT&ref=c1&lot=NS-SL-2417+%28Sample%29",
    );
    const preview = hubPlace(hubTab({ tab: "Product 360", product: PRODUCT, preview: previewParam("c2", "s1") }));
    expect(previewOf(preview.preview)).toEqual({ component: "c2", supplier: "s1" });
    expect(impactPath(PRODUCT, preview)).toBe(`/api/v1/products/${PRODUCT}/change-impact?component=c2&supplier=s1`);
    expect(impactPath(PRODUCT, { change: "ch1", preview: null })).toBe(
      `/api/v1/products/${PRODUCT}/change-impact?change=ch1`,
    );
    expect(impactPath(PRODUCT, { change: null, preview: null })).toBeNull();
  });
});

describe("change impact (U2)", () => {
  it("lists each section with its basis, one main button, and the preview banner when no change is recorded", () => {
    reads.data[`/api/v1/products/${PRODUCT}/change-impact`] = IMPACT;
    const place = hubPlace(`Product 360?product=${PRODUCT}&view=Changes&change=ch1`);
    const html = render(<ChangeImpactPanel product={PRODUCT} place={place} at={at} />);
    expect(text(html)).toContain("If SAMPLE-CHG-014 holds: what to re-check");
    for (const title of [
      "Versions",
      "Lots · 2 lots, complaints first",
      "Markets",
      "Open complaints · 1",
      "Before and after",
      "Investigations",
      "Risk rows to re-check",
      "CAPAs to re-check",
    ])
      expect(text(html)).toContain(title);
    expect(html).toContain("Builds Rev B (lot record)");
    expect(html).toContain("Risk row on OrbitCare 300 (no version recorded)");
    expect(html).toContain("Effectiveness check planned");
    expect(html).toContain("1 lot: distribution not imported");
    expect(primaries(html)).toHaveLength(1);
    expect(html).toContain("Open the risk file");
    expect(html).toContain("Field-action scope from NS-SL-2417 (Sample)");
    expect(html).toContain("The change impact document");
    expect(html).not.toContain(PREVIEW_BANNER);
    const preview = {
      ...IMPACT,
      change: null,
      preview: true,
      before_after: null,
      previewed: { component: { name: "Control Board (Sample)" }, supplier: null },
    };
    reads.data[`/api/v1/products/${PRODUCT}/change-impact`] = preview;
    const shown = render(<ChangeImpactPanel product={PRODUCT} place={hubPlace(`Product 360?preview=c2`)} at={at} />);
    expect(shown).toContain(PREVIEW_BANNER);
    expect(text(shown)).toContain("If Control Board (Sample) changed: what to re-check");
    expect(shown).not.toContain("Before and after");
    expect(shown).not.toContain("The change impact document");
  });

  it("offers See impact on each change and Preview a change on the Changes tab", () => {
    const html = page("Changes");
    expect(html).toContain("See impact");
    expect(html).toContain("Preview a change");
    expect(primaries(html)).toHaveLength(0);
  });
});

describe("the field-action scope (U3)", () => {
  it("groups the lots, never reads 0 for a lot without distribution, and shows what it cannot tell", () => {
    const groups = scopeGroups(SCOPE_READ.lots);
    expect(groups.withComplaints.map((row) => row.id)).toEqual(["l3"]);
    expect(groups.withoutComplaints.map((row) => row.id)).toEqual(["l6"]);
    expect(groups.notImported.map((row) => row.id)).toEqual(["l8"]);
    expect(shippedText({ distribution_imported: false, shipped: null })).toBe(NOT_IMPORTED);
    expect(shippedText({ distribution_imported: false, shipped: 0 })).toBe(NOT_IMPORTED);
    reads.data["/api/v1/field-scope"] = SCOPE_READ;
    const html = render(<FieldScopePanel scope={SCOPE} at={at} />);
    expect(text(html)).toContain(
      "Field-action scope: lots built with Pressure Sensor (Sample) lot NS-SL-2417 (Sample)",
    );
    for (const title of [
      "With complaints · 1",
      "Without complaints yet · 1",
      `${NOT_IMPORTED} · 1`,
      "By market",
      "By site",
    ])
      expect(text(html)).toContain(title);
    const eight = html.slice(html.indexOf(`<th scope="row">${PRODUCT}-LOT-008`));
    expect(eight.slice(0, eight.indexOf("</tr>"))).toContain(NOT_IMPORTED);
    expect(eight.slice(0, eight.indexOf("</tr>"))).not.toMatch(/<td>0<\/td><td>—/);
    expect(html).toContain("What this list cannot tell you");
    expect(html.match(/<li>Limit \d<\/li>/g)).toHaveLength(8);
    expect(primaries(html)).toHaveLength(1);
    expect(html).toContain("Download the scope list (CSV)");
    expect(html).toContain("Sign it on the investigation (SAMPLE-INV-001 Lot impact)");
    expect(html).toContain("What changed this part?");
    expect(text(html)).not.toMatch(/we recommend|recommended recall|should recall/i);
  });
});

describe("Sources (simulated)", () => {
  it("labels every system card, shows each run as five steps, and says when the runs come", () => {
    reads.data[SOURCES_PATH] = SOURCES(false);
    const html = render(<SourcesView productId="p1" version="Rev B" at={at} />);
    expect(html).toContain("Where this product&#x27;s records came from");
    expect(text(html).split(SIMULATED_LABEL).length - 1).toBe(3);
    expect(html.match(/<ol class="uw-tw-steps"/g)).toHaveLength(3);
    for (const step of ["Fields found", "Mapped", "Checked", "Written / set aside", "Reconciled and loaded"])
      expect(html).toContain(step);
    expect(html).toContain("1 set aside");
    expect(primaries(html)).toHaveLength(1);
    expect(html).toContain("Open the connected product view");
    expect(html).not.toContain("added when your trial");
    reads.data[SOURCES_PATH] = SOURCES(null);
    const older = render(<SourcesView productId="p1" version="Rev B" at={at} />);
    expect(older).toContain("added when your trial&#x27;s sample is refreshed");
    expect(older).toContain("No run recorded yet.");
  });

  it("is a free trial's: a pilot has neither Connected nor Sources", () => {
    expect(productViews(true)).toContain("Sources (simulated)");
    expect(productViews(false)).not.toContain("Connected");
    expect(productViews(false)).not.toContain("Sources (simulated)");
    const pilot = render(
      <ProductHubSection />,
      api(`Product 360?product=${PRODUCT}&version=Rev+B`, { isTrial: false }),
    );
    expect(pilot).not.toContain(">Connected<");
    expect(pilot).not.toContain("Sources (simulated)");
  });
});

const flagship = (current: number): FlagshipRun =>
  ({
    run: "flagship",
    product: { id: "p1", ref: PRODUCT, name: "OrbitCare 300", label: "OrbitCare 300", version: "Rev B" },
    investigation: { id: "inv-1", ref: "SAMPLE-INV-001", question: "Why?" },
    change: { ref: "SAMPLE-CHG-014", description: "" },
    capa: { id: "k", ref: "SAMPLE-CAPA-02", title: "Restore inspection", check_planned: false, check_status: null },
    branch: null,
    ai_proposals: 0,
    mfa_verified: null,
    steps: Array.from({ length: 7 }, (_, index) => ({ key: `k${index}`, label: `S${index}`, done: index < current })),
    current,
    finished: false,
  }) as unknown as FlagshipRun;
const story = (run: FlagshipRun) => ({ sample: null, yours: null, flagship: run }) as unknown as OneStoryData;

describe("the flagship's links (no new step)", () => {
  it("step 2 opens Connected, step 3 knows the lot genealogy, step 7 opens the sensor lot's scope", () => {
    const two = render(<FlagshipView story={story(flagship(1))} run={flagship(1)} />);
    expect(two).toContain("See everything connected to Rev B");
    expect(primaries(two)).toHaveLength(1);
    expect(connectedTab(PRODUCT, "Rev B")).toBe(`Product 360?product=${PRODUCT}&version=Rev+B&view=Connected`);
    const seven = render(<FlagshipView story={story(flagship(6))} run={flagship(6)} />);
    expect(seven).toContain("Field-action scope from NS-SL-2417");
    expect(hubPlace(sampleScopeTab(PRODUCT, "Rev B"))).toMatchObject({
      view: "Lots",
      scope: "COMPONENT_LOT:SAMPLE-ORBIT-300-C1:NS-SL-2417 (Sample)",
    });
    const lotImpact = {
      list: { factor: { kind: "COMPONENT_LOT", lot: "NS-SL-2417 (Sample)" }, totals: { lots: 5, with_complaints: 2 } },
    };
    expect(evidenceStates({ lotImpact }).known.map((item) => item.label)).toEqual([
      "Lot genealogy: NS-SL-2417 (Sample) is in 5 lots; 2 have complaints",
    ]);
    expect(evidenceStates({ lotImpact: null }).known).toEqual([]);
  });
});

describe("generic system names only", () => {
  it("never shows a vendor's name on the twin's screens", () => {
    reads.data[twinPath(PRODUCT, "Rev B")] = TWIN;
    reads.data[`/api/v1/products/${PRODUCT}/change-impact`] = IMPACT;
    reads.data["/api/v1/field-scope"] = SCOPE_READ;
    reads.data[SOURCES_PATH] = SOURCES(false);
    const shown = [
      page("Connected"),
      render(<ChangeImpactPanel product={PRODUCT} place={hubPlace("Product 360?change=ch1")} at={at} />),
      render(<FieldScopePanel scope={SCOPE} at={at} />),
      render(<SourcesView productId="p1" version="Rev B" at={at} />),
    ]
      .map(text)
      .join(" ");
    const VENDORS =
      /\b(SAP|Oracle|TrackWise|Veeva|Teamcenter|Windchill|Coupa|Agile|Arena|MasterControl|ETQ|Siemens|PTC|Dynamics|NetSuite|Epicor|Infor)\b/i;
    expect(shown).not.toMatch(VENDORS);
    expect(shown).toContain("PLM");
    expect(shown).toContain("ERP");
  });
});
