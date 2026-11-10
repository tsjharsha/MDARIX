import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { FirstContact, ShippedPicker } from "./sections/FirstContact";
import {
  identifierChip,
  NEW_IDENTIFIER,
  shipmentPick,
  typedOver,
  type IdentifierEntry,
  type ShippedItem,
} from "./intake";

// 0.10.93 (B2 step 5, spec 4.2): Log a case with ID-1 ("Not sure", confirmed or unconfirmed with a source) and the
// S-1 issue category in plain words.

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({ state: "ready", data: path ? resources.data[path.split("?")[0]] : null }),
  Drawer: ({ title, children }: { title: string; children: unknown }) => (
    <div data-title={title}>{children as never}</div>
  ),
}));

const GUIDE = {
  version: "case-check-starter-2",
  questions: [],
  answers: [],
  note: "",
  outcomes: [],
  table: [],
  requests: [{ code: "NONE", label: "Nothing" }],
  use_environments: [],
  user_types: [],
  harm_words: { version: "1", words: [] },
  fault_words: { version: "1", words: [] },
  levels: [],
  zones: ["UTC"],
  issue_categories: [
    { code: "MALFUNCTION", label: "Malfunction" },
    { code: "USAGE_HELP", label: "Usage help" },
  ],
  channels: [
    { code: "PHONE", label: "Phone" },
    { code: "REGULATOR", label: "Regulator notice" },
  ],
  patients: [
    { code: "NONE", label: "None" },
    { code: "NOT_KNOWN", label: "Not known" },
  ],
  identifiers: {
    keys: [
      { code: "product", label: "Product" },
      { code: "lot", label: "Lot" },
      { code: "serial", label: "Serial number" },
      { code: "udi", label: "UDI" },
    ],
    not_sure: ["version", "lot", "serial"],
    sources: [
      { code: "CALLER", label: "As told by the caller" },
      { code: "LABEL_OR_PHOTO", label: "Label or photo" },
    ],
  },
  starter_mark: "",
};

describe("Log a case (B2)", () => {
  it("offers Not sure for version, lot and serial only, and the issue category in plain words", () => {
    resources.data["/api/v1/intake/guide"] = GUIDE;
    const html = renderToStaticMarkup(
      <WorkspaceContext.Provider
        value={
          {
            session: { business_permissions: ["case.log"] },
            work: { products: [] },
            open: vi.fn(),
          } as unknown as WorkspaceApi
        }
      >
        <FirstContact part="calls" startLogging="CONTACT" />
      </WorkspaceContext.Provider>,
    );
    expect(html).toContain('data-title="Log a case"');
    expect(html.match(/Not sure<\/label>/g)).toHaveLength(3);
    expect(html).toContain("Usage help");
    expect(html).toContain("it never decides a complaint or a report");
    expect(html).toContain("Save the case");
    // Spec 4.2: the channel and its reference, patients and harm, what was tried, and who knew first.
    for (const text of [
      "Channel",
      "Regulator notice",
      "Reference in that channel (optional)",
      "Patients involved:",
      "What happened to the patient (optional)",
      "What was tried on the call",
    ])
      expect(html).toContain(text);
    expect(html.match(/name="patients"/g)).toHaveLength(2);
  });

  it("shows Not sure, Confirmed or Unconfirmed, and nothing for an empty identifier", () => {
    expect(identifierChip({ ...NEW_IDENTIFIER, not_sure: true }, false)?.label).toBe("Not sure");
    expect(identifierChip(NEW_IDENTIFIER, true)?.label).toBe("Unconfirmed");
    expect(identifierChip({ ...NEW_IDENTIFIER, status: "CONFIRMED", source: "LABEL_OR_PHOTO" }, true)?.label).toBe(
      "Confirmed",
    );
    expect(identifierChip(undefined, false)).toBeNull();
  });

  // ID-2: "Products and lots shipped to this hospital", from the shipment records, above the free picker.
  const SHIPPED = "/api/v1/intake/shipped-to";
  const ITEM: ShippedItem = {
    site: "Cedar Plains Medical Center (Sample)|US",
    consignee: "Cedar Plains Medical Center (Sample)",
    country: "US",
    ship_date: "2026-10-01",
    quantity: 60,
    lot: "SAMPLE-ORBIT-300-LOT-003",
    version: "Rev B",
    product_id: "p-1",
    product_name: "OrbitCare 300",
  };
  const picker = (site = "Cedar Plains Medical Center (Sample)") =>
    renderToStaticMarkup(<ShippedPicker site={site} onPick={vi.fn()} />);

  it("offers the products and lots shipped to the hospital, newest shipment of each lot once", () => {
    const older = { ...ITEM, ship_date: "2026-09-01" };
    resources.data[SHIPPED] = {
      sites: [{ site: ITEM.site, consignee: ITEM.consignee, country: "US" }],
      items: [ITEM, older],
      truncated: false,
    };
    const html = picker();
    expect(html).toContain("Products and lots shipped to this hospital");
    expect(html.match(/lot SAMPLE-ORBIT-300-LOT-003/g)).toHaveLength(1);
    expect(html).toContain("OrbitCare 300 Rev B");
    expect(html).toContain("filled in as unconfirmed");
  });

  it("asks which site when several share the name, and shows nothing without a match or a site", () => {
    const other = { ...ITEM, site: "Cedar Plains Medical Center (Sample)|DE", country: "DE" };
    resources.data[SHIPPED] = {
      sites: [
        { site: ITEM.site, consignee: ITEM.consignee, country: "US" },
        { site: other.site, consignee: ITEM.consignee, country: "DE" },
      ],
      items: [ITEM, other],
      truncated: false,
    };
    const several = picker();
    expect(several).toContain("Several sites have this name: choose one");
    expect(several).toContain("Cedar Plains Medical Center (Sample) (DE)");
    expect(several).not.toContain("lot SAMPLE-ORBIT-300-LOT-003");
    resources.data[SHIPPED] = { sites: [], items: [], truncated: false };
    expect(picker()).toBe("");
    resources.data[SHIPPED] = {
      sites: [{ site: ITEM.site, consignee: ITEM.consignee, country: "US" }],
      items: [ITEM],
      truncated: false,
    };
    expect(picker("  ")).toBe("");
  });

  it("fills product, version and lot as unconfirmed, source shipment record, and lets the person change them", () => {
    const filled = shipmentPick(ITEM, { serial: NEW_IDENTIFIER });
    expect(filled.product).toBe("p-1");
    expect(filled.lot).toBe("SAMPLE-ORBIT-300-LOT-003");
    const entry: IdentifierEntry = { not_sure: false, status: "UNCONFIRMED", source: "SHIPMENT_RECORD" };
    expect(filled.ids).toEqual({ serial: NEW_IDENTIFIER, product: entry, version: entry, lot: entry });
    expect(identifierChip(filled.ids.lot, true)?.label).toBe("Unconfirmed");
    // A lot without a loaded product or version fills the lot only.
    expect(shipmentPick({ ...ITEM, product_id: null, version: null }, {}).ids).toEqual({ lot: entry });
    // Typed over: back to the default entry; a Not sure the person ticked stays.
    expect(typedOver(filled.ids, "lot", "version")).toEqual({ serial: NEW_IDENTIFIER, product: entry });
    const unsure = { ...filled.ids, lot: { ...entry, not_sure: true } };
    expect(typedOver(unsure, "lot").lot.not_sure).toBe(true);
  });

  it("keeps the free picker and Not sure in the drawer, whatever the shipment records hold", () => {
    resources.data["/api/v1/intake/guide"] = GUIDE;
    resources.data[SHIPPED] = {
      sites: [{ site: ITEM.site, consignee: ITEM.consignee, country: "US" }],
      items: [ITEM],
      truncated: false,
    };
    const html = renderToStaticMarkup(
      <WorkspaceContext.Provider
        value={
          {
            session: { business_permissions: ["case.log"] },
            work: { products: [{ id: "p-1", name: "OrbitCare 300" }] },
            open: vi.fn(),
          } as unknown as WorkspaceApi
        }
      >
        <FirstContact part="calls" startLogging="CONTACT" />
      </WorkspaceContext.Provider>,
    );
    // No site asked yet: no quick picker, the free picker as today.
    expect(html).not.toContain("Products and lots shipped to this hospital");
    expect(html).toContain("Not named");
    expect(html.match(/Not sure<\/label>/g)).toHaveLength(3);
  });
});
