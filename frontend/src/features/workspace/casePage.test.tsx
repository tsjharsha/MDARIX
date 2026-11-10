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

  it("opens the form with every complaint of a Supplier 360 pattern ticked (owner, 10 Nov 2026)", () => {
    const api = workspace("mvp");
    const complaint = (id: string, ref: string) => ({
      id,
      business_id: null,
      complaint_identifier: ref,
      description: `${ref} reads high`,
    });
    Object.assign(api.work, {
      products: [{ id: "p1", name: "OrbitCare 300" }],
      productId: "p1",
      view: { complaints: [] },
      openInvestigationRequest: {
        productId: "p1",
        version: "Rev B",
        complaint: complaint("c1", "RV-01"),
        also: [complaint("c2", "RV-02")],
        openedFrom: "Opened from Supplier 360: pattern P-1 v1",
      },
    });
    const html = renderToStaticMarkup(
      <WorkspaceContext.Provider value={api}>
        <InvestigationsSection />
      </WorkspaceContext.Provider>,
    );
    expect(html).toContain("Open an investigation for OrbitCare 300");
    expect(html).toContain("2 selected");
    expect(html.match(/type="checkbox" checked=""/g)?.length).toBe(2);
    expect(html).toContain("RV-02 reads high");
  });
});
