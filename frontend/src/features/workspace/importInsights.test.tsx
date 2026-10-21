import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { newComplaints, ownInsights } from "./sections/GettingStarted";
import { InsightsPanel, READING_IMPORTED } from "./sections/TrialInsights";
import type { Insights } from "./trialInsights";

// 0.10.41 (item 9): after complaints are imported on Getting started, Automatic insights no longer shows the sample's
// figures ("From sample data · 37 complaints") while it reads the new ones: on a busy server that read takes a while
// (the import's signals and embeddings are worked out at the same time) and may time out. It says it is reading the
// imported complaints, reads again until the insights are theirs, then shows them.

const sample = {
  scope: "sample data",
  source_system: "MDARIX_SAMPLE",
  total_complaints: 37,
  findings: [],
} as unknown as Insights;
const workspace = { session: {}, open: vi.fn(), notify: vi.fn(), work: {} } as unknown as WorkspaceApi;
const render = (reading: boolean) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider value={workspace}>
      <InsightsPanel insights={sample} source={{ state: "ready" }} reading={reading} />
    </WorkspaceContext.Provider>,
  );

describe("Automatic insights after an import", () => {
  it("counts only the complaints an import added", () => {
    expect(
      newComplaints("complaints", { created: 4996, updated: 0, also_created: { products: 1, versions: 1, lots: 1 } }),
    ).toBe(4993);
    expect(newComplaints("complaints", { created: 0, updated: 4993 })).toBe(0);
    expect(newComplaints("products", { created: 4, updated: 0 })).toBe(0);
  });

  it("tells the imported data's insights from the sample's", () => {
    expect(ownInsights({ source_system: "TRIAL_UPLOAD" })).toBe(true);
    expect(ownInsights({ source_system: "MDARIX_SAMPLE" })).toBe(false);
    expect(ownInsights(null)).toBe(false);
  });

  it("says it is reading the imported complaints instead of showing the sample's figures", () => {
    const reading = render(true);
    expect(reading).toContain(READING_IMPORTED);
    expect(reading).toContain("From your data");
    expect(reading).not.toContain("From sample data");
    expect(reading).not.toContain("37 complaints");
    const shown = render(false);
    expect(shown).toContain("From sample data · 37 complaints");
    expect(shown).not.toContain(READING_IMPORTED);
  });
});
