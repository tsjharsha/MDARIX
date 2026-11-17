import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { Triage } from "./sections/Triage";
import type { TriageItem, TriageList } from "./intake";

// 0.10.79 (owner-reported on mdarix.com): a complaint's page opens its triage panel by the complaint
// (To triage?complaint=<id>); pressing × cleared only `item`, so `complaint=` reopened the panel at once. Closing now
// clears item, complaint and ref in one address change.

const drawers = vi.hoisted(() => ({ closes: [] as Array<() => void> }));
const ITEM = {
  key: "COMPLAINT:c1",
  kind: "COMPLAINT",
  id: "c1",
  ref: "SAMPLE-RV-11",
  identifier: "SAMPLE-RV-11",
  source: "complaints",
  intake_kind: null,
  product_name: "PulseWatch 410",
  lot: null,
  words: "SpO2 read high",
  problems: null,
  classification: null,
  suggestion: null,
  sample: true,
  flags: [],
  tier: "FLAGGED",
  tier_label: "Flagged",
  linked: [],
  awareness: {
    at: "2026-11-01T10:00:00Z",
    source: "x",
    source_label: "x",
    linked_ref: null,
    unresolved: false,
    label: null,
  },
  available_at: "2026-11-01T10:00:00Z",
  delay: { hours: 0, text: "" },
  triage_clock: {
    from: "2026-11-01T10:00:00Z",
    target_hours: 24,
    due_at: "2026-11-02T10:00:00Z",
    hours_left: 2,
    state: "OPEN",
  },
  deadlines: [],
  conflict: [],
  record: null,
} as unknown as TriageItem;
const LIST = {
  items: [ITEM],
  summary: { open: 1, done: 0, conflicts: 0 },
  people: [],
  enabled_markets: [],
} as unknown as TriageList;

vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: path?.startsWith("/api/v1/triage?") ? LIST : null,
    reload: () => undefined,
  }),
  // The drawer itself is not under test: it records its close button's handler.
  Drawer: ({ onClose }: { onClose: () => void }) => {
    drawers.closes.push(onClose);
    return <div data-drawer="open" />;
  },
}));

const render = (shownTab: string, reportTab: (tab: string, how?: string) => void) =>
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
          reportTab,
        } as unknown as WorkspaceApi
      }
    >
      <Triage />
    </WorkspaceContext.Provider>,
  );

describe("the triage panel's × closes it", () => {
  for (const shown of [
    "To triage?complaint=c1",
    "To triage?complaint=c1&item=COMPLAINT%3Ac1",
    "To triage?ref=SAMPLE-RV-11",
  ]) {
    it(`closes a panel opened by ${shown}`, () => {
      const reported: Array<[string, string | undefined]> = [];
      drawers.closes = [];
      expect(render(shown, (tab, how) => reported.push([tab, how]))).toContain('data-drawer="open"');
      drawers.closes[0]();
      expect(reported).toEqual([["To triage", "push"]]);
      // The address after closing opens no panel.
      drawers.closes = [];
      expect(render(reported[0][0], () => undefined)).not.toContain('data-drawer="open"');
    });
  }
});

describe("a complaint logged as it was heard (hero review 2, F-C4)", () => {
  it("says it was logged at once, not that it reached MDARIX 0 hours later", () => {
    const html = render("To triage", () => undefined);
    expect(html).toContain("logged at once");
    expect(html).not.toContain("later");
  });
});
