import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { AiProposalsCard, CaseSections } from "./sections/CaseSections";

// Hero review 2, fix pass 3: the investigation's Evidence step (F-A3, F-R1). The step's own panels are stand-ins here:
// what is under test is their order and what is folded.

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
}));
vi.mock("./sections/CaseHeader", () => ({ CaseHeader: () => <header />, ownerText: () => "" }));
vi.mock("./sections/CaseEvidence", () => ({ CaseEvidencePanel: () => <div data-part="evidence-table" /> }));
vi.mock("./sections/CaseIntelligence", () => ({ CaseIntelligencePanel: () => <div data-part="method-tabs" /> }));
vi.mock("../investigator/InvestigationWorkspacePanel", () => ({
  InvestigationWorkspacePanel: () => <div data-part="workspace" />,
}));
vi.mock("../ask/AskMdarixPage", () => ({ AskMdarixPage: () => <div data-part="ask" /> }));

const render = (tab: string) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider
      value={
        {
          session: { allowed_menu: ["home"], business_permissions: [] },
          work: { investigationId: "i1", investigations: [{ id: "i1" }], products: [] },
          open: vi.fn(),
          notify: vi.fn(),
          navigation: "new",
          isTrial: true,
        } as unknown as WorkspaceApi
      }
    >
      <CaseSections tab={tab} onChanged={() => undefined} />
    </WorkspaceContext.Provider>,
  );

describe("the Evidence step (F-A3, F-R1)", () => {
  it("puts the method tabs first and folds the evidence table under them", () => {
    const html = render("Evidence");
    expect(html.indexOf('data-part="method-tabs"')).toBeLessThan(html.indexOf('data-part="evidence-table"'));
    expect(html).toMatch(/<details class="uw-more uw-case-part" id="case-part-evidence">/);
  });

  it("leads with Ask when Ask was asked for, once", () => {
    const html = render("Evidence?part=ask");
    expect(html.indexOf('data-part="ask"')).toBeLessThan(html.indexOf('data-part="method-tabs"'));
    expect(html.split('data-part="ask"').length - 1).toBe(1);
  });
});

describe("F-A2: the AI proposals lead the Evidence step", () => {
  it("counts the unreviewed AI observations and hypotheses, each opening its view", () => {
    const base = "/api/v1/investigations/i1/intelligence";
    expect(renderToStaticMarkup(<AiProposalsCard investigationId="i1" onOpen={() => undefined} />)).toBe("");
    resources.data[`${base}/observations`] = {
      items: [
        { id: "o1", origin: "AI", ai_label: "AI proposal, not reviewed" },
        { id: "o2", origin: "AI", ai_label: "AI proposal, not reviewed" },
        { id: "o3", origin: "HUMAN" },
      ],
    };
    resources.data[`${base}/hypotheses`] = {
      items: [
        { id: "h1", origin: "ai", human_status: null },
        { id: "h2", origin: "human" },
      ],
    };
    const html = renderToStaticMarkup(<AiProposalsCard investigationId="i1" onOpen={() => undefined} />);
    expect(html).toContain("AI proposals · 3 waiting for your review");
    expect(html).toContain("Review 2 observations");
    expect(html).toContain("Review 1 hypothesis");
    expect(render("Evidence").indexOf("AI proposals ·")).toBeLessThan(render("Evidence").indexOf("method-tabs"));
  });
});
