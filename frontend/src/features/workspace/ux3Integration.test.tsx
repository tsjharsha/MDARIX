// UX3 (integration of UX1 and UX2): Today's Approvals card and Decisions & Reports › Approvals read the same queue and
// show the same waiting items, by the reference people read.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ApprovalsSection } from "./sections/DecisionsArea";
import { ApprovalsCard } from "./sections/HomeWork";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown>, asked: [] as string[] }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    if (path) resources.asked.push(path);
    const value = (path && resources.data[path.split("?")[0]]) ?? null;
    return { state: "ready", data: value, reload: () => undefined };
  },
}));

beforeEach(() => {
  resources.data = {};
  resources.asked = [];
});

const api = () =>
  ({
    session: { user_id: "u1", business_permissions: ["decision.sign"] },
    work: { products: [], investigations: [], setInvestigationId: vi.fn() },
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
    persona: "decision",
  }) as unknown as WorkspaceApi;

const render = (node: ReactNode) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={api()}>{node}</WorkspaceContext.Provider>);

const QUEUE = {
  total: 1,
  items: [
    {
      investigation: {
        id: "inv1",
        business_id: "INV000001",
        identifier: "SAMPLE-INV-001",
        question: "Why did pressure alarms rise after Rev B?",
        product: { id: "p1", name: "OrbitCare 300" },
      },
      brief: { business_id: "BRF000001", version: 1, quality_reviewer_name: "MDARIX sample reviewer" },
      awaiting_since: "2026-11-17T09:00:00Z",
    },
  ],
};

describe("Approvals: Today and Decisions & Reports show the same waiting items", () => {
  it("fills the Approvals screen with Today's one-page summary and the full queue, both by SAMPLE-INV-001", () => {
    resources.data["/api/v1/decisions/queue"] = QUEUE;
    const screen = render(<ApprovalsSection />);
    const today = render(<ApprovalsCard />);
    // Today's card and the screen's card are the same summary of the same first brief.
    expect(today).toContain("SAMPLE-INV-001 · brief v1");
    expect(screen).toContain("SAMPLE-INV-001 · brief v1");
    // The queue table names the item by the same reference, not the system ID.
    expect(screen).toContain("Open the decision of SAMPLE-INV-001");
    expect(screen).not.toContain("Open the decision of INV000001");
    // Both read the one queue.
    const queueReads = resources.asked.filter((path) => path.startsWith("/api/v1/decisions/queue"));
    expect(queueReads.length).toBeGreaterThanOrEqual(3);
  });
});
