// 0.10.87, the owner-approved duplication review: each trial page of the new navigation says each thing once. One
// describe per page, named with the review's rows.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { HomeSection } from "./sections/Home";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    const value = (path && resources.data[path.split("?")[0]]) ?? null;
    return { state: "ready", data: value, reload: () => undefined };
  },
}));

const api = (overrides: Partial<WorkspaceApi> = {}) =>
  ({
    session: {
      user_id: "u1",
      display_name: "Asha Quality",
      business_permissions: ["records.write"],
      current_tenant: { tenant_name: "Medisynth Devices" },
    },
    work: { products: [], investigations: [] },
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
    persona: "admin",
    personaTabs: ["home", "complaints", "trees", "reports", "investigations", "trends", "records", "team"],
    ...overrides,
  }) as unknown as WorkspaceApi;
const render = (node: ReactNode, value: WorkspaceApi = api()) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

beforeEach(() => {
  resources.data = {};
});

describe("Home (rows 15-17)", () => {
  const rise = {
    key: "orbit",
    name: "OrbitCare 300 Rev B",
    product: { id: "o", business_id: "PRD-1", identifier: "SAMPLE-ORBIT-300", name: "OrbitCare" },
    recent: 9,
    expected: 0.97,
    ratio: 9.3,
    result: "SIGNIFICANT",
  };

  it("names the organization and the data on the top bar only, and the rising product once, in the Trends card", () => {
    resources.data["/api/v1/triage/trends"] = { items: [rise] };
    const html = render(<HomeSection heading={{ current: null }} />);
    const date = html.slice(html.indexOf('class="uw-home-date"'), html.indexOf("</header>"));
    expect(date).toContain("times in");
    expect(date).not.toContain("Medisynth Devices");
    expect(html).not.toContain("Home · sample data");
    expect(html).not.toContain('class="uw-viewing"');
    expect(html).toContain("Products rising against their history");
    expect(html.split("OrbitCare 300 Rev B").length - 1).toBe(1);
    // Outside a trial the persona eyebrow stays.
    expect(render(<HomeSection heading={{ current: null }} />, api({ isTrial: false }))).toContain("Viewing as");
  });
});
