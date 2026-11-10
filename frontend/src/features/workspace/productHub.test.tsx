// 0.10.94 (W1): Product 360 on the new navigation: its address, the product cards, one product's page (empty states,
// the Rev A / Rev B compare, origin chips, no edit control, links out) and the rules behind them (spec 3, 9).
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { SAMPLE_SOURCE } from "./complaintList";
import {
  compareConfigurations,
  correctionNote,
  hubPlace,
  hubTab,
  inDataShown,
  productTab,
  rateText,
  supplierTab,
  type Origin,
} from "./productHub";
import { Changes, OriginChip, ProductHubSection, recordLine } from "./sections/ProductHub";
import { TrendHeroes } from "./sections/TrendCheck";
import type { TrendBoard, TrendItem } from "./signalAi";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    const value = (path && (resources.data[path] ?? resources.data[path.split("?")[0]])) ?? null;
    return { state: "ready", data: value, reload: () => undefined };
  },
}));

const SAMPLE: Origin = { kind: "SAMPLE", label: "Sample", detail: "Fictional sample data" };
const PLM: Origin = {
  kind: "EXTERNAL",
  label: "From SAP PLM",
  detail: "ID P-1 · last loaded 2026-11-01",
  system: "SAP PLM",
};

const api = (shownTab: string, overrides: Partial<WorkspaceApi> = {}) =>
  ({
    session: { user_id: "u1" },
    work: { products: [], investigations: [] },
    open: vi.fn(),
    notify: vi.fn(),
    reportTab: vi.fn(),
    shownTab,
    navigation: "new",
    isTrial: true,
    ...overrides,
  }) as unknown as WorkspaceApi;
const render = (node: ReactNode, value: WorkspaceApi) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

const sensor = (revision: string) => ({
  id: `c1-${revision}`,
  component_identifier: "ORBIT-C1",
  name: "Pressure Sensor",
});
const board = { id: "c2", component_identifier: "ORBIT-C2", name: "Control Board" };
const REV_A = {
  components: [sensor("a"), board],
  suppliers: [
    { id: "s-a", name: "Precision Sensors Ltd", supplier_identifier: "SUP-A", component_identifier: "ORBIT-C1" },
    { id: "s-a", name: "Precision Sensors Ltd", supplier_identifier: "SUP-A", component_identifier: "ORBIT-C2" },
  ],
};
const REV_B = {
  components: [sensor("b"), board],
  suppliers: [
    { id: "s-b", name: "NovaSense Components", supplier_identifier: "SUP-B", component_identifier: "ORBIT-C1" },
    { id: "s-a", name: "Precision Sensors Ltd", supplier_identifier: "SUP-A", component_identifier: "ORBIT-C2" },
  ],
};
const CHG = {
  id: "ch1",
  change_identifier: "SAMPLE-CHG-014",
  change_type: "Supplier change",
  description: "Supplier changed; incoming inspection 32 → 13 units per lot",
  effective_timestamp: "2026-08-22T00:00:00Z",
  affects: ["ORBIT-C1"],
  affects_names: ["Pressure Sensor"],
  versions: ["v-b"],
  complaints_before: 2,
  complaints_after: 14,
  origin: SAMPLE,
};

beforeEach(() => {
  resources.data = {};
});

describe("the page's address", () => {
  it("names the product, its version, section and list, or the supplier, in words people read", () => {
    const tab = hubTab({
      tab: "Product 360",
      product: "SAMPLE-ORBIT-300",
      version: "Rev B",
      view: "Records",
      list: "capas",
    });
    expect(tab).toBe("Product 360?product=SAMPLE-ORBIT-300&version=Rev+B&view=Records&list=capas");
    expect(hubPlace(tab)).toMatchObject({
      tab: "Product 360",
      product: "SAMPLE-ORBIT-300",
      version: "Rev B",
      list: "capas",
    });
    expect(productTab("SAMPLE-PULSE-410", "Rev A")).toBe("Product 360?product=SAMPLE-PULSE-410&version=Rev+A");
    expect(supplierTab("SAMPLE-SUP-B")).toBe("Supplier 360?supplier=SAMPLE-SUP-B");
    expect(hubPlace("Supplier 360?supplier=X").tab).toBe("Supplier 360");
    // An unknown list is ignored rather than trusted.
    expect(hubPlace("Product 360?product=P&list=passwords").list).toBeNull();
  });
});

describe("the rules behind the page", () => {
  it("compares Rev A with Rev B: the sensor's supplier changed, with the change named beside it (P360-05)", () => {
    const rows = compareConfigurations(REV_A, REV_B, [CHG], "v-b");
    expect(rows[0]).toMatchObject({ key: "ORBIT-C1", state: "changed" });
    expect(rows[0].before.map((row) => row.name)).toEqual(["Precision Sensors Ltd"]);
    expect(rows[0].after.map((row) => row.name)).toEqual(["NovaSense Components"]);
    expect(rows[0].changes.map((row) => row.change_identifier)).toEqual(["SAMPLE-CHG-014"]);
    expect(rows[1]).toMatchObject({ key: "ORBIT-C2", state: "same", changes: [] });
    expect(
      compareConfigurations({ components: [], suppliers: [] }, REV_B, [], null).every((r) => r.state === "added"),
    ).toBe(true);
  });

  it("gives no rate from unknown units, and follows the trial's data choice", () => {
    expect(rateText(31.11, true)).toBe("31.1 per 1,000 units");
    expect(rateText(null, true)).toBe("units not known");
    expect(rateText(12, false)).toBe("units not known");
    expect(inDataShown(SAMPLE, SAMPLE_SOURCE)).toBe(true);
    expect(inDataShown(PLM, SAMPLE_SOURCE)).toBe(false);
    expect(inDataShown(SAMPLE, "TRIAL_UPLOAD")).toBe(false);
    expect(inDataShown(PLM, undefined)).toBe(true);
  });

  it("says where to correct imported master data, and offers no edit (P360-07)", () => {
    expect(correctionNote(PLM)).toBe("Correct it in SAP PLM and import again.");
    expect(correctionNote(SAMPLE)).toBeNull();
    expect(renderToStaticMarkup(<OriginChip origin={PLM} />)).toContain("From SAP PLM");
    expect(renderToStaticMarkup(<OriginChip origin={PLM} />)).toContain("last loaded 2026-11-01");
  });

  it("states a planned effectiveness check as planned, never effective (P360-09)", () => {
    const line = recordLine("capas", {
      capa_identifier: "SAMPLE-CAPA-02",
      title: "Restore incoming inspection",
      check: { state: "PLANNED", label: "Effectiveness check planned for 2027-01-24; not yet recorded" },
      basis: "CAPA from SAMPLE-INV-001",
    });
    expect(line.text).toContain("planned for 2027-01-24; not yet recorded");
    expect(line.text).not.toMatch(/\beffective\b(?! check)/i);
  });

  it("lists changes with their dates and the before/after split, never as a cause (P360-04)", () => {
    const html = renderToStaticMarkup(<Changes changes={[CHG]} />);
    expect(html).toContain("SAMPLE-CHG-014");
    expect(html).toContain("Before it took effect 2 · after 14");
    expect(html).toContain("it does not infer a cause");
    expect(renderToStaticMarkup(<Changes changes={[]} />)).toContain("No change is recorded");
  });
});

describe("the product list", () => {
  it("shows a card per product with its newest version's counts as links, and an empty state", () => {
    resources.data["/api/v1/products"] = [
      {
        id: "p1",
        product_identifier: "SAMPLE-ORBIT-300",
        name: "OrbitCare 300 (Sample)",
        product_family: "Infusion",
        available_versions: ["Rev A", "Rev B"],
        origin: SAMPLE,
        counts: {
          version_identifier: "Rev B",
          open_complaints: 14,
          open_investigations: 1,
          open_signals: 1,
          open_capas: 1,
        },
      },
    ];
    const html = render(<ProductHubSection />, api("Product 360"));
    expect(html).toContain("OrbitCare 300 (Sample)");
    expect(html).toContain("<strong>14</strong> open complaints");
    expect(html).toContain("trends to review");
    expect(html).toContain('class="uw-ph-dot"');
    expect(html.indexOf("Rev B")).toBeLessThan(html.indexOf("Rev A"));
    expect(html).not.toMatch(/>(Edit|Delete|Save)</);
    resources.data["/api/v1/products"] = [];
    expect(render(<ProductHubSection />, api("Product 360"))).toContain(
      "Import your products, lots and complaints in Import your data.",
    );
  });
});

describe("one product's page", () => {
  const light = (overrides: Record<string, unknown> = {}) => ({
    product: {
      id: "p1",
      name: "OrbitCare 300 (Sample)",
      product_identifier: "SAMPLE-ORBIT-300",
      lifecycle_status: "active",
      origin: SAMPLE,
    },
    selected_version: { id: "v-b", version_identifier: "Rev B" },
    versions: [
      { id: "v-a", version_identifier: "Rev A", release_timestamp: "2025-11-15T00:00:00Z" },
      { id: "v-b", version_identifier: "Rev B", release_timestamp: "2026-08-27T00:00:00Z" },
    ],
    configuration: REV_B,
    changes: [CHG],
    manufacturing: { lots: [] },
    limitations: [],
    ...overrides,
  });

  it("shows the hero head with the versions newest first and Compare with Rev A, then the six tiles", () => {
    resources.data["/api/v1/products/SAMPLE-ORBIT-300/product-360"] = light();
    resources.data["/api/v1/products/SAMPLE-ORBIT-300/links"] = {
      tiles: {
        complaints: { count: 0, items: [] },
        investigations: {
          count: 2,
          items: [
            { id: "i1", investigation_identifier: "SAMPLE-INV-001", status: "Open" },
            // PV-1: one recording no version is under every version, as the whole product's.
            { id: "i2", investigation_identifier: "INV-0002", status: "Open", versions: [], applies_to: "PRODUCT" },
          ],
        },
        signals: { count: 0, items: [] },
        capas: { count: 0, items: [] },
        risks: { count: 0, items: [] },
        reports: { count: 0, items: [] },
      },
      monthly: { months: [], series: [], markers: [] },
    };
    const html = render(<ProductHubSection />, api("Product 360?product=SAMPLE-ORBIT-300"));
    expect(html).toContain('class="hx-monitor');
    expect(html).toContain("<h1");
    expect(html).toContain("Compare with Rev A");
    expect(html.indexOf(">Rev B<")).toBeLessThan(html.indexOf(">Rev A<"));
    expect(html).toContain("No complaints recorded for this version");
    expect(html).toContain("SAMPLE-INV-001");
    expect(html).toContain("Open · applies to the whole product");
    expect(html).toContain("No risks recorded in MDARIX for this product");
    expect(html).toContain("Sample");
    // G-2: the operational parts are flat (no hero band below the head).
    expect(html.match(/hx-monitor"/g)?.length ?? 0).toBeLessThanOrEqual(1);
  });

  it("compares Rev A beside Rev B, the supplier link opening Supplier 360 (P360-05)", () => {
    resources.data["/api/v1/products/SAMPLE-ORBIT-300/product-360?light=1"] = light();
    resources.data["/api/v1/products/SAMPLE-ORBIT-300/product-360?light=1&version_id=Rev%20B"] = light();
    resources.data["/api/v1/products/SAMPLE-ORBIT-300/product-360?light=1&version_id=Rev%20A"] = light({
      configuration: REV_A,
    });
    const html = render(
      <ProductHubSection />,
      api("Product 360?product=SAMPLE-ORBIT-300&version=Rev+B&view=Configuration&compare=Rev+A"),
    );
    expect(html).toContain("Precision Sensors Ltd");
    expect(html).toContain("NovaSense Components");
    expect(html).toContain("Different supplier");
    expect(html).toContain("SAMPLE-CHG-014");
  });

  it("tells the version story as flat cards from the same read as before (spec 3.3, G-2)", () => {
    resources.data["/api/v1/products/SAMPLE-ORBIT-300/product-360"] = light();
    resources.data["/api/v1/products/p1/versions/v-b/story"] = {
      status: "READY_FOR_REVIEW",
      version: { version_identifier: "Rev B", lifecycle_status: "active", release_timestamp: "2026-08-27T00:00:00Z" },
      counts: { complaints: 14, investigations: 1, evidence: 0 },
      complaints: [{ business_id: "CMP-1", complaint_identifier: "SAMPLE-CMP-1", status: "Open" }],
      investigations: [{ business_id: "INV-1", investigation_identifier: "SAMPLE-INV-001", status: "Open" }],
      evidence: [],
    };
    const html = render(
      <ProductHubSection />,
      api("Product 360?product=SAMPLE-ORBIT-300&version=Rev+B&view=Version+story"),
    );
    expect(html).toContain("Investigations with a complaint on Rev B");
    expect(html).toContain("SAMPLE-CMP-1");
    expect(html).toContain("SAMPLE-INV-001");
    expect(html).toContain("None recorded for Rev B");
    expect(html).toContain("See all on Records");
    expect(html).toContain("it does not infer a cause");
    expect(html).not.toContain("Product Version Story");
    expect(html.match(/hx-monitor"/g)?.length ?? 0).toBeLessThanOrEqual(1);
  });

  it("says plainly when a version has no lots, and when a product has no versions (P360-02, P360-03)", () => {
    resources.data["/api/v1/products/SAMPLE-ORBIT-300/product-360"] = light();
    expect(render(<ProductHubSection />, api("Product 360?product=SAMPLE-ORBIT-300&view=Lots"))).toContain(
      "No lots recorded for Rev B.",
    );
    resources.data["/api/v1/products/SAMPLE-ORBIT-300/product-360"] = light({ selected_version: null, versions: [] });
    const none = render(<ProductHubSection />, api("Product 360?product=SAMPLE-ORBIT-300&view=Configuration"));
    expect(none).toContain("No versions recorded");
    expect(none).toContain("a configuration belongs to a version");
  });
});

describe("a chosen version is respected (PV-1)", () => {
  it("names every version an investigation spans, and says when one records none", () => {
    expect(recordLine("investigations", { investigation_identifier: "I1", versions: ["Rev A", "Rev B"] }).text).toBe(
      "Rev A, Rev B",
    );
    expect(
      recordLine("investigations", { investigation_identifier: "I2", versions: [], applies_to: "PRODUCT" }).text,
    ).toBe("applies to the whole product");
    expect(recordLine("risks", { risk_identifier: "R1", description: "Alarm", applies_to: "PRODUCT" }).text).toBe(
      "Alarm · whole product (no version recorded)",
    );
  });
});

describe("links into Product 360 (7a, P360-08)", () => {
  it("gives a trend check card its product version, one click away", () => {
    const rising = {
      key: "g1",
      name: "OrbitCare 300 (Sample) Rev B",
      result: "SIGNIFICANT",
      recent: 9,
      recent_days: 30,
      expected: 1,
      ratio: 9.3,
      history: 6,
      history_days: 180,
      baseline: "PREVIOUS_VERSION",
      basis: "UNITS",
      lots: [],
      open_signals: [],
      product: { id: "p1", business_id: null, identifier: "SAMPLE-ORBIT-300", name: "OrbitCare 300 (Sample)" },
      product_version: { id: "v1", business_id: null, version_identifier: "Rev B" },
    } as unknown as TrendItem;
    const board = { items: [rising], recent_days: 30, history_days: 180, min_complaints: 3, summary: {} };
    const onProduct = vi.fn();
    const html = renderToStaticMarkup(
      <TrendHeroes
        board={board as unknown as TrendBoard}
        action={() => null}
        source={SAMPLE_SOURCE}
        onProduct={onProduct}
      />,
    );
    expect(html).toContain("Product 360:");
    expect(html).toContain("Rev B</button>");
    expect(
      renderToStaticMarkup(<TrendHeroes board={board as unknown as TrendBoard} action={() => null} />),
    ).not.toContain("Product 360:");
    expect(productTab(rising.product.identifier!, "Rev B")).toBe("Product 360?product=SAMPLE-ORBIT-300&version=Rev+B");
  });
});
