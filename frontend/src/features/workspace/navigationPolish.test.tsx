import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { FollowUpDrawer } from "./sections/AfterDecision";
import type { FollowUp } from "./afterDecision";
import { routeFor } from "../../app/linkTable";
import recordsSource from "./sections/Records.tsx?raw";

// B6a navigation polish (D4 backlog items 14, 15, 2 and the audit trail review on the new navigation).
const inWorkspace = (node: ReactNode, menu: string[] = ["home", "products"]) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider
      value={
        {
          session: { allowed_menu: menu, business_permissions: [] },
          open: vi.fn(),
          notify: vi.fn(),
          work: {},
        } as unknown as WorkspaceApi
      }
    >
      {node}
    </WorkspaceContext.Provider>,
  );

const FOLLOW_UP = {
  id: "f1",
  business_id: "FUP000001",
  action_type: "CAPA",
  status: "OPEN",
  capa: { id: "capa-1", business_id: "CAPA000001", capa_identifier: null, qms_reference: null },
} as unknown as FollowUp;

describe("a CAPA follow-up opens its effectiveness check (D4 #14)", () => {
  it("offers the link when the server sends the CAPA's id and Records is on the person's menu", () => {
    const html = inWorkspace(<FollowUpDrawer followUp={FOLLOW_UP} onClose={vi.fn()} onDone={vi.fn()} />);
    expect(html).toContain("CAPA000001");
    expect(html).toContain("Open its effectiveness check");
  });

  it("offers none without a CAPA id, or to a person whose menu has no Records", () => {
    const noId = { ...FOLLOW_UP, capa: { ...FOLLOW_UP.capa, id: null } } as FollowUp;
    expect(inWorkspace(<FollowUpDrawer followUp={noId} onClose={vi.fn()} onDone={vi.fn()} />)).not.toContain(
      "Open its effectiveness check",
    );
    expect(
      inWorkspace(<FollowUpDrawer followUp={FOLLOW_UP} onClose={vi.fn()} onDone={vi.fn()} />, ["products"]),
    ).not.toContain("Open its effectiveness check");
  });
});

describe('"Not effective" opens the investigation\'s decision (D4 #15)', () => {
  it("opens Decisions & actions on the new navigation and the Decision step on the classic one", () => {
    expect(recordsSource).toContain('open("Investigations", "Decision")');
    expect(recordsSource).not.toContain('open("Investigations", "Workspace")');
    expect(routeFor("Investigations", "Decision", "mvp", "new")).toEqual({
      section: "Investigations",
      tab: "Decisions & actions?part=decision",
    });
    expect(routeFor("Investigations", "Decision", "mvp", "classic")).toEqual({
      section: "Investigations",
      tab: "Decision",
    });
  });
});
