// 0.10.94 (W1): Supplier 360 on the new navigation: the list, one supplier's page, the pattern box's wording (rule
// P-1, never a confirmed signal), the SCAR line, the lots offered in a free trial only (owner, 10 Nov 2026), and the
// personas that reach Products by a link (spec 4, 9: S360-06, -08, -12, -13, -16, P360-10).
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ProductHubSection } from "./sections/ProductHub";
import { supplierViews } from "./sections/SupplierHub";
import { PERSONA_TABS, shownTabs, tabOfSection, visibleTabs } from "./HybridShell";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    const value = (path && (resources.data[path] ?? resources.data[path.split("?")[0]])) ?? null;
    return { state: "ready", data: value, reload: () => undefined };
  },
}));

const api = (shownTab: string, overrides: Partial<WorkspaceApi> = {}) =>
  ({
    session: { user_id: "u1", business_permissions: ["records.write"], allowed_menu: ["investigations"] },
    work: { products: [], investigations: [], requestOpenInvestigation: vi.fn() },
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

const SAMPLE = { kind: "SAMPLE", label: "Sample", detail: "Fictional sample data" };
const box = (overrides: Record<string, unknown>) => ({
  rule: "P-1",
  rule_version: 1,
  window_days: 90,
  thresholds: { complaints_per_version: 2, versions: 2 },
  found: false,
  investigations: [],
  versions: [],
  ...overrides,
});
const page = (pattern: Record<string, unknown>, overrides: Record<string, unknown> = {}) => ({
  supplier: {
    id: "s1",
    supplier_identifier: "SAMPLE-SUP-B",
    name: "NovaSense Components (Sample)",
    status: "active",
    origin: SAMPLE,
    since: "2026-08-17T00:00:00Z",
  },
  parts: [],
  versions: [
    {
      version_id: "v-b",
      version_identifier: "Rev B",
      product_id: "p1",
      product_name: "OrbitCare 300 (Sample)",
      product_identifier: "SAMPLE-ORBIT-300",
    },
  ],
  counts: {
    parts: 1,
    products: 1,
    versions: 1,
    lots_on_versions: 6,
    complaints: 14,
    complaints_90d: 14,
    investigations: 1,
    changes: 1,
    evidence: 2,
    evidence_requests: 0,
    capas: 1,
  },
  pattern: box(pattern),
  trend: { months: [], series: [], markers: [] },
  complaints: { count: 14, items: [{ id: "c1", complaint_identifier: "SAMPLE-RV-01", product_version_id: "v-b" }] },
  investigations: [],
  changes: [],
  evidence: [],
  evidence_requests: [],
  capas: [],
  scar_note: "Supplier corrective action requests (SCAR): planned for a later release.",
  never_decides: "MDARIX lists what was recorded and why each record is linked; it does not infer a cause.",
  ...overrides,
});
const PATH = "/api/v1/suppliers/SAMPLE-SUP-B";

beforeEach(() => {
  resources.data = {};
});

describe("the supplier list", () => {
  it("lists each supplier with its origin and counts, a link to its page (S360-16)", () => {
    resources.data["/api/v1/suppliers"] = [
      {
        id: "s9",
        supplier_identifier: "KS-1",
        name: "Kestrel Sensors",
        origin: {
          kind: "EXTERNAL",
          label: "From SAP S/4",
          detail: "ID KS-1 · last loaded 2026-11-02",
          system: "SAP S/4",
        },
        parts: 2,
        products: 2,
        versions: 3,
        complaints_90d: 9,
        open_investigations: 1,
      },
    ];
    const html = render(<ProductHubSection />, api("Suppliers"));
    expect(html).toContain("Kestrel Sensors");
    expect(html).toContain("From SAP S/4");
    expect(html).toContain("2 · 3");
    expect(html).not.toMatch(/>(Edit|Delete|Save)</);
  });
});

describe("one supplier's page", () => {
  it("says plainly that one version cannot show a cross-product pattern, and prints the rule (S360-08)", () => {
    resources.data[PATH] = page({
      case: "ONE_VERSION",
      text: "NovaSense parts are in 1 product version: OrbitCare 300 Rev B. ... No other product or version uses these parts, so a cross-product pattern cannot be seen.",
    });
    const html = render(<ProductHubSection />, api("Suppliers?supplier=SAMPLE-SUP-B"));
    expect(html).toContain("<h1");
    expect(html).toContain("Patterns across versions");
    expect(html).toContain("a cross-product pattern cannot be seen");
    expect(html).toContain("Rule P-1 version 1");
    expect(html).toContain("never a confirmed signal");
    expect(html).not.toContain("Open an investigation");
    expect(html).toContain("Recorded supplier since");
  });

  it("offers the pattern's open investigation, else a new one a person confirms (S360-06, S360-07)", () => {
    const found = {
      found: true,
      case: "PATTERN",
      text: "Pattern to review: pressure reading high on 2 versions of 2 products that contain Kestrel parts. This is a pattern to review, not a confirmed signal.",
      versions: [{ version_id: "v-b", product: "OrbitCare 300", version: "Rev B", recent: 3 }],
    };
    resources.data[PATH] = page(found);
    const html = render(<ProductHubSection />, api("Suppliers?supplier=SAMPLE-SUP-B"));
    expect(html).toContain("Pattern to review");
    expect(html).toContain("not a confirmed signal");
    expect(html).toContain("Open an investigation");
    resources.data[PATH] = page({ ...found, investigations: [{ ref: "INV-0042", held: 12 }] });
    expect(render(<ProductHubSection />, api("Suppliers?supplier=SAMPLE-SUP-B"))).toContain(
      "Open INV-0042 (covers 12 of these complaints)",
    );
  });

  it("names SCAR as a later release, nothing more (S360-12)", () => {
    resources.data[PATH] = page({ case: "ONE_VERSION", text: "One version." });
    const html = render(<ProductHubSection />, api("Suppliers?supplier=SAMPLE-SUP-B&view=CAPAs"));
    expect(html).toContain("Supplier corrective action requests (SCAR): planned for a later release.");
    expect(html).not.toMatch(/>\s*(Raise|Send|Create) (a )?SCAR/i);
  });

  it("offers the lots in a free trial only (owner, 10 Nov 2026)", () => {
    expect(supplierViews(true)).toContain("Lots");
    expect(supplierViews(false)).not.toContain("Lots");
    resources.data[PATH] = page({ case: "ONE_VERSION", text: "One version." });
    const pilot = render(<ProductHubSection />, api("Suppliers?supplier=SAMPLE-SUP-B&view=Lots", { isTrial: false }));
    expect(pilot).not.toMatch(/role="tab"[^>]*>Lots</);
    expect(pilot).not.toContain("Lot genealogy not imported");
    const trial = render(<ProductHubSection />, api("Suppliers?supplier=SAMPLE-SUP-B"));
    expect(trial).toMatch(/role="tab"[^>]*>Lots</);
  });
});

describe("personas without the Products tab (P360-10, S360-13)", () => {
  it("reach Product 360 by a link, shown as the extra tab while it is open", () => {
    const regulatory = ["home", "complaints", "trees", "reports", "records"];
    const all = Object.values(PERSONA_TABS).map((tab) => tab.section as string);
    expect(visibleTabs(regulatory, all)).not.toContain("products");
    expect(tabOfSection("Product 360")).toBe("products");
    expect(shownTabs(regulatory, "products")).toEqual({ tabs: [...regulatory, "products"], extra: "products" });
  });
});
