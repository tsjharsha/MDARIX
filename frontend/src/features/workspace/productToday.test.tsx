// UX3 (Persona Blueprint wave C): the Product Quality Engineer's Today is the Product Lifecycle Twin on the rising
// version, and the investigation cockpit's Product reality step compares it with the version before, in one click.
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ProductToday, risingVersion } from "./sections/ProductToday";
import { VersionCompareCard, compareTab, earlierVersion } from "./sections/VersionCompare";
import { ROLE_LABELS, WORKFLOW_ROLE_CODES } from "../../app/roles";
import { ASSIGNABLE_ROLES } from "../customer-admin/context";
import type { TrendItem } from "./signalAi";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
}));

beforeEach(() => {
  resources.data = {};
});

const open = vi.fn();
const render = (node: React.ReactNode) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider
      value={
        {
          session: { display_name: "Priya Product" },
          open,
          dataSource: "sample",
          persona: "pqe",
          isTrial: true,
        } as unknown as WorkspaceApi
      }
    >
      {node}
    </WorkspaceContext.Provider>,
  );

const row = (version: string, ratio: number, result = "SIGNIFICANT") =>
  ({
    key: version,
    product: { id: "p1", business_id: "PRD1", identifier: "SAMPLE-ORBIT-300", name: "OrbitCare 300" },
    product_version: { id: version, business_id: null, version_identifier: version },
    result,
    ratio,
    recent: 9,
    expected: 1,
    recent_days: 30,
    lots: ["SAMPLE-ORBIT-300-LOT-005", "SAMPLE-ORBIT-300-LOT-003", "SAMPLE-ORBIT-300-LOT-004"],
    changes: [
      {
        id: "c1",
        identifier: "SAMPLE-CHG-014",
        change_type: "SUPPLIER",
        title: "Sensor supplier changed to NovaSense",
        event_at: null,
      },
    ],
  }) as unknown as TrendItem;

const PRODUCT = {
  product: { name: "OrbitCare 300" },
  selected_version: { version_identifier: "Rev B" },
  versions: [{ version_identifier: "Rev A" }, { version_identifier: "Rev B" }],
  overview: { lot_count: 8, complaint_count: 18 },
  changes: [{ id: "c1", change_identifier: "SAMPLE-CHG-014", description: "Sensor supplier changed to NovaSense" }],
};

describe("the Product Quality Engineer's Today", () => {
  it("opens on the version rising most, never a steady one", () => {
    expect(risingVersion([row("Rev A", 1.1, "STEADY"), row("Rev B", 9.3), row("Rev C", 2.5, "ELEVATED")])?.key).toBe(
      "Rev B",
    );
    expect(risingVersion([row("Rev A", 1.1, "STEADY")])).toBeNull();
  });

  it("states what changed, which lots and how many complaints against expected, and compares the versions in one click", () => {
    resources.data["/api/v1/triage/trends"] = { items: [row("Rev B", 9.3)] };
    resources.data["/api/v1/products/SAMPLE-ORBIT-300/product-360"] = PRODUCT;
    const html = render(<ProductToday heading={{ current: null }} />);
    expect(html).toContain("OrbitCare 300 · Rev B");
    expect(html).toContain("What changed: Sensor supplier changed to NovaSense");
    expect(html).toContain("Lots with recent complaints: 003–005");
    expect(html).toContain("Complaints: 9 against 1 expected (9.3×)");
    // Each row says what it counts.
    expect(html).toContain("the newest change recorded against a part of Rev B");
    // The one main button: compare Rev A and Rev B.
    expect(html.split('class="ac-primary"').length - 1).toBe(1);
    expect(html).toMatch(/class="ac-primary"[^>]*>.*Compare Rev A and Rev B/);
    expect(compareTab("SAMPLE-ORBIT-300", "Rev B", "Rev A")).toBe(
      "Product 360?product=SAMPLE-ORBIT-300&version=Rev+B&view=Configuration&compare=Rev+A",
    );
  });

  it("says plainly when nothing is rising", () => {
    resources.data["/api/v1/triage/trends"] = { items: [row("Rev A", 1, "STEADY")] };
    expect(render(<ProductToday heading={{ current: null }} />)).toContain(
      "No version is rising against what was expected",
    );
  });

  it("the cockpit's comparison is secondary there, and needs a version before it", () => {
    resources.data["/api/v1/products/SAMPLE-ORBIT-300/product-360"] = PRODUCT;
    const html = render(<VersionCompareCard product="SAMPLE-ORBIT-300" version="Rev B" />);
    expect(html).toMatch(/class="ac-secondary"[^>]*>.*Compare Rev A and Rev B/);
    expect(html).not.toContain("ac-primary");
    expect(earlierVersion(PRODUCT.versions, "Rev A")).toBeNull();
    expect(render(<VersionCompareCard product={null} version={null} />)).toContain("names no product");
  });
});

describe("one role list, with the Product Quality Engineer", () => {
  it("names the role the same everywhere, and a customer administrator may give it", () => {
    expect(ROLE_LABELS.PRODUCT_QUALITY_ENGINEER).toBe("Product Quality Engineer");
    expect(WORKFLOW_ROLE_CODES).toContain("PRODUCT_QUALITY_ENGINEER");
    expect(ASSIGNABLE_ROLES).toContainEqual({ value: "PRODUCT_QUALITY_ENGINEER", label: "Product Quality Engineer" });
  });
});
