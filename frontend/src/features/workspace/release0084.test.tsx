// 0.10.84: the independent rating's defects on the combined D1 + D2 build, each with the test that fails before.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { legalClocks } from "./home";
import type { OversightItem } from "./oversight";
import { OVERSIGHT } from "./oversight";
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
    session: { user_id: "u1", business_permissions: ["records.write"] },
    work: { products: [], investigations: [] },
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
    persona: "admin",
    ...overrides,
  }) as unknown as WorkspaceApi;

const render = (node: ReactNode, value: WorkspaceApi = api()) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

const item = (overrides: Partial<OversightItem>): OversightItem =>
  ({
    key: "obligation:1",
    category: "OBLIGATION",
    category_label: "Authority report",
    title: "FDA 3500A: draft",
    ref: "SAMPLE-RV-11",
    complaint_id: "c-rv11",
    market: "US",
    product: null,
    owner: null,
    queue: null,
    away: null,
    due_at: "2026-12-02T18:29:59Z",
    due_label: "Wed 2 Dec 2026, 23:59 IST",
    state: "RUNNING",
    state_label: "Running",
    hours_left: 700,
    escalated_to: [],
    alerts: true,
    opens: null,
    ...overrides,
  }) as OversightItem;

// An approval task names the category OBLIGATION and gets the complaint's market (oversight/service.py), but its due
// date is the approver's target, not the legal deadline.
const approval = item({
  key: "task:t1",
  title: "Approve the US report for SAMPLE-RV-11",
  due_at: "2026-11-04T18:29:59Z",
  due_label: "Wed 4 Nov 2026, 23:59 IST",
  hours_left: 30,
});

describe("H1: Home's legal clocks are the legal deadlines only", () => {
  it("leaves an approval task out of the legal clocks", () => {
    expect(legalClocks([approval, item({})]).map((row) => row.key)).toEqual(["obligation:1"]);
  });

  it("shows the report's own deadline on the Regulatory Leader's Home, never the approval's due date", () => {
    resources.data[OVERSIGHT] = { items: [approval, item({})] };
    const html = render(<HomeSection heading={{ current: null }} />, api({ persona: "regulatory" }));
    const clocks = html.slice(html.indexOf('id="home-clocks"'));
    expect(clocks).toContain("Due Wed 2 Dec 2026, 23:59 IST");
    expect(clocks).not.toContain("Wed 4 Nov");
  });
});
