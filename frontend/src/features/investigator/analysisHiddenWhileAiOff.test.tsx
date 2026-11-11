import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "../workspace/workspaceContext";
import { aiStatusBanner } from "../workspace/intelligence";

// RCA-D13: while AI does not answer for the organization, the case workspace shows no analysis part at all (no tab,
// no section, no empty box): without a model it would be keyword rules written for the sample data.
const ai = vi.hoisted(() => ({ ready: null as boolean | null, banner: null as unknown }));
vi.mock("../workspace/useAiStatus", () => ({ useAiReady: () => ai.ready, useAiBanner: () => ai.banner }));

const { InvestigationWorkspacePanel } = await import("./InvestigationWorkspacePanel");

function render(ready: boolean | null, banner: unknown = null): string {
  ai.ready = ready;
  ai.banner = banner;
  const workspace = {
    session: { feature_set: "mvp", business_permissions: ["ai.run", "records.write"] },
    open: vi.fn(),
    notify: vi.fn(),
    work: { investigations: [], investigationId: "c" },
  } as unknown as WorkspaceApi;
  return renderToStaticMarkup(
    <WorkspaceContext.Provider value={workspace}>
      <InvestigationWorkspacePanel
        investigationId="11111111-1111-4111-8111-111111111111"
        temporalMode="current"
        asOf="2026-11-12"
        onOpenDecision={() => undefined}
        onOpenIntelligence={() => undefined}
      />
    </WorkspaceContext.Provider>,
  );
}

const analysisParts = (html: string) => [
  html.includes('id="workflow-analysis"'),
  html.includes(">Analysis</button>"),
  html.includes("Run Analysis"),
];

describe("the R1 analysis while AI is off", () => {
  it("is hidden for a free trial and for an organization with AI off", () => {
    for (const status of [{ enabled: false, trial: true }, { enabled: false }]) {
      const html = render(false, aiStatusBanner(status));
      expect(analysisParts(html)).toEqual([false, false, false]);
      // The rest of the workspace stays, with its manual ways.
      expect(html).toContain('id="workflow-hypotheses"');
    }
  });

  it("is hidden while the AI status is still loading or cannot be read", () => {
    expect(analysisParts(render(null))).toEqual([false, false, false]);
  });

  it("is shown as before while AI answers", () => {
    expect(analysisParts(render(true))).toEqual([true, true, true]);
  });
});
