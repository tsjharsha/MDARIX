import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ProductIdentityPanel, ResponsibleParties, partsLine } from "./sections/ImportReports";
import { SETTING_PERMISSIONS } from "./sections/Settings";
import { holdersText } from "./sections/Views";
import { TenantOverview } from "../admin/customers/TenantPages";

// 0.10.79: the Regulatory Leader (regulatory.review) may change Settings › Products; the read-only roles may not.
// Tenant 360 says beside Navigation that "Viewing as" needs New.

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path]) ?? null,
    reload: () => undefined,
  }),
}));

const render = (node: ReactNode, permissions: string[]) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider
      value={
        {
          session: { user_id: "u1", allowed_menu: ["home"], business_permissions: permissions },
          work: { products: [], investigations: [] },
          open: vi.fn(),
          notify: vi.fn(),
          navigation: "new",
          isTrial: true,
        } as unknown as WorkspaceApi
      }
    >
      {node}
    </WorkspaceContext.Provider>,
  );

const PRODUCT = { id: "p1", name: "VentraCare 250", product_identifier: "SAMPLE-VENTRA-250" };
resources.data["/api/v1/regulatory-reference/products/p1"] = {
  product_id: "p1",
  udi_di: "04000000025016",
  gmdn_code: null,
  gmdn_term: "Intensive-care ventilator",
  registrations: [],
};
resources.data["/api/v1/regulatory-reference/responsible-parties"] = { parties: [] };

const REGULATORY_LEADER = ["ai.run", "data.export", "regulatory.review", "regulatory.approve", "evidence.review"];
const RISK_REVIEWER = ["ai.run", "data.export", "risk.review", "evidence.review"];

describe("Settings › Products: the Regulatory Leader may change it", () => {
  it("offers Edit, Add and Set to the Regulatory Leader", () => {
    const products = render(<ProductIdentityPanel products={[PRODUCT]} />, REGULATORY_LEADER);
    expect(products).toContain(">Edit<");
    expect(render(<ResponsibleParties />, REGULATORY_LEADER)).toContain("Set a responsible party");
  });

  it("keeps the Risk Reviewer and the Executive read only", () => {
    for (const permissions of [RISK_REVIEWER, []]) {
      expect(render(<ProductIdentityPanel products={[PRODUCT]} />, permissions)).not.toContain(">Edit<");
      expect(render(<ResponsibleParties />, permissions)).not.toContain("Set a responsible party");
    }
  });

  it("names the Regulatory Reviewer among who can change it", () => {
    expect(SETTING_PERMISSIONS.Products).toEqual(["records.write", "regulatory.review"]);
    expect(holdersText(SETTING_PERMISSIONS.Products)).toContain("Regulatory Reviewer");
  });
});

describe("Tenant 360: personas need the new navigation", () => {
  it("says so beside Navigation", () => {
    const html = renderToStaticMarkup(
      <TenantOverview tenant={{ navigation: "classic", tenant_key: "T1" }} onEdit={() => undefined} />,
    );
    expect(html).toContain("Navigation");
    expect(html).toContain("“Viewing as” personas need New.");
  });
});

describe("Settings › Products: the MIR address and contact parts (B8 step 6)", () => {
  const party = {
    id: "x1",
    market: "EU",
    role: "AUTHORISED_REPRESENTATIVE",
    organisation: "Sample EU Rep",
    address: "1 Rue Exemple, Paris",
    contact_name: "Ana Sample",
    contact_email: "ar@example.test",
    contact_phone: "+33 1 00 00 00 00",
    srn: "FR-AR-000000001",
  };
  it("names the parts still to enter, then shows them once entered", () => {
    expect(partsLine(party)).toBe("MIR address and contact parts to enter (6 of 6)");
    const full = {
      ...party,
      street: "1 Rue Exemple",
      postcode: "75001",
      city: "Paris",
      country_code: "FR",
      contact_first_name: "Ana",
      contact_last_name: "Sample",
    };
    expect(partsLine(full)).toBe("1 Rue Exemple, 75001 Paris, FR · Ana Sample");
    resources.data["/api/v1/regulatory-reference/responsible-parties"] = { parties: [party] };
    expect(render(<ResponsibleParties />, REGULATORY_LEADER)).toContain("MIR address and contact parts to enter");
    resources.data["/api/v1/regulatory-reference/responsible-parties"] = { parties: [] };
  });
});
