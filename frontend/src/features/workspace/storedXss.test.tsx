// Hardening 0.10.95 (H1): text people typed or imported is shown as text. A complaint's words, an imported record's
// fields and an evidence record's name come back from the server exactly as stored; every screen that shows them
// must escape them, never turn them into markup.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ComplaintPage } from "./sections/ComplaintPage";
import { ImportedBacklog, Triage } from "./sections/Triage";
import { CaseEvidencePanel } from "./sections/CaseEvidence";
import { eventPath } from "./oversight";
import { inventoryPath } from "./evidenceWorkflow";
import { rv11 } from "../../test/rv11";

const HOSTILE = `<img src=x onerror="alert(1)"><script>alert(2)</script><a href="javascript:alert(3)">x</a>`;

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
  Drawer: ({ children }: { children: ReactNode }) => <div data-drawer="open">{children}</div>,
}));

const render = (node: ReactNode, shownTab = "") =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider
      value={
        {
          session: {
            user_id: "u1",
            allowed_menu: ["home"],
            business_permissions: ["records.write", "complaint.triage"],
          },
          work: { products: [], investigations: [] },
          open: vi.fn(),
          notify: vi.fn(),
          navigation: "new",
          isTrial: true,
          persona: "admin",
          shownTab,
          reportTab: vi.fn(),
        } as unknown as WorkspaceApi
      }
    >
      {node}
    </WorkspaceContext.Provider>,
  );

/** The hostile text is on the page, escaped, and none of it became an element or a link. */
function expectEscaped(html: string) {
  expect(html).toContain("&lt;img src=x onerror=");
  expect(html).toContain("&lt;script&gt;alert(2)&lt;/script&gt;");
  expect(html).not.toMatch(/<img\b|<script\b|href="javascript:/i);
}

describe("stored text is shown escaped (H1 stored-XSS)", () => {
  it("a complaint's words and product on the complaint page", () => {
    const view = rv11();
    view.event = { ...view.event, description: HOSTILE, product: HOSTILE };
    resources.data = { [eventPath("SAMPLE-RV-11")]: view };
    expectEscaped(render(<ComplaintPage tab="Summary?ref=SAMPLE-RV-11" />));
  });

  it("an imported complaint's fields in triage and the imported backlog", () => {
    const item = {
      key: "COMPLAINT:c1",
      kind: "COMPLAINT",
      id: "c1",
      ref: "QT-2",
      identifier: "QT-2",
      source: "Imported complaint",
      product_name: HOSTILE,
      words: HOSTILE,
      flags: [],
      tier: "FLAGGED",
      tier_label: "Flagged",
      linked: [],
      lot: null,
      awareness: { at: "2026-11-01T10:00:00Z", source: "x", source_label: "x", linked_ref: null, unresolved: false },
      available_at: "2026-11-01T10:00:00Z",
      delay: { hours: 0, text: "" },
      triage_clock: { from: "2026-11-01T10:00:00Z", target_hours: 4, due_at: "2026-11-01T14:00:00Z", hours_left: 2 },
      deadlines: [],
      conflict: [],
      speed: "FAST",
      speed_label: "Fast-track triage",
      routine_prefill: null,
      qms_to_confirm: true,
      record: {
        severity: "MINOR",
        source_system: "QMS",
        qms_triaged_at: "2026-11-02T00:00:00Z",
        qms_owner_text: HOSTILE,
        immediate_action: HOSTILE,
        completed_at: null,
        version: 1,
      },
    };
    resources.data = {
      "/api/v1/triage": { items: [item], summary: { open: 1, done: 0, conflicts: 0 }, people: [] },
      "/api/v1/triage/backlog": {
        summary: { total: 1, flagged: 0, overdue: 0, backlog_days: 30, target_days: 10 },
        page: 1,
        pages: 1,
        truncated: false,
        items: [
          {
            kind: "COMPLAINT",
            id: "c2",
            ref: "OB-01",
            identifier: "OB-01",
            product_name: HOSTILE,
            words: HOSTILE,
            note: HOSTILE,
          },
        ],
      },
    };
    expectEscaped(render(<Triage />, "To triage?item=COMPLAINT%3Ac1"));
    expectEscaped(render(<ImportedBacklog />));
  });

  it("an evidence record's name and source in the case's evidence", () => {
    resources.data = {
      [inventoryPath("i1")]: {
        items: [
          {
            evidence: { id: "e1", evidence_identifier: "EV-1", title: HOSTILE, source_reference: HOSTILE },
            origin: "DIRECT",
          },
        ],
        counts: { total: 1 },
        actions: {},
      },
    };
    expectEscaped(render(<CaseEvidencePanel investigationId="i1" caseLabel="INV-1" />));
  });

  it("no screen writes raw HTML, except the reviewed, escaped structured data of the public questions page", () => {
    const sources = import.meta.glob<string>(["/src/**/*.{ts,tsx}", "!/src/**/*.test.{ts,tsx}"], {
      query: "?raw",
      import: "default",
      eager: true,
    });
    const sinks = Object.entries(sources)
      .filter(([, source]) => /dangerouslySetInnerHTML|\.innerHTML\s*=|\.outerHTML\s*=|insertAdjacentHTML/.test(source))
      .map(([file]) => file);
    expect(sinks).toEqual(["/src/site/questions.tsx"]);
  });
});
