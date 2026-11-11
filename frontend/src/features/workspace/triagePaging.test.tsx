import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { TRIAGE_PAGE, Triage } from "./sections/Triage";
import type { TriageItem, TriageList } from "./intake";

// B6a run 3: no deadline is hidden by a read cap. Every open item is counted; one page shows TRIAGE_PAGE of them and
// says how many more there are; an item past the first page still opens by its address. B6a run 4: the server sends
// the page and the counts (``limit``), and the item past the page by its address (``want``).

const item = (index: number) =>
  ({
    key: `COMPLAINT:c${index}`,
    kind: "COMPLAINT",
    id: `c${index}`,
    ref: `LOAD-${String(index).padStart(5, "0")}`,
    identifier: null,
    source: "Imported complaint",
    words: "",
    flags: [],
    tier: "FLAGGED",
    tier_label: "Flagged",
    linked: [],
    awareness: { at: "2026-11-01T10:00:00Z", source: "x", source_label: "x", linked_ref: null, unresolved: false },
    delay: { hours: 0, text: "" },
    triage_clock: { from: "", target_hours: 24, due_at: "2026-11-02T10:00:00Z", hours_left: 2, state: "OPEN" },
    deadlines: [],
    conflict: [],
    record: null,
  }) as unknown as TriageItem;

const LIST = {
  items: Array.from({ length: TRIAGE_PAGE }, (_, index) => item(index)),
  total: TRIAGE_PAGE + 50,
  overdue: 3,
  summary: { open: TRIAGE_PAGE + 50, done: 0, conflicts: 0 },
  people: [],
  enabled_markets: [],
} as unknown as TriageList;
const asked: string[] = [];

vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    if (path) asked.push(path);
    const away = path?.includes("&want=COMPLAINT%3Ac140");
    return {
      state: "ready",
      data: away ? { ...LIST, items: [], wanted: item(140) } : path?.startsWith("/api/v1/triage?") ? LIST : null,
      reload: () => undefined,
    };
  },
  Drawer: () => <div data-drawer="open" />,
}));

const render = (shownTab: string) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider
      value={
        {
          session: { user_id: "u1", allowed_menu: ["home"], business_permissions: ["signal.triage"] },
          work: { products: [], investigations: [] },
          open: vi.fn(),
          notify: vi.fn(),
          navigation: "new",
          shownTab,
          reportTab: vi.fn(),
        } as unknown as WorkspaceApi
      }
    >
      <Triage />
    </WorkspaceContext.Provider>,
  );

describe("the triage list pages, never hides", () => {
  it("shows one page, counts the rest and offers the next", () => {
    const html = render("To triage");
    expect(html.match(/class="uw-cr-card"/g)).toHaveLength(TRIAGE_PAGE);
    expect(html).toContain("LOAD-00099");
    expect(html).not.toContain("LOAD-00100");
    expect(html).toContain("50 more events on this list.");
    expect(html).toContain("Show the next 50");
    expect(html).toContain("150 events to triage");
    expect(html).toMatch(/ac-stat-value">3</); // past the triage target, counted by the server over every item
    expect(asked).toContain("/api/v1/triage?show=open&limit=100");
  });

  it("opens an item past the first page by its address", () => {
    expect(render("To triage?item=COMPLAINT%3Ac140")).toContain('data-drawer="open"');
  });
});
