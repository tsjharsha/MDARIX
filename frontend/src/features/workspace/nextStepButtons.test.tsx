import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ComplaintNextStep } from "./sections/ComplaintNextStep";

// 0.10.70, item 5: a drawer ends with one main button.

const step = (tab: string) => ({
  event: { ref: "SAMPLE-RV-11" },
  state: "NOT_READY",
  blocked: 1,
  summary: {
    next_action: {
      label: tab === "Reportability" ? "Assess India (CDSCO) market" : "Sign the disposition",
      detail: "",
      opens: { section: "Complaints", tab, target: { section: "Complaints", tab, record: null, panel: null } },
    },
  },
});
let shown: unknown = null;
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: () => ({ state: "ready", data: shown, reload: () => undefined }),
}));

const render = (props: Parameters<typeof ComplaintNextStep>[0]) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider
      value={{ navigation: "new", open: vi.fn(), notify: vi.fn(), work: {} } as unknown as WorkspaceApi}
    >
      <ComplaintNextStep {...props} />
    </WorkspaceContext.Provider>,
  );

describe("the next step at the end of a drawer", () => {
  it("is the main button once the drawer's own step is signed", () => {
    shown = step("Dispositions");
    expect(render({ complaintId: "c1", refreshKey: "1", here: "Reportability" })).toMatch(
      /class="ac-primary"[^>]*>Sign the disposition/,
    );
  });
  it("is secondary while the drawer's own step is still to sign, so the drawer keeps one main button", () => {
    shown = step("Dispositions");
    const html = render({ complaintId: "c1", refreshKey: "1", here: "Reportability", pending: true });
    expect(html).toMatch(/class="ac-secondary"[^>]*>Sign the disposition/);
    expect(html).not.toContain("ac-primary");
  });
  it("is said, not a second button, when it is the drawer's own step", () => {
    shown = step("Reportability");
    const html = render({ complaintId: "c1", refreshKey: "1", here: "Reportability" });
    expect(html).toContain("Assess India (CDSCO) market: here, above.");
    expect(html).not.toContain('<button type="button" class="ac-primary"');
  });
});
