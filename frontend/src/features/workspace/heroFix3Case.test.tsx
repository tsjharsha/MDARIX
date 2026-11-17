import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { CaseSections } from "./sections/CaseSections";

// Hero review 2, fix pass 3: the investigation's Evidence step (F-A3, F-R1). The step's own panels are stand-ins here:
// what is under test is their order and what is folded.

vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: () => ({ state: "ready", data: null, reload: () => undefined }),
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
