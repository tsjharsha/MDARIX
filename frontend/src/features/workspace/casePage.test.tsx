import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { InvestigationsSection } from "./sections/Investigations";

/** The workspace an Investigations section needs, with no case chosen; nothing here loads data (no effects run). */
function workspace(featureSet: string): WorkspaceApi {
  return {
    session: { feature_set: featureSet, business_permissions: ["records.write", "data.export"] },
    open: vi.fn(),
    notify: vi.fn(),
    work: {
      products: [],
      productId: "",
      setProductId: vi.fn(),
      version: "",
      setVersion: vi.fn(),
      asOf: "",
      setAsOf: vi.fn(),
      mode: "current",
      setMode: vi.fn(),
      investigations: [],
      investigationId: "",
      setInvestigationId: vi.fn(),
      refreshInvestigations: vi.fn(),
      refreshProducts: vi.fn(),
      openInvestigationRequest: null,
      requestOpenInvestigation: vi.fn(),
      clearOpenInvestigationRequest: vi.fn(),
      view: null,
      state: "ready",
      error: "",
    },
  } as unknown as WorkspaceApi;
}

function render(featureSet: string, tab?: string): string {
  return renderToStaticMarkup(
    <WorkspaceContext.Provider value={workspace(featureSet)}>
      <InvestigationsSection tab={tab} />
    </WorkspaceContext.Provider>,
  );
}

const tabNames = (markup: string) => [...markup.matchAll(/role="tab"[^>]*>([^<]+)</g)].map((match) => match[1]);

describe("the one case page", () => {
  it("holds every step of a case under mvp, without the parked story", () => {
    expect(tabNames(render("mvp"))).toEqual([
      "All investigations",
      "Workspace",
      "Evidence",
      "Intelligence",
      "Ask MDARIX",
      "Scope",
      "Reviews",
      "Decision Brief",
      "Decision",
      "Record",
      "CAPAs",
    ]);
  });

  it("keeps today's tabs under full", () => {
    expect(tabNames(render("full"))).toEqual([
      "All investigations",
      "Workspace",
      "Intelligence",
      "Scope",
      "Reviews",
      "Decision Brief",
      "Decision",
      "Story",
      "CAPAs",
    ]);
  });

  it("opens the evidence and record steps, asking for a case when none is chosen", () => {
    expect(render("mvp", "Evidence")).toContain("Case evidence belongs to one investigation");
    expect(render("mvp", "Record")).toContain("The record belongs to one investigation");
    // A parked or unknown step opens the case list instead.
    expect(render("mvp", "Story")).toContain("Investigations in your organization");
    expect(render("full", "Record")).toContain("Investigations in your organization");
  });
});
