import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ImportedBacklog, Triage } from "./sections/Triage";
import type { ImportedBacklogList, TriageItem, TriageList } from "./intake";

// 0.10.93 (B2): a triage imported from the QMS on a flagged complaint waits for a person (T-D9: TR-14, TR-38), and old
// imported complaints with no flag wait in the "Imported backlog" view (OD-12, TR-21).

const ITEM = {
  key: "COMPLAINT:c1",
  kind: "COMPLAINT",
  id: "c1",
  ref: "QT-2",
  identifier: "QT-2",
  source: "Imported complaint",
  product_name: "QT Pump",
  lot: null,
  words: "Patient died after the infusion stopped",
  flags: [{ code: "DEATH", label: "Death recorded" }],
  tier: "FLAGGED",
  tier_label: "Flagged",
  linked: [],
  awareness: { at: "2026-11-01T10:00:00Z", source: "x", source_label: "x", linked_ref: null, unresolved: false },
  available_at: "2026-11-01T10:00:00Z",
  delay: { hours: 0, text: "" },
  triage_clock: { from: "2026-11-01T10:00:00Z", target_hours: 4, due_at: "2026-11-01T14:00:00Z", hours_left: 2 },
  deadlines: [],
  conflict: [],
  speed: "FAST",
  speed_label: "Fast-track triage",
  qms_to_confirm: true,
  routine_prefill: null,
  record: {
    severity: "MINOR",
    source_system: "QMS",
    qms_triaged_at: "2026-11-02T00:00:00Z",
    qms_owner_text: "Complaint unit",
    immediate_action: "Pump taken out of use",
    completed_at: null,
    version: 1,
  },
} as unknown as TriageItem;
// The server leaves Imported backlog items off the To triage list (B6a run 4: the list is paged on the server;
// tests/test_import_triage_b2.py), so the list it sends holds the new item only.
const LIST = {
  items: [ITEM],
  summary: { open: 1, done: 0, conflicts: 0 },
  people: [],
} as unknown as TriageList;
const BACKLOG: ImportedBacklogList = {
  summary: { total: 2, flagged: 1, overdue: 0, backlog_days: 30, target_days: 10 },
  page: 1,
  pages: 1,
  truncated: false,
  items: [
    {
      kind: "COMPLAINT",
      id: "c2",
      ref: "OB-01",
      identifier: "OB-01",
      product_name: "OB Pump",
      words: "Pump stopped during the infusion",
      awareness_at: "2025-11-10T00:00:00Z",
      imported_at: "2026-11-10T00:00:00Z",
      due_at: "2026-11-24T23:59:00Z",
      overdue: false,
      flags: [{ code: "MALFUNCTION", label: "Malfunction alleged" }],
      note: "Imported: check the reportability decision in your QMS",
    },
    // Section Q decision 2: an old flagged import with its QMS triage still to confirm.
    {
      kind: "COMPLAINT",
      id: "c3",
      ref: "QB-OLD",
      identifier: "QB-OLD",
      product_name: "QB Pump",
      words: "Patient died after the pump stopped",
      awareness_at: "2026-07-10T00:00:00Z",
      imported_at: "2026-11-10T00:00:00Z",
      due_at: "2026-11-24T23:59:00Z",
      overdue: false,
      flags: [{ code: "DEATH", label: "Death recorded" }],
      note: "Imported: check the reportability decision in your QMS",
      qms_to_confirm: true,
    },
    {
      kind: "COMPLAINT",
      id: "b1",
      ref: "BL-OLD",
      identifier: "BL-OLD",
      product_name: "BL Pump",
      words: "Label smudged on the box",
      awareness_at: "2025-01-10T00:00:00Z",
      imported_at: "2026-11-10T00:00:00Z",
      due_at: "2026-11-24T23:59:00Z",
      overdue: false,
    },
  ],
};

vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: path?.startsWith("/api/v1/triage/backlog") ? BACKLOG : path?.startsWith("/api/v1/triage?") ? LIST : null,
    reload: () => undefined,
  }),
  Drawer: ({ children }: { children: ReactNode }) => <div data-drawer="open">{children}</div>,
}));

const render = (node: ReactNode) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider
      value={
        {
          session: { user_id: "u1", allowed_menu: ["home"], business_permissions: ["complaint.triage"] },
          work: { products: [], investigations: [] },
          open: vi.fn(),
          notify: vi.fn(),
          navigation: "new",
          shownTab: "To triage?item=COMPLAINT%3Ac1",
          reportTab: vi.fn(),
        } as unknown as WorkspaceApi
      }
    >
      {node}
    </WorkspaceContext.Provider>,
  );

describe("QMS triage and the imported backlog (0.10.93)", () => {
  it("shows a QMS triage to confirm, with the full form and no one-click routine card", () => {
    const html = render(<Triage />);
    expect(html).toContain("From your QMS: confirm");
    expect(html).toContain("Triaged in your QMS");
    expect(html).toContain("by Complaint unit");
    expect(html).toContain("Confirm QMS triage");
    expect(html).not.toContain("Confirm triage<");
  });

  it("lists the imported backlog with its target and one click each", () => {
    const html = render(<ImportedBacklog />);
    expect(html).toContain("BL-OLD");
    expect(html).toContain("Known of more than 30 days before the import");
    expect(html).toContain("Confirm triage");
  });

  it("lists an old flagged import first, flag kept, with the QMS note and the full form, not on To triage", () => {
    const html = render(<ImportedBacklog />);
    expect(html).toContain("2 complaints to triage, 1 flagged first");
    expect(html.indexOf("OB-01")).toBeLessThan(html.indexOf("BL-OLD"));
    expect(html).toContain("Malfunction alleged");
    expect(html).toContain("Imported: check the reportability decision in your QMS");
    expect(html.match(/Open the triage form/g)).toHaveLength(1);
    expect(html.match(/Confirm triage</g)).toHaveLength(1);
    const toTriage = render(<Triage />);
    expect(toTriage).toContain("QT-2");
    expect(toTriage).not.toContain("OB-01");
  });

  it("offers Confirm QMS triage on an old flagged import whose QMS triage waits for a person", () => {
    const html = render(<ImportedBacklog />);
    const card = html.slice(html.indexOf("QB-OLD"), html.indexOf("BL-OLD"));
    expect(card).toContain("From your QMS: confirm");
    expect(card).toContain("Confirm QMS triage");
    expect(card).not.toContain("Open the triage form");
  });
});
