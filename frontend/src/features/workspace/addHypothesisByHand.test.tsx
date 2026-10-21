import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { HypothesesView } from "./sections/caseIntelligence/Hypotheses";
import { aiStatusBanner } from "./intelligence";

// 0.10.41 (DEV-019): "Add hypotheses by hand", offered while AI is off, opens the case's Hypotheses with the form to
// add one already open, instead of the view alone.

vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: () => ({ state: "ready", data: { items: [] }, reload: () => undefined }),
}));

const workspace = (permissions: string[]) =>
  ({
    session: { business_permissions: permissions },
    open: vi.fn(),
    notify: vi.fn(),
    work: {},
  }) as unknown as WorkspaceApi;
const render = (node: ReactNode, permissions = ["investigation.work", "evidence.review"]) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={workspace(permissions)}>{node}</WorkspaceContext.Provider>);
const DRAWER = 'aria-label="Add a hypothesis"';

describe("Add hypotheses by hand", () => {
  it("is the AI-off way to add hypotheses, and asks for the form", () => {
    const banner = aiStatusBanner({ enabled: false, trial: true });
    expect(banner?.manual.find((path) => path.view === "Hypotheses")).toEqual({
      view: "Hypotheses",
      label: "Add hypotheses by hand",
      add: true,
    });
    // The other ways by hand open their view, as before.
    expect(banner?.manual.filter((path) => path.add)).toHaveLength(1);
  });

  it("opens the Hypotheses view with the form to add one", () => {
    const opened = render(
      <HypothesesView investigationId="case-1" caseLabel="INV000002" readOnly={false} startAdding />,
    );
    expect(opened).toContain(DRAWER);
    expect(opened).toContain("Hypotheses");
    // Opened another way, the view shows without the form.
    expect(render(<HypothesesView investigationId="case-1" caseLabel="INV000002" readOnly={false} />)).not.toContain(
      DRAWER,
    );
  });

  it("never opens the form where nothing can be added", () => {
    expect(
      render(<HypothesesView investigationId="case-1" caseLabel="INV000002" readOnly startAdding />),
    ).not.toContain(DRAWER);
    expect(
      render(<HypothesesView investigationId="case-1" caseLabel="INV000002" readOnly={false} startAdding />, []),
    ).not.toContain(DRAWER);
  });
});
