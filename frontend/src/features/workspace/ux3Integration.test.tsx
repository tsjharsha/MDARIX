// UX3 (integration of UX1 and UX2): Today's Approvals card and Decisions & Reports › Approvals read the same queue and
// show the same waiting items, by the reference people read; each persona's Today counts its own work.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ApprovalsSection } from "./sections/DecisionsArea";
import { ApprovalsCard } from "./sections/HomeWork";
import { HomeSection } from "./sections/Home";
import { PERSONA_TILES } from "./home";

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

describe("each persona's Today counts its own work (UX3, the blueprint's Today sketches)", () => {
  const today = (persona: string) =>
    renderToStaticMarkup(
      <WorkspaceContext.Provider value={{ ...api(), persona } as unknown as WorkspaceApi}>
        <HomeSection heading={{ current: null }} />
      </WorkspaceContext.Provider>,
    );
  it("Service Desk: calls missing facts, possible duplicates, handed over; Log a call", () => {
    // Each count is its own view's total (one row a page).
    resources.data["/api/v1/intake/cases"] = { total: 3, items: [{}] };
    resources.data["/api/v1/intake/duplicates"] = { items: [{}, {}] };
    const html = today("servicedesk");
    for (const [count, title] of [
      ["3", "Calls missing facts"],
      ["2", "Possible duplicates"],
      ["3", "Handed over"],
    ])
      expect(html).toMatch(new RegExp(`<b class="uw-home-num">${count}</b><strong>${title}</strong>`));
    expect(html).toContain("Cases that became complaints in the last 30 days");
    // Each is read from its own view of the Cases list (never a per-status count the server does not send).
    expect(PERSONA_TILES.servicedesk.map((tile) => tile.path)).toEqual([
      "/api/v1/intake/cases?view=needs_information&q=&page=1&size=1",
      "/api/v1/intake/duplicates",
      "/api/v1/intake/cases?view=became_complaints&q=&page=1&size=1",
    ]);
    expect(html).toContain("Log a call");
    expect(html).not.toContain("<strong>At risk</strong>");
  });
  it("Complaint Handler: to triage, waiting for contact, reportability due", () => {
    resources.data["/api/v1/triage"] = { summary: { open: 5 } };
    resources.data["/api/v1/complaints"] = { total: 2 };
    const html = today("handler");
    expect(html).toMatch(/<b class="uw-home-num">5<\/b><strong>To triage<\/strong>/);
    expect(html).toContain("<strong>Waiting for contact</strong>");
    expect(html).toContain("<strong>Reportability due</strong>");
  });
  it("Regulatory, Decision Maker and Risk Reviewer get their own counts; the Quality Leader keeps the shared three", () => {
    expect(today("regulatory")).toContain("<strong>Legal clocks this week</strong>");
    expect(today("decision")).toContain("<strong>Waiting for your signature</strong>");
    expect(today("risk")).toContain("<strong>Risk reviews requested</strong>");
    const quality = today("quality");
    for (const title of ["Overdue", "Due this week", "At risk"]) expect(quality).toContain(`<strong>${title}</strong>`);
  });
  it("every persona's own count says what it counts and opens a list the persona may open", () => {
    for (const [persona, tiles] of Object.entries(PERSONA_TILES))
      for (const tile of tiles) {
        expect(tile.detail.length, `${persona} ${tile.key}`).toBeGreaterThan(20);
        expect(tile.opens.section).toBeTruthy();
      }
  });
});
